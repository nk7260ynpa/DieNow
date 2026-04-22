# Design: 攜手之戒關卡模擬系統

> 本文件定義「如何實作」提案中的各項能力；需求本身（WHAT）記載於 `specs/<capability>/spec.md`，動機（WHY）記載於 `proposal.md`。所有設計均以 `notes/time-structure.md` 為唯一源頭，且遵循全域 `CLAUDE.md` 規範。

## Context

- **源頭文件**：`/Users/chen/AI/DieNow/notes/time-structure.md`（使用者已確認最終定案版本）。
- **漫畫背景**：作者壁水羽的《端腦》「攜手之戒」關卡；6 名玩家、面具變聲、特殊眼鏡使玩家看不見自己號碼牌；按對按鈕亮燈、錯按致死、6 燈齊亮後防護窗打開；「第一個觸碰戒指者得到」與「除了六號之外任意一號觸碰都會導致時間線錯亂」兩條規則並存；原作百度百科揭示「六個人都為主角一人」。
- **架構定位**：1 個 Project Agent（單一 LLM persona「被困的玩家」）透過時空切片產生 6 個 pov（sub-agent contexts），各佔一 body；pov_1 新生、pov_2~5 各自持有層層遞迴的前世記憶（pov_n 的前世 = pov_{n-1} 完整人生）、pov_6 持有 5 層遞迴記憶 ≡ 漫畫主角歷盡 5 次輪迴的終局狀態；整關為**單 epoch**，**死亡不接力記憶**，**只有 pov_6 擁有自由意志**。
- **技術棧**：Python 3.11+、Pydantic v2（`frozen=True` 表達 immutable INV）、Anthropic Python SDK（`anthropic`）＋ prompt caching、pytest＋pytest-asyncio、structlog、PyYAML；整體跑在 Docker（`docker/`、`logs/`、`run.sh`）。
- **邊界假設**：物理空間採 2D 格子（grid）以降低實作複雜度；CLI 介面；無 GUI；離線測試以 `FakeAnthropicClient` 替身滿足 pytest 不依賴網路。
- **利害關係人**：主要為 Coordinator（規劃）／Specialist（實作）／Verifier（驗證）三個 subagent，以及最終的人類使用者（啟動關卡、讀 log、驗收結果）。

## Goals / Non-Goals

**Goals:**

- 以可執行程式重現「攜手之戒」關卡的時空結構、觀察對稱性、閉環規則，並具備 Pydantic 型別嚴格約束。
- 形式化 8 條 Invariants（INV-1 ~ INV-8）為 rules-engine 的執行期檢查，任何違反皆以結構化錯誤拋出並寫入 event log。
- 讓 pov_6（真 Agent）透過 Anthropic SDK＋prompt caching 完成推理任務：認知自身號碼、認知拿戒指規則、時機拿捏。
- 透過預生成閉環劇本保證 pov_1~5 的行為與因果一致，絕不出現時間悖論。
- 完整 Docker 化、log 結構化、event log 可重放。
- 提供可獨立單元測試的模組介面，並以 `FakeAnthropicClient` 支援離線測試。

**Non-Goals:**

- 不實作 GUI、可視化回放器（僅 JSONL event log 與 structlog 輸出即可）。
- 不支援多 epoch 或跨關卡連播（本 change 專注單關卡單次執行）。
- 不接入真實多人玩家（所有 pov 均為同一 Project Agent 的時空切片）。
- 不處理漫畫其他關卡或宇宙觀擴展。
- 不優化 LLM 推理品質至完美通關（可通關是期望但非硬性 KPI；重點在「系統邏輯自洽、可重放」）。

## Decisions

### D-1：採用「形式化 Ω：多時空階段自我 × 單 Epoch」模型（路線 A'）

- **決定**：整關為**單 epoch**；不存在時間線重置、不存在 epoch 推進；pov 死亡 ≠ 記憶接力（因為記憶已以預生成前世記憶的方式事先注入）。
- **理由**：這是筆記中使用者逐項確認的方向。雙 epoch / 記憶接力的先前版本會產生「pov_1 死後 pov_2 重啟時間線」的實作爆炸，且無法對應漫畫「已完成 5 次輪迴的身份」。單 epoch 模型讓關卡執行邏輯大幅簡化。
- **替代方案**：
  - *多 epoch × 靈魂接力*：每次 pov 死亡就重啟時間線、把記憶傳給下一 body；實作成本高，且與漫畫揭露的「六個人都為主角一人」終局感相悖。**否決**。
  - *即時生成前世記憶*：pov_n 死亡時才動態合成給 pov_{n+1} 的記憶；會在關卡中引入新的 LLM 依賴與時間悖論修復成本。**否決**。

