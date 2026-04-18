# Design: LLM 後端遷移至 Claude Code CLI subprocess

> 本文件定義「如何實作」提案中的 backend 遷移；需求本身（WHAT）記載於 `specs/<capability>/spec.md` 的 MODIFIED 區塊，動機（WHY）記載於 `proposal.md`。所有設計均以前一 change（`recreate-duannao-ring-of-hands`）的 `design.md` 為繼承對照，並遵循全域 `CLAUDE.md` 規範。

## Context

- **前置 change**：`openspec/changes/recreate-duannao-ring-of-hands/`（verify 第 1 次已 PASS，尚未 archive；其 `openspec/specs/` 對應 capability 尚未 materialize）。本 change 的 MODIFIED 以該 change 的 `specs/<capability>/spec.md` 為 baseline。
- **不變的部分**：
  - 關卡形式化 Ω 模型（6 bodies、pov_1~5 scripted、pov_6 free agent、單 epoch、死亡不接力記憶）。
  - INV-1 ~ INV-8 生產期保障。
  - `world-model` / `rules-engine` / `pov-manager` 三個 capability 的對外契約。
  - `LLMClient` Protocol（`LLMRequest` → `LLMResponse`）介面契約、`LLMSystemBlock` 3-block 結構（persona / rules / prior_life）、`LLMResponse` schema。
  - Dry-run 旗標、`FakeClientFixture` YAML 格式、WIN / FAIL(timeout) / FAIL(ring_paradox) 三條整合測試路徑。
- **改變的部分**：
  - LLM 後端從 `anthropic` Python SDK（HTTPS/API key）改為 Claude Code CLI（`claude -p` 非互動 subprocess，使用 `~/.claude/` OAuth session）。
  - Prompt caching 能力退場（CLI 尚未暴露 caching 控制旗標；Max 訂閱計費模式不以 token 計）。
  - Structured output 由 tool use / JSON mode 降級為 prompt 誘導 JSON + `json.loads`。
- **約束**：
  - Max 訂閱的 OAuth session 存於主機 `~/.claude/`，容器執行時以 bind mount 共享；容器 user UID/GID 需對齊主機擁有者以保有讀權。
  - CLI 呼叫透過 `subprocess.run(..., timeout=N)` 為主；stdin 傳 prompt 為替代方案；stdout 為 NDJSON。
  - 不引入任何第三方 CLI wrapper 套件；僅用 stdlib（`subprocess` / `json` / `shlex` / `pathlib`）。
  - 本專案無 git remote，commit 不 push。
- **利害關係人**：Coordinator（本文件產出者）／Specialist（後續 `/opsx:apply` 實作者）／Verifier（`/opsx:verify` 驗證者）／使用者（主機 `claude login`、驗收）。

## Goals / Non-Goals

**Goals:**

- 以 `ClaudeCLIClient`（實作既有 `LLMClient` Protocol）替換 `AnthropicClient`，不改動 `ProjectAgent` / `ScriptGenerator` / `PovManager` 等上層模組的對外行為。
- Docker 化執行環境內安裝 Claude Code CLI 並透過 volume mount 共享主機 OAuth session，使容器內執行 `claude -p "..."` 能以 Max 訂閱身份成功回應。
- 設計穩定的 stdout NDJSON 解析器，僅依賴 `type=result` 事件取得最終文字，忽略可能存在的多筆 `type=assistant` 中繼訊息，使 CLI 格式微調時有向後相容空間。
- 維持 `LLMResponse` schema 與既有 `cache_read_input_tokens` / `cache_creation_input_tokens` 欄位（值恆為 0），避免下游 structlog / summary / event log 的欄位變動。
- 維持 INV 執行期保障、所有單元測試語意、WIN / FAIL 三路徑整合測試。
- 啟動時嚴格檢查：`claude` 可執行（`claude --version` exit 0）、`~/.claude/` 存在且可讀；任一失敗 raise `ConfigValidationError`。

