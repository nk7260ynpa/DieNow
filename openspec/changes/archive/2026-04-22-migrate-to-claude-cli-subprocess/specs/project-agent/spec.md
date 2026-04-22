## MODIFIED Requirements

### Requirement: 以 Claude Code CLI subprocess 實作 pov_6 的 LLM 決策

The system SHALL 提供 `ProjectAgent` 類別，以 Claude Code CLI 的非互動模式（`claude -p "<prompt>" --output-format stream-json [--model <model_id>]`）透過 `subprocess` 呼叫進行 pov_6 的每 tick 決策；模型預設為 `claude-sonnet-4-7`，可由環境變數 `PROJECT_AGENT_MODEL` 或 `ScenarioConfig.project_agent_model` 覆寫並轉為 CLI `--model` 旗標；`ProjectAgent` MUST 僅依賴 `LLMClient` 介面，生產環境注入 `ClaudeCLIClient`，測試期以 `FakeLLMClient` 替身執行；`FakeLLMClient` MUST 可於離線環境下完整驅動 pov_6 的決策流程。

#### Scenario: 正常透過 Claude CLI 呼叫
- **GIVEN** `.env` 含有非空 `CLAUDE_CODE_OAUTH_TOKEN`（或 `ANTHROPIC_API_KEY`）且已注入容器 environment
- **AND** `CLAUDE_CLI_PATH=claude` 且 `claude --version` 執行成功
- **AND** `PROJECT_AGENT_MODEL=claude-sonnet-4-7`
- **WHEN** pov_6 於 tick 5 呼叫 `project_agent.decide(observation)`
- **THEN** `ClaudeCLIClient` MUST 以 `subprocess.run` 呼叫 `claude -p "<prompt>" --output-format stream-json --model claude-sonnet-4-7`
- **AND** prompt 內容 MUST 依序包含 persona block、rules block、prior_life block 與當前 tick 的 observation
- **AND** 回傳值為解析 CLI stdout 的 `type=result` 事件後得到的 `Action` 物件

#### Scenario: 以 FakeLLMClient 可離線測試
- **GIVEN** 測試使用 `FakeLLMClient`，預先灌入 tick 5 → `PressAction(button_id=6)` 的回應
- **WHEN** `project_agent.decide(observation)` 被呼叫
- **THEN** 回傳 `PressAction(button_id=6)`
- **AND** 無任何 `subprocess.run` 呼叫發生
- **AND** 無任何外部網路或主機 CLI 互動發生

#### Scenario: `claude` CLI 不可執行時啟動失敗
- **GIVEN** `CLAUDE_CLI_PATH=claude` 但系統 PATH 中無此指令
- **WHEN** scenario-runner 嘗試建立 `ClaudeCLIClient`
- **THEN** 建構子 MUST raise `ConfigValidationError`，reason 含 `"claude CLI 不可執行"` 或等效訊息

#### Scenario: `ClaudeCLIClient` 不重複做認證環境檢查
- **GIVEN** scenario-runner 已於 `config_loader._validate_claude_cli_environment` 完成 3 步預啟動檢查（CLI 存在 / `claude --version` 成功 / `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY` 至少其一存在）
- **WHEN** scenario-runner 以已驗證過的環境建立 `ClaudeCLIClient`
- **THEN** `ClaudeCLIClient.__init__` MUST NOT 重複檢查 `~/.claude/` 目錄、token env 或 CLI 版本
- **AND** `claude_home` kwarg 已 deprecated；若被傳入僅作向後相容容忍，不影響行為
- **AND** 缺失 token env 導致的啟動失敗由 `config_loader` 層拋出 `ConfigValidationError`（詳見 scenario-runner spec 的「`CLAUDE_CODE_OAUTH_TOKEN` 缺失時非零退出」Scenario），不由此建構子負責

### Requirement: Prompt 結構（無 caching）

