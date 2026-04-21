## MODIFIED Requirements

### Requirement: LLM 呼叫介面抽象

The system SHALL 以介面 `LLMClient` 抽象所有 LLM 呼叫；生產環境使用 `ClaudeCLIClient`（透過 `subprocess` 呼叫 Claude Code CLI 並解析 stdout NDJSON）、測試環境使用 `FakeLLMClient`（回傳預錄 `LLMResponse`）；`script-generator` MUST 僅依賴 `LLMClient` 介面，不得直接 import `anthropic`、`subprocess` 或任何 backend-specific 模組，以利離線測試；`LLMClient.call(LLMRequest) → LLMResponse` 的 Protocol 與 `LLMRequest` / `LLMResponse` / `LLMSystemBlock` / `CacheMetadata` 的欄位 schema MUST 維持不變（`CacheMetadata.cache_read_input_tokens` 與 `cache_creation_input_tokens` 欄位保留，`ClaudeCLIClient` 恆填 0）。

#### Scenario: 以 FakeLLMClient 可完整產生 5 份劇本
- **GIVEN** `FakeLLMClient` 預先灌入 5 份合法 stub scripts（fixture 中 script 內容序列化為 `LLMResponse.text` 的 JSON 字串）
- **WHEN** `script-generator` 以 `FakeLLMClient` 執行 `generate_all()`
- **THEN** 5 份 script 皆能通過驗證
- **AND** 測試 MUST 可在無網路、無 `claude` CLI 安裝的環境下通過

#### Scenario: 正式執行時使用 ClaudeCLIClient
- **GIVEN** `ScenarioConfig.llm_client="claude_cli"`（或等效設定）
- **AND** `.env` 含有非空 `CLAUDE_CODE_OAUTH_TOKEN`（或 `ANTHROPIC_API_KEY`）並由 docker-compose 透過 `env_file` 注入容器 environment
- **WHEN** scenario-runner 啟動
- **THEN** `script-generator` 收到的 `LLMClient` 實例 MUST 為 `ClaudeCLIClient`
- **AND** 該 instance 的每次 `call` MUST 透過 `subprocess.run` 執行 `claude -p "<prompt>" --output-format stream-json --verbose`

