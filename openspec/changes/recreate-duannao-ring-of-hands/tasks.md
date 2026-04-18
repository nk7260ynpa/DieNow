## 1. 專案骨架與基礎設施

- [ ] 1.1 建立 Python 專案結構：`pyproject.toml`（Python >=3.11、相依：`anthropic`、`pydantic>=2.7`、`pytest`、`pytest-asyncio`、`structlog`、`pyyaml`、`python-dotenv`）、`src/ring_of_hands/__init__.py`、`src/ring_of_hands/cli.py`（只含 entrypoint 骨架）、`tests/__init__.py`；檔案範圍：`pyproject.toml`、`src/ring_of_hands/__init__.py`、`src/ring_of_hands/cli.py`、`tests/__init__.py`
- [ ] 1.2 建立 Docker 基礎設施：`docker/Dockerfile`（`python:3.11-slim`、非 root user）、`docker/build.sh`（Google Shell Style）、`docker/docker-compose.yaml`（service `app`、volume `logs/`、env_file `.env`）；檔案範圍：`docker/Dockerfile`、`docker/build.sh`、`docker/docker-compose.yaml`
- [ ] 1.3 建立 `run.sh`（參數透傳至 `docker compose run --rm app`；Google Shell Style）、`logs/.gitkeep`、`.env.example`（`ANTHROPIC_API_KEY=`、`PROJECT_AGENT_MODEL=claude-sonnet-4-7`、`LOG_LEVEL=INFO`）；檔案範圍：`run.sh`、`logs/.gitkeep`、`.env.example`
- [ ] 1.4 建立 `.gitignore`（忽略 `logs/*` 但保留 `logs/.gitkeep`、`.env`、`__pycache__/`、`.pytest_cache/`、`*.pyc`、`dist/`、`build/`、`*.log`）；檔案範圍：`.gitignore`
- [ ] 1.5 建立預設設定檔：`configs/default.yaml`（room_size=[10,10]、6 個 body／button 起始位置、ring 位置、max_ticks=50、max_retries=3、enable_realtime_chat=true、llm_timeout_seconds=30）、`configs/personas.yaml`（6 份 persona 模板）、`tests/fixtures/dry_run.yaml`（happy path stub）；檔案範圍：`configs/default.yaml`、`configs/personas.yaml`、`tests/fixtures/dry_run.yaml`

## 2. World Model 實作

- [ ] 2.1 定義 Pydantic v2 型別：`Coord`、`Body`、`Button`、`Ring`、`WorldState`、`Action` 家族（`MoveAction`、`PressAction`、`TouchRingAction`、`SpeakAction`、`WaitAction`、`ObserveAction`）、`Event` 家族、`Observation`、`Outcome`、各模型以 `frozen=True`（INV-2、INV-5 的結構保障）；檔案範圍：`src/ring_of_hands/world_model/types.py`、`tests/world_model/test_types.py`
- [ ] 2.2 實作 `WorldEngine`：集中持有 `WorldState`、提供 `observe(pov_id)`、`dispatch(pov_id, action)`、`advance_tick()`、`snapshot()`、`event_log` 寫入介面；確保外部無法直接 mutate state；檔案範圍：`src/ring_of_hands/world_model/engine.py`、`tests/world_model/test_engine.py`
- [ ] 2.3 實作 observation 建構器：依 pov_id 過濾出可見欄位（排除 self `number_tag`、規則、目標；包含他人 bodies 摘要、`recent_public_speeches`、當前 tick、`shield_open`）；加入 INV-5 自動檢查；檔案範圍：`src/ring_of_hands/world_model/observation.py`、`tests/world_model/test_observation.py`
- [ ] 2.4 實作 `EventLog`：append-only JSONL writer、flush on close、在 dry-run 與真實執行皆可用；檔案範圍：`src/ring_of_hands/world_model/event_log.py`、`tests/world_model/test_event_log.py`

## 3. Rules Engine 實作

- [ ] 3.1 實作按鈕按壓規則：`press_button(world, body_id, button_id)` 判定 `body_id==button_id`、鄰接檢查（`chebyshev_distance<=1`）、死亡／亮燈；對應 rules-engine spec 的按壓 Scenarios；檔案範圍：`src/ring_of_hands/rules_engine/button_rule.py`、`tests/rules_engine/test_button_rule.py`
- [ ] 3.2 實作戒指觸碰規則：前置條件檢查、`body_id==6` 判定 WIN、否則 FAIL(ring_paradox)；檔案範圍：`src/ring_of_hands/rules_engine/ring_rule.py`、`tests/rules_engine/test_ring_rule.py`
- [ ] 3.3 實作移動與碰撞規則、`speak` 規則（含 `enable_realtime_chat` 路由 hook）、`die` 規則；檔案範圍：`src/ring_of_hands/rules_engine/move_rule.py`、`src/ring_of_hands/rules_engine/speak_rule.py`、`src/ring_of_hands/rules_engine/death_rule.py`、`tests/rules_engine/test_move_rule.py`、`tests/rules_engine/test_speak_rule.py`、`tests/rules_engine/test_death_rule.py`
- [ ] 3.4 實作 post-tick 終局判定：6 燈齊亮→開防護窗、`unreachable_six_lights` 提前 FAIL、`timeout`；檔案範圍：`src/ring_of_hands/rules_engine/outcome.py`、`tests/rules_engine/test_outcome.py`
- [ ] 3.5 實作 Invariants 執行期檢查（INV-1、INV-3、INV-4、INV-5、INV-6、INV-7、INV-8），違反時 raise `InvariantViolation(inv_id, detail)` 並寫 event log；檔案範圍：`src/ring_of_hands/rules_engine/invariants.py`、`tests/rules_engine/test_invariants.py`

