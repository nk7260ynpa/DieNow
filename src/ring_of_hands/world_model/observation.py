"""Observation 建構器.

為指定的 pov_id 從 `WorldState` 擷取「該 pov 合法可見的資訊」, 嚴格遵守
INV-5: 不得洩露該 pov 自己的 `number_tag`, 關卡規則陳述, 通關條件陳述.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ring_of_hands.world_model.types import (
    BodySnapshot,
    InvariantViolation,
    Observation,
    PovId,
)

if TYPE_CHECKING:
    from ring_of_hands.world_model.types import WorldState


def build_observation(
    state: "WorldState",
    pov_id: PovId,
    *,
    prior_life_summary: str | None = None,
) -> Observation:
    """為指定 pov 建構 `Observation`.

    Args:
        state: 當前 world state.
        pov_id: 觀察者 pov 編號 (1..6).
        prior_life_summary: 該 pov 的前世記憶摘要 (已預先壓縮; 為 `None`
            表示無前世記憶, 通常為 pov_1).

    Returns:
        僅含該 pov 合法可見欄位的 `Observation`.

    Raises:
        InvariantViolation: 若建構後發現含有自己號碼牌 (防止開發期錯誤;
            對應 INV-5).
    """
    self_body = next(b for b in state.bodies if b.body_id == pov_id)
    # 其他存活或死亡的 bodies (包含 corpses, 因為屍體仍佔空間且號碼牌可見).
    others = tuple(
        BodySnapshot(
            body_id=b.body_id,
            position=b.position,
            number_tag=b.number_tag,
            status=b.status,
        )
        for b in state.bodies
        if b.body_id != pov_id
    )
    observation = Observation(
        tick=state.tick,
        pov_id=pov_id,
        self_position=self_body.position,
        self_hp=self_body.hp,
        self_prior_life_summary=prior_life_summary,
        shield_open=state.shield_open,
        other_bodies=others,
        recent_public_speeches=state.recent_public_speeches,
    )

    # INV-5: 防禦式檢查. Observation 結構本身不含 self_number_tag 欄位,
    # 但 prior_life_summary 中若混入「我是 N 號」之類洩題陳述, 我們只能在
    # 呼叫端確保; 這裡做最直接的欄位存在性檢查.
    payload = observation.model_dump()
    if "self_number_tag" in payload:
        raise InvariantViolation("INV-5", "observation 不得含 self_number_tag")
    return observation


__all__ = ["build_observation"]
