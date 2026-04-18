"""Script 生成的 prompt 組裝器.

將 persona / 世界環境 / prior_life 組裝成 `LLMRequest`, 並對可重用部分
 (persona, 世界環境, prior_life) 附加 cache_control.
"""

from __future__ import annotations

import json
from typing import Any

from ring_of_hands.llm.base import (
    LLMMessage,
    LLMRequest,
    LLMSystemBlock,
    LLMToolDefinition,
)
from ring_of_hands.script_generator.types import Persona, Script, ScriptConfig


# Anthropic tool 定義: 要求 LLM 以此 tool 輸出結構化 Script.
PRODUCE_SCRIPT_TOOL: LLMToolDefinition = LLMToolDefinition(
    name="produce_script",
    description=(
        "輸出單一 pov 的閉環劇本. 必須符合 Script schema: pov_id / persona / "
        "events / death_cause. events 需按 t 非遞減排序, 最後一個 event 必為 "
        "actor=pov_id, action_type=die."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pov_id": {"type": "integer", "minimum": 1, "maximum": 5},
            "persona": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "traits": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["name"],
            },
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "t": {"type": "integer", "minimum": 0},
                        "actor": {"type": "integer", "minimum": 1, "maximum": 6},
                        "action_type": {
                            "type": "string",
                            "enum": [
                                "move",
                                "speak",
                                "press",
                                "touch_ring",
                                "observe",
                                "wait",
                                "die",
                            ],
                        },
                        "payload": {"type": "object"},
                        "targets": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["t", "actor", "action_type"],
                },
            },
            "death_cause": {
                "type": "string",
                "enum": ["press_wrong", "ring_paradox", "timeout", "other"],
            },
        },
        "required": ["pov_id", "persona", "events", "death_cause"],
    },
)


def build_world_environment_block(
    *,
    room_size: tuple[int, int],
    body_start_positions: list[tuple[int, int]],
    button_positions: list[tuple[int, int]],
    ring_position: tuple[int, int],
    max_ticks: int,
) -> str:
    """建構世界環境描述 text."""
    lines = [
        "## 世界環境",
        f"- 房間大小: {room_size[0]} x {room_size[1]} grid",
        f"- 戒指位置: {tuple(ring_position)}",
        f"- 最大 tick 數: {max_ticks}",
        "- 6 個 body 起始位置:",
    ]
    for idx, pos in enumerate(body_start_positions, start=1):
        lines.append(f"  - body_{idx}: {tuple(pos)}")
    lines.append("- 6 個按鈕位置:")
    for idx, pos in enumerate(button_positions, start=1):
        lines.append(f"  - button_{idx}: {tuple(pos)}")
    lines.extend(
        [
            "## 規則 (所有玩家均戴面具並佩戴特殊眼鏡, 看不到自己的號碼牌)",
            "- body_n 按對 button_n 將使該按鈕亮燈; 按錯則立即死亡",
            "- 6 燈齊亮後防護窗開啟, 戒指變為可觸碰",
            "- 除了 body_6 之外, 任何 body 觸碰戒指都會造成時間線錯亂",
            "- 可用 action: move(delta), speak(msg, targets), press(button_id),",
            "  touch_ring, observe, wait, die",
            "## 你的任務",
            "- 以 `produce_script` tool 輸出給定 pov 的完整生命週期.",
            "- events 需按 t 非遞減排序; 最後一個 event 必為 actor=pov_id, action_type=die.",
            "- 若該 pov 有前世記憶, 你 MUST 忠實重現前世中的互動 (尤其是與自己前一",
            "  世對話或互動的事件), 不可修改任何座標、訊息文字或時機.",
        ]
    )
    return "\n".join(lines)


def build_persona_block(persona: Persona, pov_id: int) -> str:
    """建構 persona block."""
    traits = ", ".join(persona.traits) if persona.traits else "未指定"
    return (
        f"## 你的身份\n"
        f"- 你即將扮演 pov_{pov_id}.\n"
        f"- 名稱: {persona.name}\n"
        f"- 描述: {persona.description}\n"
        f"- 特質: {traits}\n"
        f"- 你看不見自己的號碼牌, 也不知道關卡規則與通關條件. 但作為劇本作者, "
        f"你正在寫這個 pov 的完整生命週期."
    )


def build_prior_life_block(prior_life: Script | None) -> str:
    """建構前世記憶 block."""
    if prior_life is None:
        return "## 前世記憶\n- 無. 你是 pov_1, 從無到有地摸索."
    serialized = json.dumps(
        prior_life.model_dump(mode="json"), ensure_ascii=False, indent=2
    )
    prior_pov = prior_life.pov_id
    return (
        "## 前世記憶 (遞迴)\n"
        f"以下為你的直接前世 (pov_{prior_pov} 的完整生命週期), 其 prior_life 鏈會遞迴包含更早的前世.\n"
        f"你的劇本 MUST 在涉及 pov_{prior_pov} 的互動事件上與此完全一致.\n"
        "```json\n"
        f"{serialized}\n"
        "```"
    )


def build_script_request(
    *,
    pov_id: int,
    persona: Persona,
    prior_life: Script | None,
    world_env_block: str,
    config: ScriptConfig,
    retry_feedback: str | None = None,
) -> LLMRequest:
    """組裝單一 pov 的 script 生成請求.

    Args:
        pov_id: 目標 pov (1..5).
        persona: 該 pov 的 persona.
        prior_life: 前世記憶 (= script_{n-1}); pov_1 為 None.
        world_env_block: 世界環境描述 (可重用, 由呼叫端提前建構).
        config: ScriptConfig.
        retry_feedback: 若上一次生成失敗, 附上 diff / parse error 摘要.
    """
    persona_block_text = build_persona_block(persona, pov_id)
    prior_life_block_text = build_prior_life_block(prior_life)

    system_blocks: list[LLMSystemBlock] = [
        LLMSystemBlock(text=world_env_block, cache=True, label="world_env"),
        LLMSystemBlock(text=persona_block_text, cache=True, label="persona"),
        LLMSystemBlock(text=prior_life_block_text, cache=True, label="prior_life"),
    ]

    user_text = (
        f"請為 pov_{pov_id} 撰寫完整劇本, 以 `produce_script` tool 回傳."
    )
    if retry_feedback:
        user_text += (
            "\n\n上一次嘗試有問題, 需要修正. 修正提示:\n"
            f"{retry_feedback}"
        )

    messages = (LLMMessage(role="user", content=user_text),)

    return LLMRequest(
        model=config.model,
        system_blocks=tuple(system_blocks),
        messages=messages,
        max_tokens=config.max_tokens,
        tools=(PRODUCE_SCRIPT_TOOL,),
        tool_choice={"type": "tool", "name": "produce_script"},
        temperature=config.temperature,
        timeout_seconds=config.llm_timeout_seconds,
        metadata={"purpose": "script_generation", "pov_id": pov_id},
    )


__all__ = [
    "PRODUCE_SCRIPT_TOOL",
    "build_persona_block",
    "build_prior_life_block",
    "build_script_request",
    "build_world_environment_block",
]
