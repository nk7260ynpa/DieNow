"""Script 生成失敗 → 寫 issues.md, CLI 非零退出.

本 change (`migrate-to-claude-cli-subprocess`) 後, 生成失敗改為 LLM 回傳
非 JSON 文字而觸發 retry 耗盡 (不再是 Anthropic tool_use.input 驗證錯誤).
"""

from __future__ import annotations

from pathlib import Path

from ring_of_hands.llm.base import LLMResponse
from ring_of_hands.llm.fake_client import FakeLLMClient
from ring_of_hands.scenario_runner.config_loader import load_config
from ring_of_hands.scenario_runner.runner import ScenarioRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"


class TestScriptGenerationFailure:
    def test_invalid_scripts_fail_and_write_issues(
        self, tmp_path: Path
    ) -> None:
        # FakeLLMClient 對所有 script_generation 請求都回非 JSON 文字.
        client = FakeLLMClient()
        for _ in range(10):
            client.add_script_response(
                1,
                LLMResponse(text="I'm unable to produce a script."),
            )
        # issues.md 重導向 tmp_path 以免污染 repo.
        issues_md = tmp_path / "issues.md"

        config = load_config(
            CONFIGS_DIR / "default.yaml",
            personas_path=CONFIGS_DIR / "personas.yaml",
            dry_run=True,
        )
        # Override issues_md_path.
        config_dict = config.model_dump()
        config_dict["issues_md_path"] = issues_md
        from ring_of_hands.scenario_runner.types import ScenarioConfig

        new_config = ScenarioConfig(**config_dict)

        runner = ScenarioRunner(
            new_config,
            log_dir=tmp_path / "logs",
            llm_client_override=client,
        )
        summary = runner.run()
        assert summary.outcome.result == "FAIL"
        assert summary.outcome.cause == "script_generation_failed"
        assert issues_md.exists()
        content = issues_md.read_text(encoding="utf-8")
        assert "[Specialist]" in content
        assert "HIGH" in content
