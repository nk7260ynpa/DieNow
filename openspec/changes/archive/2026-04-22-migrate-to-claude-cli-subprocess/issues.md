# Issues

## [使用者驗收] [2026-04-18T22:45:00+08:00] [嚴重度: HIGH] 真跑時 Claude CLI 在容器內 401 認證失敗，Docker 化認證方案需重新設計

### 問題

使用者於主機執行 `./run.sh`（真跑、非 dry-run）驗收時，scenario runner 在 `script_1` 生成階段連續 3 次失敗，錯誤碼 `cli_nonzero_exit:1`，最終 scenario FAIL（`cause=script_generation_failed`）。Dry-run 仍 WIN（因走 FakeLLMClient）。

主對話直接在容器內手動呼叫 `claude -p "..." --output-format stream-json --verbose` 抓根因，確認三個相關缺陷：

1. **缺少必要 flag**：`claude -p` 搭配 `--output-format stream-json` 時 CLI 強制要求 `--verbose`；`claude_cli_client.py` 未帶此 flag，導致 CLI 直接非零退出、連 result event 都發不出來（這就是 `cli_nonzero_exit:1` 而非具體 error reason 的主因）。
2. **Mount 不完整**：Claude Code CLI 的主 config 檔案是 `~/.claude.json`（使用者 home 根目錄的檔案，主機上 115 KB），而非 `~/.claude/` 目錄；但 `docker/docker-compose.yaml` 只 mount 了 `~/.claude/` 目錄，容器啟動時 CLI 報 `Claude configuration file not found at: /home/app/.claude.json`。
3. **Keychain 無法跨容器**（核心 design 缺陷）：即使加上 `.claude.json` mount + `--verbose`，CLI 仍回應 `Failed to authenticate. API Error: 401 "Invalid authentication credentials"`。macOS 上 Claude Code 的 OAuth token 實際儲存於 **macOS Keychain**，`.claude.json` 只含 metadata；Linux 容器根本沒有 macOS Keychain 可讀。這個限制在 design D-5/D-6 未被預見。

### 影響

- 本 change 的核心動機（走 Max 訂閱免 API 費用）真跑路徑**完全無法運作**
- `verify` 時主對話沒發現此問題：因 verifier 只跑 dry-run（走 FakeLLMClient）；真跑驗證落在使用者人工驗收階段才暴露
- design.md D-5（`.claude.json` mount 路徑）與 D-6（volume mount 即可承繼 session）的描述與實際 macOS 行為不符
- `scenario-runner` spec 的「Docker 化執行環境 / 容器內 claude 讀主機 OAuth」Scenario 在當前實作下只是**編譯通過、實際無法執行**

### 建議修復方向

Claude Code CLI v2.1.114 有官方指令 `claude setup-token`（`claude --help` 可見），描述「Set up a long-lived authentication token (requires Claude subscription)」。此命令產生可跨機器（含容器）使用的 long-lived OAuth token，搭配環境變數 `CLAUDE_CODE_OAUTH_TOKEN` 注入即可認證，不再依賴 Keychain。

建議修改清單（Specialist 自行決定具體檔案分工，此為方向建議）：

1. **`src/ring_of_hands/llm/claude_cli_client.py`**
   - 呼叫 `claude` 時固定加上 `--verbose`（與 `--output-format stream-json` 搭配）
   - NDJSON 解析器要能處理 `--verbose` 多增的診斷事件（多半仍為 JSON 行，只是量增加；只取 `type=result` 即可）

2. **`.env.example`**
   - 新增 `CLAUDE_CODE_OAUTH_TOKEN=`（空值，附註說明以 `claude setup-token` 取得）

3. **`docker/docker-compose.yaml`**
   - 透過 `environment:` 或 `env_file: .env` 傳遞 `CLAUDE_CODE_OAUTH_TOKEN` 進容器
   - 移除 `~/.claude/` mount（不再必要；改以 env 為主要認證）
   - 若保留 `~/.claude/` mount 作為 fallback，同時加上 `~/.claude.json`，並在註解明示「token env 為主、mount 為備援」

