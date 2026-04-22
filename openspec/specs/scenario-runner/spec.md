# scenario-runner Specification

## Purpose
TBD - created by archiving change recreate-duannao-ring-of-hands. Update Purpose after archive.
## Requirements
### Requirement: CLI 入口與設定載入

The system SHALL 提供 `python -m ring_of_hands.cli run --config <path>` 指令（及對應的 `run.sh` shell wrapper）做為關卡執行入口；CLI MUST 讀取 YAML 設定檔（例如 `configs/default.yaml`）、合併 `.env` 中的環境變數（至少讀 `ANTHROPIC_API_KEY`、`PROJECT_AGENT_MODEL`、`LOG_LEVEL`）、解析成 `ScenarioConfig`（Pydantic v2 model）；任何驗證失敗 MUST 以非零 exit code 結束並印出可讀錯誤。

#### Scenario: 預設設定啟動成功
- **GIVEN** `configs/default.yaml` 存在、`ANTHROPIC_API_KEY` 已設定
- **WHEN** 使用者執行 `python -m ring_of_hands.cli run --config configs/default.yaml`
- **THEN** scenario-runner 進入主迴圈
- **AND** stdout 顯示初始化資訊（room size、max_ticks、model）

#### Scenario: 缺少 config 檔時非零退出
- **WHEN** 使用者執行 `python -m ring_of_hands.cli run --config configs/missing.yaml`
- **THEN** exit code `!= 0`
- **AND** stderr 顯示 `ConfigValidationError: configs/missing.yaml not found`

#### Scenario: 缺少 API Key 非零退出
- **GIVEN** `ANTHROPIC_API_KEY` 未設定且 `llm_client="anthropic"`
- **WHEN** 使用者執行 `python -m ring_of_hands.cli run --config configs/default.yaml`
- **THEN** exit code `!= 0`
- **AND** stderr 顯示可操作建議（「請填入 `.env` 中的 `ANTHROPIC_API_KEY`」）

### Requirement: 執行流程編排

The system SHALL 於主流程依序：
1. 驗證 `ScenarioConfig`；
2. 建立 `LLMClient`、`ProjectAgent`；
3. 呼叫 `script_generator.generate_all()` 取得 5 份 immutable `Script`；
4. 建立 `WorldEngine` 與 `PovManager`（以 5 份 script + pov_6 persona 初始化）；
5. 進入 tick 主迴圈：`for tick in range(max_ticks):`
   - 5.1 `pov_manager.tick_scripted_povs(tick)`（依序 pov_1~5）
   - 5.2 若尚未終局，呼叫 `pov_manager.tick_free_agent(tick)`（pov_6）
   - 5.3 `world_engine.advance_tick()`
   - 5.4 `rules_engine.post_tick_checks()`（包含 unreachable_six_lights、timeout）
   - 5.5 若 `outcome` 已決則 `break`
6. 產生 `OutcomeEvent` 與結算摘要；
7. 關閉 event log 檔案、輸出 summary 至 stdout 與 `logs/`。

#### Scenario: WIN 路徑完整流程
- **GIVEN** 以 FakeAnthropicClient 預錄 happy path（5 份合法 script、pov_6 在 6 燈齊亮後 PressAction + TouchRingAction）
- **WHEN** scenario-runner 執行
- **THEN** 主迴圈正常結束於 `outcome.result="WIN"`
- **AND** `logs/events_<ts>.jsonl` 存在且內容包含 `OutcomeEvent(result="WIN")`

#### Scenario: FAIL(timeout) 路徑
- **GIVEN** pov_6 所有 tick 皆回傳 WaitAction
- **WHEN** scenario-runner 執行到 `tick == max_ticks`
- **THEN** `outcome.result="FAIL"`、`outcome.cause="timeout"`
- **AND** event log 最後一筆為 `OutcomeEvent`

#### Scenario: Script 生成失敗時不進入 tick 迴圈
- **GIVEN** script_generator 於第 3 份劇本驗證失敗達 retry 上限
- **WHEN** scenario-runner 捕獲 `ScriptValidationError`
- **THEN** 主迴圈 MUST NOT 執行任何 tick
- **AND** `issues.md` 已追加對應紀錄
- **AND** CLI 以非零 exit code 結束

### Requirement: Event Log 與 Structlog

The system SHALL 為每次關卡執行建立：
- `logs/events_<ISO-8601 時間戳>.jsonl`：每行為一個 Pydantic `Event` 的 JSON 序列化（append-only）；
- `logs/run_<ISO-8601 時間戳>.log`：以 structlog 輸出的人類可讀日誌（key-value pair）；
`logs/` 目錄 MUST 由 `run.sh` 於 Docker container 內掛載至宿主機；所有寫入 MUST 在 scenario-runner 結束前 flush；關卡啟動時同時 echo 路徑到 stdout。

