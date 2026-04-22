# project-agent Specification

## Purpose
TBD - created by archiving change recreate-duannao-ring-of-hands. Update Purpose after archive.
## Requirements
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

### Requirement: Prompt 結構與 Prompt Caching

The system SHALL 將 ProjectAgent 送往 LLM 的 `system` 內容切分為 3 個可快取區塊並對每個區塊附加 `cache_control={"type":"ephemeral"}`：
1. **persona_block**：「被困的玩家」的靜態人格描述；
2. **rules_block**：世界與 action 的通用規則陳述（不含關於「body_6 才能拿戒指」的洩題資訊）；
3. **prior_life_block**：pov_6 的 5 層遞迴前世記憶（即 `script_5` 序列化為壓縮 JSON，內含遞迴 `prior_life` 鏈）。

`user` 內容為每 tick 動態 observation（包含當前 tick、`self_position`、`self_hp`、他人 bodies 摘要、`recent_public_speeches`、可用 action 清單、`shield_open` 狀態），MUST NOT 添加 `cache_control`。

#### Scenario: system 內容含 3 個快取區塊
- **WHEN** `project_agent.decide(observation)` 組裝 request
- **THEN** 送往 SDK 的 `system` 參數 MUST 為長度 3 的 list
- **AND** 每個 element 的 `cache_control.type == "ephemeral"`
- **AND** 第 3 塊（prior_life_block）文字長度最大

#### Scenario: user 不帶 cache_control
- **WHEN** 組裝第 N tick 的 request
- **THEN** `messages` 中最後一則 user message MUST NOT 含 `cache_control`
- **AND** 內容包含當前 tick 與 observation 序列化

#### Scenario: cache_read_input_tokens 指標被記錄
- **GIVEN** tick 2 的 request
- **WHEN** LLM 回應 metadata 含 `cache_read_input_tokens=12000`
- **THEN** ProjectAgent MUST 以 structlog 記錄 `{tick=2, cache_read_input_tokens=12000, cache_creation_input_tokens=...}`
- **AND** 指標隨 event log 一同輸出至 `logs/`

### Requirement: 結構化 Action 解析

The system SHALL 要求 LLM 以嚴格 JSON schema 回傳 action（可使用 Anthropic tool use 或 JSON mode）；解析後 MUST 為 `Action` 子型別之一：`MoveAction(delta)`、`PressAction(button_id)`、`TouchRingAction()`、`SpeakAction(msg, targets)`、`WaitAction()`、`ObserveAction()`；解析失敗時 MUST raise `ActionParseError`，pov-manager 捕獲後降級為 `WaitAction`（見 pov-manager spec）。

#### Scenario: 合法 JSON 解析成 PressAction
- **GIVEN** LLM 回傳 `{"action":"press","button_id":6}`
- **WHEN** ProjectAgent 解析回應
- **THEN** 回傳 `PressAction(button_id=6)`
- **AND** 不 raise 任何例外

#### Scenario: 非法 JSON 觸發 ActionParseError
- **GIVEN** LLM 回傳 `"I think I should press button 6"`（純文字，非 JSON）
- **WHEN** ProjectAgent 解析回應
- **THEN** MUST raise `ActionParseError(raw_response=...)`

#### Scenario: JSON schema 驗證失敗
- **GIVEN** LLM 回傳 `{"action":"fly","target":"sky"}`（unknown action）
- **WHEN** ProjectAgent 解析回應
- **THEN** MUST raise `ActionParseError(reason="unknown_action_type")`

### Requirement: 即時對話模式（pov_k, k<6）

The system SHALL 為 pov-manager 的即時對話請求提供 `project_agent.realtime_reply(pov_id, prior_life_summary, upcoming_script_hint, incoming_msg)` 介面；此呼叫的 system 內容 MUST 包含 pov_k 的 persona、pov_k 的 prior_life 壓縮敘述、為避免破壞劇本 pov_k 即將發生的事件要點（抽象層級、不含具體時機）；`cache_control` 同樣應用於可重用的 persona 與 prior_life；回傳為字串（回應文字）。

#### Scenario: 產生 pov_3 的即時回應
- **GIVEN** pov_3 persona 為「好奇、愛問問題」、pov_6 發問「你記得上一世嗎？」
- **WHEN** `project_agent.realtime_reply(pov_id=3, ..., incoming_msg="你記得上一世嗎？")`
- **THEN** 回傳非空字串
- **AND** 字串內容 MUST NOT 包含 pov_3 即將死亡的具體 tick 或具體按鈕編號（避免破壞劇本）

#### Scenario: enable_realtime_chat=false 時不暴露此介面
- **GIVEN** `ScenarioConfig.enable_realtime_chat=false`
- **WHEN** pov-manager 仍呼叫 `realtime_reply`
- **THEN** MUST raise `FeatureDisabledError`

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