4. **`src/ring_of_hands/scenario_runner/config_loader.py`**
   - 啟動檢查改為：非 dry-run 時必須 `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY` 其一存在（可以文件推薦前者）
   - 移除 `~/.claude/` 可讀檢查（已不再強制）

5. **`run.sh`**
   - 非 dry-run 時改為檢查 `.env` 是否包含有值的 `CLAUDE_CODE_OAUTH_TOKEN`
   - 移除主機端 `claude` 可執行性檢查與 `~/.claude/` 存在性檢查（容器內已自帶 CLI，且認證改走 env）

6. **`docker/Dockerfile`**
   - `@anthropic-ai/claude-code` 安裝保留；無須改動

7. **`README.md`**
   - 前置需求：改為「跑 `claude setup-token` → 把 token 貼入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`」
   - 移除「mount `~/.claude/` 繼承 session」的段落
   - 故障排除：新增「401 authentication_error」案例

8. **測試**
   - `tests/scenario_runner/test_config_loader.py`：更新啟動檢查測試為 env 變數存在性
   - `tests/cli/test_cli.py`：`test_claude_cli_missing_non_dry_run_exits_nonzero` 與 `test_claude_home_missing_non_dry_run_exits_nonzero` 需改為 token 缺失的情境，或取消後補上 `test_oauth_token_missing_non_dry_run_exits_nonzero`
   - `tests/llm/test_claude_cli_client.py`：assertion 應驗證 args 包含 `--verbose`

9. **Spec 修訂**（若 Specialist 認為實作已不符現有 spec 文字）
   - 不得自行修改 `specs/scenario-runner/spec.md`；請寫 `issues.md` 追記，由 Coordinator 決定是否 spec 補丁
   - 合理情況：「Docker 化執行環境」Requirement 的幾個 Scenario 需替換（token env 取代 mount），這屬於 spec 層修訂，應走 Coordinator 路徑

### 驗證方式（Specialist 修復後人工驗收項）

1. 主機執行 `claude setup-token` 取得 token
2. 將 token 貼入 `.env`：`CLAUDE_CODE_OAUTH_TOKEN=<value>`
3. `./run.sh --dry-run` 仍 WIN（迴歸）
4. `./run.sh`（真跑）能完成 scenario（不論 WIN/FAIL，關鍵是**不可因認證 401 而失敗**）
5. 手動 `docker compose run --rm app claude -p "hi" --output-format stream-json --verbose` 應回傳非 401 的 `type=result` 事件

### 上游參考

- Claude Code CLI 2.1.114：`claude setup-token` 官方指令
- GitHub `anthropics/claude-code#43333`：`claude -p` 與 OAuth 計費行為
- `apiKeySource:"none"` 出現在容器內 init event 確認 CLI 未走 API key 路徑

---

## [Specialist] [2026-04-18T23:00:00+08:00] [嚴重度: MED] [狀態: RESOLVED @ 2026-04-21 by Coordinator] scenario-runner spec 的「Docker 化執行環境 / CLI 預啟動檢查」幾個 Scenario 已與實作脫節，請 Coordinator 評估是否 spec 補丁

### 實作現況（修復後）

1. **Scenario「`~/.claude/` 不存在時非零退出」(L34~L39)**：實作已**移除**該 Scenario 的 `~/.claude/` 檢查。現行非 dry-run 啟動檢查第 3 步改為驗證 `CLAUDE_CODE_OAUTH_TOKEN`（或 `ANTHROPIC_API_KEY`）env 是否設定，因 macOS Keychain token 無法跨容器。
2. **Scenario「run.sh 在 ~/.claude/ 缺失時阻擋」(L96~L100)**：`run.sh` 不再檢查 `~/.claude/`；改檢查 `.env` 檔案是否包含有值的 `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY`。
3. **Scenario「run.sh 在主機缺 claude 時先行阻擋」(L89~L94)**：`run.sh` 不再檢查主機 `claude` 可執行，因容器內已自帶 CLI（Dockerfile 安裝）、認證靠 env 注入。
4. **Scenario「容器內 claude 能讀到主機 OAuth session」(L102~L107)**：現行 compose 已移除 `~/.claude` mount；容器內的 `claude` 透過 env `CLAUDE_CODE_OAUTH_TOKEN` 承繼身份。這個 Scenario 的 WHEN/THEN 需要替換為「容器內 `claude` 以 env token 承繼身份」。
5. **Requirement「Docker 化執行環境」的 `.env.example` bullet（L80）**：新增 `CLAUDE_CODE_OAUTH_TOKEN=` 欄位；`CLAUDE_HOME` 標為向後相容。這只是 spec 補強說明，非行為變動。

