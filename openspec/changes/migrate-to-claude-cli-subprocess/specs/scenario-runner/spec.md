## MODIFIED Requirements

### Requirement: CLI 入口與設定載入

The system SHALL 提供 `python -m ring_of_hands.cli run --config <path>` 指令（及對應的 `run.sh` shell wrapper）做為關卡執行入口；CLI MUST 讀取 YAML 設定檔（例如 `configs/default.yaml`）、合併 `.env` 中的環境變數（至少讀 `CLAUDE_CLI_PATH`、`CLAUDE_CLI_TIMEOUT_SECONDS`、`CLAUDE_CODE_OAUTH_TOKEN`、`ANTHROPIC_API_KEY`、`CLAUDE_HOME`、`PROJECT_AGENT_MODEL`、`LOG_LEVEL`；`CLAUDE_HOME` 保留為向後相容，不再參與啟動檢查）、解析成 `ScenarioConfig`（Pydantic v2 model）；設定合併後 MUST 通過下列預啟動檢查：
1. `shutil.which(CLAUDE_CLI_PATH)` 不為 None；
2. `subprocess.run([cli_path, "--version"], capture_output=True, timeout=5, check=False)` exit code == 0；
3. 環境變數 `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY` 其一存在且為非空字串（前者為建議認證方式；後者保留為 fallback）。

任一檢查失敗 MUST raise `ConfigValidationError`（由 `ring_of_hands.llm.base` 重新匯出），以非零 exit code 結束，並印出可操作建議（提示執行 `claude setup-token` 或安裝 CLI）。

#### Scenario: 預設設定啟動成功
- **GIVEN** `configs/default.yaml` 存在
- **AND** `CLAUDE_CLI_PATH=claude` 且 `shutil.which("claude")` 有值
- **AND** `claude --version` exit code 為 0
- **AND** 環境變數 `CLAUDE_CODE_OAUTH_TOKEN` 為非空字串（或 `ANTHROPIC_API_KEY` 為非空字串）
- **WHEN** 使用者執行 `python -m ring_of_hands.cli run --config configs/default.yaml`
- **THEN** scenario-runner 進入主迴圈
- **AND** stdout 顯示初始化資訊（room size、max_ticks、model、`claude` CLI 版本）

#### Scenario: 缺少 config 檔時非零退出
- **WHEN** 使用者執行 `python -m ring_of_hands.cli run --config configs/missing.yaml`
- **THEN** exit code `!= 0`
- **AND** stderr 顯示 `ConfigValidationError: configs/missing.yaml not found`

#### Scenario: 缺少 claude CLI 時非零退出
- **GIVEN** 系統 PATH 中無 `claude` 可執行檔
- **AND** `ScenarioConfig.llm_client="claude_cli"`
- **WHEN** 使用者執行 `python -m ring_of_hands.cli run --config configs/default.yaml`
- **THEN** exit code `!= 0`
- **AND** stderr 顯示可操作建議，至少包含「安裝 Claude Code CLI（例如 `curl -fsSL https://claude.ai/install.sh | bash`）」字樣
- **AND** 不發出任何 LLM 呼叫

