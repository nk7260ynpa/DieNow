## ADDED Requirements

### Requirement: 管理 6 個 pov context

The system SHALL 於 scenario-runner 啟動時建立 6 個 pov context（pov_1 ~ pov_6）；每個 context MUST 持有 `pov_id`、`persona`、`prior_life`（pov_1 為 `None`、pov_2~6 為對應的 `script_{n-1}`）、`script`（pov_1~5 為對應的 `script_n`、pov_6 為 `None`）、`is_alive`；pov_manager 為所有 pov context 的擁有者，外部 MUST 僅透過 `pov_manager.get_context(pov_id)`、`pov_manager.tick_scripted_povs(tick)`、`pov_manager.request_realtime_reply(pov_id, prompt)` 介面互動。

#### Scenario: 初始化 6 個 context
- **GIVEN** `script_1~script_5` 與 pov_6 的 persona 皆備妥
- **WHEN** scenario-runner 呼叫 `pov_manager.initialize(scripts, pov6_persona)`
- **THEN** `pov_manager.contexts` 長度為 6
- **AND** `pov_1.prior_life is None`、`pov_1.script == script_1`
- **AND** `pov_6.prior_life == script_5`、`pov_6.script is None`
- **AND** 所有 pov 的 `is_alive=True`

#### Scenario: Corpse 更新為 is_alive=False
- **GIVEN** body_3 於 tick 7 被判定 corpse
- **WHEN** pov-manager 於 tick 7 post-tick 處理死亡事件
- **THEN** `pov_3.is_alive=False`
- **AND** 後續 tick 對 pov_3 的 `tick_scripted_povs` 呼叫 MUST 略過 pov_3

### Requirement: 劇本執行器（pov_1 ~ pov_5）

The system SHALL 於每個 tick 依 pov_id 順序 1→2→3→4→5 讓 pov_manager 查找對應劇本中 `t == 當前 tick` 的事件；若查到 MUST 依序透過 `WorldEngine.dispatch()` 提交動作（每筆事件轉成對應 `Action` 物件）；若 pov 當前 `is_alive=False` 或該 tick 無對應事件則略過；scripted action 不得由 LLM 即時決策（主幹鎖死），僅 `speak` 類事件可交由 project-agent 以 persona 填充「措辭細節」，但 `msg` 主幹內容 MUST 與 script 一致。

#### Scenario: tick 命中時按劇本 dispatch
- **GIVEN** `script_2.events` 含 `(t=4, actor=2, action_type="press", payload={"button_id":2}, targets=[])`
- **AND** pov_2 `is_alive=True`
- **WHEN** pov-manager 處理 tick 4
- **THEN** `WorldEngine.dispatch(pov_id=2, action=PressAction(button_id=2))` 被呼叫
- **AND** rules-engine 驗證此 action 與 script 一致（INV-8）

#### Scenario: 死亡 pov 略過劇本
- **GIVEN** `script_3.events` 含 `(t=10, actor=3, action_type="move", ...)`
- **AND** pov_3 於 tick 8 已 corpse
- **WHEN** pov-manager 處理 tick 10
- **THEN** pov_3 的 scripted action MUST 不被 dispatch
- **AND** 不產生任何錯誤（死亡後略過為合法行為）

#### Scenario: Scripted action 與 WorldState 衝突時回報 INV-8
- **GIVEN** `script_4.events` 含 `(t=6, actor=4, action_type="move", payload={"delta":(1,0)})`
- **AND** 實際 tick 6 時 `(body_4.x+1, body_4.y)` 位置被 corpse 佔據
- **WHEN** pov-manager 嘗試 dispatch 該 move
- **THEN** rules-engine raise `InvariantViolation(inv_id="INV-8", detail="scripted move collides with corpse")`
- **AND** scenario-runner 立即終止並記錄於 issues.md（由 Coordinator 後續處理）

### Requirement: pov_6 observation 產生與 action 分派

The system SHALL 於每 tick（在 pov_1~5 的 scripted 動作處理完之後）為 pov_6 呼叫 `world_engine.observe(pov_id=6)` 取得 `Observation`；pov_manager MUST 將 observation 傳給 project-agent 的 `decide(observation)` 介面；project-agent 回傳的 `Action` MUST 經 pov_manager 透過 `world_engine.dispatch(pov_id=6, action=...)` 提交；同一 tick 對 pov_6 僅允許提交 1 次自由 action（INV-7）。

