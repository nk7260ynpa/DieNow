# Ring of Hands (攜手之戒關卡模擬)

以多時空階段自我模型重現漫畫《端腦》（作者：**壁水羽**）中的「攜手之戒」關卡。
6 個 body 皆為同一 Project Agent 的時空切片; pov_1 新生, pov_2~5 攜帶遞迴前世記憶,
pov_6 攜帶 5 層遞迴前世記憶並作為**唯一自由主體**。

## 專案目的

- 使單一 LLM-backed Project Agent 能作為玩家實際「被關進」攜手之戒關卡, 但系統
  內不會出現時間悖論。
- 透過「預生成閉環劇本 + 執行期 Invariants 檢查」維持一致性 (INV-1 ~ INV-8)。
- 留下結構化 event log 可離線重放。

## 技術棧

- Python 3.11+
- Pydantic v2 (`frozen=True` 強制 immutable)
- **LLM 後端: Claude Code CLI subprocess + Claude Max 訂閱**
  透過 `subprocess.run(["claude", "-p", ...])` 非互動呼叫 Claude CLI,
  計費由主機 `claude login` 建立的 Max 訂閱 OAuth session 承擔;
  **不使用** `anthropic` Python SDK。
- pytest / pytest-asyncio
- structlog / PyYAML / python-dotenv
- Docker (python:3.11-slim, 內含 Claude CLI, 非 root user)

## 目錄架構

```
.
├── README.md                    # 本檔
├── pyproject.toml               # Python 套件定義 (無 anthropic 依賴)
├── run.sh                       # 啟動 container 執行主程式/測試
├── .env.example                 # 環境變數範例 (CLAUDE_CLI_PATH 等)
├── .gitignore
├── docker/
│   ├── Dockerfile               # python:3.11-slim + Claude CLI + 非 root user
│   ├── build.sh                 # 建立 Docker image (自動帶 APP_UID/GID)
│   └── docker-compose.yaml      # service `app`, volume logs/ + ~/.claude
├── configs/
│   ├── default.yaml             # 預設關卡 config
│   └── personas.yaml            # pov_1..5 persona 模板
├── logs/                        # 關卡執行的 events/run/summary (gitignore)
│   └── .gitkeep
├── src/
│   └── ring_of_hands/
│       ├── __init__.py
│       ├── cli.py               # CLI 入口
│       ├── world_model/         # (capability) 世界狀態唯一事實來源
│       │   ├── engine.py        #   WorldEngine + observe/dispatch
│       │   ├── event_log.py     #   JSONL append-only writer
│       │   ├── observation.py   #   INV-5 受控的 observation 建構器
│       │   └── types.py         #   Body/Button/Ring/WorldState/Action/Event
│       ├── rules_engine/        # (capability) 規則 + Invariants 強制
│       │   ├── dispatcher.py    #   dispatch 路由 + install_default_dispatcher
│       │   ├── invariants.py    #   INV-3/4/7/8 檢查
│       │   ├── button_rule.py
│       │   ├── ring_rule.py
│       │   ├── move_rule.py
│       │   ├── speak_rule.py
│       │   ├── death_rule.py
│       │   └── outcome.py       #   post_tick_checks (6 燈/unreachable/timeout)
│       ├── llm/                 # LLMClient 抽象層
│       │   ├── base.py          #   Protocol + LLMRequest/Response + ConfigValidationError
│       │   ├── claude_cli_client.py  # ClaudeCLIClient (subprocess + NDJSON 解析)
│       │   └── fake_client.py   #   FakeLLMClient (離線測試替身)
│       ├── script_generator/    # (capability) 預生成閉環劇本
│       │   ├── types.py         #   Script/ScriptEvent (frozen)
│       │   ├── prompt_builder.py
│       │   ├── validator.py     #   時間一致性驗證
│       │   └── generator.py     #   generate_all + retry + issues.md
│       ├── pov_manager/         # (capability) 管理 6 pov context
│       │   ├── types.py
│       │   └── manager.py       #   tick_scripted_povs / tick_free_agent /
│       │                        #   request_realtime_reply
│       ├── project_agent/       # (capability) pov_6 + realtime reply
│       │   ├── agent.py         #   ProjectAgent + 3-block system prompt
│       │   ├── action_parser.py #   parse_action_from_response (JSON + fence 去除)
│       │   ├── realtime.py
│       │   ├── error_handling.py #  FailureTracker + CLI 錯誤 reason 清單
│       │   └── metrics.py       #   log_llm_metrics
│       └── scenario_runner/     # (capability) 主流程編排 + CLI
│           ├── types.py         #   ScenarioConfig (含 cli_path / claude_home)
│           ├── config_loader.py #   CLI 預啟動檢查
│           ├── runner.py        #   ScenarioRunner.run()
│           ├── cli_main.py      #   argparse CLI
│           ├── logging_setup.py
│           └── summary.py
├── tests/
│   ├── world_model/
│   ├── rules_engine/
│   ├── llm/                     # test_base / test_claude_cli_client / test_claude_cli_ndjson / test_fake_client
│   ├── script_generator/
│   ├── pov_manager/
│   ├── project_agent/
│   ├── scenario_runner/
│   ├── cli/
│   ├── integration/             # 端到端測試 (happy path / timeout / ring_paradox ...)
│   └── fixtures/
│       └── dry_run.yaml
├── notes/
│   └── time-structure.md        # 探索階段的時間結構/因果閉環筆記 (唯一源頭)
└── openspec/                    # OpenSpec 工件 (Coordinator 產出)
    └── changes/
        ├── recreate-duannao-ring-of-hands/     # 首次實作
        └── migrate-to-claude-cli-subprocess/   # 本 change: LLM 後端遷移
```

