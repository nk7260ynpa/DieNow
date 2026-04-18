"""PovManager: 協調 scripted pov 與自由 agent.

介面原則:
- `contexts` / `scripts` 以 MappingProxyType 暴露, 外部不得直接改寫.
- `tick_scripted_povs(tick)` 依序處理 pov_1 ~ pov_5 的劇本動作.
- `tick_free_agent(tick)` 處理 pov_6 自由決策.
- `request_realtime_reply(pov_id, incoming_msg)` 給 rules-engine 的
  realtime_chat_hook 使用, 產生回應字串並處理衝突降級.
- `handle_death(pov_id)` 由 rules-engine 死亡事件的訂閱者呼叫.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any, Callable, Mapping

from ring_of_hands.pov_manager.types import PovContext
from ring_of_hands.rules_engine.dispatcher import DispatchContext
from ring_of_hands.script_generator.types import Persona, Script
from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import (
    Action,
    ActionDowngradedEvent,
    DeathEvent,
    Event,
    InvariantViolation,
    MoveAction,
    ObserveAction,
    PovId,
    PressAction,
    SpeakAction,
    SpeakEvent,
    TouchRingAction,
    WaitAction,
)


logger = logging.getLogger(__name__)


# 簡化型別別名: pov-manager 呼叫 project-agent 的 callable 介面.
AgentDecideFn = Callable[[int, "Any"], Action]  # (pov_id, observation) -> Action
RealtimeReplyFn = Callable[[int, dict[str, Any]], str]  # (pov_k, kwargs) -> str


class PovManager:
    """管理 6 個 pov contexts.

    Args:
        engine: WorldEngine (唯一事實來源).
        scripts: pov_1..5 的劇本清單.
        pov6_persona: pov_6 的 persona.
        pov5_persona: (可選) 若 pov_6 需要作為 pov_k<6 的 realtime persona 時
            不適用. 此欄位為預留.
        agent_decide_fn: 呼叫 project-agent 取得 pov_6 action 的 callable.
        realtime_reply_fn: 呼叫 project-agent 以取得 pov_k<6 的即時回應字串.
        enable_realtime_chat: 是否啟用即時對話.
    """

    def __init__(
        self,
        *,
        engine: WorldEngine,
        scripts: list[Script],
        pov6_persona: Persona,
        agent_decide_fn: AgentDecideFn,
        realtime_reply_fn: RealtimeReplyFn | None = None,
        enable_realtime_chat: bool = True,
    ) -> None:
        if len(scripts) != 5:
            raise ValueError("scripts 必須為 5 筆 (對應 pov_1 ~ pov_5)")

        contexts: dict[int, PovContext] = {}
        for i, script in enumerate(scripts, start=1):
            if script.pov_id != i:
                raise ValueError(
                    f"scripts[{i-1}].pov_id ({script.pov_id}) 與預期 ({i}) 不符"
                )
            contexts[i] = PovContext(
                pov_id=i,
                persona=script.persona,
                prior_life=script.prior_life,
                script=script,
                is_alive=True,
            )
        # pov_6.
        contexts[6] = PovContext(
            pov_id=6,
            persona=pov6_persona,
            prior_life=scripts[-1],  # script_5 作為 pov_6 的前世記憶 (遞迴包含 1..4).
            script=None,
            is_alive=True,
        )

        self._contexts: dict[int, PovContext] = contexts
        self._scripts: dict[int, Script] = {
            i: script for i, script in enumerate(scripts, start=1)
        }
        self._engine = engine
        self._agent_decide_fn = agent_decide_fn
        self._realtime_reply_fn = realtime_reply_fn
        self._enable_realtime_chat = enable_realtime_chat
        # 由 runner 透過 install_default_dispatcher 的 context_provider 讀取:
        # 在每次 dispatch 前, PovManager 寫入下一步的 expected_scripted_event,
        # 讓 dispatcher 知道該 action 是 scripted 還是 free agent.
        self._next_dispatch_context: dict[int, DispatchContext] = {}

    # --- Read-only 暴露 ----------------------------------------------------

    @property
    def contexts(self) -> Mapping[int, PovContext]:
        """Read-only mapping of pov_id -> PovContext."""
        return MappingProxyType(self._contexts)

    @property
    def scripts(self) -> Mapping[int, Script]:
        """Read-only mapping of pov_id -> Script (pov_1..5)."""
        return MappingProxyType(self._scripts)

    def get_context(self, pov_id: PovId) -> PovContext:
        """取得指定 pov 的 context."""
        return self._contexts[pov_id]

    def prior_life_summaries(self) -> dict[int, str | None]:
        """給 WorldEngine 的 observation 注入各 pov 的前世記憶摘要."""
        out: dict[int, str | None] = {}
        for pov_id, ctx in self._contexts.items():
            if ctx.prior_life is None:
                out[pov_id] = None
            else:
                out[pov_id] = _summarize_prior_life(ctx.prior_life)
        return out

    # --- Tick 主流程 -------------------------------------------------------

    def tick_scripted_povs(self, tick: int) -> None:
        """處理 pov_1 ~ pov_5 的 scripted action."""
        for pov_id in (1, 2, 3, 4, 5):
            if self._engine.outcome is not None:
                return
            ctx = self._contexts[pov_id]
            if not ctx.is_alive:
                continue
            scripted_event = ctx.next_scripted_event_for_tick(tick)
            if scripted_event is None:
                continue
            if scripted_event["action_type"] == "die":
                # die 事件不 dispatch; rules-engine 會在其他情境下自然造成死亡.
                continue
            action = _action_from_scripted_event(scripted_event)
            # 告訴 dispatcher: 此 pov 接下來的 dispatch 為 scripted.
            self._next_dispatch_context[pov_id] = {
                "is_free_agent": False,
                "expected_scripted_event": scripted_event,
            }
            try:
                self._engine.dispatch(pov_id, action)
            except InvariantViolation as exc:  # pragma: no cover - scripted 應不會違規
                logger.error(
                    "scripted pov_%d 在 tick %d 觸發 invariant violation: %s",
                    pov_id,
                    tick,
                    exc,
                )
                raise
            finally:
                self._next_dispatch_context.pop(pov_id, None)

    def tick_free_agent(self, tick: int) -> None:
        """處理 pov_6 的自由決策."""
        if self._engine.outcome is not None:
            return
        ctx = self._contexts[6]
        if not ctx.is_alive:
            return
        observation = self._engine.observe(6)
        try:
            action = self._agent_decide_fn(6, observation)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pov_6 agent decide 發生例外, 降級為 WaitAction: %s", exc
            )
            self._engine.write_event(
                ActionDowngradedEvent(
                    tick=tick,
                    actor=6,
                    payload={"reason": "llm_parse_error", "detail": str(exc)},
                )
            )
            action = WaitAction()
        # 告訴 dispatcher 這是 free agent.
        self._next_dispatch_context[6] = {"is_free_agent": True}
        try:
            self._engine.dispatch(6, action)
        finally:
            self._next_dispatch_context.pop(6, None)

    def consume_dispatch_context(
        self, pov_id: int, _action: Action | None = None
    ) -> DispatchContext:
        """由 runner 注入的 context_provider 呼叫, 取得下一步 dispatch 的 context.

        Args:
            pov_id: 發起 dispatch 的 pov.
            _action: 未使用, 僅為符合 context_provider(pov_id, action) 簽章.

        若未事先設定, 預設 pov_6 為 free agent, pov_1..5 為 scripted 但無
        expected event.
        """
        ctx = self._next_dispatch_context.get(pov_id)
        if ctx is not None:
            return dict(ctx)
        return {"is_free_agent": pov_id == 6}

    # --- 即時對話 ----------------------------------------------------------

    def request_realtime_reply(
        self, target_pov_id: int, incoming_action: SpeakAction
    ) -> list[Event]:
        """供 rules-engine 的 realtime_chat_hook 使用.

        Args:
            target_pov_id: 被點名的 pov (1..5).
            incoming_action: pov_6 發出的 SpeakAction.

        Returns:
            產生的額外事件 (SpeakEvent 與可能的 ActionDowngradedEvent).
        """
        if not self._enable_realtime_chat:
            return []
        if self._realtime_reply_fn is None:
            return []
        ctx = self._contexts.get(target_pov_id)
        if ctx is None or not ctx.is_alive:
            return []
        tick = self._engine.state.tick
        # 蒐集 pov_k 即將發生的劇本事件要點 (抽象層級, 不含具體 tick/button).
        upcoming_hint = self._upcoming_script_hint(ctx, tick)
        try:
            reply_text = self._realtime_reply_fn(
                target_pov_id,
                {
                    "incoming_msg": incoming_action.msg,
                    "prior_life_summary": (
                        _summarize_prior_life(ctx.prior_life)
                        if ctx.prior_life is not None
                        else None
                    ),
                    "upcoming_script_hint": upcoming_hint,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pov_%d 即時回應失敗, 降級為模糊回應: %s", target_pov_id, exc
            )
            reply_text = "..."

        # 衝突檢查: 若回應提到 ring / 即將離開等關鍵詞且劇本預定 pov_k 仍會
        # 按按鈕, 視為衝突 → 降級為「...」
        downgraded = False
        conflict_keywords = ["戒指", "拿戒指", "離開", "先走"]
        if (
            self._has_pending_press_in_script(ctx, after_tick=tick)
            and any(kw in reply_text for kw in conflict_keywords)
        ):
            downgraded = True
            reply_text = "..."

        events: list[Event] = [
            SpeakEvent(
                tick=tick,
                actor=target_pov_id,
                payload={
                    "msg": reply_text,
                    "targets": [6],
                    "reply_to": incoming_action.msg,
                },
            )
        ]
        self._engine.append_public_speech(
            {
                "tick": tick,
                "actor": target_pov_id,
                "msg": reply_text,
                "targets": [6],
            }
        )
        if downgraded:
            events.append(
                ActionDowngradedEvent(
                    tick=tick,
                    actor=target_pov_id,
                    payload={"reason": "script_conflict"},
                )
            )
        return events

    # --- 死亡處理 ----------------------------------------------------------

    def handle_death(self, pov_id: int) -> None:
        """由 scenario-runner / rules-engine 通知: pov_id 已死亡."""
        if 1 <= pov_id <= 6:
            self._contexts[pov_id].is_alive = False

    def sync_alive_flags(self) -> None:
        """依 world state 重新同步 is_alive 標記."""
        for body in self._engine.state.bodies:
            self._contexts[body.body_id].is_alive = body.status == "alive"

    # --- 輔助方法 ----------------------------------------------------------

    def _upcoming_script_hint(self, ctx: PovContext, tick: int) -> str:
        if ctx.script is None:
            return "無"
        upcoming = [e for e in ctx.script.events if e.t >= tick]
        if not upcoming:
            return "無"
        summary = ", ".join(
            f"{e.action_type}@t={e.t}" for e in upcoming[:3]
        )
        return f"將會進行: {summary}"

    def _has_pending_press_in_script(
        self, ctx: PovContext, *, after_tick: int
    ) -> bool:
        if ctx.script is None:
            return False
        for event in ctx.script.events:
            if event.t >= after_tick and event.action_type == "press":
                return True
        return False


def _action_from_scripted_event(event: dict[str, Any]) -> Action:
    """將 script event dict 轉為 Action."""
    action_type = event["action_type"]
    payload = event.get("payload", {}) or {}
    targets = event.get("targets", []) or []
    if action_type == "move":
        delta = payload.get("delta", [0, 0])
        return MoveAction(delta=(int(delta[0]), int(delta[1])))
    if action_type == "press":
        return PressAction(button_id=int(payload.get("button_id")))
    if action_type == "touch_ring":
        return TouchRingAction()
    if action_type == "speak":
        return SpeakAction(
            msg=str(payload.get("msg", "")),
            targets=tuple(int(t) for t in targets),
        )
    if action_type == "wait":
        return WaitAction()
    if action_type == "observe":
        return ObserveAction()
    raise ValueError(f"無法轉為 Action 的 scripted action_type: {action_type}")


def _summarize_prior_life(prior_life: Script) -> str:
    """壓縮式摘要 prior_life 用於 observation."""
    events = prior_life.events
    depth = 0
    cursor: Script | None = prior_life
    while cursor is not None:
        depth += 1
        cursor = cursor.prior_life
    return (
        f"直接前世: pov_{prior_life.pov_id} ({len(events)} 筆事件), "
        f"前世鏈深度: {depth}"
    )


__all__ = [
    "AgentDecideFn",
    "PovManager",
    "RealtimeReplyFn",
]