#### Scenario: pov_6 每 tick 一次自由決策
- **GIVEN** 當前 tick 為 9
- **WHEN** pov-manager 完成 pov_1~5 的 scripted 處理
- **THEN** `world_engine.observe(pov_id=6)` 被呼叫一次
- **AND** `project_agent.decide(observation)` 被呼叫一次
- **AND** 對應 `world_engine.dispatch(pov_id=6, action=<回傳 action>)` 被呼叫恰 1 次

#### Scenario: pov_6 已 corpse 時略過決策
- **GIVEN** pov_6 `is_alive=False`（理論上僅可能發生於開發期錯誤，屬於 FAIL 終局前置條件）
- **WHEN** pov-manager 處理當前 tick
- **THEN** MUST 略過 pov_6 的決策呼叫
- **AND** scenario-runner 於 post-tick 判定為 `FAIL(unreachable_six_lights)` 或既有終局原因

#### Scenario: pov_6 回傳非法 action 降級為 wait
- **GIVEN** project-agent 因 LLM 回應解析失敗而拋出 `ActionParseError`
- **WHEN** pov-manager 接收到例外
- **THEN** pov-manager MUST dispatch `WaitAction` 作為降級行為
- **AND** 新增 `ActionDowngradedEvent(actor=6, reason="llm_parse_error", tick=<當前 tick>)`

### Requirement: 即時對話路由

The system SHALL 當 rules-engine 通知「pov_6 透過 `speak` 動作點名 pov_k（k<6）」時，由 pov-manager 呼叫 project-agent（`role="realtime_reply"`）傳入 pov_k 的 persona、pov_k 的 prior_life、pov_k 當前 tick 以後的 scripted events 摘要（用於避免劇本衝突）、pov_6 的訊息內容；project-agent 回傳 pov_k 的回應字串；pov-manager MUST 驗證該回應不與 pov_k 的後續 scripted events 衝突（例如若劇本已預定 pov_k 於下一 tick 死亡，而回應中出現「我等下就離開房間」則視為衝突），衝突時降級為預設的模糊回應（`"..."` 或 `"我不知道"`）並產生 `ActionDowngradedEvent`。

#### Scenario: 正常即時回應
- **GIVEN** `enable_realtime_chat=true`、pov_3 存活、pov_6 以 `speak(msg="你是誰？", targets=[3])` 發話
- **WHEN** pov-manager 處理即時對話請求
- **THEN** `project_agent.realtime_reply(pov_id=3, ...)` 被呼叫
- **AND** 回傳字串以 `SpeakEvent(actor=3, msg=<回應>, targets=[6])` 寫入 event log
- **AND** 不得修改任何 script

#### Scenario: 即時回應與 script 衝突時降級
- **GIVEN** `script_3` 預定 pov_3 於 tick 下一 tick 按對 button_3
- **AND** project-agent 回覆「我要去拿戒指」
- **WHEN** pov-manager 執行衝突檢查
- **THEN** 回應改為「...」
- **AND** 新增 `ActionDowngradedEvent(actor=3, reason="script_conflict")`

#### Scenario: enable_realtime_chat=false 時不呼叫 LLM
- **GIVEN** `ScenarioConfig.enable_realtime_chat=false`
- **WHEN** pov_6 `speak(msg="hi", targets=[3])`
- **THEN** pov-manager MUST NOT 呼叫 project-agent 的 realtime_reply
- **AND** pov_3 於下一 tick observation 中仍看得到 pov_6 的訊息，但自身不自動回應

### Requirement: pov_manager 介面為唯讀暴露

The system SHALL 將 `pov_manager.contexts` 與 `pov_manager.scripts` 以 read-only（例如 `MappingProxyType` 或 `tuple`）暴露；外部 MUST NOT 能直接改寫任一 context 或 script；context 內部可變欄位僅 `is_alive`，且只能由 pov-manager 自身因應 rules-engine 的死亡事件更新。

#### Scenario: 外部寫入 contexts 失敗
- **WHEN** 任一模組嘗試 `pov_manager.contexts[2].is_alive = False`（從外部）
- **THEN** MUST 因為 `MappingProxyType` 或等效保護 raise `TypeError`

#### Scenario: pov-manager 自身可在處理死亡事件時更新 is_alive
- **GIVEN** body_5 被判死
- **WHEN** pov-manager 收到 `DeathEvent(actor=5)`
- **THEN** `pov_5.is_alive` 變為 `False`
- **AND** 此更新 MUST 僅由 pov-manager 內部私有方法觸發