**Non-Goals:**

- 不重新設計關卡規則、pov 切片、因果閉環或 INV。
- 不增加任何 Python 第三方依賴；不改用 Node 版 `@anthropic-ai/claude-code` 以外的官方非 SDK 呼叫方式。
- 不實作 Claude CLI 的「多輪互動對話」或「tool use」特性；本次 backend 僅用單次請求-單次回應模式（`claude -p ...` 非互動）。
- 不嘗試偽造或還原 prompt caching 能力；一旦上游釋出 CLI 層 caching 旗標，另案處理（列入 Open Question）。
- 不處理主機 `claude login` session 過期的自動重登；由使用者手動 `claude login`。
- 不修改前一個 change（`recreate-duannao-ring-of-hands/`）的任何 artifact。
- 不修改 `notes/time-structure.md`、`~/.claude/CLAUDE.md`、`.claude/commands/`、`.claude/skills/`。

## Decisions

### D-1：採用 Claude Code CLI `claude -p` 非互動子程序為唯一 backend 呼叫通道

- **決定**：`ClaudeCLIClient.call(LLMRequest) → LLMResponse` 的實作為：
  1. 將 `request.system_blocks` 依序串接為 `## System\n<block1>\n\n<block2>\n\n<block3>` 形式的單一 prompt 前綴。
  2. 附加 `request.messages` 的最後一則 user message 作為 prompt 主體。
  3. 以 `subprocess.run([cli_path, "-p", full_prompt, "--output-format", "stream-json"] + (["--model", request.model] if request.model else []), capture_output=True, text=True, timeout=request.timeout_seconds, check=False)` 呼叫。
  4. 逐行解析 stdout 為 NDJSON 事件；以**最後一則 `type=result` 事件的 `result` 欄位**作為 `LLMResponse.text`；若無 `type=result` 事件則 raise `LLMCallFailedError(reason="no_result_event")`。
  5. `LLMResponse.tool_use = None`、`LLMResponse.usage = {}`、`LLMResponse.cache = CacheMetadata(0, 0)`、`LLMResponse.raw = {"stdout_events_count": N}`。
- **理由**：
  - `claude -p` 是官方支援的非互動模式，為程式化呼叫 Max 訂閱 Claude 的唯一合法管道。
  - `--output-format stream-json` 將回應結構化為 NDJSON，雖然存在多種事件（`type=system` / `type=assistant` / `type=result` / `type=error`）但**最終文字必然包含於 `type=result.result`**；只解析該欄位可隔離 CLI 版本升級造成的中繼事件格式微調。
  - `subprocess.run` 同步呼叫已足夠；本專案每關約 30~60 次 LLM 呼叫，無並發需求。
- **替代方案**：
  - *以 `claude --print --output-format json`（非 stream-json）*：一次性 JSON 輸出，解析更簡單；但若未來需要逐步顯示中間思考過程，stream-json 保留較大空間。暫定 stream-json，`ClaudeCLIClient` 保留 `output_format` 建構參數供切換。**採用 stream-json 為預設**。
  - *透過 stdin 傳送 prompt（`claude -p --stdin`）*：避免 prompt 過長導致 shell 命令行長度超限。Specialist 實作時若 prompt 超過 100 KB 則改走 stdin；預設走 `-p <prompt>` 直接傳值。**採二擇一的 fallback 策略**。
  - *寫 Node.js wrapper 使用 `@anthropic-ai/claude-code` SDK*：引入 Node 執行環境成本過高；本專案已為 Python 生態。**否決**。
  - *使用第三方 Python wrapper 套件*：目前生態中的 wrapper 套件均非官方，維護性與安全性未驗證。**否決**。

### D-2：stdout NDJSON 事件解析策略

