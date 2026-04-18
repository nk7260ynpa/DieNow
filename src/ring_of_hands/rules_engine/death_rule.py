"""死亡規則.

Corpse 狀態不可復活 (IllegalStateTransition). 其他死亡情境 (按錯按鈕, ring_paradox,
由上層主動標記死亡) 皆透過此 helper 執行.
"""

from __future__ import annotations

from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import DeathEvent, IllegalStateTransition


def kill_body(engine: WorldEngine, body_id: int, cause: str) -> DeathEvent:
    """將 body 標記為 corpse.

    Args:
        engine: WorldEngine.
        body_id: 要標死的 body.
        cause: 死因 (`press_wrong`, `ring_paradox`, ...).

    Returns:
        產生的 `DeathEvent`; 呼叫端負責將此 event 寫入 log / 聚合.

    Raises:
        IllegalStateTransition: 若嘗試將 corpse → alive (由 update_body 的
            其他 helper 使用時意外觸發).
    """
    body = engine.find_body(body_id)
    if body.status == "corpse":
        raise IllegalStateTransition(f"body_{body_id} 已是 corpse, 不得再次標死.")
    engine.update_body(body_id, status="corpse", hp=0)
    return DeathEvent(
        tick=engine.state.tick,
        actor=body_id,
        payload={"cause": cause},
    )


def ensure_not_resurrection(current_status: str, next_status: str) -> None:
    """Guard: 禁止 corpse → alive 的狀態轉換."""
    if current_status == "corpse" and next_status == "alive":
        raise IllegalStateTransition("corpse → alive 為禁止轉換.")


__all__ = ["ensure_not_resurrection", "kill_body"]