## 4. LLM Client 抽象

- [ ] 4.1 定義 `LLMClient` Protocol 與資料結構（request / response / cache metadata）；檔案範圍：`src/ring_of_hands/llm/base.py`、`tests/llm/test_base.py`
- [ ] 4.2 實作 `AnthropicClient`：包裝 `anthropic` SDK、套用 `cache_control={"type":"ephemeral"}` 到 system blocks、timeout 30s、重試機制；檔案範圍：`src/ring_of_hands/llm/anthropic_client.py`、`tests/llm/test_anthropic_client.py`
- [ ] 4.3 實作 `FakeAnthropicClient`：讀取 fixture（YAML/JSON）並回傳預錄 response；支援 cache metadata 模擬；檔案範圍：`src/ring_of_hands/llm/fake_client.py`、`tests/llm/test_fake_client.py`

## 5. Script Generator 實作

- [ ] 5.1 定義 `Script`、`ScriptEvent`、`Persona`、`DeathCause` Pydantic 型別（`frozen=True`，INV-2）；檔案範圍：`src/ring_of_hands/script_generator/types.py`、`tests/script_generator/test_types.py`
- [ ] 5.2 實作 prompt 組裝器：依目標 pov_id、persona、世界環境、prior_life 產生 LLM input（對 prior_life_block 套用 `cache_control`）；檔案範圍：`src/ring_of_hands/script_generator/prompt_builder.py`、`tests/script_generator/test_prompt_builder.py`
- [ ] 5.3 實作時間一致性驗證器：比對 `script_n` 與 `script_{n-1}`，輸出 `ValidationResult(valid, diff)`；檔案範圍：`src/ring_of_hands/script_generator/validator.py`、`tests/script_generator/test_validator.py`
- [ ] 5.4 實作 `ScriptGenerator.generate_all()`：依序 pov_1~5 呼叫 LLM、驗證、retry；超過 `max_retries` 寫 `issues.md` 並 raise；檔案範圍：`src/ring_of_hands/script_generator/generator.py`、`tests/script_generator/test_generator.py`

## 6. POV Manager 實作

- [ ] 6.1 定義 `PovContext`（`pov_id`、`persona`、`prior_life`、`script`、`is_alive`）與 `PovManager` 骨架；contexts/scripts 以 `MappingProxyType` 暴露；檔案範圍：`src/ring_of_hands/pov_manager/types.py`、`src/ring_of_hands/pov_manager/manager.py`、`tests/pov_manager/test_types.py`
- [ ] 6.2 實作劇本執行器 `tick_scripted_povs(tick)`：pov_1~5 依序查找 `t==tick` 事件、dispatch、略過 corpse；檔案範圍：`src/ring_of_hands/pov_manager/script_executor.py`、`tests/pov_manager/test_script_executor.py`
- [ ] 6.3 實作自由 Agent 呼叫 `tick_free_agent(tick)`：observe + decide + dispatch（pov_6）；解析失敗降級為 WaitAction；檔案範圍：`src/ring_of_hands/pov_manager/free_agent_runner.py`、`tests/pov_manager/test_free_agent_runner.py`
- [ ] 6.4 實作即時對話路由 `request_realtime_reply()`：組裝 pov_k prompt、呼叫 project-agent、衝突檢查、降級為模糊回應；檔案範圍：`src/ring_of_hands/pov_manager/realtime_chat.py`、`tests/pov_manager/test_realtime_chat.py`
- [ ] 6.5 實作死亡事件訂閱：接收 `DeathEvent` 更新 `is_alive=False`（僅 pov-manager 內部可改）；檔案範圍：`src/ring_of_hands/pov_manager/death_handler.py`、`tests/pov_manager/test_death_handler.py`

## 7. Project Agent 實作

- [ ] 7.1 實作 `ProjectAgent.decide(observation)`：組裝 system blocks（persona / rules / prior_life，皆帶 `cache_control`）、user message（observation）、呼叫 LLMClient、解析結構化 action；檔案範圍：`src/ring_of_hands/project_agent/agent.py`、`tests/project_agent/test_agent.py`
- [ ] 7.2 實作 action 解析器：嚴格 JSON schema 驗證（Pydantic）；解析失敗 raise `ActionParseError`；檔案範圍：`src/ring_of_hands/project_agent/action_parser.py`、`tests/project_agent/test_action_parser.py`
- [ ] 7.3 實作 `ProjectAgent.realtime_reply(pov_id, ...)`：對 pov_1~5 提供即時對話生成；錯誤處理同 decide；檔案範圍：`src/ring_of_hands/project_agent/realtime.py`、`tests/project_agent/test_realtime.py`
- [ ] 7.4 實作 LLM 呼叫失敗與連續失敗熔斷：timeout、網路錯誤、3 次連續失敗 raise `LLMUnavailableError` 並寫 issues.md；檔案範圍：`src/ring_of_hands/project_agent/error_handling.py`、`tests/project_agent/test_error_handling.py`
- [ ] 7.5 實作 cache metrics 記錄：每次呼叫後以 structlog 輸出 `cache_read_input_tokens`、`cache_creation_input_tokens`、`usage` 等；檔案範圍：`src/ring_of_hands/project_agent/metrics.py`、`tests/project_agent/test_metrics.py`