- **決定**：`ClaudeCLIClient` 內部提供 `_parse_ndjson(stdout: str) -> LLMResponse` 純函數，流程：
  1. 按 `\n` 切行；對每行 `json.loads`；忽略無法解析的行（記 warning）。
  2. 收集所有 `type=result` 事件；若有多則，取最後一則；若 0 則 raise `LLMCallFailedError(reason="no_result_event")`。
  3. 若出現 `type=error` 事件，raise `LLMCallFailedError(reason=f"cli_error:{err_text}")`。
  4. 從 `type=result.result` 取 final text；若 `result` 欄位不存在則 raise `LLMCallFailedError(reason="result_missing_text")`。
  5. 從 `type=result.usage`（若存在）嘗試讀取 `input_tokens` / `output_tokens`（CLI 若回傳即記錄，未回傳則保持 0）；但 `cache_read_input_tokens` / `cache_creation_input_tokens` 一律 0。
- **理由**：
  - 只依賴 `type=result` 可對未來 CLI 新增 event type 保持向後相容。
  - `FakeLLMClient` 可以 NDJSON 字串預錄取代真實 CLI 回應，便於在不 mock subprocess 的情況下測試 parser。
- **替代方案**：
  - *解析每則 `type=assistant.message.content` 累加*：若 CLI 未來改 message 邊界規則則實作會破損。**否決**。

### D-3：Prompt 結構保留 3-block 系統訊息；移除 cache_control

- **決定**：
  - `LLMRequest.system_blocks` 的語意保留（persona / rules / prior_life），但 `LLMSystemBlock.cache` 欄位在 `ClaudeCLIClient` 中**被忽略**（不視為錯誤，以便與 `FakeLLMClient` 共用 request）。
  - Prompt 組合順序：`## Persona\n{persona_text}\n\n## Rules\n{rules_text}\n\n## Prior Life\n{prior_life_text}\n\n## Observation / Task\n{user_message}`（以 Markdown heading 分隔，方便 LLM 辨識）。
  - `CacheMetadata.cache_read_input_tokens` / `cache_creation_input_tokens` 兩欄位保留於 `LLMResponse.cache`，但 `ClaudeCLIClient` 寫入恆為 0；`metrics.log_llm_metrics` 照常輸出（即使值為 0），保持 log schema 不變。
- **理由**：
  - 使 `ProjectAgent._build_decide_request` / `ScriptGenerator._build_script_request` 的 prompt 組裝程式碼幾乎不需修改。
  - 保留 3-block 結構可讓上游恢復 caching 時僅需在 `ClaudeCLIClient` 內部重新啟用而不動 caller code。
  - Log schema 穩定性：Verifier 的 integration tests 依賴 `cache_read_input_tokens` 欄位存在；若移除欄位需同時修改 scenario-runner spec。為最小化 blast radius，保留欄位但值恆 0。
- **替代方案**：
  - *完全刪除 `LLMSystemBlock.cache` 欄位*：會波及所有 caller 與 fixture；**否決**，換取向後相容。
  - *移除 `CacheMetadata`*：會改寫 `metrics.py`、`structlog` key、整合測試對 `run.log` 的斷言；**否決**。

### D-4'（取代前版 D-4）：Structured output 由 prompt 誘導 JSON + `json.loads` 實現

- **決定**：
  - **ProjectAgent `decide`**：system/user prompt 追加 `"請以以下格式回覆（僅回 JSON，不要其他文字）：{\"action\":\"...\",\"...\":...}"` 的指示；CLI 回應後 `action_parser.parse_action_from_response` 優先從 `response.text` 做 `json.loads`（`tool_use` 路徑保留為 fallback，實務上 `ClaudeCLIClient` 恆為 `None`）。
  - **ScriptGenerator**：類似策略；prompt 明確要求輸出 `Script` 的 JSON schema 一致的物件，然後以 `Script.model_validate` 驗證；若 LLM 回傳包含 Markdown code fence（```json ... ```），解析器需自動去除 fence。
  - 解析失敗統一 raise `ActionParseError` / `ScriptGenerationError`（由 pov-manager / script-generator 照原流程降級 / retry）。