### D-2：單一 Project Agent，以 pov_6 為唯一自由主體

- **決定**：整個系統只有 1 個 LLM-backed persona「被困的玩家」。關卡啟動前由此 Agent 產生 `script_1~script_5`；關卡執行期此 Agent 僅以 pov_6 身份發出自由意志的 action；pov_1~5 不再接受 LLM 自由決策，僅執行 immutable 劇本（含 LLM 補完之即時對話回應，但主幹鎖死）。
- **理由**：只有 pov_6 的行為不影響任何 pov 的前世記憶（沒有 pov_7），因此 pov_6 的自由意志不會破壞因果閉環（INV-3、INV-4、INV-7）。若讓 pov_1~5 同樣自由，則關卡執行時任何 pov_k（k<6）的舉動都必須同步修改 pov_{k+1..6} 的前世記憶，瞬間退化為 NP-hard 的一致性維護。
- **替代方案**：
  - *6 個完全自由的 LLM 玩家*：如上，一致性不可解。**否決**。
  - *6 個全劇本化*：玩家退居旁觀者，失去「讓 Agent 實際體驗關卡」的原始需求。**否決**。

### D-3：預生成閉環劇本（Pre-generated Closed-loop Scripts）

- **決定**：關卡啟動前，script-generator 依序生成 `script_1~script_5`，每份劇本產出後立即進行「時間一致性驗證」，不通過即 retry（預設上限 3 次，可由 `ScriptConfig.max_retries` 調整），超過上限寫入 `issues.md` 並中止。
- **理由**：此為維持 INV-3（因果閉環）的唯一實務可行手段；人類確認過此路徑，可避免關卡執行期即時修復悖論。
- **劇本生成演算法（順序）**：
  1. 以 `pov_1` 的 persona + 世界環境描述（房間尺寸、6 body 起始位置、按鈕位置、戒指位置、面具／眼鏡設定）→ LLM 產出 `script_1`。
  2. 以 `pov_2` 的 persona + `script_1`（作為 pov_2 的 `prior_life`）+ 世界環境 → LLM 產出 `script_2`；自動驗證「script_2 中任何涉及 pov_1 的事件（`actor=pov_1` 或 `targets 含 pov_1`）必須在 `script_1` 中以相同 `t`、相同 action_type、相同 payload 出現」。
  3. 以同樣方式產出 `script_3~script_5`，每份驗證「涉及 pov_{n-1} 的事件一致性」。
  4. 驗證不通過 → 把失敗 diff 寫入下一次 prompt 的修正提示、重跑；達 `max_retries` 仍失敗則中止。
- **劇本格式（Pydantic v2 model）**：
  - `Script`：`pov_id: int`、`persona: Persona`、`prior_life: Script | None`、`events: list[ScriptEvent]`、`death_cause: DeathCause`、`created_at`、`llm_meta`（請求／回應元資料）。
  - `ScriptEvent`：`t: int`（tick）、`actor: PovId`、`action_type: Literal["move","speak","press","touch_ring","observe","wait","die"]`、`payload: dict[str, Any]`、`targets: list[PovId]`。
  - Script 與 ScriptEvent 皆以 `model_config = ConfigDict(frozen=True)` 表達 immutable（INV-2）。
- **替代方案**：
  - *即時補償*：關卡執行時發現悖論才修；邊界條件爆炸。**否決**。
  - *靜態硬編碼劇本*：喪失「每次跑都有不同人格旅程」的彈性；未達需求。**否決**。

### D-4：pov_6 的 Prompt 結構與 Prompt Caching 邊界

- **決定**：pov_6 每 tick 呼叫 Claude Sonnet（預設 `claude-sonnet-4-7` 或環境變數 `PROJECT_AGENT_MODEL` 指定的值）的 `messages.create`，結構為：
  - **system messages**（依序，套用 prompt caching；最大化 cache hit）：
    1. 靜態 persona 與「被困的玩家」共通指令（可快取，`cache_control={"type":"ephemeral"}`）。
    2. 關卡通用規則陳述（「你不知道自己的號碼、不知道規則、不知道目標」等陳述，不含 spec 洩題）（可快取）。
    3. 5 層遞迴前世記憶（以壓縮 JSON 描述 `script_5` 及其 `prior_life` 鏈）（可快取；此為最大 context，caching 收益最高）。
  - **user messages**（每 tick 動態）：當前 observation（公開資訊）＋ 可用 action schema。
  - **回應**：要求 LLM 以結構化 JSON 回傳 action；解析失敗則降級為 `wait` 並記錄警告（不得崩潰）。