## 8. Scenario Runner 實作

- [ ] 8.1 定義 `ScenarioConfig`（Pydantic v2，含所有可配置欄位）、`ScenarioSummary`；檔案範圍：`src/ring_of_hands/scenario_runner/types.py`、`tests/scenario_runner/test_types.py`
- [ ] 8.2 實作 config 載入器：YAML + `.env` 合併、Pydantic 驗證、不合法時 raise `ConfigValidationError`；檔案範圍：`src/ring_of_hands/scenario_runner/config_loader.py`、`tests/scenario_runner/test_config_loader.py`
- [ ] 8.3 實作主流程 `ScenarioRunner.run()`：依序完成 config 驗證 → LLMClient／ProjectAgent 建立 → `script_generator.generate_all()` → `WorldEngine` + `PovManager` 初始化 → tick 迴圈 → 終局判定 → summary 輸出；檔案範圍：`src/ring_of_hands/scenario_runner/runner.py`、`tests/scenario_runner/test_runner.py`
- [ ] 8.4 實作 CLI (`cli.py`) 的 `run` 子指令：解析 `--config`、`--dry-run`、`--log-level`；串接 `ScenarioRunner.run()`；非零 exit code 處理；檔案範圍：`src/ring_of_hands/cli.py`、`tests/cli/test_cli.py`
- [ ] 8.5 實作 summary 與 logs 輸出：`logs/events_<ts>.jsonl`、`logs/run_<ts>.log`（structlog）、`logs/summary_<ts>.json`；關卡失敗亦 flush；檔案範圍：`src/ring_of_hands/scenario_runner/logging_setup.py`、`src/ring_of_hands/scenario_runner/summary.py`、`tests/scenario_runner/test_summary.py`

## 9. 整合測試與 Dry-run

- [ ] 9.1 撰寫整合測試 `test_full_win_path`：使用 FakeAnthropicClient + `tests/fixtures/dry_run.yaml`，從 CLI 層級跑完 happy path；驗證 `outcome.result="WIN"`、event log 格式、summary 欄位；檔案範圍：`tests/integration/test_full_win_path.py`、`tests/fixtures/dry_run.yaml`（如需微調）
- [ ] 9.2 撰寫整合測試 `test_timeout_fail_path`：pov_6 永遠 WaitAction → FAIL(timeout)；檔案範圍：`tests/integration/test_timeout_fail_path.py`
- [ ] 9.3 撰寫整合測試 `test_ring_paradox_fail_path`：stub 讓非 body_6 在 6 燈齊亮後搶先 touch_ring → FAIL(ring_paradox)；檔案範圍：`tests/integration/test_ring_paradox_fail_path.py`
- [ ] 9.4 撰寫整合測試 `test_unreachable_six_lights`：stub body_3 死亡且 button_3 未亮 → 提前 FAIL；檔案範圍：`tests/integration/test_unreachable_six_lights.py`
- [ ] 9.5 撰寫整合測試 `test_script_generation_failure`：FakeAnthropicClient 回傳無法通過驗證的 scripts 三次 → 寫 issues.md、CLI 非零退出；檔案範圍：`tests/integration/test_script_generation_failure.py`

## 10. 文件與最終校驗

- [ ] 10.1 撰寫 `README.md`：專案目的（註明壁水羽作《端腦》攜手之戒）、技術棧、目錄樹（標註 6 個 capability 對應模組）、快速開始（`./docker/build.sh` → 填 `.env` → `./run.sh --dry-run` → `./run.sh`）、測試指令（`./run.sh pytest`）、指向 `openspec/changes/recreate-duannao-ring-of-hands/` 的連結；檔案範圍：`README.md`
- [ ] 10.2 依本 change 的 `spec.md` 逐項自我比對，在 `tasks.md` 完成前進行最終 spec 覆核（只讀 openspec/changes 與 src/、tests/、configs/、docker/、README.md）；若發現範圍外需要改動的檔案（例如 `CLAUDE.md`）MUST 寫入 `issues.md` 而非直接改動；檔案範圍：`openspec/changes/recreate-duannao-ring-of-hands/issues.md`（僅在必要時新增；否則不動）
- [ ] 10.3 執行 `./run.sh pytest` 確認所有單元與整合測試通過；產出測試 summary 由 Specialist 附在 task commit message；本 task 不新增實作檔，僅為驗證關卡；檔案範圍：無新增（僅執行測試）