- **Prompt 增強細則**：
  - 在 `ProjectAgent` 的 user prompt 末尾（`_format_observation_for_user` 內）加入：
    ```
    請輸出一個 JSON 物件，形如：
    {"action":"move|press|touch_ring|speak|wait|observe", ...}
    move 需含 "delta":[dx,dy]；press 需含 "button_id":N；
    speak 需含 "msg":"...","targets":[...]；其他不需額外欄位。
    僅輸出 JSON，勿附加說明。
    ```
  - 在 `ScriptGenerator` 的 user prompt 中要求：
    ```
    請輸出一個 JSON 物件，對應 Script schema：
    {"pov_id":N,"persona":{...},"events":[{"t":0,"actor":N,"action_type":"...","payload":{},"targets":[]}, ...],"death_cause":"press_wrong|ring_paradox|timeout|other"}
    events 需按 t 非遞減排序，最後一筆 action_type 必為 "die" 且 actor=pov_id。
    僅輸出 JSON。
    ```
- **理由**：
  - Claude Code CLI 尚未穩定暴露 programmatic tool use 介面；prompt 誘導 + 嚴格 schema 驗證 + retry 機制在本專案已為既有 pipeline 的一部分（`ScriptGenerator.max_retries`），降級路徑已成熟。
  - `action_parser` 早已支援 `response.text` JSON fallback 路徑；改動集中於「tool_use 不再作為主要路徑」。
- **替代方案**：
  - *使用 Claude CLI 實驗性 `--tool-use` 旗標*：官方 CLI 文件目前未公開該功能；風險高。**否決**。
  - *另外部署 XML 結構輸出*：Claude 擅長 XML 但後續驗證程式變複雜；JSON 已足。**否決**。

### D-5：認證機制與環境變數

- **決定**：
  - `.env.example` 移除 `ANTHROPIC_API_KEY`；新增：
    ```
    CLAUDE_CLI_PATH=claude
    CLAUDE_CLI_TIMEOUT_SECONDS=30
    # 可選：若使用者 claude login 存放位置非預設 ~/.claude 則覆寫。
    CLAUDE_HOME=
    PROJECT_AGENT_MODEL=claude-sonnet-4-7
    LOG_LEVEL=INFO
    ```
  - `ClaudeCLIClient.__init__` 在建構時驗證：
    1. `shutil.which(cli_path)` 不為 None（可執行）。
    2. `subprocess.run([cli_path, "--version"], capture_output=True, timeout=5, check=False)` exit code == 0。
    3. `claude_home` 路徑存在（`Path(claude_home or "~/.claude").expanduser().is_dir()`）。
  - 任一檢查失敗 raise `ConfigValidationError`（既有例外類別，位於 `project_agent.agent`；本 change 可將其上提到 `llm.base` 以避免循環匯入；Specialist 決定）。
  - 錯誤訊息包含可操作建議（例如「請執行 `claude login` 後重試」）。
- **理由**：
  - `claude --version` 為最輕量的存活檢查；`~/.claude/` 為 session token 存放處，檢查存在性可早期攔截「忘了 `claude login`」的人為失誤。
  - 保留 `CLAUDE_HOME` override 可支援非預設路徑（雖目前 Claude CLI 預設 `~/.claude`）。
- **替代方案**：
  - *呼叫 `claude whoami` 驗證 session*：增加啟動時間且可能觸發 rate limit；暫以檔案存在性代替，不發 API。
  - *不做啟動檢查，首次呼叫失敗才報錯*：錯誤延後、難診斷。**否決**。

### D-6：Docker 化執行環境