#### Scenario: 正式執行時 claude CLI 未安裝則啟動失敗
- **GIVEN** 主機 PATH 中無 `claude` 指令
- **AND** `ScenarioConfig.llm_client="claude_cli"`
- **WHEN** scenario-runner 嘗試建構 `ClaudeCLIClient`
- **THEN** MUST raise `ConfigValidationError`
- **AND** 不呼叫任何 LLM 端點
- **AND** stderr 含可操作建議（提示以 `curl -fsSL https://claude.ai/install.sh | bash` 安裝 CLI，或於 `pip`／主機環境確認 CLI 於 PATH；以及執行 `claude setup-token` 取得 long-lived OAuth token 後寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`）

### Requirement: 依序產生 5 份閉環劇本

The system SHALL 於關卡啟動前依序（pov_1 → pov_2 → pov_3 → pov_4 → pov_5）呼叫 LLM 產生 `script_1, script_2, script_3, script_4, script_5` 共 5 份劇本；每次呼叫輸入 MUST 包含：目標 pov 的 `persona`、世界環境描述（房間尺寸、6 body 起始位置、按鈕位置、戒指位置、面具／眼鏡設定、可用 action 原語清單）、當該 pov 有前世時的完整 `prior_life`（= 上一份劇本）；prompt 末尾 MUST 明確要求 LLM「僅輸出 JSON 物件，不要附加說明文字」並附上 `Script` schema 範本；每份劇本輸出 MUST 為通過 Pydantic 驗證的 `Script` 物件。

#### Scenario: script_1 無前世、結構完整
- **WHEN** `script-generator` 以 `pov_1` 的 persona 呼叫 LLM 產生 `script_1`
- **THEN** LLM 回傳的 `LLMResponse.text` 為合法 JSON（可能包覆在 Markdown code fence 中）
- **AND** 經解析後得到 `Script(pov_id=1, prior_life=None, events=[...], persona=..., death_cause=...)`
- **AND** `events` 為時間排序（`t` 嚴格非遞減）、每筆 event 的 `actor` 必為合法 pov_id
- **AND** `events` 最後 MUST 為 `actor=pov_1, action_type="die"` 的事件
- **AND** `death_cause` 為 `press_wrong|ring_paradox|timeout|other` 其中之一

#### Scenario: script_n (n>=2) 必帶 prior_life
- **WHEN** `script-generator` 產生 `script_3`
- **THEN** 回傳 `Script(pov_id=3, prior_life=<script_2 完整結構>, ...)`
- **AND** `prior_life.pov_id == 2`
- **AND** `prior_life.prior_life.pov_id == 1`（遞迴確認 2 層前世）

#### Scenario: LLM 回傳無法解析時觸發 retry
- **GIVEN** `ScriptConfig.max_retries=3`
- **WHEN** LLM 首次 `LLMResponse.text` 無法被 `json.loads` + Pydantic 解析為合法 `Script`
- **THEN** `script-generator` MUST 重試，且下一次 prompt 包含解析錯誤提示（附上先前的錯誤 message 或 diff）
- **AND** 若 3 次皆失敗 MUST raise `ScriptGenerationError` 並寫入 `issues.md`

#### Scenario: 解析 Markdown code fence 包裹的 JSON
- **GIVEN** LLM 回傳 `LLMResponse.text='```json\n{"pov_id":1,"persona":{...},"events":[...],"death_cause":"..."}\n```'`
- **WHEN** `script-generator` 解析 response
- **THEN** MUST 自動去除 code fence 後再 `json.loads`
- **AND** 正常得到 `Script(pov_id=1, ...)`

### Requirement: 時間一致性驗證

The system SHALL 在每份 `script_n`（n ∈ {2,3,4,5}）生成後，立即對照 `script_{n-1}`（即 `prior_life`）執行時間一致性驗證；驗證通過的定義為：`script_n.events` 中所有 `actor == n-1` 的事件 OR `targets` 含 `n-1` 的事件，MUST 在 `script_{n-1}.events` 中以相同 `t`、相同 `action_type`、相同 `payload`、相同 `targets` 出現；任一不一致 → 驗證失敗；反之亦然（`script_{n-1}` 中 `actor/targets` 涉及 pov_n 的事件 MUST 在 `script_n` 中對應存在）。此 Requirement 的邏輯與 LLM 後端實作方式無關，MUST 保持不變。

#### Scenario: 閉環一致時驗證通過
- **GIVEN** `script_1` 含 event `(t=3, actor=2, action_type="speak", payload={"msg":"hi"}, targets=[1])`
- **AND** `script_2` 含 event `(t=3, actor=2, action_type="speak", payload={"msg":"hi"}, targets=[1])`
- **WHEN** 驗證器比對兩份劇本
- **THEN** 驗證結果為 `valid=true`
- **AND** 無 diff

#### Scenario: 閉環不一致時驗證失敗並回傳 diff
- **GIVEN** `script_1` 含 event `(t=3, actor=2, action_type="speak", payload={"msg":"hi"}, targets=[1])`
- **AND** `script_2` 含 event `(t=3, actor=2, action_type="speak", payload={"msg":"hello"}, targets=[1])`
- **WHEN** 驗證器比對兩份劇本
- **THEN** 驗證結果為 `valid=false`
- **AND** diff 包含 `{"t":3, "field":"payload.msg", "prior":"hi", "current":"hello"}`

#### Scenario: 驗證失敗觸發 retry 並於 prompt 附加 diff 提示
- **GIVEN** script_3 首次驗證失敗、`max_retries=3`
- **WHEN** `script-generator` 進入第二次生成嘗試
- **THEN** LLM 輸入 prompt MUST 額外包含先前驗證失敗的 diff 描述
- **AND** 若第二次仍失敗則進入第三次；三次皆失敗 raise `ScriptValidationError`

### Requirement: Retry 上限與 issues.md 記錄

The system SHALL 在任何 script 生成或驗證流程中達到 `max_retries`（預設 3，可由 `ScriptConfig.max_retries` 覆寫）仍失敗時，中止整個關卡啟動流程；MUST 將失敗摘要（失敗的 script_n、diff 內容、retry 次數、LLM 原始回應摘要）追加寫入 `openspec/changes/migrate-to-claude-cli-subprocess/issues.md`（格式：`[Coordinator|Specialist|Verifier] [<ISO-8601 時間戳>] [嚴重度: HIGH] <描述>`）；MUST raise 結構化例外供上層捕獲。

#### Scenario: 超過 retry 上限時寫入 issues.md
- **GIVEN** `max_retries=3` 且 `script_4` 三次驗證皆失敗
- **WHEN** `script-generator` 放棄重試
- **THEN** system raise `ScriptValidationError`
- **AND** `issues.md` 追加一筆 `HIGH` 嚴重度紀錄，含失敗 pov_id、diff、三次 LLM response 摘要
- **AND** scenario-runner 立即終止，不進入 tick 主迴圈

#### Scenario: max_retries 可由 config 覆寫
- **WHEN** scenario-runner 以 `ScriptConfig(max_retries=5)` 啟動
- **THEN** `script-generator` MUST 允許同一 script 最多 5 次生成嘗試
- **AND** 仍 fail 時比照上述寫 issues.md

### Requirement: Script 為 Immutable

The system SHALL 使 `Script` 與 `ScriptEvent` 皆以 Pydantic v2 `model_config = ConfigDict(frozen=True)` 宣告；script 一旦通過驗證並回傳，任何嘗試修改其欄位的程式碼 MUST 引發 `ValidationError` / `TypeError`；劇本修改僅能透過「捨棄舊物件、建立新物件」的方式處理（但執行期不允許這樣做；僅限 `script-generator` 自身內部在驗證前的建構階段）。

#### Scenario: 修改已回傳的 Script 欄位失敗
- **GIVEN** `script_1` 已回傳
- **WHEN** 任一程式嘗試 `script_1.events[0].payload["msg"] = "changed"`
- **THEN** system MUST raise `TypeError` 或 `ValidationError`
- **AND** `script_1` 原內容保持不變

#### Scenario: Script 不可被 pov-manager 替換
- **GIVEN** pov-manager 持有 `script_2` 引用
- **WHEN** 任一程式嘗試 `pov_manager.scripts[2] = new_script`
- **THEN** 以 `MappingProxyType` 或等效 read-only 容器禁止此行為並 raise `TypeError`
