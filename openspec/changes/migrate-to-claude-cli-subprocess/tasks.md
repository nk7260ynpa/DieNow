## 1. LLM Client 介面層調整

- [ ] 1.1 將 `ConfigValidationError` 由 `ring_of_hands.project_agent.agent` 搬至 `ring_of_hands.llm.base`，並於 `project_agent.agent` 以 `from ring_of_hands.llm.base import ConfigValidationError as ConfigValidationError` 保持向後相容；`LLMSystemBlock.cache` 欄位註解補上「`ClaudeCLIClient` 會忽略此值」；`CacheMetadata` 欄位文件說明「非 Anthropic SDK 後端恆填 0」；對應單元測試更新以涵蓋 re-export 等價性；檔案範圍：`src/ring_of_hands/llm/base.py`、`src/ring_of_hands/project_agent/agent.py`（僅為 re-export 行）、`tests/llm/test_base.py`
- [ ] 1.2 實作 `ClaudeCLIClient`：`__init__` 進行啟動檢查（`shutil.which` / `claude --version` / `CLAUDE_HOME` 目錄存在），失敗 raise `ConfigValidationError` 並於訊息附上可操作建議；`call(LLMRequest) → LLMResponse` 組裝 `-p <prompt> --output-format stream-json [--model <id>]` 命令、prompt 超過 100 KB 改走 stdin；將 `subprocess.TimeoutExpired` / returncode != 0 / `FileNotFoundError` / NDJSON 解析錯誤 / `type=error` 事件 / 無 `type=result` 事件等依 design D-8 對應表轉為 `LLMCallFailedError`；檔案範圍：`src/ring_of_hands/llm/claude_cli_client.py`
- [ ] 1.3 撰寫 `_parse_ndjson(stdout: str) → LLMResponse` 純函數：忽略無法解析的行（warning log）、多則 `type=result` 取最末一則、無 `type=result` raise、`type=error` raise、`type=result.usage` 填入 `input_tokens` / `output_tokens`，`cache_read_input_tokens` 與 `cache_creation_input_tokens` 恆為 0；搭配 `test_claude_cli_client.py` 與 `test_claude_cli_ndjson.py` 覆蓋 design D-7 列舉之 6 條路徑（正常 / 多 assistant + 1 result / 0 result / type=error / 無法解析行忽略 / timeout / non-zero exit / __init__ 驗證錯誤）；檔案範圍：`src/ring_of_hands/llm/claude_cli_client.py`、`tests/llm/test_claude_cli_client.py`、`tests/llm/test_claude_cli_ndjson.py`
- [ ] 1.4 將 `FakeAnthropicClient` 更名為 `FakeLLMClient`：class rename、所有 import 轉向；response builder 不再產生 `tool_use` 欄位，改以 `json.dumps(script_dict)` / `json.dumps(action_dict)` 注入 `LLMResponse.text`；保留讀入舊 fixture（含 `tool_use`）時列印 `DeprecationWarning` 的相容路徑；對應測試改 class 名稱與 fixture 斷言；檔案範圍：`src/ring_of_hands/llm/fake_client.py`、`tests/llm/test_fake_client.py`
- [ ] 1.5 刪除 `ring_of_hands.llm.anthropic_client` 模組與其單元測試；移除所有 `from ring_of_hands.llm.anthropic_client import` 的外部引用（若存在）；檔案範圍：`src/ring_of_hands/llm/anthropic_client.py`（刪除）、`tests/llm/test_anthropic_client.py`（刪除）

## 2. Project Agent 改為 ClaudeCLIClient 後端

