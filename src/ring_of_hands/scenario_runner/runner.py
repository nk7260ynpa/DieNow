"""ScenarioRunner: 整合 script_generator / world_engine / pov_manager /
project_agent 為完整關卡主流程.

本 change (`migrate-to-claude-cli-subprocess`) 將生產後端由 Anthropic SDK
改為 Claude Code CLI subprocess (`ClaudeCLIClient`). `llm_client` 為
`"claude_cli"` 時建立 `ClaudeCLIClient`; 為 `"fake"` 時建立 `FakeLLMClient`.
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ring_of_hands.llm.base import (
    ConfigValidationError as _ConfigError,
    LLMClient,
    LLMResponse,
)
from ring_of_hands.llm.fake_client import FakeClientFixture, FakeLLMClient
from ring_of_hands.pov_manager.manager import PovManager
from ring_of_hands.project_agent.agent import (
    LLMUnavailableError,
    ProjectAgent,
)
from ring_of_hands.rules_engine.dispatcher import install_default_dispatcher
from ring_of_hands.rules_engine.outcome import post_tick_checks
from ring_of_hands.scenario_runner.summary import ScenarioSummary, build_summary
from ring_of_hands.scenario_runner.types import ScenarioConfig
from ring_of_hands.script_generator.generator import (
    ScriptGenerationError,
    ScriptGenerator,
    ScriptValidationError,
)
from ring_of_hands.script_generator.types import ScriptConfig
from ring_of_hands.world_model.engine import WorldEngine, build_initial_state
from ring_of_hands.world_model.event_log import EventLog
from ring_of_hands.world_model.types import (
    Outcome,
    OutcomeEvent,
    ScriptGenerationFailedEvent,
    SpeakAction,
)


logger = logging.getLogger(__name__)


@dataclass
class _MetricsAggregator:
    """LLM usage 累計."""

    llm_call_count: int = 0
    llm_total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def record(self, response: LLMResponse) -> None:
        self.llm_call_count += 1
        input_tokens = int(response.usage.get("input_tokens", 0))
        output_tokens = int(response.usage.get("output_tokens", 0))
        self.llm_total_tokens += input_tokens + output_tokens
        self.cache_read_tokens += response.cache.cache_read_input_tokens
        self.cache_creation_tokens += response.cache.cache_creation_input_tokens

    def as_dict(self) -> dict[str, int]:
        return {
            "llm_call_count": self.llm_call_count,
            "llm_total_tokens": self.llm_total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
        }


class _MetricsLLMClient:
    """LLMClient 裝飾器, 累計 usage 後轉發."""

    def __init__(self, inner: LLMClient, aggregator: _MetricsAggregator) -> None:
        self._inner = inner
        self._agg = aggregator

    def call(self, request):
        response = self._inner.call(request)
        self._agg.record(response)
        return response


class ScenarioRunner:
    """整個關卡的執行器."""

    def __init__(
        self,
        config: ScenarioConfig,
        *,
        log_dir: Path | str = "logs",
        llm_client_override: LLMClient | None = None,
        fake_fixture_override: FakeClientFixture | None = None,
    ) -> None:
        self._config = config
        self._log_dir = Path(log_dir)
        self._llm_client_override = llm_client_override
        self._fake_fixture_override = fake_fixture_override

    def run(self) -> ScenarioSummary:
        """執行完整關卡並回傳 summary."""
        start_ts = time.time()
        timestamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        events_path = self._log_dir / f"events_{timestamp}.jsonl"
        run_log_path = self._log_dir / f"run_{timestamp}.log"
        summary_path = self._log_dir / f"summary_{timestamp}.json"

        event_log = EventLog(path=events_path)
        metrics = _MetricsAggregator()

        logger.info(
            "scenario_runner: 開始關卡 (events=%s, run_log=%s, llm_client=%s, model=%s)",
            events_path,
            run_log_path,
            self._config.llm_client,
            self._config.project_agent_model,
        )

        # --- 建立 LLMClient & ProjectAgent ---
        try:
            base_client = self._build_llm_client()
        except (_ConfigError, FileNotFoundError) as exc:
            logger.error("LLMClient 建立失敗: %s", exc)
            outcome = Outcome(result="FAIL", cause="config_invalid", tick=0)
            event_log.append(
                OutcomeEvent(
                    tick=0,
                    payload={"result": "FAIL", "cause": "config_invalid", "detail": str(exc)},
                )
            )
            event_log.close()
            return build_summary(
                outcome=outcome,
                total_ticks=0,
                alive_bodies_at_end=0,
                lit_buttons_at_end=0,
                metrics=metrics.as_dict(),
                event_log_path=str(events_path),
                run_log_path=str(run_log_path),
                execution_duration_seconds=time.time() - start_ts,
            )

        llm_client = _MetricsLLMClient(base_client, metrics)

        # --- 產生 5 份 Script ---
        try:
            scripts = self._generate_scripts(llm_client)
        except (ScriptGenerationError, ScriptValidationError) as exc:
            logger.error("Script 生成失敗: %s", exc)
            event_log.append(
                ScriptGenerationFailedEvent(
                    tick=0, payload={"reason": str(exc)}
                )
            )
            outcome = Outcome(result="FAIL", cause="script_generation_failed", tick=0)
            event_log.append(
                OutcomeEvent(
                    tick=0,
                    payload={"result": "FAIL", "cause": "script_generation_failed"},
                )
            )
            event_log.close()
            return build_summary(
                outcome=outcome,
                total_ticks=0,
                alive_bodies_at_end=0,
                lit_buttons_at_end=0,
                metrics=metrics.as_dict(),
                event_log_path=str(events_path),
                run_log_path=str(run_log_path),
                execution_duration_seconds=time.time() - start_ts,
            )

        # --- 建立 WorldEngine / Agent / Manager ---
        state = build_initial_state(
            room_size=self._config.world.room_size,
            body_start_positions=[
                tuple(p) for p in self._config.world.body_start_positions
            ],
            button_positions=[
                tuple(p) for p in self._config.world.button_positions
            ],
            ring_position=tuple(self._config.world.ring_position),
        )
        engine = WorldEngine(state=state, event_log=event_log)

        project_agent = ProjectAgent(
            llm_client=llm_client,
            model=self._config.project_agent_model,
            pov6_persona=self._config.pov6_persona,
            pov6_prior_life=scripts[-1],
            max_tokens=2048,
            temperature=0.7,
            llm_timeout_seconds=self._config.llm_timeout_seconds,
            enable_realtime_chat=self._config.enable_realtime_chat,
        )

        def _agent_decide(pov_id: int, observation) -> Any:
            return project_agent.decide(observation)

        def _realtime_reply(pov_id: int, kwargs: dict[str, Any]) -> str:
            return project_agent.realtime_reply(
                pov_id,
                persona=manager.get_context(pov_id).persona,
                prior_life=manager.get_context(pov_id).prior_life,
                incoming_msg=kwargs.get("incoming_msg", ""),
                upcoming_script_hint=kwargs.get("upcoming_script_hint", "無"),
            )

        manager = PovManager(
            engine=engine,
            scripts=scripts,
            pov6_persona=self._config.pov6_persona,
            agent_decide_fn=_agent_decide,
            realtime_reply_fn=_realtime_reply,
            enable_realtime_chat=self._config.enable_realtime_chat,
        )

        # 注入 prior_life summaries 供 observe 使用.
        for pov_id, summary in manager.prior_life_summaries().items():
            engine._prior_life_summaries[pov_id] = summary  # type: ignore[attr-defined]

        def _realtime_chat_hook(speaker_id, action: SpeakAction):
            events = []
            for target in action.targets:
                if 1 <= target <= 5:
                    events.extend(manager.request_realtime_reply(target, action))
            return events

        install_default_dispatcher(
            engine,
            max_speak_length=self._config.max_speak_length,
            realtime_chat_hook=_realtime_chat_hook,
            context_provider=manager.consume_dispatch_context,
        )

        # --- 主迴圈 ---
        final_outcome: Outcome | None = None
        try:
            for tick in range(1, self._config.max_ticks + 1):
                engine.advance_tick()
                if engine.state.tick != tick:
                    break
                manager.sync_alive_flags()

                manager.tick_scripted_povs(tick)
                if engine.outcome is not None:
                    break

                if manager.get_context(6).is_alive:
                    try:
                        manager.tick_free_agent(tick)
                    except LLMUnavailableError as exc:
                        logger.error("LLM 連續失敗, 中止關卡: %s", exc)
                        final_outcome = Outcome(
                            result="FAIL", cause="llm_unavailable", tick=tick
                        )
                        engine.set_outcome(final_outcome)
                        event_log.append(
                            OutcomeEvent(
                                tick=tick,
                                payload={
                                    "result": "FAIL",
                                    "cause": "llm_unavailable",
                                    "detail": str(exc),
                                },
                            )
                        )
                        break

                if engine.outcome is not None:
                    break

                outcome = post_tick_checks(
                    engine, max_ticks=self._config.max_ticks
                )
                if outcome is not None:
                    break
        finally:
            if engine.outcome is not None:
                final_outcome = engine.outcome
            elif final_outcome is None:
                final_outcome = Outcome(
                    result="FAIL",
                    cause="timeout",
                    tick=engine.state.tick,
                )
                engine.set_outcome(final_outcome)
                event_log.append(
                    OutcomeEvent(
                        tick=engine.state.tick,
                        payload={"result": "FAIL", "cause": "timeout"},
                    )
                )
            event_log.close()

        alive_count = sum(
            1 for b in engine.state.bodies if b.status == "alive"
        )
        lit_count = sum(1 for b in engine.state.buttons if b.lit)
        summary = build_summary(
            outcome=final_outcome,
            total_ticks=engine.state.tick,
            alive_bodies_at_end=alive_count,
            lit_buttons_at_end=lit_count,
            metrics=metrics.as_dict(),
            event_log_path=str(events_path),
            run_log_path=str(run_log_path),
            execution_duration_seconds=time.time() - start_ts,
        )

        logger.info(
            "scenario_runner: 關卡結束 outcome=%s cause=%s ticks=%d",
            summary.outcome.result,
            summary.outcome.cause,
            summary.total_ticks,
        )
        from ring_of_hands.scenario_runner.summary import write_summary_file

        write_summary_file(summary, summary_path)
        return summary

    # --- 輔助方法 ---------------------------------------------------------

    def _build_llm_client(self) -> LLMClient:
        if self._llm_client_override is not None:
            return self._llm_client_override
        if self._config.llm_client == "fake" or self._config.dry_run:
            fixture = self._fake_fixture_override
            if fixture is None:
                fixture = FakeClientFixture.from_yaml(
                    self._config.dry_run_fixture_path
                )
            return FakeLLMClient(fixture)
        # 生產後端: Claude Code CLI subprocess.
        from ring_of_hands.llm.claude_cli_client import ClaudeCLIClient

        return ClaudeCLIClient(
            cli_path=self._config.cli_path,
            claude_home=self._config.claude_home,
            timeout_seconds=self._config.llm_timeout_seconds,
        )

    def _generate_scripts(self, llm_client: LLMClient):
        script_cfg = ScriptConfig(
            model=self._config.project_agent_model,
            max_retries=self._config.max_retries,
            llm_timeout_seconds=self._config.llm_timeout_seconds,
        )
        gen = ScriptGenerator(
            llm_client=llm_client,
            personas=list(self._config.pov1_to_5_personas),
            config=script_cfg,
            world_environment={
                "room_size": list(self._config.world.room_size),
                "body_start_positions": [
                    list(p) for p in self._config.world.body_start_positions
                ],
                "button_positions": [
                    list(p) for p in self._config.world.button_positions
                ],
                "ring_position": list(self._config.world.ring_position),
                "max_ticks": self._config.max_ticks,
            },
            issues_md_path=self._config.issues_md_path,
        )
        return gen.generate_all()


__all__ = ["ScenarioRunner"]
