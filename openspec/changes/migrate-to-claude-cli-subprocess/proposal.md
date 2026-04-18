# Proposal: 將 LLM 後端由 Anthropic SDK 遷移至 Claude Code CLI subprocess

## Why

- 使用者擁有 **Claude Max 訂閱**，希望本專案的 LLM 呼叫走 Max 訂閱的計費額度，而不是以 API key 逐次計算 token 費用。
- 官方 `anthropic` Python SDK 與 `claude-agent-sdk-python` **不支援** Claude Max 訂閱認證；相關 Upstream issue 已被明確否決（`anthropics/claude-code#6536` closed as not planned；`anthropics/claude-agent-sdk-python#559` Max plan billing request 無計畫）。
- 唯一能以 Max 訂閱身份程式化呼叫 Claude 模型的合法路徑為 **Claude Code CLI（`claude -p` 非互動模式 + `--output-format stream-json`）subprocess**：由使用者先於主機以 `claude login` 完成 OAuth session，再由 Python 以 `subprocess` 呼叫 CLI。
- 本 change 為**技術債遷移**（Backend Swap），遊戲使命、INV-1~INV-8 生產期保障、`world-model` / `rules-engine` / `pov-manager` 三個 capability 的對外行為、關卡勝敗條件、劇本結構、因果閉環等核心需求**完全不變**。

## What Changes

- **BREAKING**：移除 `anthropic>=0.39.0` 依賴；刪除 `src/ring_of_hands/llm/anthropic_client.py`。
- **BREAKING**：新增 `src/ring_of_hands/llm/claude_cli_client.py`（`ClaudeCLIClient`），以 `subprocess.run(["claude", "-p", "<prompt>", "--output-format", "stream-json", ...])` 實作 `LLMClient` Protocol。
- **BREAKING**：`.env.example` 移除 `ANTHROPIC_API_KEY`；新增 `CLAUDE_CLI_PATH`（預設 `claude`）、`CLAUDE_CLI_TIMEOUT_SECONDS`（預設 `30`）。
- **BREAKING**：scenario-runner 啟動檢查由「驗證 `ANTHROPIC_API_KEY` 存在」改為「驗證 `claude --version` 可執行 + 已透過 `claude login` 建立 OAuth session（檢查 `~/.claude/` 目錄存在且可讀）」；失敗 raise `ConfigValidationError`。
- **BREAKING**：`docker/Dockerfile` 新增 Claude Code CLI 安裝步驟（`curl -fsSL https://claude.ai/install.sh | bash` 或等效程序）；`docker/docker-compose.yaml` 新增 volume 將主機 `~/.claude/` 掛載至容器相同路徑以共享 OAuth session；容器 user 權限需對齊主機 `~/.claude/` 擁有者（UID/GID mapping）。
- **BREAKING**：Prompt caching 能力**移除**；`ProjectAgent` 與 `ScriptGenerator` 仍維持 3-block system 結構（persona / rules / prior_life）以保留未來恢復 caching 的彈性，但不再附加 `cache_control={"type":"ephemeral"}`；`CacheMetadata.cache_read_input_tokens` 與 `cache_creation_input_tokens` 欄位保留但恆為 `0`。
- **BREAKING**：結構化 Action 解析由「Anthropic tool use（`tool_choice={"type":"tool","name":"submit_action"}`）」降級為「純 prompt 誘導 LLM 輸出 JSON + `json.loads` 解析」；解析失敗仍沿用既有降級策略為 `WaitAction`（見 pov-manager spec）。
- **BREAKING**：結構化 Script 生成由「`produce_script` tool use」降級為「prompt 誘導 JSON 輸出 + Pydantic 驗證」。
- **BREAKING**：測試替身 `FakeAnthropicClient` **更名**為 `FakeLLMClient`；`FakeClientFixture` 保留；mock 的介面由「tool_use payload」改為「stdout NDJSON 事件流」或「直接回傳預錄 `LLMResponse`」。（`FakeLLMClient` 是實作介面 `LLMClient` 的共用 fake，不綁定 backend。）
- **BREAKING**：LLM 呼叫 Timeout/Error 處理由「Anthropic SDK 的 `APITimeoutError` / `APIConnectionError` / `APIStatusError`」改為「`subprocess.TimeoutExpired` / `subprocess.CalledProcessError` / CLI `type=error` 事件」；錯誤→`LLMCallFailedError` 的語意保持不變。
- **BREAKING**：模型版本指定由 SDK 呼叫參數 `model=...` 改為 CLI `--model` 旗標；支援的模型名命名規則維持不變（`claude-sonnet-4-*`、`claude-opus-4-*`、`claude-haiku-4-*`）。
- README.md 更新：新的啟動程序（`claude login` 先於主機執行）、移除 API key 設定步驟。

## Capabilities

### New Capabilities

- 無。本 change 僅改實作 backend，不引入新 capability。

### Modified Capabilities

- `project-agent`：LLM 呼叫的 backend 由 Anthropic SDK 改為 Claude CLI subprocess；prompt caching 能力移除；結構化 action 解析降級為 prompt 誘導 JSON；錯誤類型對應 `subprocess` 層的異常；模型版本透過 `--model` 旗標指定。
- `script-generator`：LLM 呼叫介面抽象仍維持，但預設實作由 `AnthropicClient` 改為 `ClaudeCLIClient`；測試替身由 `FakeAnthropicClient` 改名為 `FakeLLMClient`；script 產出由 tool use 降級為 prompt 誘導 JSON。
- `scenario-runner`：啟動檢查由 `ANTHROPIC_API_KEY` 改為 `claude` CLI 可執行 + 已登入；Docker 化執行環境新增 Claude CLI 安裝與 `~/.claude/` volume mount；README 更新。