- **Caching 規則**：遵循 `claude-api` skill；每個可快取 block 加 `cache_control={"type":"ephemeral"}`，最多 4 個 cache block。實測 caching 命中率作為 log metric 輸出（key = `cache_read_input_tokens` / `cache_creation_input_tokens`）。
- **理由**：前世記憶龐大、每 tick 重複送出成本極高；prompt caching 正是解方。
- **替代方案**：
  - *每 tick 重發 full prompt*：成本爆炸。**否決**。
  - *向量檢索摘要前世記憶*：失去精確性、引入另一 stack。**否決**。

### D-5：World Engine 作為唯一事實來源

- **決定**：`WorldEngine` 類別持有所有世界狀態（`WorldState` Pydantic model，包含 tick、bodies、buttons、ring、lights、防護窗狀態、event log 引用）。所有 pov 只能透過 `WorldEngine.observe(pov_id) -> Observation` 讀取，與透過 `WorldEngine.dispatch(pov_id, action) -> DispatchResult` 提交動作。pov 不得直接改寫 state（INV-1）。
- **理由**：單一事實來源可完全支撐 event log 可重放（INV-6）；任何 state 變更都要先進 rules-engine 驗證。
- **替代方案**：
  - *分散式狀態*：pov 各自持有副本；同步災難。**否決**。

### D-6：Rules Engine 以 Pydantic 驗證 + 純函數執行

- **決定**：`RulesEngine` 為純函數集合；輸入 `(WorldState, Action) → (WorldState', list[Event])`。每項 action 都跑對應 rule；rule 失敗就 raise 結構化例外（`RuleViolation(inv_id, detail)`）並寫 event log。
- **主要規則**：
  - `press_button(body_id, button_id)`：若 `body_id == button_id` → 亮燈＋success event；否則 → body 死亡＋`death` event（`cause=press_wrong`）。
  - `touch_ring(body_id)`：前置條件「6 燈齊亮＋防護窗開」；若 `body_id == 6` → WIN；否則 → FAIL（`cause=ring_paradox`），body 死亡並立即結算敗局。
  - `move(body_id, delta)`：碰撞檢查（其他存活 body、按鈕區域、牆壁）；違規則不動＋警告 event。
  - `speak(body_id, msg, targets)`：寫入 event；若觸發 pov_1~5 的即時對話回應需求則向 pov-manager 發訊息。
  - `die(body_id, cause)`：body 變空殼，不再出現在 observation 的「可按按鈕」清單。
  - `tick_advance()`：tick 遞增；若 tick > `max_ticks` → FAIL（`cause=timeout`）。
- **INV 執行期檢查**：
  - INV-1：Dispatch 後比對 state 是否由其他路徑被改寫（unit test 覆蓋）。
  - INV-2：任何對 `Script` 的 mutation 嘗試必須 raise（Pydantic frozen 保障）。
  - INV-3：已在劇本生成階段驗證；執行期另做 sanity check（scripted action 與 event log 是否一致）。
  - INV-4：pov_6 的 action 不會觸發任何 script 修改；以型別與 dispatch 白名單保障。
  - INV-5：`observe(pov_id)` 絕不洩露 `pov_id` 自己的號碼、規則陳述、目標陳述。
  - INV-6：每個 event 都 append-only 寫入 `EventLog`（JSONL）。
  - INV-7：同一 tick 內任何 pov 僅接受一個 action；dispatch 對同一 pov 的重覆 action 會 raise。
  - INV-8：scripted pov 的 action 必須與當前 tick 的劇本一致，否則 raise `CausalViolation`。

### D-7：觀察對稱性與 Observation Schema