#### Scenario: JSONL 每行為合法 JSON
- **GIVEN** 關卡正常跑完
- **WHEN** 檢視 `logs/events_<ts>.jsonl`
- **THEN** 檔案每一行 MUST 能獨立被 `json.loads` 解析
- **AND** 每行含 `tick`、`event_type`、`actor`、`payload` 欄位

#### Scenario: run.log 有 cache metrics
- **GIVEN** 啟用 Anthropic 真實呼叫
- **WHEN** 檢視 `run_<ts>.log`
- **THEN** MUST 至少一筆日誌含 `cache_read_input_tokens` 與 `cache_creation_input_tokens`

#### Scenario: 關卡失敗也會 flush 日誌
- **GIVEN** script_generator 失敗
- **WHEN** CLI 退出
- **THEN** `logs/events_<ts>.jsonl` 仍包含 `ScriptGenerationFailedEvent`
- **AND** `logs/run_<ts>.log` 的最後一行描述失敗摘要

### Requirement: Dry-run 與 Fake LLM 模式

The system SHALL 提供 `--dry-run` CLI 旗標；啟用時 MUST 使用 `FakeAnthropicClient`（預錄 stub）、MUST NOT 呼叫任何真實 LLM 端點、MUST 仍然走完整 tick 迴圈；`ScenarioConfig.dry_run_fixture_path` 指定 stub 檔案位置（預設 `tests/fixtures/dry_run.yaml`）；此模式主要用於 CI 與離線整合測試。

#### Scenario: dry-run 跑完 happy path
- **GIVEN** `tests/fixtures/dry_run.yaml` 提供合法 5 份 script + pov_6 WIN 路徑 actions
- **WHEN** 使用者執行 `./run.sh python -m ring_of_hands.cli run --config configs/default.yaml --dry-run`
- **THEN** 主迴圈執行完成、`outcome.result="WIN"`
- **AND** 無任何網路呼叫

#### Scenario: dry-run 找不到 fixture 非零退出
- **GIVEN** `dry_run_fixture_path` 指向不存在檔案
- **WHEN** 啟動 dry-run
- **THEN** exit code `!= 0`
- **AND** stderr 顯示 `FixtureNotFoundError`

### Requirement: 關卡結算摘要

The system SHALL 於關卡結束後產生 `ScenarioSummary`（JSON）並寫入 `logs/summary_<ts>.json` 與 echo 至 stdout；欄位 MUST 包含：`outcome.result`、`outcome.cause`、`total_ticks`、`alive_bodies_at_end`、`lit_buttons_at_end`、`llm_call_count`、`llm_total_tokens`、`cache_read_tokens`、`cache_creation_tokens`、`execution_duration_seconds`。

#### Scenario: WIN 時 summary 正確
- **GIVEN** 關卡以 WIN 結束、總 tick=32
- **WHEN** 檢視 `logs/summary_<ts>.json`
- **THEN** `outcome.result="WIN"`、`total_ticks=32`、`alive_bodies_at_end >= 1`（至少 body_6）、`lit_buttons_at_end=6`

#### Scenario: FAIL(ring_paradox) 時 summary 正確
- **GIVEN** 某 tick 非 body_6 搶先拿到戒指
- **WHEN** 檢視 summary
- **THEN** `outcome.result="FAIL"`、`outcome.cause="ring_paradox"`

### Requirement: Docker 化執行環境

The system SHALL 提供以下檔案以 Docker 化：

- `docker/Dockerfile`：`python:3.11-slim`；安裝 `pyproject.toml` 相依；
  非 root user 執行；
- `docker/build.sh`：`docker build -t ring-of-hands:local -f docker/Dockerfile .`
  （遵守 Google Shell Style）；
- `docker/docker-compose.yaml`：服務 `app`，volume 掛載 `logs/` 至
  `/app/logs`、env_file `.env`；
- `run.sh`：參數透傳至 `docker compose run --rm app "$@"`（無參數時預設
  `python -m ring_of_hands.cli run --config configs/default.yaml`）；
- `logs/.gitkeep`：保留 `logs/` 目錄；
- `.gitignore`：忽略 `logs/*`、`.env`、`__pycache__/`、`.pytest_cache/`、
  `*.pyc`、`dist/`、`build/`；
- `.env.example`：`ANTHROPIC_API_KEY=`、`PROJECT_AGENT_MODEL=claude-sonnet-4-6`、
  `LOG_LEVEL=INFO`，並含選擇性示例註解 `# CLAUDE_CLI_TIMEOUT_SECONDS=180`。