The system SHALL 將 `ProjectAgent` 送往 LLM 的 system 內容切分為 3 個邏輯區塊，以 `LLMSystemBlock` 承載並依序組合為單一 prompt 前綴：
1. **persona_block**：「被困的玩家」的靜態人格描述；
2. **rules_block**：世界與 action 的通用規則陳述（不含關於「body_6 才能拿戒指」的洩題資訊）；
3. **prior_life_block**：pov_6 的 5 層遞迴前世記憶（即 `script_5` 序列化為壓縮 JSON，內含遞迴 `prior_life` 鏈）。

`ClaudeCLIClient` MUST 將這 3 個 block 依序串接為 prompt 前綴（建議以 Markdown heading 分隔），`LLMSystemBlock.cache` 欄位 MUST 被視為 informational metadata 而**不**轉為任何 CLI 旗標；`LLMResponse.cache.cache_read_input_tokens` 與 `cache_creation_input_tokens` MUST 保留欄位但 `ClaudeCLIClient` 填入值恆為 `0`。user 內容為每 tick 動態 observation（包含當前 tick、`self_position`、`self_hp`、他人 bodies 摘要、`recent_public_speeches`、可用 action 清單、`shield_open` 狀態）。

#### Scenario: system_blocks 仍為 3 個邏輯區塊
- **WHEN** `project_agent._build_decide_request(observation)` 組裝 `LLMRequest`
- **THEN** `LLMRequest.system_blocks` MUST 為長度 3 的 tuple
- **AND** 三個 block 的 `label` 分別為 `"persona"`、`"rules"`、`"prior_life"`
- **AND** `prior_life_block` 的 text 長度最大
- **AND** 每個 block 的 `cache` 欄位允許為 True 或 False，實作 MUST 不因此改變 CLI 旗標組成

#### Scenario: ClaudeCLIClient 不附加任何 cache 控制
- **GIVEN** `LLMRequest` 含 3 個 `cache=True` 的 system_blocks
- **WHEN** `ClaudeCLIClient.call(request)` 被呼叫
- **THEN** `subprocess.run` 的 args MUST NOT 包含 `--cache`、`--no-cache` 或任何宣稱控制 caching 的旗標
- **AND** `LLMResponse.cache.cache_read_input_tokens == 0`
- **AND** `LLMResponse.cache.cache_creation_input_tokens == 0`

#### Scenario: cache metrics 仍被 structlog 記錄（值為 0）
- **GIVEN** 任一 tick 的 `decide` 呼叫
- **WHEN** `ProjectAgent._log_metrics(response, kind="decide")` 執行
- **THEN** structlog 記錄 MUST 含 `cache_read_input_tokens=0` 與 `cache_creation_input_tokens=0`
- **AND** 指標隨 event log 一同輸出至 `logs/`（保持下游欄位 schema 穩定）

### Requirement: 結構化 Action 解析（prompt 誘導 JSON）

The system SHALL 在 `ProjectAgent` 的 user prompt 中明確要求 LLM 以嚴格 JSON 物件格式回覆 action（不可附加說明文字或 Markdown 以外的內容）；`action_parser.parse_action_from_response(response)` MUST 優先嘗試從 `response.text` 做 `json.loads`（可自動去除 Markdown code fence），`tool_use` 路徑保留為 fallback 以便與舊 fixture 相容；解析結果 MUST 為 `Action` 子型別之一：`MoveAction(delta)`、`PressAction(button_id)`、`TouchRingAction()`、`SpeakAction(msg, targets)`、`WaitAction()`、`ObserveAction()`；解析失敗時 MUST raise `ActionParseError`，pov-manager 捕獲後降級為 `WaitAction`。

#### Scenario: LLM 回傳純 JSON 文字被正確解析
- **GIVEN** `ClaudeCLIClient` 回傳 `LLMResponse(text='{"action":"press","button_id":6}', tool_use=None)`
- **WHEN** `action_parser.parse_action_from_response(response)` 被呼叫
- **THEN** 回傳 `PressAction(button_id=6)`
- **AND** 不 raise 任何例外