- [ ] 2.1 修改 `ProjectAgent._build_decide_request`：system_blocks 仍為 3 個（persona / rules / prior_life），但移除 `cache_control={"type":"ephemeral"}` 相關程式碼；user prompt 末尾加入 design D-4' 規定的 JSON 輸出指令（`"僅輸出 JSON 物件..."`）；移除 `SUBMIT_ACTION_TOOL` / `tool_choice` / `tools` 欄位（或設為空 tuple）；對應 assertion 更新；檔案範圍：`src/ring_of_hands/project_agent/agent.py`、`tests/project_agent/test_agent.py`
- [ ] 2.2 修改 `action_parser.parse_action_from_response`：優先從 `response.text` 做 `json.loads`（自動去除 Markdown code fence，例如 ```json ... ```）；`tool_use` 路徑保留為 fallback 並附 `DeprecationWarning`；解析失敗依舊 raise `ActionParseError(reason=...)`；新增 scenarios 涵蓋「純 JSON」「code fence 包裹 JSON」「未知 action_type」「非 JSON」「舊 tool_use fixture 相容」；檔案範圍：`src/ring_of_hands/project_agent/action_parser.py`、`tests/project_agent/test_action_parser.py`
- [ ] 2.3 修改 `ProjectAgent.realtime_reply`：移除 `cache_control`；response 取 `response.text.strip()` 作為回覆字串（來自 CLI `type=result.result`）；錯誤處理同 `decide`；檔案範圍：`src/ring_of_hands/project_agent/realtime.py`、`tests/project_agent/test_realtime.py`
- [ ] 2.4 調整 `error_handling.py`：將 `LLMCallFailedError` 的 reason 映射統一為 design D-8 字串（`cli_timeout` / `cli_nonzero_exit:<rc>` / `cli_not_found` / `ndjson_parse_error` / `cli_error:<err>` / `no_result_event`）；連續 `consecutive_failure_limit=3` raise `LLMUnavailableError` 的行為保留；新增對應單元測試；檔案範圍：`src/ring_of_hands/project_agent/error_handling.py`、`tests/project_agent/test_error_handling.py`
- [ ] 2.5 調整 `metrics.py`：`cache_read_input_tokens` / `cache_creation_input_tokens` 欄位仍輸出但允許為 0；structlog event 名稱與欄位 schema 不變；補充測試斷言「backend 為 ClaudeCLIClient 時兩值為 0 且欄位仍存在」；檔案範圍：`src/ring_of_hands/project_agent/metrics.py`、`tests/project_agent/test_metrics.py`
- [ ] 2.6 更新 `conftest.py`（若有引用 `FakeAnthropicClient` 的 fixture）與 `project_agent` 的其他相關測試：更新 import 名稱，調整 fixture 為新的 response.text JSON 形式；檔案範圍：`tests/project_agent/conftest.py`

## 3. Script Generator 改為 ClaudeCLIClient 後端

- [ ] 3.1 調整 `prompt_builder.py`：移除 `PRODUCE_SCRIPT_TOOL` 常數與所有 tool-use 欄位組裝；user prompt 末尾加入 design D-4' 規定的 `Script` JSON schema 範本與「僅輸出 JSON」指示；system_blocks 仍套 3-block 結構但不設 `cache_control`；驗證失敗 retry 時仍於 prompt 補上前一次錯誤 diff；對應單元測試更新；檔案範圍：`src/ring_of_hands/script_generator/prompt_builder.py`、`tests/script_generator/test_prompt_builder.py`
- [ ] 3.2 修改 `generator.py` 的回應解析：改從 `response.text` 讀取 JSON 字串，自動去除 Markdown code fence 後以 `json.loads` + `Script.model_validate` 驗證；解析失敗仍觸發 retry，超過 `max_retries` raise `ScriptGenerationError` 並寫 `issues.md`；Markdown code fence 的 scenario 需新增測試；檔案範圍：`src/ring_of_hands/script_generator/generator.py`、`tests/script_generator/test_generator.py`
- [ ] 3.3 更新 `tests/fixtures/dry_run.yaml` 與任何整合測試使用的 fixture：將 script 與 action 內容改以 `LLMResponse.text` 承載 JSON 字串；若保留任何 `tool_use` 欄位作為相容路徑測試，需於註解標記為 DeprecationWarning demo；檔案範圍：`tests/fixtures/dry_run.yaml`、`tests/fixtures/` 下其他相關 fixture 檔（範圍僅限本 change 實際使用者）

## 4. Scenario Runner 啟動檢查改為 Claude CLI

- [ ] 4.1 修改 `config_loader.py`：`ScenarioConfig` 欄位新增 `cli_path`（對應 `CLAUDE_CLI_PATH`，預設 `"claude"`）、`llm_timeout_seconds`（對應 `CLAUDE_CLI_TIMEOUT_SECONDS`，預設 30）、`claude_home`（對應 `CLAUDE_HOME`，預設 `"~/.claude"`）；移除 `ANTHROPIC_API_KEY` 相關驗證；加入 design D-5 的三項預啟動檢查（`shutil.which` / `claude --version` exit 0 / `claude_home.is_dir()`）；`dry_run` 模式 MUST 跳過這些 CLI 相關檢查；失敗 raise `ConfigValidationError` 並附可操作建議；對應單元測試需覆蓋：CLI 未安裝、版本檢查非 0、`~/.claude/` 不存在、dry-run 豁免；檔案範圍：`src/ring_of_hands/scenario_runner/config_loader.py`、`src/ring_of_hands/scenario_runner/types.py`、`tests/scenario_runner/test_config_loader.py`、`tests/scenario_runner/test_types.py`
- [ ] 4.2 調整 `runner.py`：LLM client 選擇由 `ScenarioConfig.llm_client` 決定，`"claude_cli"` 建立 `ClaudeCLIClient`、`"fake"` 建立 `FakeLLMClient`；移除任何直接 import `anthropic` 或 `AnthropicClient` 的程式碼；啟動訊息增加 `claude --version` 字串；檔案範圍：`src/ring_of_hands/scenario_runner/runner.py`、`tests/scenario_runner/test_runner.py`
- [ ] 4.3 更新 CLI 入口（`cli_main.py`）與 `cli.py`：啟動訊息、錯誤輸出對齊新的 `ConfigValidationError` 訊息格式；新增 scenario 測試「缺 claude CLI 時非零退出」與「`~/.claude/` 缺失時非零退出」；檔案範圍：`src/ring_of_hands/scenario_runner/cli_main.py`、`src/ring_of_hands/cli.py`、`tests/cli/test_cli.py`