- **決定**：所有 pov 看到的 observation 結構一致：
  - 自己可見：`self_position`、`self_hp`、`self_prior_life_summary`（若有；壓縮摘要，不含自己號碼）、`self_visible_actions`、目前 tick、是否處於「防護窗已開」狀態。
  - 他人可見：每位其他存活 body 的 `position`、`number_tag`（號碼牌）、`mask_voice_id`（面具＋變聲識別，但匿名化）、最近 N 條公開對話。
  - **不可見**：自己號碼、關卡規則陳述、通關條件、其他 pov 的 prior_life、其他 pov 的 pending action。
- **死亡 body**：observation 中標為 `status="corpse"`，仍顯示號碼牌（屍體上的號碼牌可見）、仍佔空間。
- **理由**：對應筆記 Q4 的「自己號碼牌／規則／目標不可見」三連；也對應漫畫中眼鏡／面具的設定。

### D-8：Scenario Runner（CLI 與 Tick 迴圈）

- **決定**：`scenario_runner.run(config: ScenarioConfig)` 為主入口：
  1. 驗證配置（人格檔案、LLM 設定、max_ticks 等）。
  2. 呼叫 `script_generator.generate_all(config)` → 取得 `script_1~script_5`（含 retry）。
  3. 初始化 `WorldEngine`、`PovManager`、`ProjectAgent`。
  4. 主迴圈：`for tick in range(max_ticks):` → 依序呼叫 pov_1~5 的劇本執行器（受 `is_alive` 與「當前 tick 是否有該 pov 的 scripted event」保護），最後呼叫 pov_6 的 ProjectAgent 自由決策；每個 action 送 dispatch。
  5. 終局判定：WIN（body_6 拿到戒指）/ FAIL（非 body_6 拿到戒指 / timeout / 6 燈無法齊）。
  6. 輸出最終 event log 與 summary。
- **CLI**：`python -m ring_of_hands.cli run --config configs/default.yaml`（或等值腳本）。
- **Docker**：`run.sh` 啟動 container 執行上述 CLI；掛載 `logs/`；由 `docker-compose.yaml`（若存在）統一管理。
- **替代方案**：以事件驅動 async 模型（asyncio.Queue）；初版採同步 tick 迴圈更易於 debug 與 log 對齊。

### D-9：即時對話（pov_1~5 被 pov_6 搭話時）

- **決定**：劇本中僅鎖定主幹動作（move / press / touch_ring / die 等）；當 pov_6 對某 pov_k（k<6）使用 `speak` 動作，pov-manager 為該 pov_k 呼叫 LLM（同 Project Agent，但 persona 切換為 `Persona_k`；使用 pov_k 的 prior_life 作為 context）產生即時回應；此回應寫入 event log 但**不得修改已驗證的 script events**（若 LLM 回應內容與 script 衝突，dispatch 時由 rules-engine 拒絕並降級為「模糊回應」）。
- **理由**：保留擬真感，同時避免破壞因果閉環（INV-3、INV-8）。
- **風險**：即時對話成本；可配置 `enable_realtime_chat: bool` 關閉。

### D-10：Event Log 與 Structlog

- **決定**：`EventLog` 寫入 JSONL（每行一個 Pydantic `Event` 序列化）至 `logs/events_<timestamp>.jsonl`；並行以 structlog 輸出可讀日誌至 `logs/run_<timestamp>.log`。
- **欄位**：`tick`、`event_type`、`actor`、`payload`、`world_snapshot_hash`（可選，用於重放一致性校驗）。
- **重放**：提供 `scenario_runner.replay(event_log_path)`（本 change 僅保證資料結構支援；完整 replay CLI 可延後）。

### D-11：測試策略

- **單元測試**：
  - `test_world_model`：bodies、按鈕、戒指狀態轉移；碰撞檢查。
  - `test_rules_engine`：每條規則（按對／按錯、6 燈齊亮、戒指觸碰勝敗、timeout、死亡）；INV 違反時的 raise。
  - `test_script_generator`：以 `FakeAnthropicClient` 回傳固定 stub scripts，驗證閉環驗證器能抓 diff、retry 邏輯；驗證超過 retry 時寫 issues.md。
  - `test_pov_manager`：劇本執行器的 tick 對齊、即時對話路由。
  - `test_project_agent`：prompt 組裝、prompt caching 參數存在、結構化 action 解析、解析失敗降級為 `wait`。
  - `test_scenario_runner`：整段 happy path（以 FakeAnthropicClient 提供一套事先備好的 `script_1~5` + pov_6 action 序列，驗證 WIN 路徑）。
