# Tasks: fix-default-model-and-timeouts

> 所有任務於 feature branch `opsx/fix-default-model-and-timeouts` 上進行。
> 任何超出各 task 宣告檔案範圍的修改均視為 scope creep；若實作中發現需變
> 更 `README.md`、`CLAUDE.md` 或其他未宣告檔案，寫入 `issues.md` 交 Coordinator。

## Task 1: 更新 configs 與 .env.example 預設值

- **檔案範圍**:
  - `configs/default.yaml`
  - `.env.example`
- **相依**: 無
- **驗收條件**:
  - [ ] `configs/default.yaml` L38 `llm_timeout_seconds` 由 `30` 改為 `180`
  - [ ] `configs/default.yaml` L47 `project_agent_model` 由 `"claude-sonnet-4-7"`
        改為 `"claude-sonnet-4-6"`
  - [ ] `.env.example` 中 `PROJECT_AGENT_MODEL=` 範例由 `claude-sonnet-4-7`
        改為 `claude-sonnet-4-6`
  - [ ] `.env.example` 新增一行註解示例 `# CLAUDE_CLI_TIMEOUT_SECONDS=180`
        （緊接在 `PROJECT_AGENT_MODEL` 區塊後或於 LLM 區塊內適當處）
  - [ ] 全檔 `rg -n 'claude-sonnet-4-7'` 於上述兩檔均無命中
  - [ ] 全檔 `rg -n '\b30\b' configs/default.yaml` 無意外的 timeout 相關命中
  - [ ] 不修改範圍外的檔案

## Task 2: 更新 Pydantic default（scenario-runner 與 script-generator）

- **檔案範圍**:
  - `src/ring_of_hands/scenario_runner/types.py`
  - `src/ring_of_hands/scenario_runner/config_loader.py`
  - `src/ring_of_hands/script_generator/types.py`
- **相依**: Task 1
- **驗收條件**:
  - [ ] `scenario_runner/types.py` L50 `llm_timeout_seconds: float = Field(gt=0.0, default=30.0)`
        的 default 改為 `180.0`
  - [ ] `scenario_runner/types.py` L53 `project_agent_model: str = "claude-sonnet-4-7"`
        改為 `"claude-sonnet-4-6"`
  - [ ] `scenario_runner/config_loader.py` L110 fallback `"claude-sonnet-4-7"`
        改為 `"claude-sonnet-4-6"`
  - [ ] `scenario_runner/config_loader.py` L121 fallback `30.0` 改為 `180.0`
  - [ ] `script_generator/types.py` L98 `model: str = "claude-sonnet-4-7"`
        改為 `"claude-sonnet-4-6"`
  - [ ] `script_generator/types.py` L102 `llm_timeout_seconds: float = 30.0`
        改為 `180.0`
  - [ ] 於三檔執行 `rg -n 'claude-sonnet-4-7|\\b30\\.0\\b'` 僅剩與 default 無關
        的命中（例如 docstring 內描述歷史數字、或明顯非 timeout 的常數）；
        每一處殘留需於 commit message 說明保留理由
  - [ ] 不修改範圍外的檔案

## Task 3: 更新 LLM client 與 LLMRequest 預設 timeout

- **檔案範圍**:
  - `src/ring_of_hands/llm/claude_cli_client.py`
  - `src/ring_of_hands/llm/base.py`
- **相依**: 無（可與 Task 2 併行）
- **驗收條件**:
  - [ ] `claude_cli_client.py` L78 `timeout_seconds: float = 30.0` 改為
        `180.0`
  - [ ] `claude_cli_client.py` 內 docstring 提及 `30 秒` 之處若存在，同步
        更新為 `180 秒`
  - [ ] `base.py` L68 `LLMRequest.timeout_seconds: float = 30.0` 改為 `180.0`
  - [ ] `rg -n 'timeout.*=.*30\.0' src/ring_of_hands/llm/` 無命中（若有殘留，
        於 commit message 說明保留理由）
  - [ ] 不修改範圍外的檔案

## Task 4: 補齊 / 更新單元測試

