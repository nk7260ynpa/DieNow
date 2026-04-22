"""Script 生成的 prompt 組裝器.

將 persona / 世界環境 / prior_life 組裝成 `LLMRequest`, 並要求 LLM 以嚴格
JSON 物件格式輸出 `Script`.

本 change (`migrate-to-claude-cli-subprocess`) 將 structured output 由
Anthropic tool use 降級為「prompt 誘導 JSON」; 故:
- 移除 `PRODUCE_SCRIPT_TOOL` 常數與所有 tool-use 欄位.
- user prompt 末尾附上 `Script` JSON schema 範本與「僅輸出 JSON」指示.
- system_blocks 仍為 3-block 結構 (world_env / persona / prior_life) 以
  保留日後恢復 caching 的彈性; `cache` 欄位保留但 `ClaudeCLIClient` 忽略.
"""

from __future__ import annotations

import json

from ring_of_hands.llm.base import (
    LLMMessage,
    LLMRequest,
    LLMSystemBlock,
)
from ring_of_hands.script_generator.types import Persona, Script, ScriptConfig


_SCRIPT_JSON_SCHEMA_HINT = (
    "\n\n## 輸出格式要求\n"
    "請直接輸出一個 JSON 物件 (不要附加解釋文字; 不要使用 Markdown code fence).\n"
    "該 JSON 物件 MUST 符合以下 Script schema:\n"
    "```\n"
    "{\n"
    '  "pov_id": <integer 1..5>,\n'
    '  "persona": {"name": "...", "description": "...", "traits": ["..."]},\n'
    '  "events": [\n'
    '    {"t": <int>, "actor": <1..6>, "action_type": "move|speak|press|touch_ring|observe|wait|die", '
    '"payload": {...}, "targets": [<int>, ...]},\n'
    "    ...\n"
    "  ],\n"
    '  "death_cause": "press_wrong|ring_paradox|timeout|other"\n'
    "}\n"
    "```\n"
    "- events 需按 t 非遞減排序; 最後一個 event 必為 actor=pov_id, action_type=die.\n"
    "- 若此 pov 有前世記憶, 你 MUST 忠實重現前世中涉及此 pov 的互動事件 (相同 t / 相同 payload / 相同 targets).\n"
    "- 僅輸出 JSON, 勿加任何其他文字."
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
            "- 為給定 pov 撰寫完整生命週期的劇本 (events).",
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

    # 3-block system 結構: world_env / persona / prior_life. `cache` 欄位
    # 保留為 informational metadata; `ClaudeCLIClient` 會忽略.
    system_blocks: list[LLMSystemBlock] = [
        LLMSystemBlock(text=world_env_block, cache=True, label="world_env"),
        LLMSystemBlock(text=persona_block_text, cache=True, label="persona"),
        LLMSystemBlock(text=prior_life_block_text, cache=True, label="prior_life"),
    ]

    user_text = (
        f"請為 pov_{pov_id} 撰寫完整劇本, 並以 JSON 物件回傳."
    )
    if retry_feedback:
        user_text += (
            "\n\n上一次嘗試有問題, 需要修正. 修正提示:\n"
            f"{retry_feedback}"
        )
    user_text += _SCRIPT_JSON_SCHEMA_HINT

    messages = (LLMMessage(role="user", content=user_text),)

    return LLMRequest(
        model=config.model,
        system_blocks=tuple(system_blocks),
        messages=messages,
        max_tokens=config.max_tokens,
        tools=(),
        tool_choice=None,
        temperature=config.temperature,
        timeout_seconds=config.llm_timeout_seconds,
        metadata={"purpose": "script_generation", "pov_id": pov_id},
    )


__all__ = [
    "build_persona_block",
    "build_prior_life_block",
    "build_script_request",
    "build_world_environment_block",
]