#### Scenario: `CLAUDE_CODE_OAUTH_TOKEN` 缺失時非零退出
- **GIVEN** `claude` CLI 已安裝可執行
- **AND** 環境變數 `CLAUDE_CODE_OAUTH_TOKEN` 未設定或為空字串
- **AND** 環境變數 `ANTHROPIC_API_KEY` 未設定或為空字串
- **WHEN** 使用者執行 `python -m ring_of_hands.cli run --config configs/default.yaml`
- **THEN** exit code `!= 0`
- **AND** stderr 顯示可操作建議「請先於主機執行 `claude setup-token` 並將 token 寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`」或等效訊息
- **AND** 不發出任何 LLM 呼叫

#### Scenario: CLAUDE_CLI_TIMEOUT_SECONDS 覆寫預設 timeout
- **GIVEN** `.env` 設 `CLAUDE_CLI_TIMEOUT_SECONDS=60`
- **WHEN** config 載入完成
- **THEN** `ScenarioConfig.llm_timeout_seconds` MUST 為 60
- **AND** 所有後續 `subprocess.run(..., timeout=...)` 呼叫 MUST 以此值為上限

### Requirement: Dry-run 與 Fake LLM 模式

The system SHALL 提供 `--dry-run` CLI 旗標；啟用時 MUST 使用 `FakeLLMClient`（預錄 stub；由 `FakeAnthropicClient` 更名而來，內部 response builder 以 `LLMResponse.text` 承載 JSON 字串）、MUST NOT 呼叫任何真實 LLM 端點或 `subprocess.run` 呼叫 `claude`、MUST 仍然走完整 tick 迴圈；`ScenarioConfig.dry_run_fixture_path` 指定 stub 檔案位置（預設 `tests/fixtures/dry_run.yaml`）；此模式主要用於 CI 與離線整合測試，且 MUST 可在未安裝 `claude` CLI、未登入、無 `~/.claude/` 的環境下成功執行。

#### Scenario: dry-run 跑完 happy path
- **GIVEN** `tests/fixtures/dry_run.yaml` 提供合法 5 份 script（以 JSON 文字形式承載於 `LLMResponse.text`）+ pov_6 WIN 路徑 actions
- **WHEN** 使用者執行 `./run.sh python -m ring_of_hands.cli run --config configs/default.yaml --dry-run`
- **THEN** 主迴圈執行完成、`outcome.result="WIN"`
- **AND** 無任何網路呼叫
- **AND** 無任何 `subprocess.run([cli_path, ...])` 對 `claude` 的呼叫

#### Scenario: dry-run 找不到 fixture 非零退出
- **GIVEN** `dry_run_fixture_path` 指向不存在檔案
- **WHEN** 啟動 dry-run
- **THEN** exit code `!= 0`
- **AND** stderr 顯示 `FixtureNotFoundError`

#### Scenario: dry-run 不要求 claude CLI 與 OAuth token
- **GIVEN** 主機無 `claude` 可執行檔
- **AND** 環境變數 `CLAUDE_CODE_OAUTH_TOKEN` 與 `ANTHROPIC_API_KEY` 皆未設定
- **WHEN** 使用者執行 `./run.sh --dry-run`
- **THEN** scenario-runner 正常啟動進入主迴圈
- **AND** 不 raise `ConfigValidationError`（dry-run 模式跳過 claude CLI 與 token 預啟動檢查）

### Requirement: Docker 化執行環境

The system SHALL 提供以下檔案以 Docker 化：
- `docker/Dockerfile`：`python:3.11-slim`；安裝 `pyproject.toml` 相依（不再含 `anthropic`）；**額外安裝 Claude Code CLI**（建議 `npm install -g @anthropic-ai/claude-code`；或 `curl -fsSL https://claude.ai/install.sh | bash` 降級方案）並確保 CLI 位於 `PATH` 中；建立非 root 的 `app` user，其 UID/GID 由 `build-arg`（`APP_UID`、`APP_GID`）覆寫以對齊主機擁有者；
- `docker/build.sh`：`docker build --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g) -t ring-of-hands:local -f docker/Dockerfile .`（遵守 Google Shell Style）；
- `docker/docker-compose.yaml`：服務 `app`，volume 掛載 `logs/` 至 `/app/logs`；透過 `env_file: ../.env` 將 `CLAUDE_CODE_OAUTH_TOKEN`（與其他 `.env` 變數）注入容器，容器內 `claude` CLI 由此認證 Max 訂閱身份；**不得** 掛載 `${HOME}/.claude` 或 `${HOME}/.claude.json`（macOS Keychain 無法跨容器，且 token 改走 env）；
- `run.sh`：非 dry-run 啟動 container 前 MUST 先檢查 `.env` 存在且含有非空值的 `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY`；通過後參數透傳至 `docker compose run --rm app "$@"`（無參數時預設 `python -m ring_of_hands.cli run --config configs/default.yaml`）；dry-run 模式（第一個參數為 `--dry-run` 或參數含有 `--dry-run`）MUST 跳過此檢查；
- `logs/.gitkeep`：保留 `logs/` 目錄；
- `.gitignore`：忽略 `logs/*`、`.env`、`__pycache__/`、`.pytest_cache/`、`*.pyc`、`dist/`、`build/`；
- `.env.example`：**移除** `ANTHROPIC_API_KEY` 為必要欄位（仍可作為 fallback 保留，附註「可選 fallback」）；**新增** `CLAUDE_CODE_OAUTH_TOKEN=`（留空，附註「請先於主機執行 `claude setup-token` 取得 long-lived token 後貼入」）、`CLAUDE_CLI_PATH=claude`、`CLAUDE_CLI_TIMEOUT_SECONDS=30`；`CLAUDE_HOME=` 保留為 **向後相容** 欄位（目前不參與啟動檢查，可留空）；保留 `PROJECT_AGENT_MODEL=claude-sonnet-4-7`、`LOG_LEVEL=INFO`。

#### Scenario: run.sh 啟動 container 並執行 CLI
- **GIVEN** image `ring-of-hands:local` 已建立
- **AND** `.env` 檔存在且含有非空值的 `CLAUDE_CODE_OAUTH_TOKEN`（或 dry-run 模式）
- **WHEN** 使用者執行 `./run.sh --dry-run`
- **THEN** Docker container 啟動、執行 `python -m ring_of_hands.cli run --config configs/default.yaml --dry-run`
- **AND** `logs/` 目錄內新增 events/run/summary 三份檔案