- **檔案範圍**:
  - `tests/scenario_runner/test_config_loader.py`（既有檔補 case，或於既有
    檔 scope 內的最相近測試檔擴充）
  - `tests/script_generator/test_types.py`（既有檔；若無則於此路徑新建）
  - `tests/llm/test_claude_cli_client.py`（既有檔補 case）
  - `tests/llm/test_base.py`（若已存在則補 case；若無則於此路徑新建）
- **相依**: Task 1、Task 2、Task 3
- **驗收條件**:
  - [ ] 新增 `test_default_model_is_sonnet_4_6`：於空 env、無 YAML override 時，
        `load_config()` 回傳的 `ScenarioConfig.project_agent_model == "claude-sonnet-4-6"`
  - [ ] 新增 `test_default_timeout_is_180`：於空 env、無 YAML override 時，
        `ScenarioConfig.llm_timeout_seconds == 180.0`
  - [ ] 新增 `test_env_overrides_model`：設定 `PROJECT_AGENT_MODEL=claude-opus-4-7`
        → `ScenarioConfig.project_agent_model == "claude-opus-4-7"`
  - [ ] 新增 `test_yaml_overrides_timeout`：YAML 指定 `llm_timeout_seconds: 60`
        → `ScenarioConfig.llm_timeout_seconds == 60.0`
  - [ ] 新增 `test_script_generator_config_defaults`：`ScriptGeneratorConfig()`
        無傳參 → `.model == "claude-sonnet-4-6"`、`.llm_timeout_seconds == 180.0`
  - [ ] 新增 `test_claude_cli_client_default_timeout_is_180`：`ClaudeCLIClient()`
        無傳 `timeout_seconds` → `._timeout_seconds == 180.0`
  - [ ] 新增 `test_llm_request_default_timeout_is_180`：`LLMRequest(model="x",
        system_blocks=(), messages=())` → `.timeout_seconds == 180.0`
  - [ ] 修正任何既有硬編 `30.0` 或 `claude-sonnet-4-7` 的 assertion，使之
        通過新 default
  - [ ] `docker compose run --rm app pytest` 全綠
  - [ ] 不修改範圍外的檔案

## Task 5: 同步 spec delta

- **檔案範圍**:
  - `openspec/changes/fix-default-model-and-timeouts/specs/project-agent/spec.md`
  - `openspec/changes/fix-default-model-and-timeouts/specs/scenario-runner/spec.md`
  - `openspec/changes/fix-default-model-and-timeouts/specs/script-generator/spec.md`
- **相依**: Task 1
- **驗收條件**:
  - [ ] 三份 delta spec 已寫入上述檔案（內容由 Coordinator 產出，Specialist
        僅於後續實作階段確認與實作一致、不需再動）
  - [ ] 各 delta 僅包含 MODIFIED / ADDED / REMOVED 段落，並維持 BDD 格式
  - [ ] 各 Scenario 的字面值（模型名、秒數）與 Task 1–3 的實作一致
- **附註**: 此 task 由 Coordinator 於 `/opsx:propose` 時完成；Specialist
  於 `/opsx:apply` 時**不應**修改這些 delta 檔，除非 Verifier FAIL 的
  `issues.md` 明確要求。

## Commit 切分建議

- Commit 1（Task 1）：`fix(config): 將預設模型改為 sonnet-4-6、timeout 改為 180s`
- Commit 2（Task 2 + Task 3 合併或拆兩個）：`fix(llm): 更新 Pydantic default
  與 LLM client timeout 為 180s`
- Commit 3（Task 4）：`test: 新增預設值與 override 優先序單元測試`
- Commit 5（Task 5 由 Coordinator 於 propose 階段完成，不需 Specialist 再 commit）

## 超出範圍（明確排除）

- 不修改 `.env`、`.claude/commands/opsx/*.md`、`.claude/skills/openspec-*/SKILL.md`
- 不新增 per-call-kind timeout 機制（方案 B，見 design.md）
- 不改 script-generator 閉環驗證策略（LOW 議題，延後）
- 不新增模型白名單
