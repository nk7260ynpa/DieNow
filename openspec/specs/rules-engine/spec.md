# rules-engine Specification

## Purpose
TBD - created by archiving change recreate-duannao-ring-of-hands. Update Purpose after archive.
## Requirements
### Requirement: 按鈕按壓判定

The system SHALL 當任一存活 body 發起 `press(body_id, button_id)` 動作時執行以下判定：若 `body_id == button_id` → 將對應 button 設為 `lit=true` 並產生 `ButtonLitEvent`；若 `body_id != button_id` → 將該 body 的 `status` 設為 `corpse`、`hp=0` 並產生 `DeathEvent(cause="press_wrong")`；按壓的前置條件為該 body 的 `position` 需與 button 位置滿足配置中的鄰接規則（預設：重合或 `chebyshev_distance <= 1`）。

#### Scenario: body 按下正確按鈕
- **GIVEN** body_4 `alive` 且位置鄰接 button_4
- **WHEN** rules-engine 處理 `press(body_id=4, button_id=4)`
- **THEN** `button_4.lit=true`
- **AND** 新增 `ButtonLitEvent(button_id=4, actor=4, tick=<當前 tick>)`
- **AND** body_4 `status` 保持 `alive`

#### Scenario: body 按下錯誤按鈕立即死亡
- **GIVEN** body_4 `alive` 且位置鄰接 button_2
- **WHEN** rules-engine 處理 `press(body_id=4, button_id=2)`
- **THEN** body_4 `status="corpse"`、`hp=0`
- **AND** `button_2.lit` 保持 `false`
- **AND** 新增 `DeathEvent(actor=4, cause="press_wrong", tick=<當前 tick>)`

#### Scenario: 距離過遠無法按壓
- **GIVEN** body_4 距離 button_4 的 `chebyshev_distance=3`
- **WHEN** rules-engine 處理 `press(body_id=4, button_id=4)`
- **THEN** rules-engine 拒絕此動作並記錄 `ActionRejectedEvent(reason="out_of_range")`
- **AND** `button_4.lit` 保持 `false`
- **AND** body_4 `status` 保持 `alive`

### Requirement: 戒指觸碰判定

The system SHALL 當任一存活 body 發起 `touch_ring(body_id)` 動作時執行以下判定：前置條件為 `shield_open == true` 且 `ring.touchable == true` 且該 body 位置鄰接戒指（預設 `chebyshev_distance <= 1`）；若前置條件不滿足 → 拒絕並記錄 `ActionRejectedEvent(reason="ring_not_ready"|"out_of_range")`；若前置條件滿足且 `body_id == 6` → 標記關卡 `outcome.result="WIN"`、`ring.owner=6` 並產生 `OutcomeEvent(result="WIN")`；若前置條件滿足且 `body_id != 6` → 該 body 死亡、`outcome.result="FAIL"`、`cause="ring_paradox"` 並產生 `OutcomeEvent(result="FAIL", cause="ring_paradox")` 並立即終止關卡。

#### Scenario: body_6 在條件滿足時正確拿到戒指
- **GIVEN** 6 燈齊亮、`shield_open=true`、`ring.touchable=true`、body_6 鄰接戒指
- **WHEN** rules-engine 處理 `touch_ring(body_id=6)`
- **THEN** `outcome.result="WIN"`
- **AND** `ring.owner=6`
- **AND** 新增 `OutcomeEvent(result="WIN", tick=<當前 tick>)`
- **AND** scenario-runner 結束主迴圈

#### Scenario: 非 body_6 觸碰戒指導致 FAIL
- **GIVEN** 6 燈齊亮、`shield_open=true`、`ring.touchable=true`、body_3 鄰接戒指
- **WHEN** rules-engine 處理 `touch_ring(body_id=3)`
- **THEN** body_3 `status="corpse"`
- **AND** `outcome.result="FAIL"`
- **AND** `outcome.cause="ring_paradox"`
- **AND** 新增 `OutcomeEvent(result="FAIL", cause="ring_paradox")`
- **AND** scenario-runner 立即終止主迴圈