#### Scenario: LLM 回傳 Markdown code fence 包裹的 JSON 被正確解析
- **GIVEN** `LLMResponse(text='```json\n{"action":"wait"}\n```', tool_use=None)`
- **WHEN** `action_parser.parse_action_from_response(response)` 被呼叫
- **THEN** 回傳 `WaitAction()`
- **AND** 不 raise 任何例外

#### Scenario: 非 JSON 純文字觸發 ActionParseError
- **GIVEN** `LLMResponse(text='I think I should press button 6', tool_use=None)`
- **WHEN** `action_parser.parse_action_from_response(response)` 被呼叫
- **THEN** MUST raise `ActionParseError(reason=...)`，reason 含「text 非合法 JSON」或等效說明

#### Scenario: JSON schema 驗證失敗
- **GIVEN** `LLMResponse(text='{"action":"fly","target":"sky"}', tool_use=None)`
- **WHEN** `action_parser.parse_action_from_response(response)` 被呼叫
- **THEN** MUST raise `ActionParseError(reason="unknown_action_type: fly")`

#### Scenario: 舊 fixture 的 tool_use 路徑向後相容
- **GIVEN** `LLMResponse(text="", tool_use={"name":"submit_action","input":{"action":"wait"}})`
- **WHEN** `action_parser.parse_action_from_response(response)` 被呼叫
- **THEN** 回傳 `WaitAction()`
- **AND** 不 raise 任何例外
- **AND** 實作 MAY 列印 `DeprecationWarning` 提醒 fixture 升級

### Requirement: 即時對話模式（pov_k, k<6）

The system SHALL 為 pov-manager 的即時對話請求提供 `project_agent.realtime_reply(pov_id, prior_life_summary, upcoming_script_hint, incoming_msg)` 介面；此呼叫的 system 內容 MUST 包含 pov_k 的 persona、pov_k 的 prior_life 壓縮敘述、為避免破壞劇本 pov_k 即將發生的事件要點（抽象層級、不含具體時機）；system_blocks 同樣為邏輯上可重用的 3-block 結構（persona / prior_life），但 `ClaudeCLIClient` 不對其套用 caching；回傳為字串（回應文字），來源為 CLI stdout 的最後一則 `type=result.result` 欄位並經 `.strip()`；LLM 呼叫失敗或連續失敗處理流程與 `decide` 一致。

#### Scenario: 產生 pov_3 的即時回應
- **GIVEN** pov_3 persona 為「好奇、愛問問題」、pov_6 發問「你記得上一世嗎？」
- **WHEN** `project_agent.realtime_reply(pov_id=3, persona=..., prior_life=..., incoming_msg="你記得上一世嗎？")` 被呼叫
- **THEN** `ClaudeCLIClient` MUST 以 `subprocess.run` 呼叫 CLI，prompt 含 pov_3 persona 與 prior_life 摘要
- **AND** 回傳非空字串
- **AND** 字串內容 MUST NOT 包含 pov_3 即將死亡的具體 tick 或具體按鈕編號

#### Scenario: enable_realtime_chat=false 時不暴露此介面
- **GIVEN** `ScenarioConfig.enable_realtime_chat=false`
- **WHEN** pov-manager 仍呼叫 `realtime_reply`
- **THEN** MUST raise `FeatureDisabledError`

### Requirement: LLM 呼叫的錯誤與 Timeout 處理

The system SHALL 為每次 LLM 呼叫設置預設 30 秒 timeout，由 `ScenarioConfig.llm_timeout_seconds` 或環境變數 `CLAUDE_CLI_TIMEOUT_SECONDS` 覆寫，並以 `subprocess.run(..., timeout=N)` 實施；以下 subprocess 層錯誤 MUST 被捕獲並轉為 `LLMCallFailedError`（reason 字串如下表）：

| 來源 | reason |
|------|--------|
| `subprocess.TimeoutExpired` | `"cli_timeout"` |
| `subprocess.CalledProcessError` 或 returncode != 0 | `"cli_nonzero_exit:<rc>"` |
| `FileNotFoundError`（CLI 消失） | `"cli_not_found"` |
| NDJSON 整段無法解析 | `"ndjson_parse_error"` |
| 收到 `type=error` 事件 | `"cli_error:<err_text>"` |
| 未取得 `type=result` 事件 | `"no_result_event"` |