- **決定**：
  - `docker/Dockerfile` 於 base layer 安裝 Claude CLI。優先使用官方安裝腳本：
    ```dockerfile
    RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
        && curl -fsSL https://claude.ai/install.sh | bash \
        && apt-get clean && rm -rf /var/lib/apt/lists/*
    ```
    並將 CLI 路徑加入 `PATH`（Specialist 視安裝腳本實際結果調整）。若 Specialist 發現該 URL 在 Docker 環境下無法使用，降級為 `npm install -g @anthropic-ai/claude-code`（需額外裝 Node）。
  - 容器使用者 UID/GID 可由 `build-arg` 覆寫（`APP_UID`、`APP_GID`），預設為主機 `$(id -u)` / `$(id -g)`；`docker/build.sh` 自動帶入。這樣容器內 `app` user 對 bind-mounted `~/.claude/` 擁有讀權。
  - `docker/docker-compose.yaml` 新增：
    ```yaml
    volumes:
      - ../logs:/app/logs
      - ${HOME}/.claude:/home/app/.claude:ro
    ```
    （若 `~/.claude` 不存在則 compose 會自動以目錄建立；為避免此行為，`run.sh` 啟動前先確認 `~/.claude/` 存在並可讀。）
  - `run.sh` 在 `exec docker compose ...` 前加入：
    ```bash
    if ! command -v claude >/dev/null 2>&1; then
      echo "ERROR: 'claude' CLI 未安裝於主機，請先執行 curl -fsSL https://claude.ai/install.sh | bash" >&2
      exit 1
    fi
    if [[ ! -d "${HOME}/.claude" ]]; then
      echo "ERROR: ~/.claude 不存在，請先執行 'claude login' 建立 OAuth session" >&2
      exit 1
    fi
    ```
- **理由**：
  - 讓容器內的 Claude CLI 讀取主機的 OAuth session，免除在容器內重新 login 的困擾（容器為 ephemeral，每次啟動都要重登不實際）。
  - UID/GID 對齊避免「ro mount 但 uid 不符導致 EACCES」問題。
- **替代方案**：
  - *只在主機執行 CLI，容器 `subprocess.run` 透過 shared FS 呼叫*：會打破「容器化執行」原則；**否決**。
  - *在容器內放 interactive `claude login`*：非互動無法完成 OAuth flow；**否決**。

### D-7：測試策略

- **單元測試**：
  - `tests/test_llm/test_claude_cli_client.py`（新增）：
    - `_parse_ndjson` 正常路徑（1 則 `type=result`）。
    - `_parse_ndjson` 多則 `type=assistant` + 1 則 `type=result`。
    - `_parse_ndjson` 0 則 `type=result` → raise。
    - `_parse_ndjson` `type=error` → raise。
    - `_parse_ndjson` 無法解析的行被忽略（以 warning log assertion）。
    - `call` 整合：以 `unittest.mock.patch("subprocess.run")` 模擬 stdout；驗證 CLI 旗標正確（`-p`、`--output-format stream-json`、`--model`）。
    - `call` timeout：mock `subprocess.run` raise `subprocess.TimeoutExpired` → 轉為 `LLMCallFailedError(reason="cli_timeout")`。
    - `call` non-zero exit：mock `subprocess.run` 回傳 returncode != 0 → 轉為 `LLMCallFailedError(reason="cli_nonzero_exit:...")`。
    - `__init__` 驗證：`shutil.which` 為 None → raise `ConfigValidationError`；`~/.claude` 不存在 → raise。
  - `tests/test_llm/test_fake_client.py`（微調）：class import 改為 `FakeLLMClient`；既有 fixture 測試維持。
  - `tests/test_project_agent/test_agent.py`（微調）：
    - 移除 `SUBMIT_ACTION_TOOL` / `tool_choice` 相關 assertion；新增「LLM 回傳純文字 JSON 被正確解析為 `Action`」測試。
    - `cache_control` 相關 assertion 移除；保留「system_blocks 長度為 3」的結構檢查。
    - `_build_decide_request` 的斷言：不再檢查 `tools` 非空（改為空 tuple）。
  - `tests/test_project_agent/test_action_parser.py`（新增或擴充）：`response.text` 包含 Markdown code fence 時能解析；純 JSON 亦能解析；非 JSON raise。
  - `tests/test_script_generator/test_generator.py`（微調）：
    - fixture 改為 `response.text` 為 JSON 字串；不再依賴 `tool_use.input`。
    - 移除 `PRODUCE_SCRIPT_TOOL` assertion。