#### Scenario: 防護窗未開時拒絕觸碰
- **GIVEN** 僅 5 燈亮、`shield_open=false`、body_6 鄰接戒指
- **WHEN** rules-engine 處理 `touch_ring(body_id=6)`
- **THEN** 動作被拒絕並記錄 `ActionRejectedEvent(reason="ring_not_ready")`
- **AND** `outcome.result` 保持未決

### Requirement: 移動與碰撞

The system SHALL 當存活 body 發起 `move(body_id, delta)`（`delta ∈ {(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,1),(1,-1),(-1,1),(0,0)}`）時，計算目標座標；若目標超出房間邊界、或目標格子已被其他 body（alive 或 corpse）、按鈕、戒指或牆壁佔據，MUST 拒絕此動作並記錄 `ActionRejectedEvent(reason="collision"|"out_of_bounds")`；否則更新 body 位置並產生 `MoveEvent`。

#### Scenario: 合法移動成功
- **GIVEN** body_1 位於 `(2,2)`、`(3,2)` 為空
- **WHEN** rules-engine 處理 `move(body_id=1, delta=(1,0))`
- **THEN** body_1 位置變為 `(3,2)`
- **AND** 新增 `MoveEvent(actor=1, from=(2,2), to=(3,2))`

#### Scenario: 與 corpse 碰撞時拒絕
- **GIVEN** body_1 位於 `(2,2)`、body_5 `status="corpse"` 位於 `(3,2)`
- **WHEN** rules-engine 處理 `move(body_id=1, delta=(1,0))`
- **THEN** body_1 位置保持 `(2,2)`
- **AND** 新增 `ActionRejectedEvent(reason="collision")`

#### Scenario: 越界拒絕
- **GIVEN** body_1 位於 `(0,0)`、房間大小 `(10,10)`
- **WHEN** rules-engine 處理 `move(body_id=1, delta=(-1,0))`
- **THEN** body_1 位置保持 `(0,0)`
- **AND** 新增 `ActionRejectedEvent(reason="out_of_bounds")`

### Requirement: 說話與即時對話

The system SHALL 允許存活 body 發起 `speak(body_id, msg, targets)`；`msg` 為非空字串（長度上限由 config `max_speak_length` 預設 512 字元）；`targets` 為被指名對話的 pov_id 清單或空（代表公開廣播）；執行時 system 將訊息寫入 event log 並可見於所有存活 pov 在下一 tick 的 observation 中。當 `targets` 含任一 pov_k（k<6）時，pov-manager MUST 被通知以便產生即時對話回應；回應內容經 rules-engine 檢查後若與 pov_k 之 scripted events 衝突，MUST 降級為模糊回應並記錄 `ActionDowngradedEvent(reason="script_conflict")`。

#### Scenario: 公開廣播被所有存活 pov 觀察到
- **GIVEN** body_2、body_4、body_6 存活；body_3 為 corpse
- **WHEN** rules-engine 處理 `speak(body_id=6, msg="Hello", targets=[])`
- **THEN** 新增 `SpeakEvent(actor=6, msg="Hello", targets=[])`
- **AND** body_2 與 body_4 於下一 tick observation 的 `recent_public_speeches` 中可見此訊息
- **AND** body_3（corpse）不會出現在下一輪發言 dispatch 清單

#### Scenario: 對 pov_3 點名對話觸發即時回應
- **GIVEN** body_3 存活、`enable_realtime_chat=true`
- **WHEN** rules-engine 處理 `speak(body_id=6, msg="你記得三號的事嗎？", targets=[3])`
- **THEN** pov-manager MUST 呼叫 project-agent 以 pov_3 的 persona 與 prior_life 產生回應
- **AND** 回應 MUST 與 pov_3 當前 tick 的 scripted events 不衝突；若衝突則改寫為模糊回應
- **AND** 新增 `SpeakEvent` 與（若降級）`ActionDowngradedEvent`