## 前置需求

### 1. 於主機安裝 Claude Code CLI

由於本專案透過 `subprocess` 呼叫 Claude CLI, **主機**必須先安裝 CLI。

```bash
# 方式 A: 官方安裝腳本
curl -fsSL https://claude.ai/install.sh | bash

# 方式 B: 透過 npm (需先有 Node.js)
npm install -g @anthropic-ai/claude-code

# 驗證
claude --version
```

### 2. 於主機執行 `claude login` 建立 Claude Max 訂閱 OAuth session

```bash
claude login
```

此指令會啟動瀏覽器登入流程, 登入後會於主機 `~/.claude/` 目錄建立 session 檔。
Docker container 會透過 bind mount 共享此目錄, 因此容器內的 `claude`
可以承繼 Max 訂閱身份進行非互動呼叫。

### 3. (可選) 設定環境變數

複製範例檔並視需要編輯:

```bash
cp .env.example .env
```

主要欄位:

| 變數 | 預設 | 說明 |
|------|------|------|
| `CLAUDE_CLI_PATH` | `claude` | `claude` 可執行檔路徑 |
| `CLAUDE_CLI_TIMEOUT_SECONDS` | `30` | 每次 CLI 呼叫的 timeout (秒) |
| `CLAUDE_HOME` | 空 (= `~/.claude`) | OAuth session 存放目錄 |
| `PROJECT_AGENT_MODEL` | `claude-sonnet-4-7` | Project agent 使用的模型; 空字串代表走 CLI 預設 |
| `LOG_LEVEL` | `INFO` | structlog 等級 |

**本 change 起已移除 `ANTHROPIC_API_KEY` 的設定**;
若舊 `.env` 仍有此欄位會被忽略。

## 快速開始

1. 依「前置需求」於主機安裝 Claude CLI 並執行 `claude login`。

2. 建立 Docker image (自動帶入主機 UID/GID 以對齊 `~/.claude` 擁有者):

   ```bash
   ./docker/build.sh
   ```

3. 準備 `.env` (從範例複製即可; 不需要 API Key):

   ```bash
   cp .env.example .env
   ```

4. 先以 dry-run 模式驗證流程 (不呼叫真實 LLM, 不需要 CLI 已登入):

   ```bash
   ./run.sh --dry-run
   ```

   dry-run 使用 `tests/fixtures/dry_run.yaml` 預錄的劇本與 pov_6 action 序列,
   目的為驗證主流程且保證終局為 `WIN`。

5. 正式執行 (以 Max 訂閱呼叫 Claude CLI):

   ```bash
   ./run.sh
   ```

   關卡結束後, 會於 `logs/` 目錄產生:

   - `events_<timestamp>.jsonl`: 所有 event 的 JSON lines.
   - `run_<timestamp>.log`: 人類可讀 log (含 LLM metrics, cache metrics 恆為 0).
   - `summary_<timestamp>.json`: `ScenarioSummary` JSON.