- **整合測試**：
  - `test_full_run_with_fake_llm`：從 CLI 呼叫 `run` 以 FakeAnthropicClient 跑完整關卡，assert event log 結構正確、最終 outcome 為 WIN。
  - `test_timeout_path`：pov_6 一直 `wait`，驗證 timeout FAIL。
  - `test_wrong_ring`：以 stub 方式強制非 body_6 觸碰戒指，驗證 FAIL 判定正確。
- **執行環境**：一律於 Docker 內 `pytest`（`docker compose run --rm app pytest` 或 `./run.sh pytest`）。

### D-12：設定檔與環境變數

- `configs/default.yaml`：房間尺寸、按鈕／body 起始位置、戒指位置、max_ticks、max_retries、model name、是否啟用即時對話。
- `configs/personas.yaml`：6 份 persona 模板（可由 script-generator 解讀）。
- `.env.example`：`ANTHROPIC_API_KEY=`、`PROJECT_AGENT_MODEL=claude-sonnet-4-7`、`LOG_LEVEL=INFO`。
- `.gitignore`：`logs/*`（保留 `logs/.gitkeep`）、`.env`、`__pycache__/`、`.pytest_cache/`、`*.pyc`、`dist/`、`build/`。

## Risks / Trade-offs

- [R-1 劇本閉環驗證的通過率] → **Mitigation**：retry 機制＋下一次 prompt 注入 diff 提示；若仍失敗則停機並寫 `issues.md`；上限 `max_retries` 預設 3，可由 config 調高。
- [R-2 LLM 回應不結構化] → **Mitigation**：定義嚴格 JSON schema；解析失敗降級為 `wait` 並在 event log 記錄 `parse_error`；Specialist 實作時可考慮改用 Anthropic tool use / structured output。
- [R-3 Prompt caching 未命中] → **Mitigation**：按 `claude-api` skill 準則設置 cache_control；log metrics 觀察；若命中率低於閾值（例如 < 60%）則在 `issues.md` 提出調整計畫。
- [R-4 即時對話破壞因果] → **Mitigation**：`enable_realtime_chat` 預設開啟，但 dispatch 時對即時對話內容再次驗證不得牴觸 script events；違規時降級為模糊回應。
- [R-5 成本] → **Mitigation**：以 `FakeAnthropicClient` 測試；實跑時於 README 揭露預估成本；提供 `dry_run` 參數跳過 LLM 呼叫（回傳預錄 action）。
- [R-6 pov_6 無法推理出正確行為] → **Mitigation**：本 change 不以「實機 LLM 必勝」為 KPI；系統保證只要 pov_6 輸出合法 action，流程皆可推進；最差情況為 timeout FAIL，仍是合法終局。
- [R-7 Python 版本／SDK 相容性] → **Mitigation**：`pyproject.toml` 鎖定 `python>=3.11`、`anthropic>=0.39.0`、`pydantic>=2.7`；Docker image 指定 `python:3.11-slim`。
- [R-8 開發中修改 CLAUDE.md 的需求被遺忘] → **Mitigation**：遵守全域規範，Specialist 若需改 `CLAUDE.md` 必須寫入 `issues.md`；Coordinator 在後續 `tasks.md` 調整中處理。

## Migration Plan

- **初次部署**：執行 `./docker/build.sh` 建 image → 設定 `.env` → `./run.sh` 執行 demo；pytest 由 `./run.sh pytest` 觸發。
- **回滾策略**：本 change 為新建專案第一個實作 change，無前版可回滾；若實作過程發現 spec 有重大問題，Coordinator 依全域規範重啟 `/opsx:propose` 流程，並先於 `issues.md` 記錄理由。

## Open Questions

1. 房間尺寸預設採多少 grid？暫定 `10 x 10`；body / button / ring 具體座標於 `configs/default.yaml` 定稿，Specialist 實作時可微調並回報。
2. Persona 內容是否要人工撰寫範例、或完全由 LLM 生成？初版提供 3 份人工模板 + 隨機挑選；後續可擴充。
3. 即時對話開關預設 `true` 或 `false`？暫定 `true`，便於觀察關卡張力；若成本過高再改 default。
4. Event log 的 `world_snapshot_hash` 是否本次實作？初版僅保留欄位，計算邏輯列為 Optional，由 Specialist 視 effort 決定是否納入。
5. 若 LLM 回應時間過長是否需要 timeout？建議 30s per call，可由 config 覆寫；Specialist 實作時納入。