#### Scenario: run.sh 在 .env 缺 `CLAUDE_CODE_OAUTH_TOKEN` 時阻擋
- **GIVEN** `.env` 檔不存在，或存在但 `CLAUDE_CODE_OAUTH_TOKEN` 未設定／為空字串
- **AND** `.env` 亦未提供非空值的 `ANTHROPIC_API_KEY`
- **WHEN** 使用者執行 `./run.sh`（非 dry-run）
- **THEN** `run.sh` MUST 以非零 exit code 結束
- **AND** stderr 顯示可操作建議「請執行 `claude setup-token` 後將 token 寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`」或等效訊息
- **AND** MUST NOT 嘗試啟動 Docker container

#### Scenario: 容器內 claude 以 `CLAUDE_CODE_OAUTH_TOKEN` 承繼 Max 訂閱身份
- **GIVEN** `.env` 含有透過 `claude setup-token` 取得的有效 `CLAUDE_CODE_OAUTH_TOKEN`
- **AND** `docker-compose.yaml` 透過 `env_file: ../.env` 將該變數注入容器
- **AND** 容器 **未** 掛載 `${HOME}/.claude` 或 `${HOME}/.claude.json`
- **WHEN** 容器內 `subprocess.run(["claude", "--version"])` 執行
- **THEN** exit code 為 0
- **AND** 容器內 `claude -p "ping" --output-format stream-json --verbose` 可完成單次呼叫而不回傳 401（以 Max 訂閱身份走 OAuth token，`apiKeySource` 非 `api_key`）

#### Scenario: logs/ 寫入權限正確
- **GIVEN** Docker container 以非 root user 執行
- **WHEN** scenario-runner 寫入 `/app/logs/events_<ts>.jsonl`
- **THEN** 檔案成功寫入、宿主機 `logs/` 目錄可見此檔
- **AND** 檔案擁有者為 container user（非 root）

### Requirement: README 記載架構

The system SHALL 提供 `README.md`，內容 MUST 至少包含：
- 專案目的（一段）與《端腦》作者壁水羽出處；
- 技術棧與 Python 版本；**LLM 後端說明 MUST 明確標示為「Claude Code CLI subprocess + Claude Max 訂閱」**，並註明不使用 `anthropic` Python SDK；
- 目錄架構樹（標註各 capability 對應的原始碼目錄）；
- **前置需求章節**：MUST 說明 (1) 主機需安裝 Claude Code CLI（附官方安裝指令；或可直接透過容器內 CLI）、(2) 主機需執行 `claude setup-token` 取得 long-lived OAuth token、(3) 將 token 貼入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`，由 `docker-compose.yaml` 透過 `env_file` 注入容器；
- 快速開始（`./docker/build.sh` → 填 `.env`（`CLAUDE_CODE_OAUTH_TOKEN=<token>`，不再需要 `ANTHROPIC_API_KEY`） → `./run.sh --dry-run` → `./run.sh`）；
- **故障排除章節**：至少涵蓋 (1) `ConfigValidationError: claude CLI not found` 的處理、(2) `ConfigValidationError: CLAUDE_CODE_OAUTH_TOKEN missing` 的處理（提示執行 `claude setup-token` 並更新 `.env`）、(3) `LLMCallFailedError(reason="cli_auth_error")` 或 `401 authentication_error` 的處理（token 失效需重新 `claude setup-token`）、(4) `LLMCallFailedError(reason="cli_timeout")` 的處理（調整 `CLAUDE_CLI_TIMEOUT_SECONDS`）；
- 執行 pytest 的方式（`./run.sh pytest`）；
- 指向 `openspec/changes/migrate-to-claude-cli-subprocess/` 與 `openspec/changes/recreate-duannao-ring-of-hands/` 兩個 change 的連結；
- 提示 `CLAUDE.md` 的存在（若有團隊共享版本）。

#### Scenario: README 含目錄樹
- **WHEN** 使用者檢視 `README.md`
- **THEN** 文件 MUST 包含程式碼 block 呈現目錄樹
- **AND** 目錄樹 MUST 列出 `src/`、`docker/`、`configs/`、`tests/`、`logs/` 等頂層項目
- **AND** 標示 `world-model`、`rules-engine`、`script-generator`、`pov-manager`、`project-agent`、`scenario-runner` 六個 capability 對應的模組路徑

#### Scenario: README 說明 Claude CLI 前置流程
- **WHEN** 使用者閱讀「前置需求」章節
- **THEN** 章節 MUST 依序說明 (1) 安裝 CLI（或使用容器內 CLI）、(2) 執行 `claude setup-token` 取得 long-lived token、(3) 將 token 寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`
- **AND** MUST NOT 提及 `ANTHROPIC_API_KEY` 作為必要設定項（可作為 fallback 列出）

#### Scenario: README 含 dry-run 指示
- **WHEN** 使用者閱讀快速開始章節
- **THEN** 指示 MUST 包含 `./run.sh --dry-run` 這行指令
- **AND** 說明 dry-run 不會呼叫真實 LLM 也不需要 `CLAUDE_CODE_OAUTH_TOKEN`

#### Scenario: README 含故障排除常見錯誤
- **WHEN** 使用者閱讀故障排除章節
- **THEN** 章節 MUST 列出至少 4 種錯誤代碼/訊息及其對應處置建議
- **AND** `cli_timeout` 的處置 MUST 指出可透過 `CLAUDE_CLI_TIMEOUT_SECONDS` 調整