## 執行測試

所有測試皆為離線可跑 (mock `subprocess.run`, 不需要實際 Claude CLI):

```bash
./run.sh pytest
```

或在容器內:

```bash
docker compose -f docker/docker-compose.yaml run --rm app pytest
```

## 故障排除

| 錯誤訊息 | 原因 | 處置 |
|---------|------|------|
| `ConfigValidationError: claude CLI 不可執行` | 主機未安裝 Claude CLI 或不在 PATH | 執行 `curl -fsSL https://claude.ai/install.sh \| bash` 或 `npm install -g @anthropic-ai/claude-code` 安裝; 確認 `claude --version` 可執行 |
| `ConfigValidationError: ~/.claude 不存在` / `請先執行 claude login` | 主機未執行過 `claude login` | 於主機執行 `claude login` 建立 OAuth session |
| `LLMCallFailedError(reason="cli_auth_error")` 或 CLI stderr 提示 session/auth 失敗 | Max 訂閱 OAuth session 過期 | 於主機重新執行 `claude login` |
| `LLMCallFailedError(reason="cli_timeout")` | 單次 `claude -p ...` 呼叫超過預設 30 秒 | 調大 `CLAUDE_CLI_TIMEOUT_SECONDS` (例如設為 60); 或確認主機網路/服務狀況 |
| `LLMCallFailedError(reason="cli_nonzero_exit:<rc>")` | CLI 非零退出 (常見於 auth 失效或模型不可用) | 檢查 stderr 內容; 對應處理 auth 或換模型 |
| `LLMCallFailedError(reason="no_result_event")` | CLI 成功執行但 stdout 無 `type=result` 事件 | 檢查 CLI 版本; 必要時回報並提供原始 stdout |
| `ndjson_parse_error` | CLI stdout 完全無法以 NDJSON 解析 | 檢查 CLI 版本或主機環境; 此錯誤亦可能為 CLI 發生 crash |
| `ScriptGenerationError` / `issues.md` 追加紀錄 | LLM 連續回傳非合法 JSON script 導致 retry 耗盡 | 檢查 prompt caching / 模型版本; 必要時提高 `max_retries` |

## 系統 Invariants

| ID | 內容 | 檢查時機 |
|----|------|----------|
| INV-1 | state mutation 只能經由 `WorldEngine.dispatch` | 結構保證 (Pydantic frozen) |
| INV-2 | Script immutable | 結構保證 (Pydantic frozen) |
| INV-3 | scripted pov 的 action 與劇本吻合 | dispatch 前 |
| INV-4 | pov_6 不得走 scripted 路徑 | dispatch 前 |
| INV-5 | observation 不得洩露自己的 number_tag/規則/目標 | build_observation 時 |
| INV-6 | event append-only | EventLog 結構保證 |
| INV-7 | 同一 tick 單一 pov 僅接受一次自由 action | register_free_action |
| INV-8 | 不存在違反劇本的行為鏈 | dispatch 前 + runtime |

違反任一 Invariant 時會 raise `InvariantViolation(inv_id, detail)` 並寫入 event log。

## 進一步閱讀

- `notes/time-structure.md` — 時間結構與因果閉環的設計筆記 (唯一源頭)。
- `openspec/changes/recreate-duannao-ring-of-hands/` — 首次實作的完整 OpenSpec 文件。
- `openspec/changes/migrate-to-claude-cli-subprocess/` — 本 change 的 OpenSpec 文件:
  - `proposal.md`: 遷移動機與 BREAKING 變更摘要。
  - `design.md`: 架構決策 (D-1 ~ D-10), 含 NDJSON 解析策略、CLI 啟動檢查、錯誤映射表等。
  - `specs/<capability>/spec.md`: 各 capability 的 MODIFIED Requirements 與 Scenarios。
  - `tasks.md`: 實作任務清單。

## 漫畫出處

- 作品: 《端腦》(Die Now)
- 作者: **壁水羽**
- 關卡: 「攜手之戒」(Ring of Joining Hands)

核心設定:「六個人都為主角一人」— 主角夏馳透過靈魂寄宿輪迴體驗六個身份。
本實作以「多時空階段自我 × 單 Epoch × 預生成閉環劇本」重構此設定, 使 pov_6
成為唯一自由主體, 其餘 pov 按 immutable 劇本執行。
