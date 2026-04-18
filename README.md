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
- Anthropic Python SDK (`anthropic`) 搭配 prompt caching
- pytest / pytest-asyncio
- structlog / PyYAML / python-dotenv
- Docker (python:3.11-slim, 非 root user)

## 目錄架構

```
.
├── README.md                    # 本檔
├── pyproject.toml               # Python 套件定義
├── run.sh                       # 啟動 container 執行主程式/測試
├── .env.example                 # 環境變數範例 (ANTHROPIC_API_KEY 等)
├── .gitignore
├── docker/
│   ├── Dockerfile               # python:3.11-slim + 非 root user
│   ├── build.sh                 # 建立 Docker image
│   └── docker-compose.yaml      # service `app`, volume logs/, env_file
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
│       │   ├── base.py          #   Protocol + LLMRequest/Response
│       │   ├── anthropic_client.py
│       │   └── fake_client.py   #   離線測試替身
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
│       │   ├── agent.py         #   ProjectAgent + 3 段 cache system block
│       │   ├── action_parser.py #   parse_action_from_response
│       │   ├── realtime.py
│       │   ├── error_handling.py #  FailureTracker
│       │   └── metrics.py       #   log_llm_metrics
│       └── scenario_runner/     # (capability) 主流程編排 + CLI
│           ├── types.py         #   ScenarioConfig
│           ├── config_loader.py
│           ├── runner.py        #   ScenarioRunner.run()
│           ├── cli_main.py      #   argparse CLI
│           ├── logging_setup.py
│           └── summary.py
├── tests/
│   ├── world_model/
│   ├── rules_engine/
│   ├── llm/
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
        └── recreate-duannao-ring-of-hands/
```

## 快速開始

1. 建立 Docker image:

   ```bash
   ./docker/build.sh
   ```

2. 準備 `.env` (從範例複製):

   ```bash
   cp .env.example .env
   # 編輯 .env, 填入 ANTHROPIC_API_KEY
   ```

3. 先以 dry-run 模式驗證流程 (不呼叫真實 LLM):

   ```bash
   ./run.sh --dry-run
   ```

   dry-run 使用 `tests/fixtures/dry_run.yaml` 預錄的劇本與 pov_6 action 序列,
   目的為驗證主流程且保證終局為 `WIN`。**dry-run 不會呼叫 Anthropic API**,
   亦不消耗金鑰。

4. 正式執行 (呼叫 Anthropic API):

   ```bash
   ./run.sh
   ```

   關卡結束後, 會於 `logs/` 目錄產生:

   - `events_<timestamp>.jsonl`: 所有 event 的 JSON lines.
   - `run_<timestamp>.log`: 人類可讀 log (含 LLM cache metrics).
   - `summary_<timestamp>.json`: `ScenarioSummary` JSON.

## 執行測試

```bash
./run.sh pytest
```

或在容器內:

```bash
docker compose -f docker/docker-compose.yaml run --rm app pytest
```

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

- `notes/time-structure.md` — 時間結構與因果閉環的設計筆記（唯一源頭）。
- `openspec/changes/recreate-duannao-ring-of-hands/` — 完整 OpenSpec 文件:
  - `proposal.md`: 動機與變更摘要。
  - `design.md`: 架構決策與 Prompt Caching 設計。
  - `specs/<capability>/spec.md`: 每個 capability 的 Requirements 與 Scenarios。
  - `tasks.md`: 實作任務清單。

## 漫畫出處

- 作品: 《端腦》（Die Now）
- 作者: **壁水羽**
- 關卡: 「攜手之戒」(Ring of Joining Hands)

核心設定:「六個人都為主角一人」—— 主角夏馳透過靈魂寄宿輪迴體驗六個身份。
本實作以「多時空階段自我 × 單 Epoch × 預生成閉環劇本」重構此設定, 使 pov_6
成為唯一自由主體, 其餘 pov 按 immutable 劇本執行。
