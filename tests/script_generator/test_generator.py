"""ScriptGenerator 主流程測試.

對應本 change (`migrate-to-claude-cli-subprocess`) 的 script-generator spec:
- LLMResponse.text 為合法 JSON (純文字或 Markdown code fence 包裹) → 解析成 Script.
- 以 FakeLLMClient 可完整產生 5 份劇本.
- 超過 retry 上限時寫入 issues.md.
- LLM 回傳無法解析時觸發 retry.
- script_1 無前世; script_n (n>=2) prior_life 鏈長度正確.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ring_of_hands.llm.base import LLMResponse
from ring_of_hands.llm.fake_client import FakeClientFixture, FakeLLMClient
from ring_of_hands.script_generator.generator import (
    ScriptGenerationError,
    ScriptGenerator,
    ScriptValidationError,
)
from ring_of_hands.script_generator.types import Persona, ScriptConfig


DEFAULT_PERSONAS = [
    Persona(name=f"pov_{i}", description="", traits=()) for i in range(1, 6)
]
WORLD_ENV = {
    "room_size": [10, 10],
    "body_start_positions": [[1, 1], [1, 8], [4, 1], [4, 8], [8, 1], [8, 8]],
    "button_positions": [[2, 2], [2, 7], [5, 2], [5, 7], [7, 2], [7, 7]],
    "ring_position": [5, 5],
    "max_ticks": 50,
}


def _valid_script_data(pov_id: int) -> dict:
    return {
        "pov_id": pov_id,
        "persona": {"name": f"pov_{pov_id}"},
        "events": [
            {
                "t": 1,
                "actor": pov_id,
                "action_type": "move",
                "payload": {"delta": [1, 0]},
                "targets": [],
            },
            {
                "t": 10,
                "actor": pov_id,
                "action_type": "die",
                "payload": {"cause": "timeout"},
                "targets": [],
            },
        ],
        "death_cause": "timeout",
    }


def _json_response(data: dict) -> LLMResponse:
    """以 response.text = json.dumps(data) 建立 LLMResponse."""
    return LLMResponse(text=json.dumps(data, ensure_ascii=False))


def _fenced_json_response(data: dict) -> LLMResponse:
    """以 Markdown code fence 包裹 JSON 建立 LLMResponse."""
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return LLMResponse(text=f"```json\n{body}\n```")


class TestGenerateAll:
    def test_happy_path_produces_five_scripts(self) -> None:
        """以 FakeLLMClient (fixture 提供 5 份 JSON 字串 script) 可完整產生."""
        fixture = FakeClientFixture(
            scripts=[_valid_script_data(i) for i in range(1, 6)]
        )
        client = FakeLLMClient(fixture)
        gen = ScriptGenerator(
            llm_client=client,
            personas=DEFAULT_PERSONAS,
            config=ScriptConfig(max_retries=3),
            world_environment=WORLD_ENV,
        )
        scripts = gen.generate_all()
        assert len(scripts) == 5
        # prior_life 鏈遞增.
        assert scripts[0].prior_life is None
        assert scripts[1].prior_life is not None and scripts[1].prior_life.pov_id == 1
        assert scripts[4].prior_life is not None
        chain = scripts[4]
        depth = 0
        while chain.prior_life is not None:
            depth += 1
            chain = chain.prior_life
        assert depth == 4

    def test_parses_markdown_code_fenced_json(self) -> None:
        """LLM 回傳 Markdown code fence 包裹的 JSON 仍可解析."""
        client = FakeLLMClient()
        for i in range(1, 6):
            client.add_script_response(i, _fenced_json_response(_valid_script_data(i)))
        gen = ScriptGenerator(
            llm_client=client,
            personas=DEFAULT_PERSONAS,
            config=ScriptConfig(max_retries=3),
            world_environment=WORLD_ENV,
        )
        scripts = gen.generate_all()
        assert len(scripts) == 5
        assert scripts[0].pov_id == 1

    def test_retry_on_parse_failure_then_success(self) -> None:
        """第一次回傳非 JSON 文字, 第二次才回合法 JSON."""
        client = FakeLLMClient()
        # pov_1: 第 1 次回傳非 JSON.
        client.add_script_response(
            1,
            LLMResponse(text="這不是 JSON, 只是描述文字."),
        )
        # pov_1: 第 2 次回傳合法 JSON.
        client.add_script_response(1, _json_response(_valid_script_data(1)))
        for i in range(2, 6):
            client.add_script_response(i, _json_response(_valid_script_data(i)))
        gen = ScriptGenerator(
            llm_client=client,
            personas=DEFAULT_PERSONAS,
            config=ScriptConfig(max_retries=3),
            world_environment=WORLD_ENV,
        )
        scripts = gen.generate_all()
        assert len(scripts) == 5
        # pov_1 call 了兩次 (1 失敗 + 1 成功); 可由 call_log 檢查.
        purposes = [p for p, _ in client.call_log]
        assert purposes.count("script_generation") >= 6

    def test_retry_exhausted_raises_and_writes_issues(
        self, tmp_path: Path
    ) -> None:
        """pov_1 所有嘗試皆回傳非 JSON → 寫 issues.md 並 raise."""
        client = FakeLLMClient()
        for _ in range(5):
            client.add_script_response(
                1,
                LLMResponse(text="I'm not JSON at all."),
            )
        issues_md = tmp_path / "issues.md"
        gen = ScriptGenerator(
            llm_client=client,
            personas=DEFAULT_PERSONAS,
            config=ScriptConfig(max_retries=3),
            world_environment=WORLD_ENV,
            issues_md_path=issues_md,
        )
        with pytest.raises(ScriptGenerationError):
            gen.generate_all()
        assert issues_md.exists()
        content = issues_md.read_text(encoding="utf-8")
        assert "[Specialist]" in content
        assert "HIGH" in content
        assert "pov_1" in content

    def test_closure_violation_after_retries_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """pov_2 始終回傳不一致的 event 導致閉環驗證失敗."""
        s1 = _valid_script_data(1)
        s1["events"].insert(
            1,
            {
                "t": 3,
                "actor": 2,
                "action_type": "speak",
                "payload": {"msg": "hello"},
                "targets": [1],
            },
        )
        s2_wrong = _valid_script_data(2)
        s2_wrong["events"].insert(
            1,
            {
                "t": 3,
                "actor": 2,
                "action_type": "speak",
                "payload": {"msg": "hi"},
                "targets": [1],
            },
        )
        fixture = FakeClientFixture(
            scripts=[s1, s2_wrong, s2_wrong, s2_wrong]
        )
        client = FakeLLMClient(fixture)
        issues_md = tmp_path / "issues.md"
        gen = ScriptGenerator(
            llm_client=client,
            personas=DEFAULT_PERSONAS,
            config=ScriptConfig(max_retries=3),
            world_environment=WORLD_ENV,
            issues_md_path=issues_md,
        )
        with pytest.raises(ScriptValidationError) as exc_info:
            gen.generate_all()
        assert exc_info.value.pov_id == 2
        assert issues_md.exists()

    def test_mismatched_pov_id_raises_script_generation_error(
        self, tmp_path: Path
    ) -> None:
        """LLM 回傳的 pov_id 與預期不符觸發 retry; retry 耗盡後 raise."""
        client = FakeLLMClient()
        wrong_data = _valid_script_data(99)  # 錯誤 pov_id
        for _ in range(5):
            client.add_script_response(1, _json_response(wrong_data))
        gen = ScriptGenerator(
            llm_client=client,
            personas=DEFAULT_PERSONAS,
            config=ScriptConfig(max_retries=3),
            world_environment=WORLD_ENV,
        )
        with pytest.raises(ScriptGenerationError):
            gen.generate_all()


class TestBackwardCompatToolUse:
    def test_tool_use_fallback_still_works(self) -> None:
        """舊 fixture 可能以 tool_use 承載 script; 應仍可解析."""
        import warnings

        client = FakeLLMClient()
        for i in range(1, 6):
            client.add_script_response(
                i,
                LLMResponse(
                    text="",
                    tool_use={
                        "name": "produce_script",
                        "input": _valid_script_data(i),
                    },
                ),
            )
        gen = ScriptGenerator(
            llm_client=client,
            personas=DEFAULT_PERSONAS,
            config=ScriptConfig(max_retries=3),
            world_environment=WORLD_ENV,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            scripts = gen.generate_all()
        assert len(scripts) == 5
        # 至少一次 DeprecationWarning.
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )
