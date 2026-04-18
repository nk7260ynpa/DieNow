"""POV Manager 的內部型別."""

from __future__ import annotations

from dataclasses import dataclass, field

from ring_of_hands.script_generator.types import Persona, Script


@dataclass
class PovContext:
    """單一 pov 的 context.

    Attributes:
        pov_id: 1..6.
        persona: 該 pov 的 persona.
        prior_life: 該 pov 的前世記憶 (pov_1 為 None; pov_n 為 script_{n-1}).
        script: 該 pov 的劇本 (pov_6 為 None, 因其為自由主體).
        is_alive: 是否存活; 由 PovManager 私有方法維護.
    """

    pov_id: int
    persona: Persona
    prior_life: Script | None
    script: Script | None
    is_alive: bool = True
    # 記錄已執行過的 scripted events (index) 以便推進.
    _executed_event_count: int = field(default=0, compare=False)

    def next_scripted_event_for_tick(self, tick: int) -> dict | None:
        """查詢該 pov 在當前 tick 應執行的劇本事件 (若有).

        Script 內同一 tick 可能有多筆事件 (例如 speak 後 press); 本實作逐一
        推進 `_executed_event_count`, 每次 tick 呼叫取第一個 `t == tick` 的
        尚未執行事件.
        """
        if self.script is None:
            return None
        events = self.script.events
        # 找出第一個 t>=tick 且尚未執行的事件.
        for idx in range(self._executed_event_count, len(events)):
            event = events[idx]
            if event.t == tick:
                self._executed_event_count = idx + 1
                return {
                    "t": event.t,
                    "actor": event.actor,
                    "action_type": event.action_type,
                    "payload": dict(event.payload),
                    "targets": list(event.targets),
                }
            if event.t > tick:
                return None
        return None

    def has_pending_scripted_event_for_tick(self, tick: int) -> bool:
        """不推進 counter 地 peek 是否有 scripted event."""
        if self.script is None:
            return False
        events = self.script.events
        for idx in range(self._executed_event_count, len(events)):
            event = events[idx]
            if event.t == tick:
                return True
            if event.t > tick:
                return False
        return False


__all__ = ["PovContext"]
