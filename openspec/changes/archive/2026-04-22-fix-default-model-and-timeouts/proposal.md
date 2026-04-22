# Proposal: fix-default-model-and-timeouts

## Intent（意圖）

上個 change `migrate-to-claude-cli-subprocess` 於 2026-04-22 真跑驗收時（見
`openspec/changes/archive/2026-04-22-migrate-to-claude-cli-subprocess/issues.md`
最末條「[使用者驗收] 2026-04-22T00:50:00」）暴露兩個與遷移無關、屬專案預設值
錯誤的問題，導致預設設定下的乾淨安裝無法完成一場關卡：

1. **HIGH — 預設模型 `claude-sonnet-4-7` 不存在**。2026-04 當前 Claude 4.X
   家族為 Sonnet 4.6、Opus 4.7、Haiku 4.5；不存在 sonnet-4-7。CLI 回應
   `api_error_status:404 "model may not exist"`，subprocess `returncode=1`，
   `ClaudeCLIClient` 僅能轉出 `CLIProcessError(cli_nonzero_exit:1)`，終端
   使用者看到的是晦澀的非零退出碼，而非明確的「模型錯誤」訊息。
2. **MED — 預設 `llm_timeout_seconds=30` 對劇本生成不足**。`pov_1` 劇本
   （長 prompt + 結構化 JSON + 5-event 閉環）實測耗時 60–180 秒；30 秒
   timeout 導致 `script_generator.generate_all()` 在第 1 份劇本就被
   `CLITimeoutError` 打斷，關卡無法進入 tick 迴圈。

本 change 將所有相關 default 從錯誤值（`claude-sonnet-4-7`、`30` 秒）改為
正確值（`claude-sonnet-4-6`、`180` 秒），使「乾淨 clone 後 `./run.sh`」這條
smoke path 再次可用，並同步 spec 中出現相同字面值的 Scenario。

## Scope（範圍）

**會改動**：

- `configs/default.yaml`：`llm_timeout_seconds`、`project_agent_model`
- `.env.example`：`PROJECT_AGENT_MODEL` 範例值、（新增）`CLAUDE_CLI_TIMEOUT_SECONDS`
  範例值
- `src/ring_of_hands/scenario_runner/config_loader.py`：`project_agent_model`
  與 `llm_timeout_seconds` 的 fallback default
- `src/ring_of_hands/scenario_runner/types.py`：`ScenarioConfig.llm_timeout_seconds`、
  `ScenarioConfig.project_agent_model` 的 Pydantic default
- `src/ring_of_hands/script_generator/types.py`：`ScriptGeneratorConfig.model`、
  `ScriptGeneratorConfig.llm_timeout_seconds` 的 Pydantic default
- `src/ring_of_hands/llm/claude_cli_client.py`：`ClaudeCLIClient.__init__` 的
  `timeout_seconds` default
- `src/ring_of_hands/llm/base.py`：`LLMRequest.timeout_seconds` 的 Pydantic default
- 對應單元測試：驗證「無 env 無 YAML 時取到 `claude-sonnet-4-6` / `180.0`」、
  env 覆寫優先、YAML 覆寫優先
- Spec delta（同步 default 字面值）：
  - `specs/project-agent/spec.md`（`claude-sonnet-4-7` → `claude-sonnet-4-6`
    共 3 處；timeout `30` → `180`）
  - `specs/scenario-runner/spec.md`（`.env.example` 範例值）
  - `specs/script-generator/spec.md`（若有 default 提及，對齊之；經盤點目前
    無直接字面值，delta 僅新增 default 宣告 Scenario）

**不會改動**：

- `.claude/commands/opsx/*.md` 與 `.claude/skills/openspec-*/SKILL.md` 現有未
  commit 的本機修改（與本 change 無關，不納入 scope）。
- `.env`（本機檔、不在 repo）。修復 default 後 `.env` 中為驗收而臨時加入的
  `PROJECT_AGENT_MODEL=claude-sonnet-4-6`、`CLAUDE_CLI_TIMEOUT_SECONDS=180`
  兩行 override 於修復後「理論上可以刪除」，但由 Specialist 宣告於 Final
  Report 告知使用者，不列入 tasks。
- 任何 LLM 呼叫邏輯、retry 策略、cache metadata、logging schema。

## Success Criteria（成功標準）

- 於全新 clone 的 repo（無 `.env` override，僅填 `ANTHROPIC_API_KEY`）執行
  `./run.sh`，`script_generator.generate_all()` 能在 180 秒內完成第 1 份
  劇本，scenario-runner 進入 tick 迴圈、產生至少一筆 `OutcomeEvent`。
- `python -m ring_of_hands.cli run --config configs/default.yaml --dry-run`
  單元測試通過（FakeAnthropicClient 路徑不受 default 改動影響）。
- 新增單元測試於以下情境全部通過：
  - 空 `.env` 空 `yaml overrides` → `ScenarioConfig.project_agent_model ==
    "claude-sonnet-4-6"`、`llm_timeout_seconds == 180.0`。
  - `PROJECT_AGENT_MODEL=claude-opus-4-7` env → override 生效。
  - YAML `llm_timeout_seconds: 60` → override 生效。
  - `ClaudeCLIClient()` 無參數建立 → `self._timeout_seconds == 180.0`。
  - `LLMRequest(model=..., system_blocks=(), messages=())` 預設 →
    `timeout_seconds == 180.0`。
- `openspec/specs/{project-agent,scenario-runner,script-generator}/spec.md`
  內再無 `claude-sonnet-4-7` 字串、無 `預設 30 秒 timeout` 字串。

## Risks（風險）

- **風險 1**：`LLMRequest.timeout_seconds` default 改為 180 後，pov_6 每 tick
  的 decide 若發生真實網路逾時，使用者將等待較久（原為 30 秒）。
  **緩解**：現有「連續 3 次失敗中止」保護仍在；且 decide prompt 短、正常
  延遲 <5 秒，180 秒純為上界。
- **風險 2**：單元測試中若有 hard-code `30.0` 或 `claude-sonnet-4-7` 的
  assertion，會因 default 改動而 fail。
  **緩解**：Specialist 負責 `rg` 搜尋並同步修復；Verifier 跑全部測試。
- **風險 3**：使用者本機 `.env` 仍寫 `PROJECT_AGENT_MODEL=claude-sonnet-4-7`。
  **緩解**：不是 spec 風險（本機檔），但 Specialist 於 Final Report 提醒
  使用者。

## Non-Goals / Out of Scope

- **Per-call-kind timeout（方案 B）**：另分 `decide`/`generate_script` 兩組
  timeout default，本 change 不做。見 design.md「Architecture Decision」段
  對方案 A vs B 的取捨理由。若未來有需求再開新 change。
- **script-generator 閉環驗證策略**：上次驗收的「LOW — LLM 跨 pov 產出
  不一致，`ScriptValidationError`」屬設計層議題，需重構驗證/重試邏輯，
  **不納入本 change**。
- **模型清單白名單**：目前 `project-agent` Requirement「模型版本可配置」
  使用通配規則 `claude-sonnet-4-*`、`claude-opus-4-*`、`claude-haiku-4-*`
  允許，不引入具體版本白名單。
- `.env` 的清理與 `.claude/` 既有本機修改。

## Rollback Strategy（回滾策略）

改動皆為單檔字面值替換（Python default argument、YAML 值、Pydantic default）；
回滾策略為 `git revert <merge-commit>`，無資料遷移、無 API 變更、無外部相依
升級。若 180 秒 timeout 被證實對 decide call 過長，回滾後可改走方案 B。