### 建議處理

**不自行改 spec**（遵守 Specialist 邊界）；建議 Coordinator 於下一次 propose/continue 時，針對上述 Scenario 開 spec 補丁 change（或併入本 change 前 archive 做 inline 補丁）。補丁方向：

- 保留 Requirement 的架構；替換 4 個 Scenario 的 GIVEN/WHEN/THEN：
  - `~/.claude/ 不存在時非零退出` → `CLAUDE_CODE_OAUTH_TOKEN 缺失時非零退出`
  - `run.sh 在 ~/.claude/ 缺失時阻擋` → `run.sh 在 .env 缺 CLAUDE_CODE_OAUTH_TOKEN 時阻擋`
  - `run.sh 在主機缺 claude 時先行阻擋` → 刪除（或改為「容器內 claude 不可執行時阻擋」，但這屬 build-time 失敗，意義不大）
  - `容器內 claude 能讀到主機 OAuth session` → `容器內 claude 以 CLAUDE_CODE_OAUTH_TOKEN 承繼 Max 訂閱身份`（volume mount 改為 env_file 注入）

### 驗證實況

本次修復的所有測試 232 筆全部通過；spec 與實作的語意差異僅在上述 Scenario 文字層面，行為一致性由實作 + issues.md 追記維持。若 Verifier 因 spec 文字與實作有差異而 FAIL，請參考本條目；不應要求 Specialist 回到 `~/.claude/ mount` 方案（已證實不可行）。

---

## [Coordinator] [2026-04-21T10:30:00+08:00] [嚴重度: LOW] scenario-runner spec 補丁完成，同步至 `CLAUDE_CODE_OAUTH_TOKEN` env 認證方案

### 摘要

依 Specialist MED 條目建議，對 `specs/scenario-runner/spec.md` 進行文字層補丁，使 spec 與修復後的實作（`CLAUDE_CODE_OAUTH_TOKEN` env 注入方案）一致。**未變動任何實作程式碼、未修改 `tasks.md`／`proposal.md`／`design.md`**。

### 實際修改清單