- **整合測試**：
  - `tests/test_integration/*`：`FakeLLMClient` fixture 維持 WIN / FAIL(timeout) / FAIL(ring_paradox) 三路徑；fixture YAML schema 不變（`FakeClientFixture` 介面穩定）。
- **執行環境**：
  - 本地：`./run.sh pytest`（容器內跑）。
  - 離線：單元測試不需 `claude` CLI；CI 與開發機無需 login。
  - 真實整合：`./run.sh --dry-run` 仍使用 `FakeLLMClient`；`./run.sh`（無 `--dry-run`）才走真實 `ClaudeCLIClient`，需要主機已 `claude login`。

### D-8：錯誤與 Timeout 處理對應

- **決定**（`ClaudeCLIClient` 內部錯誤映射表）：

| 來源 | 例外 / 條件 | 轉換為 |
|------|------------|--------|
| `subprocess.TimeoutExpired` | 子程序執行超時 | `LLMCallFailedError(reason="cli_timeout")` |
| `subprocess.run(..., check=False)` returncode != 0 | CLI 非零退出 | `LLMCallFailedError(reason=f"cli_nonzero_exit:{rc}", cause=None)`（附 stderr 摘要） |
| `FileNotFoundError` | `cli_path` 路徑在呼叫期消失 | `LLMCallFailedError(reason="cli_not_found")` |
| NDJSON 解析失敗 | stdout 完全無法解析 | `LLMCallFailedError(reason="ndjson_parse_error")` |
| `type=error` 事件 | CLI 明示錯誤 | `LLMCallFailedError(reason=f"cli_error:{err}")` |
| 未取得 `type=result` | 正常退出但無結果 | `LLMCallFailedError(reason="no_result_event")` |
- **ProjectAgent 上層語意保留**：單次 `LLMCallFailedError` → 轉 `ActionParseError`（由 pov-manager 降為 WaitAction）；連續 `consecutive_failure_limit`（預設 3）次 → raise `LLMUnavailableError` 終止關卡。
- **理由**：將所有 subprocess 層錯誤塞進既有的 `LLMCallFailedError`，`ProjectAgent.decide` / `realtime_reply` / `ScriptGenerator` 上層邏輯無需改動。

### D-9：FakeLLMClient 的 response builder 精簡化

- **決定**：
  - `FakeLLMClient`（由 `FakeAnthropicClient` 更名）的內部 `_load_from_fixture` 不再構造 `tool_use` 欄位；改為直接將 fixture 中的 script dict / action dict 以 `json.dumps` 序列化為 `LLMResponse.text`（符合 `ClaudeCLIClient` 的自然回傳格式）。
  - `tool_use` 相容路徑：若舊測試 fixture 仍包含 `tool_use`（例如前一 change 留存），FakeLLMClient 在建構時列印 `DeprecationWarning` 但仍可支援；Specialist 於本次 apply 時統一升級 fixture。
  - 新 `FakeLLMClient` 對 request 的 metadata purpose 分派不變（`script_generation` / `agent_decide` / `realtime_reply`）。
- **理由**：
  - 讓 fake 與真實 `ClaudeCLIClient` 的 response shape 一致（`text` 欄位為 JSON 字串），減少測試偏差。
  - 保留對舊 fixture 的向後相容避免阻塞 verify。
- **替代方案**：
  - *直接 breaking 移除 `tool_use` 支援*：整合測試 fixture 需同步修改；**本 change 決定一次性升級**（反正 fixture 也在本 change scope 中）。但仍保留 warning 作為 soft 轉換。

### D-10：`ConfigValidationError` 例外位置

