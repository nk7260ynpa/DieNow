# world-model Specification

## Purpose
TBD - created by archiving change recreate-duannao-ring-of-hands. Update Purpose after archive.
## Requirements
### Requirement: World State 為唯一事實來源

The system SHALL 在 `WorldEngine` 中集中持有整個關卡的世界狀態（`WorldState`），且所有對世界的讀取與變更 MUST 透過 `WorldEngine.observe()` 與 `WorldEngine.dispatch()` 介面進行；pov、script-generator、scenario-runner 或任何外部呼叫端 MUST NOT 直接改寫 `WorldState` 欄位。

#### Scenario: 透過 observe 介面讀取自身視角
- **WHEN** pov_3 呼叫 `world_engine.observe(pov_id=3)`
- **THEN** system 回傳僅包含 pov_3 自己的 `self_position`、`self_hp`、`self_prior_life_summary`、其他存活 body 的 `position` 與 `number_tag`、當前 tick、防護窗狀態
- **AND** 回傳結果 MUST NOT 含 pov_3 自己的 `number_tag`、關卡規則陳述、通關條件陳述

#### Scenario: 禁止繞過 WorldEngine 直接改寫狀態
- **WHEN** 任一呼叫端嘗試執行 `world_engine.state.bodies[0].hp = 0`（或任何直接 mutation）
- **THEN** system MUST 透過 Pydantic `frozen=True` 或等效機制 raise `TypeError` / `ValidationError`
- **AND** 世界狀態 MUST 保持不變

#### Scenario: 所有變更透過 dispatch 驗證
- **WHEN** pov_2 呼叫 `world_engine.dispatch(pov_id=2, action=MoveAction(delta=(1,0)))`
- **THEN** system 先經由 rules-engine 驗證再套用到新版 `WorldState`
- **AND** 產生對應的 `MoveEvent` 寫入 `EventLog`

### Requirement: 場景初始狀態

The system SHALL 在關卡啟動時產生 `WorldState` 初始值，包含：10x10 grid 房間（尺寸可由 `ScenarioConfig.room_size` 覆寫）、6 個 body（body_1 ~ body_6，每個 body 的 `position` 來自 `ScenarioConfig.body_start_positions`、`hp=100`、`number_tag=1..6`、`status="alive"`）、6 個按鈕（button_1 ~ button_6，`position` 來自 config、`lit=false`）、1 枚戒指（`position` 來自 config、`touchable=false`、`owner=None`）、防護窗狀態 `shield_open=false`、`tick=0`。

#### Scenario: 預設 10x10 房間初始化
- **WHEN** scenario-runner 以預設 `ScenarioConfig` 啟動關卡
- **THEN** `WorldState.room_size` 為 `(10, 10)`
- **AND** 6 個 body 均為 `alive`、hp=100
- **AND** 6 個按鈕均為 `lit=false`
- **AND** `shield_open=false`
- **AND** `tick=0`

#### Scenario: Config 覆寫房間尺寸
- **WHEN** scenario-runner 以 `ScenarioConfig(room_size=(12, 12))` 啟動
- **THEN** `WorldState.room_size` 為 `(12, 12)`
- **AND** 所有 body / button / ring 的初始 position MUST 落在 `(0..11, 0..11)` 範圍內

#### Scenario: Config 起始位置超出房間時拒絕啟動
- **WHEN** scenario-runner 收到 `body_start_positions` 含座標 `(15, 5)` 但 `room_size=(10,10)`
- **THEN** system MUST raise `ConfigValidationError`
- **AND** 世界狀態 MUST NOT 被建立

### Requirement: Body 狀態機

The system SHALL 對每個 body 維持以下狀態：`alive`（可移動、可按按鈕、可說話）、`corpse`（仍佔據 grid 格子、保留 `number_tag`、無法再提交任何 action）。狀態轉移 `alive → corpse` 僅由 rules-engine 的死亡判定觸發，且 MUST 為不可逆。

#### Scenario: Body 死亡後仍佔空間
- **GIVEN** body_3 的 `status="corpse"` 位於 grid `(4, 5)`
- **WHEN** body_1 嘗試 `move(delta=(1,0))` 且 delta 後的目標座標為 `(4, 5)`
- **THEN** rules-engine 拒絕該移動（視為碰撞）
- **AND** body_1 停留原地

#### Scenario: Corpse 不再出現在可 dispatch 的 pov 清單
- **GIVEN** body_4 `status="corpse"`
- **WHEN** scenario-runner 進入下一 tick
- **THEN** tick 迴圈 MUST 略過為 pov_4 請求 action 的步驟

#### Scenario: Corpse 狀態不可復活
- **WHEN** 任何元件嘗試將 `status` 從 `corpse` 改回 `alive`
- **THEN** system MUST raise `IllegalStateTransition`

### Requirement: 按鈕與戒指模型

The system SHALL 為每個 button 維持 `{id, position, lit}` 欄位；為戒指維持 `{position, touchable, owner}` 欄位；防護窗狀態 `shield_open` 為布林；`touchable` 的轉換由 rules-engine 負責（見 rules-engine spec）。

#### Scenario: 正確按壓後燈亮
- **GIVEN** body_2 位置與 button_2 位置相鄰或重合且按鈕 `lit=false`
- **WHEN** rules-engine 處理完 `press(body_id=2, button_id=2)` 成功
- **THEN** `button_2.lit=true`
- **AND** 產生 `ButtonLitEvent(button_id=2)`

#### Scenario: 6 燈齊亮後戒指變可觸碰
- **GIVEN** 6 個按鈕皆 `lit=true`
- **WHEN** rules-engine 在 tick 結束後進行 post-tick 判定
- **THEN** `ring.touchable` MUST 變為 `true`
- **AND** `shield_open` MUST 變為 `true`
- **AND** 產生 `ShieldOpenEvent`

#### Scenario: 燈未齊時戒指保持不可觸碰
- **GIVEN** 僅 5 盞燈為 `lit=true`（例如 button_3 的 body 已死）
- **WHEN** tick 推進至 `max_ticks`
- **THEN** `ring.touchable` MUST 保持 `false`
- **AND** `shield_open` MUST 保持 `false`

### Requirement: Tick 時間制

The system SHALL 以 tick 為世界時間單位；`tick` 為非負整數、初始為 0；scenario-runner 每個迴圈結束後呼叫 `WorldEngine.advance_tick()` 使 `tick` +1；當 `tick >= max_ticks` 且尚未分出勝負時，system MUST 標記為 FAIL（`cause=timeout`）。

#### Scenario: Tick 單調遞增
- **GIVEN** 當前 `tick=5`
- **WHEN** scenario-runner 呼叫 `advance_tick()`
- **THEN** `tick` 變為 `6`
- **AND** 任何 tick < 5 的 event MUST NOT 在 tick 6 之後被新增（單調性）

#### Scenario: Timeout 觸發敗局
- **GIVEN** `max_ticks=50` 且當前 `tick=50`
- **WHEN** scenario-runner 進行終局判定
- **THEN** `outcome.result="FAIL"`
- **AND** `outcome.cause="timeout"`
- **AND** 產生 `OutcomeEvent(result="FAIL", cause="timeout")`