`ProjectAgent` 單次 `LLMCallFailedError` MUST 轉為 `ActionParseError`（由 pov-manager 降級為 `WaitAction`）；連續 `consecutive_failure_limit`（預設 3）次 LLM 呼叫失敗 MUST raise `LLMUnavailableError` 並中止 scenario-runner（寫入 issues.md）。

#### Scenario: CLI 超時不中斷關卡
- **GIVEN** tick 7 的 `claude` subprocess 執行時間超過 30 秒
- **WHEN** `ClaudeCLIClient.call` 捕獲 `subprocess.TimeoutExpired`
- **THEN** MUST raise `LLMCallFailedError(reason="cli_timeout")`
- **AND** `ProjectAgent.decide` 轉為 `ActionParseError(reason="llm_call_failed: cli_timeout")`
- **AND** pov-manager 降級為 `WaitAction`、關卡繼續到 tick 8

#### Scenario: CLI 非零退出（例如 session 失效）
- **GIVEN** tick 7 的 `claude` subprocess 以 returncode 1 退出，stderr 為 `"auth required"`
- **WHEN** `ClaudeCLIClient.call` 檢查 returncode
- **THEN** MUST raise `LLMCallFailedError(reason="cli_nonzero_exit:1")`（cause 或訊息 MUST 包含 stderr 摘要）
- **AND** `ProjectAgent.decide` 轉為 `ActionParseError`

#### Scenario: CLI 回傳 type=error 事件
- **GIVEN** stdout 包含一行 `{"type":"error","error":{"message":"model unavailable"}}`
- **WHEN** `ClaudeCLIClient._parse_ndjson` 處理事件流
- **THEN** MUST raise `LLMCallFailedError(reason="cli_error:model unavailable")`（reason 含 err_text）

#### Scenario: 連續 3 次失敗中止關卡
- **GIVEN** tick 7、8、9 的 LLM 呼叫皆失敗
- **WHEN** `ProjectAgent.decide` 第 3 次捕獲錯誤
- **THEN** MUST raise `LLMUnavailableError`
- **AND** scenario-runner 終止，`issues.md` 追加 HIGH 嚴重度紀錄

### Requirement: 模型版本可配置（透過 CLI `--model` 旗標）

The system SHALL 允許使用者在 `.env`、`ScenarioConfig` 或 CLI 參數中指定 LLM 模型；MUST 支援所有符合 `claude-sonnet-4-*`、`claude-opus-4-*`、`claude-haiku-4-*` 命名規則的模型名；不合法的模型名 MUST 於啟動時 raise `ConfigValidationError`；實際呼叫時 MUST 將模型名透過 CLI `--model <model_id>` 旗標傳遞；若 `model` 未指定或為空字串，`ClaudeCLIClient` MUST 省略 `--model` 旗標（走 CLI 預設）。

#### Scenario: 從環境變數讀取模型並透過 --model 傳遞
- **GIVEN** `PROJECT_AGENT_MODEL=claude-opus-4-7`
- **WHEN** `ClaudeCLIClient.call(request)` 被觸發
- **THEN** `subprocess.run` 的 args MUST 含 `["--model", "claude-opus-4-7"]`

#### Scenario: 不合法模型名拒絕啟動
- **GIVEN** `PROJECT_AGENT_MODEL=gpt-4`
- **WHEN** scenario-runner 嘗試建立 `ProjectAgent`
- **THEN** MUST raise `ConfigValidationError(reason="unsupported_model")`

#### Scenario: 未指定模型時走 CLI 預設
- **GIVEN** `LLMRequest.model` 為空字串
- **WHEN** `ClaudeCLIClient.call(request)` 執行
- **THEN** `subprocess.run` 的 args MUST NOT 含 `--model` 旗標
- **AND** 仍可正常回傳 `LLMResponse`（CLI 以其內建預設模型執行）