## Impact

### Affected code

- **刪除**：`src/ring_of_hands/llm/anthropic_client.py`。
- **新增**：`src/ring_of_hands/llm/claude_cli_client.py`（`ClaudeCLIClient`、NDJSON 事件解析、subprocess 生命週期管理）。
- **更名 + 調整介面**：`src/ring_of_hands/llm/fake_client.py` 中 `FakeAnthropicClient` → `FakeLLMClient`（class 更名，fixture schema 不變；內部 response builder 不再依賴 Anthropic-specific `tool_use` 結構）。
- **修改**：
  - `src/ring_of_hands/llm/base.py`：`CacheMetadata` 欄位保留、標註為「恆為 0」；`LLMSystemBlock.cache` 欄位保留但在 `ClaudeCLIClient` 中忽略。
  - `src/ring_of_hands/project_agent/agent.py`：移除 `cache_control` 依賴；移除 `SUBMIT_ACTION_TOOL` tool use 呼叫；改以 prompt 誘導 JSON 輸出；`decide` 與 `realtime_reply` 的錯誤處理對應新 backend。
  - `src/ring_of_hands/project_agent/action_parser.py`：優先從 `response.text` 做 `json.loads`（tool_use 路徑改為 fallback，保留向後相容）。
  - `src/ring_of_hands/project_agent/metrics.py`：`cache_read_input_tokens` / `cache_creation_input_tokens` 保留欄位但值恆為 0；不影響輸出 schema。
  - `src/ring_of_hands/script_generator/generator.py`：script 解析由 `tool_use.input` 改為 `response.text` JSON。
  - `src/ring_of_hands/script_generator/prompt_builder.py`：移除 `PRODUCE_SCRIPT_TOOL` 常數；改以純 prompt 要求 LLM 輸出 JSON；移除 `tool_choice`、移除 `tools`。
  - `src/ring_of_hands/scenario_runner/`（實際檔案路徑以現況為準）：啟動檢查由 `ANTHROPIC_API_KEY` 改為 `claude` CLI 可執行性驗證。
- **配置**：
  - `.env.example`：移除 `ANTHROPIC_API_KEY`；新增 `CLAUDE_CLI_PATH`、`CLAUDE_CLI_TIMEOUT_SECONDS`、`CLAUDE_HOME`（可選，預設 `~/.claude`）。
  - `pyproject.toml`：移除 `anthropic>=0.39.0`；不新增任何 Python 依賴（僅 stdlib `subprocess`、`json`、`shlex`、`os`、`pathlib`）。
  - `docker/Dockerfile`：新增 Claude CLI 安裝；調整 user UID/GID 以便與主機 `~/.claude/` 對齊。
  - `docker/docker-compose.yaml`：新增 volume `~/.claude:/home/app/.claude:ro`（或等效路徑）。
  - `run.sh`：在啟動 container 前先檢查主機 `claude` 是否可執行、`~/.claude/` 是否存在。

### Affected tests

- **全部通過 `LLMClient` 介面的單元測試**：改用 `FakeLLMClient`；大多數只需改 import 名稱。
- **`tests/test_llm/test_anthropic_client.py`**（若存在）→ 刪除；新增 `tests/test_llm/test_claude_cli_client.py`（測 subprocess mock + NDJSON 解析 + timeout + error）。
- **`tests/test_project_agent/test_agent.py`**：`SUBMIT_ACTION_TOOL`、`cache_control` 相關 assertion 移除；新增「LLM 回傳純文字 JSON」的解析測試。
- **`tests/test_script_generator/test_generator.py`**：`PRODUCE_SCRIPT_TOOL` 相關 assertion 移除；fixture 內 script 改用純文字 JSON 回應。
- **`tests/test_integration/*`**：Fixture 格式略調整；WIN / FAIL(timeout) / FAIL(wrong_ring) 三條路徑維持。
- **新增**：`tests/test_llm/test_claude_cli_ndjson.py`，測試 CLI stdout NDJSON 多種邊界（多 `type=assistant` 訊息 / `type=error` / 超時 / 非預期輸出）。

### Affected dependencies

- **Python**：移除 `anthropic>=0.39.0`。無新增依賴。
- **系統（Docker image）**：新增 Claude Code CLI 安裝（`curl -fsSL https://claude.ai/install.sh | bash` 或 Node 版本的 `npm install -g @anthropic-ai/claude-code`；Specialist 於 design.md 決定安裝方式）。
- **主機端前置**：使用者 MUST 於主機執行 `claude login` 一次以建立 OAuth session；session 過期時需重新登入。

### Operational impact

- Docker image build 時間增加（約 +1~3 分鐘，視 Claude CLI 安裝媒介）。
- Docker image 大小增加（預估 +50~150 MB）。
- 關卡執行期的每個 LLM 呼叫都需要 spawn 一個 `claude` 子程序，會比 SDK-in-process 呼叫多出 fork/exec 成本（預估每 call 多 50~200 ms）；以本專案每關約 30~60 次 LLM 呼叫計，總開銷 +3~12 秒，可接受。
- 所有計費由 Max 訂閱額度承擔，不再產生 API token 費用。