- **決定**：
  - 前一 change 將 `ConfigValidationError` 定義於 `project_agent.agent`；本次將其上提至 `llm.base`（與 `LLMCallFailedError` 同模組），`project_agent.agent` 改 re-export 以保持向後相容。
  - 理由：`ClaudeCLIClient.__init__` 會在建構時 raise 此錯誤，但其邏輯上不屬於 project_agent 模組；上提後可讓 `scenario_runner` 的啟動檢查直接 `from ring_of_hands.llm.base import ConfigValidationError`。
- **替代方案**：
  - *複製一份於 `llm.base`*：造成兩個 class 名稱相同但 identity 不同的比對坑。**否決**。

## Risks / Trade-offs

- **[R-1 Claude CLI stream-json 格式變動]** → CLI 為非 SDK，API/格式不保證穩定。**Mitigation**：`_parse_ndjson` 只依賴 `type=result.result` 欄位；保留 `FakeLLMClient` 可預錄任何 NDJSON 字串作為迴歸測試 fixture；`tests/test_llm/test_claude_cli_ndjson.py` 覆蓋多版本事件流的容錯行為。
- **[R-2 Docker 內 OAuth session 過期]** → 使用者 `claude login` 的 session 可能過期（官方文件未明示壽命）。**Mitigation**：README 明確記載「若 CLI 回傳 `type=error` 且 reason 涉及 session/auth，請主機執行 `claude login`」；`ClaudeCLIClient` 啟動檢查僅驗證 `~/.claude/` 存在，不驗證 session 有效（避免誤觸 rate limit），而在實跑時遇到 auth error 以 `LLMCallFailedError(reason="cli_auth_error")` 形式冒出。
- **[R-3 Max plan rate limit 超限]** → Max 訂閱有每日使用量上限；若關卡含大量 pov_6 tick 可能觸頂。**Mitigation**：保留 `--dry-run` 預設走 `FakeLLMClient`、整合測試不在 CI 跑真實 backend、README 建議先以 dry-run 驗證再執行一次真跑；`consecutive_failure_limit=3` 可快速失敗終止關卡，不會持續浪費配額。
- **[R-4 Prompt caching 失去]** → 每 tick 都重送 persona + rules + prior_life 全文。**Trade-off**：以 Max 訂閱計費而非 token 計費，成本單位改為「訂閱使用時數與 RPM」而非「token 金額」；使用者已接受。**Mitigation**：`ClaudeCLIClient` 保留 3-block system prompt 結構；Open Question 持續追蹤 upstream caching 支援時機。
- **[R-5 subprocess 每 call 額外 fork/exec 成本]** → 每次 LLM 呼叫多 50~200 ms。**Trade-off**：本專案每關約 30~60 次呼叫，總增加 3~12 秒；可接受。**Mitigation**：不做任何 async 改造；若未來有並發需求再評估 `asyncio.create_subprocess_exec`。
- **[R-6 CLI prompt 超長導致 argv 溢出]** → pov_6 的 prior_life 可能為數萬 tokens。**Mitigation**：`ClaudeCLIClient` 實作 `prompt_length_threshold`（預設 100 KB）；超過時改以 `stdin` 傳送 prompt（`subprocess.run(..., input=prompt_text)`）；Specialist 實作時覆蓋此邏輯。
- **[R-7 Docker image size 增加]** → Claude CLI 安裝後 image 可能膨脹 50~150 MB。**Trade-off**：可接受；build 時間亦可接受。
- **[R-8 `ConfigValidationError` 搬家破壞既有 import]** → 移到 `llm.base` 後若有外部 caller 直接 `from ring_of_hands.project_agent.agent import ConfigValidationError` 會斷。**Mitigation**：保留 re-export；於 agent.py 加 `from ring_of_hands.llm.base import ConfigValidationError as ConfigValidationError`。

## Migration Plan

- **主機前置**：
  1. 使用者於主機執行：
     ```bash
     curl -fsSL https://claude.ai/install.sh | bash    # 安裝 CLI（或等效程序）
     claude login                                       # 建立 OAuth session
     claude --version                                   # 驗證
     ```
  2. 確認 `~/.claude/` 存在且包含 session 相關檔案。