#### Scenario: run.sh 啟動 container 並執行 CLI

- **GIVEN** image `ring-of-hands:local` 已建立
- **WHEN** 使用者執行 `./run.sh --dry-run`
- **THEN** Docker container 啟動、執行 `python -m ring_of_hands.cli run --config configs/default.yaml --dry-run`
- **AND** `logs/` 目錄內新增 events/run/summary 三份檔案

#### Scenario: logs/ 寫入權限正確

- **GIVEN** Docker container 以非 root user 執行
- **WHEN** scenario-runner 寫入 `/app/logs/events_<ts>.jsonl`
- **THEN** 檔案成功寫入、宿主機 `logs/` 目錄可見此檔
- **AND** 檔案擁有者為 container user（非 root）

#### Scenario: .env.example 提供正確預設模型

- **WHEN** 使用者檢視 `.env.example`
- **THEN** 檔案 MUST 包含 `PROJECT_AGENT_MODEL=claude-sonnet-4-6` 一行
- **AND** 檔案 MUST NOT 包含字串 `claude-sonnet-4-7`

### Requirement: README 記載架構

The system SHALL 提供 `README.md`，內容 MUST 至少包含：
- 專案目的（一段）與《端腦》作者壁水羽出處；
- 技術棧與 Python 版本；
- 目錄架構樹（標註各 capability 對應的原始碼目錄）；
- 快速開始（`./docker/build.sh` → 填 `.env` → `./run.sh --dry-run` → `./run.sh`）；
- 執行 pytest 的方式（`./run.sh pytest`）；
- 指向 `openspec/changes/recreate-duannao-ring-of-hands/` 的連結；
- 提示 `CLAUDE.md` 的存在（若有團隊共享版本）。

#### Scenario: README 含目錄樹
- **WHEN** 使用者檢視 `README.md`
- **THEN** 文件 MUST 包含程式碼 block 呈現目錄樹
- **AND** 目錄樹 MUST 列出 `src/`、`docker/`、`configs/`、`tests/`、`logs/` 等頂層項目
- **AND** 標示 `world-model`、`rules-engine`、`script-generator`、`pov-manager`、`project-agent`、`scenario-runner` 六個 capability 對應的模組路徑

#### Scenario: README 含 dry-run 指示
- **WHEN** 使用者閱讀快速開始章節
- **THEN** 指示 MUST 包含 `./run.sh --dry-run` 這行指令
- **AND** 說明 dry-run 不會呼叫真實 LLM

### Requirement: 預設值鎖定

The system SHALL 在無 `.env` override、YAML 無對應欄位的情況下，將
`ScenarioConfig` 的預設值固定為：

- `project_agent_model = "claude-sonnet-4-6"`
- `llm_timeout_seconds = 180.0`

以保證「乾淨 clone 後 `./run.sh`」的 smoke path 在不手動編輯任何設定
檔的情況下可正確呼叫 Anthropic 服務、並給予 script generation 足夠
時間。

#### Scenario: 空 env 空 YAML 時採預設模型

- **GIVEN** `PROJECT_AGENT_MODEL` 環境變數未設定
- **AND** YAML 設定檔 MUST NOT 定義 `project_agent_model` 欄位
- **WHEN** `config_loader.load_config()` 被呼叫
- **THEN** 回傳 `ScenarioConfig.project_agent_model == "claude-sonnet-4-6"`

#### Scenario: 空 env 空 YAML 時採預設 timeout

- **GIVEN** `CLAUDE_CLI_TIMEOUT_SECONDS` 等相關環境變數皆未設定
- **AND** YAML 設定檔 MUST NOT 定義 `llm_timeout_seconds` 欄位
- **WHEN** `config_loader.load_config()` 被呼叫
- **THEN** 回傳 `ScenarioConfig.llm_timeout_seconds == 180.0`

#### Scenario: YAML 覆寫 timeout 優先於預設

- **GIVEN** YAML 設定檔含 `llm_timeout_seconds: 60`
- **WHEN** `config_loader.load_config()` 被呼叫
- **THEN** 回傳 `ScenarioConfig.llm_timeout_seconds == 60.0`

#### Scenario: env 覆寫 model 優先於預設

- **GIVEN** `PROJECT_AGENT_MODEL=claude-opus-4-7`
- **AND** YAML 設定檔未定義 `project_agent_model`
- **WHEN** `config_loader.load_config()` 被呼叫
- **THEN** 回傳 `ScenarioConfig.project_agent_model == "claude-opus-4-7"`