## 5. 套件與執行環境

- [ ] 5.1 調整 `pyproject.toml`：自 `dependencies` 移除 `anthropic>=0.39.0`；不新增任何 Python 第三方依賴（僅 stdlib `subprocess` / `json` / `shlex` / `pathlib` / `shutil`）；檔案範圍：`pyproject.toml`
- [ ] 5.2 調整 `.env.example`：移除 `ANTHROPIC_API_KEY`；新增 `CLAUDE_CLI_PATH=claude`、`CLAUDE_CLI_TIMEOUT_SECONDS=30`、`CLAUDE_HOME=`（留空代表使用預設 `~/.claude`）；保留 `PROJECT_AGENT_MODEL=claude-sonnet-4-7`、`LOG_LEVEL=INFO`；檔案範圍：`.env.example`
- [ ] 5.3 調整 `docker/Dockerfile`：加入 Claude Code CLI 安裝層（優先 `curl -fsSL https://claude.ai/install.sh | bash`；若網路受阻可降級為 `npm install -g @anthropic-ai/claude-code` 並加裝 Node，Specialist 視實際情況決定並於 commit message 說明選項）；將 `app` user 的 UID/GID 改為由 `ARG APP_UID` / `ARG APP_GID` 傳入（預設維持 1001 但可覆寫）；安裝後確認 `claude` 可於 `app` user 身份執行、`PATH` 包含 CLI 路徑；檔案範圍：`docker/Dockerfile`
- [ ] 5.4 調整 `docker/build.sh`：呼叫 `docker build` 時自動帶入 `--build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g)`；遵守 Google Shell Style；檔案範圍：`docker/build.sh`
- [ ] 5.5 調整 `docker/docker-compose.yaml`：新增 volume `- ${HOME}/.claude:/home/app/.claude:ro`（若 CLI 需寫回 token 則調整為 rw，Specialist 實測確認並於 commit message 說明）；保留 logs volume 與 env_file；檔案範圍：`docker/docker-compose.yaml`
- [ ] 5.6 調整 `run.sh`：啟動 container 前新增主機端前置檢查（`command -v claude` 不存在 → 顯示安裝指令後 exit 1；`[[ ! -d "${HOME}/.claude" ]]` → 提示 `claude login` 後 exit 1）；dry-run 模式（`--dry-run` 參數）跳過這兩項檢查以保離線測試能力；遵守 Google Shell Style；檔案範圍：`run.sh`

## 6. 文件更新

- [ ] 6.1 更新 `README.md`：LLM 後端章節改標「Claude Code CLI subprocess + Claude Max 訂閱」；新增「前置需求」章節說明安裝 CLI、`claude login`、`~/.claude/` volume；快速開始改為 `./docker/build.sh` → 填 `.env`（不再需要 `ANTHROPIC_API_KEY`） → `./run.sh --dry-run` → `./run.sh`；新增「故障排除」章節涵蓋 `cli_not_found` / `~/.claude/ not found` / `cli_auth_error` / `cli_timeout` 四種情境及處置；加上指向 `openspec/changes/migrate-to-claude-cli-subprocess/` 的連結；檔案範圍：`README.md`

## 7. 回歸測試與最終校驗

- [ ] 7.1 更新整合測試 `tests/integration/*`：Fixture 改以 `response.text` 承載 JSON；WIN / FAIL(timeout) / FAIL(ring_paradox) / unreachable_six_lights / script_generation_failure 五條路徑仍 pass；`test_script_generation_failure` 需改為觸發新的 JSON 解析錯誤而非 `tool_use.input` 驗證錯誤；檔案範圍：`tests/integration/test_full_win_path.py`、`tests/integration/test_timeout_fail_path.py`、`tests/integration/test_ring_paradox_fail_path.py`、`tests/integration/test_unreachable_six_lights.py`、`tests/integration/test_script_generation_failure.py`
- [ ] 7.2 於 Docker container 內執行 `./run.sh pytest` 確認全部單元與整合測試通過；於 commit message 附上最終 pytest summary；同時以 `./run.sh --dry-run` 驗證仍可輸出 `outcome.result="WIN"`；本 task 不新增實作檔，僅為驗證關卡；檔案範圍：無新增（僅執行測試）
- [ ] 7.3 依本 change 的所有 `spec.md` 與 `proposal.md` 逐項自我比對，確認 `tasks.md` 全部完成且未遺漏範圍；若實作過程中發現需調整其他未宣告檔案（例如 `CLAUDE.md` / `notes/` / `.claude/`）MUST 寫入 `issues.md` 而非直接改動；檔案範圍：`openspec/changes/migrate-to-claude-cli-subprocess/issues.md`（僅在必要時新增；否則不動）
