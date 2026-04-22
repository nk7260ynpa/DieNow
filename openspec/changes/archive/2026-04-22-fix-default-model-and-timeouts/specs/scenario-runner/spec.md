# Delta for scenario-runner

本 delta 對應 change `fix-default-model-and-timeouts`，用於修正
`.env.example` 中錯誤的預設模型字面值，並鎖定 `ScenarioConfig` 預設值
（模型 = `claude-sonnet-4-6`、timeout = 180 秒）。

## MODIFIED Requirements

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

## ADDED Requirements

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