1. **Requirement「CLI 入口與設定載入」描述**：啟動檢查第 3 步由「`CLAUDE_HOME` 目錄可讀」改為「`CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY` env 其一存在」；`.env` 讀取變數清單補上 token 欄位；錯誤訊息提示改為 `claude setup-token`。
2. **Scenario「預設設定啟動成功」**：前置條件由「`~/.claude/` 目錄存在」改為「`CLAUDE_CODE_OAUTH_TOKEN` 非空」。
3. **Scenario「`~/.claude/` 不存在時非零退出」→「`CLAUDE_CODE_OAUTH_TOKEN` 缺失時非零退出」**：GIVEN/WHEN/THEN 全面改寫為 env 變數缺失情境；stderr 建議訊息改為 `claude setup-token` 流程。
4. **Scenario「dry-run 不要求 claude CLI 與 ~/.claude/」→「dry-run 不要求 claude CLI 與 OAuth token」**：前置條件改為 token env 未設定亦可通過。
5. **Requirement「Docker 化執行環境」描述**：`docker-compose.yaml` bullet 由「mount `${HOME}/.claude`」改為「`env_file: ../.env` 注入 `CLAUDE_CODE_OAUTH_TOKEN`」，並明示「MUST NOT 掛載 `${HOME}/.claude`／`${HOME}/.claude.json`」（macOS Keychain 跨容器限制）；`run.sh` bullet 改為檢查 `.env` 中的 token 存在性；`.env.example` bullet 新增 `CLAUDE_CODE_OAUTH_TOKEN=` 欄位說明並將 `CLAUDE_HOME` 標為向後相容。
6. **Scenario「run.sh 啟動 container 並執行 CLI」**：前置條件由「主機 `claude` 可執行且 `~/.claude/` 存在」改為「`.env` 含有非空 `CLAUDE_CODE_OAUTH_TOKEN`（或 dry-run）」。
7. **Scenario「run.sh 在主機缺 claude 時先行阻擋」**：**刪除**（容器內自帶 CLI，主機檢查已失去意義）。
8. **Scenario「run.sh 在 ~/.claude/ 缺失時阻擋」→「run.sh 在 .env 缺 `CLAUDE_CODE_OAUTH_TOKEN` 時阻擋」**：改為檢查 `.env` 檔中 token 欄位。
9. **Scenario「容器內 claude 能讀到主機 OAuth session」→「容器內 claude 以 `CLAUDE_CODE_OAUTH_TOKEN` 承繼 Max 訂閱身份」**：GIVEN/WHEN/THEN 全面改寫為 env_file 注入路徑；THEN 補上 `--verbose` 旗標與「非 401」的實測條件。
10. **Requirement「README 記載架構」描述與兩個相關 Scenario**：`claude login` 全面改為 `claude setup-token`；`~/.claude/ not found` 故障排除改為 `CLAUDE_CODE_OAUTH_TOKEN missing`；README 前置章節順序改為「安裝 CLI → setup-token → 寫 `.env`」。

### 影響範圍

- 僅修改 `specs/scenario-runner/spec.md`。
- 未動 `proposal.md`（動機無變）、`design.md`（D-5/D-6 的歷史設計意圖保留作為 context；實際實作已透過本 change 諸多 commits 演進到 env token 方案）、`tasks.md`（所有 task 已完成）。
- 本補丁為 **文字層補丁**，不要求 Specialist 重新 apply；但 Verifier 下一次 `/opsx:verify` 應能以此 spec 作為 baseline 無縫通過。

### 後續追蹤

- 真跑人工驗收（Pending A）仍待使用者完成。
- `design.md` 的 D-5/D-6 與現實不符之處，若未來做更嚴謹的 design 同步，可另開補丁 change（或於 archive 前於 design.md 頂端 append 一段「Amendment 2026-04-18」註記）。本次不動 design.md 以控制 scope。

---

## [Coordinator] [2026-04-21T14:30:00+08:00] [嚴重度: LOW] project-agent 與 script-generator spec 第二輪補丁 + Dockerfile 註解順手更新

### 摘要

依 Verifier 第 3/4 次 PASS with observation 所列殘留漂移，對 `specs/project-agent/spec.md` 與 `specs/script-generator/spec.md` 進行文字層補丁，使其與已修復實作（`CLAUDE_CODE_OAUTH_TOKEN` env 方案、`config_loader._validate_claude_cli_environment` 預啟動檢查、`ClaudeCLIClient.__init__` 不重複檢查環境）一致；並順手更新 `docker/Dockerfile` 兩處過時註解。未變動任何實作程式邏輯、未修改 `tasks.md`／`proposal.md`／`design.md`。

### 實際修改清單

