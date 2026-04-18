"""ClaudeCLIClient 測試.

以 `unittest.mock.patch` 隔離 `subprocess.run`, 避免實際呼叫 `claude` CLI.
對應 design D-1, D-5, D-7, D-8.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ring_of_hands.llm.base import (
    ConfigValidationError,
    LLMCallFailedError,
    LLMMessage,
    LLMRequest,
    LLMSystemBlock,
)
from ring_of_hands.llm.claude_cli_client import (
    ClaudeCLIClient,
    _build_prompt,
    _parse_ndjson,
)


def _make_request(
    *,
    model: str = "claude-sonnet-4-7",
    system_blocks: tuple[LLMSystemBlock, ...] | None = None,
    user_msg: str = "tick=1",
    timeout: float = 30.0,
) -> LLMRequest:
    sb = system_blocks or (
        LLMSystemBlock(text="你是被困的玩家.", cache=True, label="persona"),
        LLMSystemBlock(text="關卡規則...", cache=True, label="rules"),
        LLMSystemBlock(text="前世記憶 json...", cache=True, label="prior_life"),
    )
    return LLMRequest(
        model=model,
        system_blocks=sb,
        messages=(LLMMessage(role="user", content=user_msg),),
        timeout_seconds=timeout,
    )


def _fake_completed(
    *, stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _cli_result_event(text: str = "ok") -> str:
    """產生單一 NDJSON `type=result` 行."""
    return '{"type":"result","subtype":"success","result":"%s"}\n' % text


# ---------------------------------------------------------------------------
# __init__ / 啟動檢查
# ---------------------------------------------------------------------------


class TestStartupChecks:
    def test_cli_not_in_path_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "ring_of_hands.llm.claude_cli_client.shutil.which",
            lambda _: None,
        )
        with pytest.raises(ConfigValidationError) as excinfo:
            ClaudeCLIClient(cli_path="claude")
        assert "claude CLI 不可執行" in str(excinfo.value)

    def test_cli_version_nonzero_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "ring_of_hands.llm.claude_cli_client.shutil.which",
            lambda p: p,
        )
        monkeypatch.setattr(
            "ring_of_hands.llm.claude_cli_client.subprocess.run",
            lambda *a, **kw: _fake_completed(returncode=1, stderr="err"),
        )
        with pytest.raises(ConfigValidationError) as excinfo:
            ClaudeCLIClient(cli_path="claude")
        assert "退出碼 1" in str(excinfo.value)

    def test_env_reads_claude_cli_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _which(p: str) -> str:
            captured["which_arg"] = p
            return p

        monkeypatch.setenv("CLAUDE_CLI_PATH", "/opt/claude")
        monkeypatch.setattr(
            "ring_of_hands.llm.claude_cli_client.shutil.which", _which
        )
        monkeypatch.setattr(
            "ring_of_hands.llm.claude_cli_client.subprocess.run",
            lambda *a, **kw: _fake_completed(stdout="1.0.0"),
        )
        client = ClaudeCLIClient()
        assert captured["which_arg"] == "/opt/claude"
        assert client  # 防止 unused-variable warning

    def test_skip_startup_checks_for_testing(self) -> None:
        """skip_startup_checks=True 允許在測試內建構而不驗 CLI 存在."""
        client = ClaudeCLIClient(
            cli_path="any",
            skip_startup_checks=True,
        )
        assert client is not None

    def test_claude_home_kwarg_is_ignored_for_compat(self) -> None:
        """`claude_home` kwarg 仍接受但已不再驗證 (2026-04-18 後)."""
        client = ClaudeCLIClient(
            cli_path="any",
            claude_home="/nonexistent/path",  # 故意指一個不存在的路徑.
            skip_startup_checks=True,
        )
        assert client is not None


# ---------------------------------------------------------------------------
# call(): subprocess 命令組裝
# ---------------------------------------------------------------------------


class TestCallCommandConstruction:
    @pytest.fixture
    def client(self) -> ClaudeCLIClient:
        return ClaudeCLIClient(
            cli_path="claude",
            skip_startup_checks=True,
        )

    def test_args_include_prompt_and_model_and_output_format(
        self, client: ClaudeCLIClient
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return _fake_completed(stdout=_cli_result_event("done"))

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            resp = client.call(_make_request(model="claude-sonnet-4-7"))

        args = captured["args"]
        assert args[0] == "claude"
        assert args[1] == "-p"
        # 第 2 個 arg 為 prompt 文本 (string, 非 "-").
        assert "Persona" in args[2]
        assert "Rules" in args[2]
        assert "Prior Life" in args[2]
        assert "Observation / Task" in args[2]
        # --output-format stream-json
        idx_fmt = args.index("--output-format")
        assert args[idx_fmt + 1] == "stream-json"
        # --verbose MUST 存在 (CLI 硬性規定 stream-json 必須搭 --verbose).
        assert "--verbose" in args
        # --model claude-sonnet-4-7
        idx_model = args.index("--model")
        assert args[idx_model + 1] == "claude-sonnet-4-7"

        assert resp.text == "done"

    def test_verbose_flag_required_with_stream_json(
        self, client: ClaudeCLIClient
    ) -> None:
        """stream-json 輸出格式 MUST 搭配 --verbose; 即使沒有 --model 也要有."""
        captured: dict[str, Any] = {}

        def _fake_run(args, **kwargs):
            captured["args"] = args
            return _fake_completed(stdout=_cli_result_event("ok"))

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            client.call(_make_request(model=""))

        assert "--verbose" in captured["args"]
        idx_fmt = captured["args"].index("--output-format")
        assert captured["args"][idx_fmt + 1] == "stream-json"

    def test_omits_model_flag_when_empty(
        self, client: ClaudeCLIClient
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_run(args, **kwargs):
            captured["args"] = args
            return _fake_completed(stdout=_cli_result_event())

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            client.call(_make_request(model=""))

        assert "--model" not in captured["args"]

    def test_no_cache_control_flags_in_args(
        self, client: ClaudeCLIClient
    ) -> None:
        """CLI 不支援 caching 旗標; args MUST NOT 含 --cache / --no-cache."""
        captured: dict[str, Any] = {}

        def _fake_run(args, **kwargs):
            captured["args"] = args
            return _fake_completed(stdout=_cli_result_event())

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            resp = client.call(_make_request())

        assert "--cache" not in captured["args"]
        assert "--no-cache" not in captured["args"]
        # cache metadata 恆為 0.
        assert resp.cache.cache_read_input_tokens == 0
        assert resp.cache.cache_creation_input_tokens == 0

    def test_prompt_over_threshold_goes_via_stdin(
        self, client: ClaudeCLIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """prompt 超過 100 KB 時 args[2] == "-" 且 stdin 為 prompt."""
        # 縮小閾值便於測試.
        monkeypatch.setattr(
            "ring_of_hands.llm.claude_cli_client.PROMPT_STDIN_THRESHOLD", 50
        )
        captured: dict[str, Any] = {}

        def _fake_run(args, **kwargs):
            captured["args"] = args
            captured["input"] = kwargs.get("input")
            return _fake_completed(stdout=_cli_result_event("ok"))

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            # system block 加大到 > 50 字元.
            big = "x" * 200
            req = _make_request(
                system_blocks=(
                    LLMSystemBlock(text=big, cache=False, label="persona"),
                )
            )
            client.call(req)

        assert captured["args"][2] == "-"
        assert captured["input"] is not None
        assert len(captured["input"]) > 50


# ---------------------------------------------------------------------------
# call(): 錯誤映射
# ---------------------------------------------------------------------------


class TestCallErrorMapping:
    @pytest.fixture
    def client(self) -> ClaudeCLIClient:
        return ClaudeCLIClient(
            cli_path="claude",
            skip_startup_checks=True,
        )

    def test_timeout_raises_cli_timeout(
        self, client: ClaudeCLIClient
    ) -> None:
        def _fake_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd=["claude"], timeout=1)

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            with pytest.raises(LLMCallFailedError) as excinfo:
                client.call(_make_request())
        assert excinfo.value.reason == "cli_timeout"

    def test_file_not_found_raises_cli_not_found(
        self, client: ClaudeCLIClient
    ) -> None:
        def _fake_run(*a, **kw):
            raise FileNotFoundError("no such file")

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            with pytest.raises(LLMCallFailedError) as excinfo:
                client.call(_make_request())
        assert excinfo.value.reason == "cli_not_found"

    def test_nonzero_exit_raises(self, client: ClaudeCLIClient) -> None:
        def _fake_run(*a, **kw):
            return _fake_completed(
                returncode=2, stderr="auth required", stdout=""
            )

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            with pytest.raises(LLMCallFailedError) as excinfo:
                client.call(_make_request())
        assert excinfo.value.reason == "cli_nonzero_exit:2"
        # cause 訊息應含 stderr 摘要.
        assert "auth required" in str(excinfo.value.cause)

    def test_empty_stdout_raises_ndjson_parse_error(
        self, client: ClaudeCLIClient
    ) -> None:
        def _fake_run(*a, **kw):
            return _fake_completed(stdout="")

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            with pytest.raises(LLMCallFailedError) as excinfo:
                client.call(_make_request())
        assert excinfo.value.reason == "ndjson_parse_error"

    def test_usage_from_result_event(self, client: ClaudeCLIClient) -> None:
        stdout = (
            '{"type":"system","subtype":"init","session":"abc"}\n'
            '{"type":"result","subtype":"success","result":"hi",'
            '"usage":{"input_tokens":123,"output_tokens":5}}\n'
        )

        def _fake_run(*a, **kw):
            return _fake_completed(stdout=stdout)

        with patch(
            "ring_of_hands.llm.claude_cli_client.subprocess.run", _fake_run
        ):
            resp = client.call(_make_request())
        assert resp.text == "hi"
        assert resp.usage == {"input_tokens": 123, "output_tokens": 5}
        # cache 恆 0.
        assert resp.cache.cache_read_input_tokens == 0
        assert resp.cache.cache_creation_input_tokens == 0


# ---------------------------------------------------------------------------
# _build_prompt()
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_labels_mapped_to_markdown_headings(self) -> None:
        req = _make_request(
            system_blocks=(
                LLMSystemBlock(text="P", cache=True, label="persona"),
                LLMSystemBlock(text="R", cache=True, label="rules"),
                LLMSystemBlock(text="L", cache=True, label="prior_life"),
            ),
            user_msg="observe",
        )
        prompt = _build_prompt(req)
        assert "## Persona\nP" in prompt
        assert "## Rules\nR" in prompt
        assert "## Prior Life\nL" in prompt
        assert "## Observation / Task\nobserve" in prompt

    def test_missing_label_uses_block_index(self) -> None:
        req = _make_request(
            system_blocks=(
                LLMSystemBlock(text="A"),
                LLMSystemBlock(text="B"),
            ),
            user_msg="go",
        )
        prompt = _build_prompt(req)
        assert "## Block 1\nA" in prompt
        assert "## Block 2\nB" in prompt

    def test_picks_last_user_message(self) -> None:
        req = LLMRequest(
            model="m",
            system_blocks=(LLMSystemBlock(text="x"),),
            messages=(
                LLMMessage(role="user", content="first"),
                LLMMessage(role="assistant", content="mid"),
                LLMMessage(role="user", content="final"),
            ),
        )
        prompt = _build_prompt(req)
        assert "final" in prompt
        assert "first" not in prompt.split("## Observation / Task\n")[1]
