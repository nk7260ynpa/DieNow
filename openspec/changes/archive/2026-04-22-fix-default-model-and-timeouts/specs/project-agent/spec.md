# Delta for project-agent

本 delta 對應 change `fix-default-model-and-timeouts`，用於修正 baseline
spec 中錯誤的預設模型字面值（`claude-sonnet-4-7` 不存在）與過短的預設
timeout（30 秒對 script generation 不足）。

## MODIFIED Requirements

### Requirement: 以 Anthropic SDK 實作 pov_6 的 LLM 決策

The system SHALL 提供 `ProjectAgent` 類別，以 `anthropic` Python SDK（
`messages.create`）呼叫 Claude 模型進行 pov_6 的每 tick 決策；模型預設為
`claude-sonnet-4-6`，可由環境變數 `PROJECT_AGENT_MODEL` 或 `ScenarioConfig
.project_agent_model` 覆寫；ProjectAgent MUST 僅依賴 `LLMClient` 介面，
測試期以 `FakeAnthropicClient` 替身執行。

#### Scenario: 正常呼叫 Claude 模型決策

- **GIVEN** `ANTHROPIC_API_KEY` 已設定、`PROJECT_AGENT_MODEL=claude-sonnet-4-6`
- **WHEN** ProjectAgent 於 tick 5 執行 `decide(observation)`
- **THEN** 呼叫 `LLMClient.call()` 一次
- **AND** 請求參數包含 `model="claude-sonnet-4-6"`、system blocks、user messages、tool/structured output 設定

#### Scenario: 無 API Key 時 raise ConfigValidationError

- **GIVEN** `llm_client="anthropic"` 但 `ANTHROPIC_API_KEY` 未設定
- **WHEN** ProjectAgent 初始化
- **THEN** MUST raise `ConfigValidationError`

### Requirement: LLM 呼叫的錯誤與 Timeout 處理

The system SHALL 為每次 LLM 呼叫設置預設 180 秒 timeout（可由
`ScenarioConfig.llm_timeout_seconds` 覆寫）；網路錯誤或逾時 MUST 被捕獲
並轉為 `ActionParseError`（由 pov-manager 降級為 WaitAction）；連續 3 次
LLM 呼叫失敗 MUST raise `LLMUnavailableError` 並中止 scenario-runner（寫
入 issues.md）。

#### Scenario: 預設 timeout 為 180 秒

- **GIVEN** 未指定 `ScenarioConfig.llm_timeout_seconds`、未指定 `.env` 中
  相關 override
- **WHEN** `ScenarioConfig` 被載入
- **THEN** `config.llm_timeout_seconds == 180.0`
- **AND** 傳遞給 `LLMClient.call()` 的 `LLMRequest.timeout_seconds` 為 `180.0`

#### Scenario: 單次逾時不中斷關卡

- **GIVEN** tick 7 的 LLM 呼叫逾時
- **WHEN** ProjectAgent 捕獲 `TimeoutError`
- **THEN** MUST 轉換為 `ActionParseError(reason="timeout")`
- **AND** pov-manager 降級為 WaitAction、關卡繼續到 tick 8

#### Scenario: 連續 3 次失敗中止關卡

- **GIVEN** tick 7、8、9 的 LLM 呼叫皆失敗
- **WHEN** ProjectAgent 第 3 次捕獲錯誤
- **THEN** MUST raise `LLMUnavailableError`
- **AND** scenario-runner 終止，`issues.md` 追加 HIGH 嚴重度紀錄

### Requirement: 模型版本可配置

The system SHALL 允許使用者在 `.env`、`ScenarioConfig` 或 CLI 參數中指定
LLM 模型；MUST 支援所有符合 `claude-sonnet-4-*`、`claude-opus-4-*`、
`claude-haiku-4-*` 命名規則的模型；不合法的模型名 MUST 於啟動時 raise
`ConfigValidationError`；預設模型為 `claude-sonnet-4-6`（2026-04 實際存在
於 Anthropic 服務之 Sonnet 4.X 家族最新版本）。

#### Scenario: 未指定模型時採用預設

- **GIVEN** `PROJECT_AGENT_MODEL` 未設定、`ScenarioConfig.project_agent_model`
  未指定、YAML 未指定
- **WHEN** scenario-runner 建立 ProjectAgent
- **THEN** 實際 LLM 請求的 `model` 欄位為 `"claude-sonnet-4-6"`

#### Scenario: 從環境變數讀取模型

- **GIVEN** `PROJECT_AGENT_MODEL=claude-opus-4-7`
- **WHEN** scenario-runner 建立 ProjectAgent
- **THEN** 實際 LLM 請求的 `model` 欄位為 `"claude-opus-4-7"`

#### Scenario: 不合法模型名拒絕啟動

- **GIVEN** `PROJECT_AGENT_MODEL=gpt-4`
- **WHEN** scenario-runner 嘗試建立 ProjectAgent
- **THEN** MUST raise `ConfigValidationError(reason="unsupported_model")`