1. **`specs/project-agent/spec.md`** — Scenario「正常透過 Claude CLI 呼叫」：GIVEN 由「主機已執行 `claude login` 且 `~/.claude/` 存在」改為「`.env` 含有非空 `CLAUDE_CODE_OAUTH_TOKEN`（或 `ANTHROPIC_API_KEY`）且已注入容器 environment」。
2. **`specs/project-agent/spec.md`** — Scenario「`~/.claude/` 不存在時啟動失敗」：**改寫**為「`ClaudeCLIClient` 不重複做認證環境檢查」。理由（選擇這個方案的原因）：實作已將認證檢查職責遷至 `config_loader._validate_claude_cli_environment`；單純刪除 Scenario 會失去對「project-agent 層不重複檢查」這個正向契約的描述；改寫為正向契約能保留職責邊界描述並明示 token 缺失時的 Fail 責任歸屬於 scenario-runner spec，避免 spec 漏洞。`claude_home` kwarg 的 deprecated 狀態亦在此 Scenario 明示。
3. **`specs/script-generator/spec.md`** — Scenario「正式執行時使用 ClaudeCLIClient」：GIVEN 由「主機已執行 `claude login` 且 `~/.claude/` 存在」改為 `env_file` 注入 token 的情境；THEN 補上 `--verbose` 旗標（與 scenario-runner spec 一致，呼應 `-p + stream-json` 強制要求）。
4. **`specs/script-generator/spec.md`** — Scenario「正式執行時 claude CLI 未安裝則啟動失敗」的 stderr 建議訊息：由「提示安裝 CLI 與執行 `claude login`」改為「提示安裝 CLI（`curl -fsSL https://claude.ai/install.sh | bash` 或 PATH 檢查）並執行 `claude setup-token` 後寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`」，用詞對齊 `config_loader._validate_claude_cli_environment` 的實際錯誤訊息（L198-202 / L227-230）。
5. **`docker/Dockerfile`** — L2-5 header comment：由「容器內的 claude 會讀取主機 `~/.claude`」改為「容器內的 claude 以 `CLAUDE_CODE_OAUTH_TOKEN` env 承繼身份；不再 bind mount `~/.claude`」，並補充 macOS Keychain 限制註記。
6. **`docker/Dockerfile`** — L71 附近 `mkdir -p /home/app/.claude` 前註解：由「由 docker-compose bind mount 掛入主機 ~/.claude」改為「認證走 env；保留空目錄僅為 CLI 可能寫入 cache/log 之便」。空目錄本身保留（無害）。

### Dockerfile 動作的權限判斷

純註解行不涉及 Python/shell 實作邏輯、不影響 runtime 行為、不影響測試，視為文件層補丁，Coordinator 可觸及；未動 `RUN`／`COPY`／`CMD` 等任何會影響 image build 結果的指令（`mkdir -p /home/app/.claude` 維持原狀）。若後續 Verifier 仍認為此處應由 Specialist 處理，可以 reverted 並改由 Specialist 接手；但目前邊界判斷傾向這是最輕量、最安全的補丁。

### 影響範圍

- 文件層補丁，僅修改 spec（2 檔）+ Dockerfile 註解（2 處）。
- 未變動任何 Python／shell 實作邏輯，不需要 Specialist 重新 apply。
- 預期 Verifier 第 4/4 次執行可以乾淨 PASS（殘留漂移已全部收斂）。

### 後續追蹤

- 真跑人工驗收（Pending A）仍由使用者端完成。
- 若 Verifier 第 4 次仍 FAIL，依 CLAUDE.md 規範停止自動迴圈並交人類。

---

## [使用者驗收] [2026-04-22T00:50:00+08:00] [嚴重度: INFO] 真跑驗收 PASS（認證機制通過；但發現 3 個非本 change 範圍內的新問題）

### 驗收流程

1. 主機執行 `claude setup-token` 取得 long-lived OAuth token
2. 貼入 `/Users/chen/AI/DieNow/.env` 的 `CLAUDE_CODE_OAUTH_TOKEN=`
3. `./run.sh --dry-run` → WIN（迴歸通過）
4. `./run.sh`（真跑）→ 行為如下記錄

### 認證機制驗收結果: ✅ PASS

- 容器內 CLI 透過 `CLAUDE_CODE_OAUTH_TOKEN` env 成功認證（`apiKeySource:"none"`、`is_error:false`）
- **不再出現 `401 authentication_error`**（本 change 核心修復目標達成）
- pov_1 劇本成功生成（耗時 ~63 秒）

按進度筆記 Pending A 的 PASS 判定：「不可因 `401 authentication_error` 失敗；outcome 為 WIN 或合理 FAIL 均算通過」——符合。

### 本次真跑 outcome: FAIL（合理 FAIL，非認證問題）

- `outcome.result="FAIL"`, `cause="script_generation_failed"`
- 根因：script_2 在 3 次 retry 中出現 2 次 timeout + 1 次閉環驗證失敗（LLM 產出跨 pov 對白不一致）
- 此類 FAIL 屬「LLM 品質／劇本一致性」議題，與本 change 「CLI subprocess 遷移 + 認證機制」目標正交

### 另附發現的 3 個新問題（建議另開 change 處理，不阻擋本 change archive）

#### 問題 1（HIGH）: 預設模型名稱 `claude-sonnet-4-7` 不存在

- 事實：2026-04 當前 Claude 4.X 家族為 Sonnet **4.6**、Opus 4.7、Haiku 4.5；不存在 sonnet-4-7
- 影響位置：
  - `configs/default.yaml` L47 `project_agent_model: "claude-sonnet-4-7"`
  - `src/ring_of_hands/scenario_runner/config_loader.py` L110 預設值
  - `src/ring_of_hands/scenario_runner/types.py` L53 `project_agent_model: str = "claude-sonnet-4-7"`
  - `src/ring_of_hands/script_generator/types.py` L98 `model: str = "claude-sonnet-4-6"`（原文 `4-7`）
- 觸發症狀：CLI 回應 `api_error_status:404 "model may not exist"`，`subprocess` 以 returncode=1 退出，上層僅見 `cli_nonzero_exit:1`（無具體錯誤）
- 建議：新 change 修為 `claude-sonnet-4-6`；spec 中「模型版本可配置」Requirement 的 Scenario 亦需同步

#### 問題 2（MED）: 預設 timeout 30s 對劇本生成不足

- 事實：pov_1 劇本（長 prompt + 結構化 JSON 輸出 + 5-event 閉環）實測耗時 60-180s
- 影響位置：
  - `.env.example` 提示 `CLAUDE_CLI_TIMEOUT_SECONDS=30` 過短
  - `src/ring_of_hands/llm/claude_cli_client.py` 預設 `timeout_seconds=30.0`
- 建議：新 change 將預設調至 180-240s；或依呼叫種類區分（`decide` 短、`generate_script` 長）

#### 問題 3（LOW，設計層）: 閉環驗證策略過於脆弱

- 事實：script_generator 的閉環驗證（`script_n.events` 中涉及 `n-1` 的事件 MUST 與 `script_{n-1}` 完全一致）要求 LLM 跨 pov 產出逐字一致的對白；LLM 在 retry 間產出文字幾乎必有微幅差異
- 當前表現：即便延長 timeout，pov_2 仍因閉環 diff FAIL；3 次 retry 全用完即終止關卡
- 建議方向（需設計討論，不一定要立即改）：
  - (a) 放寬比對策略至「語義一致性」或「結構一致性」（action_type / target / t 一致即可，payload.msg 可 fuzzy 比對）
  - (b) 提高 `max_retries` 預設（5-8 次）並於 prompt 更強烈地傳達「必須 copy 前一劇本字面」
  - (c) 改為「前 n-1 份劇本固定為 LLM 已產出、後續 pov 的劇本以「引用」方式建構」而非獨立生成
  - 屬於 scenario-level 設計議題，建議另開獨立 change 評估

### archive 建議

**可立即 archive**：本 change（`migrate-to-claude-cli-subprocess`）的核心目標——將 LLM 後端從 Anthropic SDK 遷移至 Claude CLI subprocess、支援 Max 訂閱認證——已達成並通過真跑驗收。上述 3 個問題均屬 scenario-runner 預設配置／LLM 呼叫策略層，非本 change 範圍，應另立 change 處理（建議命名 `fix-default-model-and-timeouts` 處理問題 1+2，問題 3 可延後評估）。
