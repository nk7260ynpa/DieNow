"""Project Agent: 以 Anthropic SDK 為 pov_6 決策.

核心介面:
- `decide(observation)` → 回傳合法 `Action`.
- `realtime_reply(pov_id, incoming_msg, ...)` → 回傳字串.

錯誤處理:
- 連續 3 次 LLM 呼叫失敗 → raise `LLMUnavailableError`.
- 單次失敗 / 解析失敗 → raise `ActionParseError` 讓 pov-manager 降級 Wait.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import structlog

from ring_of_hands.llm.base import (
    LLMCallFailedError,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMSystemBlock,
    LLMToolDefinition,
)
from ring_of_hands.project_agent.action_parser import (
    ActionParseError,
    parse_action_from_response,
)
from ring_of_hands.script_generator.types import Persona, Script
from ring_of_hands.world_model.types import Action, Observation


logger = logging.getLogger(__name__)
structlog_logger = structlog.get_logger("project_agent")


class ConfigValidationError(Exception):
    """設定不合法 (缺 API key / 模型名非支援)."""


class FeatureDisabledError(Exception):
    """試圖使用被 config 關閉的功能."""


class LLMUnavailableError(Exception):
    """LLM 連續失敗, 已超出閾值."""


SUPPORTED_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^claude-sonnet-4-.+$"),
    re.compile(r"^claude-opus-4-.+$"),
    re.compile(r"^claude-haiku-4-.+$"),
)


def validate_model_name(model: str) -> None:
    """驗證模型名稱是否符合支援命名規則."""
    for pattern in SUPPORTED_MODEL_PATTERNS:
        if pattern.match(model):
            return
    raise ConfigValidationError(
        f"unsupported_model: {model} (僅支援 claude-sonnet-4-*, "
        "claude-opus-4-*, claude-haiku-4-*)"
    )


# Anthropic tool 定義: 要求 LLM 以 submit_action 回傳結構化 action.
SUBMIT_ACTION_TOOL = LLMToolDefinition(
    name="submit_action",
    description=(
        "提交此 tick 的 action. 必須為以下其中一種: "
        "{action=move, delta=[dx,dy]}, {action=press, button_id=N}, "
        "{action=touch_ring}, {action=speak, msg=..., targets=[...]}, "
        "{action=wait}, {action=observe}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["move", "press", "touch_ring", "speak", "wait", "observe"],
            },
            "delta": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
            },
            "button_id": {"type": "integer", "minimum": 1, "maximum": 6},
            "msg": {"type": "string"},
            "targets": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 6},
            },
        },
        "required": ["action"],
    },
)


class ProjectAgent:
    """pov_6 的 Project Agent, 也支援 pov_k<6 的即時對話."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model: str,
        pov6_persona: Persona,
        pov6_prior_life: Script,
        rules_text: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        llm_timeout_seconds: float = 30.0,
        enable_realtime_chat: bool = True,
        consecutive_failure_limit: int = 3,
    ) -> None:
        validate_model_name(model)
        self._llm = llm_client
        self._model = model
        self._persona = pov6_persona
        self._prior_life = pov6_prior_life
        self._rules_text = rules_text or _default_rules_text()
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._llm_timeout = llm_timeout_seconds
        self._enable_realtime_chat = enable_realtime_chat
        self._consecutive_failure_limit = consecutive_failure_limit
        self._consecutive_failures = 0

    # --- pov_6 decide ------------------------------------------------------

    def decide(self, observation: Observation) -> Action:
        """pov_6 每 tick 的自由決策.

        Args:
            observation: 當前 tick 的 observation.

        Returns:
            合法 `Action`.

        Raises:
            ActionParseError: LLM 回應無法解析 (由 pov-manager 降級為 Wait).
            LLMUnavailableError: 連續失敗超過閾值, 中止關卡.
        """
        request = self._build_decide_request(observation)
        try:
            response = self._llm.call(request)
        except LLMCallFailedError as exc:
            self._consecutive_failures += 1
            logger.warning(
                "pov_6 decide LLM 呼叫失敗 (連續 %d 次): %s",
                self._consecutive_failures,
                exc,
            )
            if self._consecutive_failures >= self._consecutive_failure_limit:
                raise LLMUnavailableError(
                    f"LLM 連續 {self._consecutive_failures} 次失敗: {exc.reason}"
                ) from exc
            raise ActionParseError(
                f"llm_call_failed: {exc.reason}", raw_response=None
            ) from exc

        self._log_metrics(response, kind="decide")
        try:
            action = parse_action_from_response(response)
        except ActionParseError:
            # 解析失敗不計入連續 LLM 呼叫失敗 (SDK 層成功; 只是內容有誤).
            raise
        self._consecutive_failures = 0
        return action

    # --- pov_k realtime_reply ---------------------------------------------

    def realtime_reply(
        self,
        pov_id: int,
        *,
        persona: Persona,
        prior_life: Script | None,
        incoming_msg: str,
        upcoming_script_hint: str = "無",
    ) -> str:
        """為 pov_k (k<6) 生成即時對話回應字串."""
        if not self._enable_realtime_chat:
            raise FeatureDisabledError("enable_realtime_chat=false")
        request = self._build_realtime_request(
            pov_id=pov_id,
            persona=persona,
            prior_life=prior_life,
            incoming_msg=incoming_msg,
            upcoming_script_hint=upcoming_script_hint,
        )
        try:
            response = self._llm.call(request)
        except LLMCallFailedError as exc:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._consecutive_failure_limit:
                raise LLMUnavailableError(
                    f"LLM 連續 {self._consecutive_failures} 次失敗: {exc.reason}"
                ) from exc
            logger.warning(
                "pov_%d realtime_reply 失敗, 返回模糊回應: %s", pov_id, exc
            )
            return "..."
        self._log_metrics(response, kind="realtime")
        self._consecutive_failures = 0
        text = response.text.strip() if response.text else ""
        return text or "..."

    # --- Prompt 組裝 -------------------------------------------------------

    def _build_decide_request(self, observation: Observation) -> LLMRequest:
        persona_block_text = _persona_block_text(self._persona)
        rules_block_text = self._rules_text
        prior_life_json = json.dumps(
            self._prior_life.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        prior_life_block_text = (
            "## 前世記憶 (5 層遞迴)\n"
            "以下為你的直接前世 (pov_5) 的完整生命週期, 其 prior_life 鏈遞迴包含 pov_1..4.\n"
            "```json\n"
            f"{prior_life_json}\n"
            "```"
        )
        system_blocks = (
            LLMSystemBlock(text=persona_block_text, cache=True, label="persona"),
            LLMSystemBlock(text=rules_block_text, cache=True, label="rules"),
            LLMSystemBlock(text=prior_life_block_text, cache=True, label="prior_life"),
        )
        user_text = _format_observation_for_user(observation)
        messages = (LLMMessage(role="user", content=user_text),)
        return LLMRequest(
            model=self._model,
            system_blocks=system_blocks,
            messages=messages,
            max_tokens=self._max_tokens,
            tools=(SUBMIT_ACTION_TOOL,),
            tool_choice={"type": "tool", "name": "submit_action"},
            temperature=self._temperature,
            timeout_seconds=self._llm_timeout,
            metadata={"purpose": "agent_decide", "tick": observation.tick},
        )

    def _build_realtime_request(
        self,
        *,
        pov_id: int,
        persona: Persona,
        prior_life: Script | None,
        incoming_msg: str,
        upcoming_script_hint: str,
    ) -> LLMRequest:
        persona_block_text = _persona_block_text(persona, pov_id=pov_id)
        prior_text = (
            "無"
            if prior_life is None
            else json.dumps(
                prior_life.model_dump(mode="json"), ensure_ascii=False, indent=2
            )
        )
        prior_life_block_text = (
            f"## 前世記憶 (pov_{pov_id})\n"
            "```json\n"
            f"{prior_text}\n"
            "```"
        )
        system_blocks = (
            LLMSystemBlock(text=persona_block_text, cache=True, label="persona"),
            LLMSystemBlock(text=prior_life_block_text, cache=True, label="prior_life"),
        )
        user_text = (
            f"你剛聽到 pov_6 對你說: {incoming_msg!r}\n"
            f"你接下來的大略行程: {upcoming_script_hint}\n"
            f"請以 pov_{pov_id} 身份回覆. 回答必須簡短, 並且 MUST 不可透露具體的\n"
            "tick, 具體的按鈕編號或'我要去拿戒指'等資訊."
        )
        return LLMRequest(
            model=self._model,
            system_blocks=system_blocks,
            messages=(LLMMessage(role="user", content=user_text),),
            max_tokens=256,
            tools=(),
            tool_choice=None,
            temperature=self._temperature,
            timeout_seconds=self._llm_timeout,
            metadata={"purpose": "realtime_reply", "pov_id": pov_id},
        )

    def _log_metrics(self, response: LLMResponse, *, kind: str) -> None:
        """以 structlog 記錄 cache metrics 與 usage."""
        structlog_logger.info(
            "llm_call",
            kind=kind,
            cache_read_input_tokens=response.cache.cache_read_input_tokens,
            cache_creation_input_tokens=response.cache.cache_creation_input_tokens,
            usage=response.usage,
        )


def _default_rules_text() -> str:
    return (
        "## 關卡規則說明 (系統允許透露給你的部分)\n"
        "- 你與另外 5 位玩家身處同一房間, 所有人均戴面具 + 特殊眼鏡.\n"
        "- 你看不到自己的號碼牌, 但看得到其他人身上的號碼牌.\n"
        "- 房間有 6 顆按鈕, 一枚戒指; 遊戲目標與拿戒指的規則僅能從觀察與前世記憶推斷.\n"
        "- 每 tick 你只能提交 1 個 action. 可用 action: move/press/touch_ring/\n"
        "  speak/wait/observe.\n"
        "- 作為玩家, 請冷靜思考, 不要貿然按按鈕或觸碰戒指.\n"
    )


def _persona_block_text(persona: Persona, pov_id: int | None = None) -> str:
    traits = ", ".join(persona.traits) if persona.traits else "未指定"
    who = f"pov_{pov_id}" if pov_id is not None else "pov_6"
    return (
        f"## 你的身份\n"
        f"- 你是 {who} ({persona.name}).\n"
        f"- 描述: {persona.description}\n"
        f"- 特質: {traits}"
    )


def _format_observation_for_user(observation: Observation) -> str:
    """將 observation 格式化為 user content."""
    others = [
        {
            "body_id": b.body_id,
            "position": list(b.position),
            "number_tag": b.number_tag,
            "status": b.status,
        }
        for b in observation.other_bodies
    ]
    data = {
        "tick": observation.tick,
        "self_position": list(observation.self_position),
        "self_hp": observation.self_hp,
        "self_prior_life_summary": observation.self_prior_life_summary,
        "shield_open": observation.shield_open,
        "other_bodies": others,
        "recent_public_speeches": list(observation.recent_public_speeches),
        "available_actions": list(observation.available_actions),
    }
    return (
        "## 當前觀察\n"
        "```json\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
        + "\n```\n"
        "請呼叫 submit_action tool 提交此 tick 的動作."
    )


__all__ = [
    "ConfigValidationError",
    "FeatureDisabledError",
    "LLMUnavailableError",
    "ProjectAgent",
    "SUBMIT_ACTION_TOOL",
    "SUPPORTED_MODEL_PATTERNS",
    "validate_model_name",
]