- **套件與配置**：
  1. Specialist 於 `/opsx:apply` 時：
     - 更新 `pyproject.toml`（移除 `anthropic>=0.39.0`）。
     - 更新 `.env.example`（移除 `ANTHROPIC_API_KEY`；新增 `CLAUDE_CLI_PATH` / `CLAUDE_CLI_TIMEOUT_SECONDS` / `CLAUDE_HOME`）。
     - 更新 `docker/Dockerfile`（新增 CLI 安裝與 UID/GID build-arg）。
     - 更新 `docker/docker-compose.yaml`（新增 `~/.claude` volume）。
     - 更新 `run.sh`（主機前置檢查）。
- **實作順序**（Specialist apply 流程；實際 task 於 `tasks.md` 展開）：
  1. 建立 `ClaudeCLIClient`（含 `_parse_ndjson`）與單元測試。
  2. 將 `ConfigValidationError` 搬至 `llm.base` 並保留 re-export。
  3. 更新 `FakeAnthropicClient` → `FakeLLMClient`（class rename + response builder 改輸出 `text` 欄位）。
  4. 更新 `ProjectAgent`（prompt 加 JSON 指令、移除 `SUBMIT_ACTION_TOOL` 引用）。
  5. 更新 `ScriptGenerator` / `prompt_builder`（移除 `PRODUCE_SCRIPT_TOOL`、改 prompt 誘導 JSON）。
  6. 刪除 `anthropic_client.py`；從 `pyproject.toml` 移除 `anthropic`。
  7. 更新 `.env.example` / `Dockerfile` / `docker-compose.yaml` / `run.sh`。
  8. 更新 README.md 的啟動章節。
  9. 跑完整 pytest（含整合測試 WIN / FAIL 三路徑）。
- **回滾策略**：
  - 若本 change apply 後發生無法修復的問題，以 `git reset --hard <prev-head>` 回到 branch 起點（HEAD 為前一 change 的最後 commit `bbf13c0`）。
  - 由於本 change 僅在 `opsx/migrate-to-claude-cli-subprocess` branch 進行、尚未 merge 回 main，回滾不影響前一 change。
  - `anthropic` SDK 仍可在 pyproject.toml 中恢復安裝作為應急（git revert 即可）。

## Open Questions

1. **上游 Claude CLI 是否會增加 prompt caching 旗標**？目前無規劃；若未來出現則新開 change `restore-prompt-caching-via-cli` 處理。
2. **Claude CLI `--model` 支援的模型清單是否與 SDK 一致**？Specialist 實作時以 `claude --help` 驗證；若 CLI 僅支援 alias（如 `sonnet`）則 `PROJECT_AGENT_MODEL` 需支援 alias 映射（新增於 `validate_model_name`）。Coordinator 建議：優先嘗試 full name，fallback 到不帶 `--model` 旗標（走 CLI 預設）。
3. **Docker 內 `~/.claude` mount 為 ro 是否足夠**？若 CLI 運行期需寫回 session cache（例如 refresh token），ro 會失敗；Specialist 驗證：若失敗改為 rw mount。
4. **Max 訂閱是否對 `claude -p` 有獨立 rate limit**？官方未公開明確數字；Specialist 實作時在 `LLMCallFailedError` 的 reason 中辨識 rate-limit error（透過 stderr pattern match）並記入 structlog。
5. **是否需要實作 `claude -p --resume`（延續上一輪對話）以減輕 prior_life 重送**？初版不實作；若 Max 訂閱使用量實測過高再評估。
6. **prompt 超長走 stdin 的閾值**（預設 100 KB）是否合適？Specialist 以實測調整，若有調整寫入 `issues.md`。
7. **是否應於 `.gitignore` 新增 `~/.claude` 相關保護**？使用者 home directory 本就在專案外，無需；但 `.env` 仍須保持忽略。