#### Scenario: 空訊息被拒絕
- **WHEN** rules-engine 處理 `speak(body_id=2, msg="", targets=[])`
- **THEN** 動作被拒絕並記錄 `ActionRejectedEvent(reason="empty_message")`

### Requirement: 終局判定

The system SHALL 在以下情況之一被觸發時立即終止主迴圈並產生 `OutcomeEvent`：
- **WIN**：body_6 成功觸碰戒指；
- **FAIL(ring_paradox)**：非 body_6 成功觸碰戒指；
- **FAIL(timeout)**：`tick >= max_ticks` 且未分出勝負；
- **FAIL(unreachable_six_lights)**：場上存活 body 加上已亮燈的數量不可能湊到 6（例如 button_3 對應的 body_3 已 corpse 且 button_3 尚未亮），且沒有其他 body 能代按（按鈕與 body 編號為一對一）。

#### Scenario: 必要 body 死亡且其按鈕未亮時提前宣告敗局
- **GIVEN** body_3 `status="corpse"`、button_3 `lit=false`
- **WHEN** rules-engine 於 post-tick 檢查
- **THEN** `outcome.result="FAIL"`
- **AND** `outcome.cause="unreachable_six_lights"`
- **AND** scenario-runner 立即終止主迴圈

#### Scenario: 必要 body 死亡但該按鈕已先亮不算敗局
- **GIVEN** body_3 在 tick 10 按對 button_3 使其 `lit=true`，body_3 在 tick 15 因其他原因 `corpse`
- **WHEN** rules-engine 於 tick 15 post-tick 檢查
- **THEN** `outcome.result` 保持未決（因 button_3 已亮，不影響 6 燈齊亮條件）

### Requirement: Invariants 執行期強制

The system SHALL 於 dispatch 與 post-tick 階段強制以下 Invariants；違反者 MUST raise `InvariantViolation(inv_id=<ID>, detail=...)` 並寫入 event log：
- INV-1：任何 state mutation 只能經由 `WorldEngine.dispatch`；
- INV-2：已產出的 `Script` 為 immutable；
- INV-3：任何 pov_1~5 的 scripted action MUST 與當前 tick 的劇本條目匹配；
- INV-4：pov_6 的 action 不得觸發任何 script mutation；
- INV-5：`observe(pov_id)` 不得洩露該 pov 自己的 `number_tag`、規則、目標；
- INV-6：所有 event append-only 寫入 `EventLog`；
- INV-7：同一 tick 對同一 pov 僅接受一個自由意志 action；
- INV-8：不存在違反劇本的行為鏈。

#### Scenario: INV-3 違反 raise CausalViolation
- **GIVEN** `script_2` 指定 pov_2 於 tick 5 執行 `move(delta=(1,0))`
- **WHEN** pov-manager 在 tick 5 實際 dispatch `move(body_id=2, delta=(0,1))`
- **THEN** rules-engine MUST raise `InvariantViolation(inv_id="INV-3")`
- **AND** 新增 `InvariantViolationEvent(inv_id="INV-3", actor=2, tick=5)`

#### Scenario: INV-5 違反被自動攔截
- **WHEN** observation 建構器嘗試在 pov_2 的 observation 內容中塞入 `self_number_tag=2`
- **THEN** 建構器 MUST raise `InvariantViolation(inv_id="INV-5")`
- **AND** observation MUST NOT 被回傳

#### Scenario: INV-7 違反：單 tick 重覆自由 action
- **GIVEN** pov_6 已在 tick 8 dispatch 過一個 action
- **WHEN** 任何程式在 tick 8 再次 dispatch pov_6 的自由 action
- **THEN** rules-engine MUST raise `InvariantViolation(inv_id="INV-7")`

