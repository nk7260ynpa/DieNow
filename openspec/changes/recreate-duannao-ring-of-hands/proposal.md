# Proposal: 以多時空階段自我模型重現「攜手之戒」關卡

## Why

漫畫《端腦》（作者：壁水羽）中的「攜手之戒」關卡具備極高的邏輯密度：6 名玩家看似獨立、實為同一主角夏馳在時空切片下的 6 個身體階段，並且「第一個拿戒指者得到」的規則與「除了六號之外任意一號拿戒指都會造成時間線錯亂」同時存在。一般以多代理或多玩家實作會立刻碰到「多個自由意志同時活動 → 因果閉環破裂」的難題。我們需要一套**可實際執行、且保證邏輯自洽**的系統，能讓一個 Project Agent 以玩家身份實際體驗此關卡，同時不讓系統內部出現時間悖論。本提案取代先前走偏方向的舊 change（已刪除），重新以探索階段確認的「多時空階段自我 × 單 Epoch × 預生成閉環劇本」架構為單一事實來源。

## What Changes

- **新增** 以 Python 3.11+、Pydantic v2、Anthropic SDK、pytest、structlog 構築的模擬系統，目標為可在 CLI 下完整跑完一次「攜手之戒」關卡並留下可重放的 event log。
- **新增** 形式化的時空切片模型：1 個 Project Agent、6 個 pov（sub-agent contexts）、6 個 body；pov_1 新生、pov_2~5 攜帶遞迴前世記憶、pov_6 攜帶 5 層遞迴前世記憶並作為**唯一自由主體**（真 Agent）。
- **新增** 預生成閉環劇本機制（script_generator）：關卡啟動前生成 `script_1~script_5`，每份劇本嚴格包含上一份劇本描述到的共有事件，並通過時間一致性驗證（failed → retry K 次 → issues.md）。
- **新增** 關卡執行期的角色分工：pov_1~5 按 immutable 劇本演出（LLM 僅填即時對話細節，主幹鎖死），pov_6 由 Project Agent（Anthropic SDK + prompt caching）自由決策。
- **新增** 8 條系統 Invariants（INV-1 ~ INV-8）作為 rules-engine 的硬約束，覆蓋唯一事實來源、劇本不可變、因果閉環、pov_6 自由邊界、觀察對稱性、event log 可重放、單一自由主體、無時間悖論。
- **新增** 單一 epoch 語義：不存在 epoch 推進、不存在時間線重置、死亡不接力記憶（死亡即空殼）。
- **新增** 觀察對稱性：所有 pov 看得見他人號碼牌／物理環境／公開對話；看不見自己號碼牌、關卡規則、通關目標。
- **新增** CLI 入口與 Docker 化執行（`docker/`、`logs/`、`run.sh`）、`.env.example`（`ANTHROPIC_API_KEY`）、`README.md`（專案架構）。
- **新增** pytest 測試套件，含 `FakeAnthropicClient` 替身、劇本閉環驗證的單元測試、完整關卡的整合測試。

## Capabilities

### New Capabilities

- `world-model`：房間座標空間、6 個 body（位置 / HP / 號碼牌 / 面具 / 存活狀態）、6 個按鈕（位置 / 對應編號 / 亮燈狀態）、戒指（位置 / 可觸碰狀態 / 防護窗）、tick 時間制；所有狀態僅由 world-model 持有並變更。
- `rules-engine`：按鈕按壓判定（對 / 錯 / 致死）、6 燈齊亮後防護窗開啟、戒指觸碰判定（是否為 body_6、是否造成時間線錯亂）、死亡判定、勝負判定、8 條 Invariants 執行時檢查。
- `script-generator`：以 LLM 依序生成 `script_1~script_5`，每份劇本含 persona / events / prior_life / death_cause；生成後立即進行時間一致性驗證；驗證失敗時在 K 次（可配置，預設 3）內自動重試；超過上限則寫入 `issues.md` 並中止關卡啟動。
- `pov-manager`：管理 6 個 pov contexts 的生命週期；為 pov_1~5 提供劇本執行器（按時序觸發 events）；為 pov_6 提供 observation 產生器與 action 分派器；處理即時對話請求（pov_1~5 受到 pov_6 對話時的人格內回應）。
- `project-agent`：pov_6 的 LLM 實作；以 Anthropic SDK（`anthropic` Python SDK）搭配 prompt caching 呼叫 Claude 模型；system prompt 包含 persona + 規則約束 + 5 層遞迴前世記憶；user prompt 每 tick 為當前 observation；產出結構化 action。
- `scenario-runner`：CLI demo 編排；負責「劇本生成 → 關卡啟動 → tick 迴圈（pov_1~5 劇本執行 + pov_6 LLM 決策 + world-model 變更 + rules-engine 驗證）→ 終局判定」；append-only event log；log 輸出至 `logs/` 並以 structlog 記錄。

### Modified Capabilities

<!-- 無既有 spec 需修改；此為新專案首個 change。 -->

## Impact

- **程式碼**：建立全新 Python 套件（建議 `src/ring_of_hands/` 或同等路徑），包含上述 6 個 capability 對應的模組與測試；具體檔案結構於 `design.md` 定稿。
- **相依套件**：`anthropic`、`pydantic>=2`、`pytest`、`pytest-asyncio`（若採 async LLM call）、`structlog`、`pyyaml`（人格設定檔）、`python-dotenv`（讀 `.env`）。
- **外部服務**：依賴 Anthropic API（Claude 模型）；測試環境以 `FakeAnthropicClient` 替身離線執行；需 `ANTHROPIC_API_KEY` 才能實際執行 LLM。
- **基礎設施**：新增 `docker/Dockerfile`、`docker/build.sh`、`docker/docker-compose.yaml`（若適用）、`logs/.gitkeep`、`run.sh`、`.env.example`、`.gitignore`（`logs/*`、`.env`、`__pycache__/` 等）、`pyproject.toml`、`README.md`。
- **效能與成本**：劇本生成階段至少 5 次 LLM 呼叫（每 script 一次）加上驗證失敗的重試；關卡執行期每 tick 至少 1 次 pov_6 的 LLM 呼叫，以及 pov_1~5 被主動對話時的即時回應呼叫；prompt caching 預期可大幅降低 pov_6 重複送出前世記憶的成本，具體 caching 邊界於 `design.md` 定義。
- **風險集中**：劇本閉環驗證的通過率、pov_6 LLM 推理品質、LLM 回傳非結構化 action 的解析韌性；詳見 `design.md` Risks 節。
- **不影響的範圍**：本 change 不提供 GUI、不接入真實使用者多人對戰、不支援多 epoch，也不涵蓋原作其他關卡。
