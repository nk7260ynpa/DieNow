# Design: fix-default-model-and-timeouts

## Architecture Decision

### 決策：方案 A — 所有 default 統一拉高至 180 秒、模型統一為 `claude-sonnet-4-6`

**選擇理由**：

- 本 change 定位明確：**修復上個 change 驗收時發現的預設值錯誤**。越收斂
  越好，不引入新抽象。
- 方案 A 的改動型態全部是「字面值替換」：`30 → 180`、`claude-sonnet-4-7
  → claude-sonnet-4-6`，單元測試易寫、回滾容易（見 proposal.md Rollback
  Strategy）。
- 既有「連續 3 次 LLM 失敗中止關卡」的保護仍在（見 `project-agent/spec.md`
  Requirement「LLM 呼叫的錯誤與 Timeout 處理」），180 秒只是單次上界，不會
  讓關卡卡住太久。
- pov_1 劇本實測上限 180 秒，恰好覆蓋；若未來發現仍不夠，再個別調整而非
  提早做複雜抽象。

### 被否決的替代方案

**方案 B — Per-call-kind timeout（`decide`=30s、`generate_script`=180s）**：

- 需要擴充 `LLMRequest` 新增 `kind: Literal["decide", "generate_script"]`
  欄位（或類似 enum），並在 `ClaudeCLIClient.call()` 中依 kind 選擇 timeout。
- 需要擴充 `ScenarioConfig` 至少 2 個欄位：`llm_decide_timeout_seconds`、
  `llm_script_timeout_seconds`；env 變數亦需對應（如 `CLAUDE_CLI_DECIDE_
  TIMEOUT`、`CLAUDE_CLI_SCRIPT_TIMEOUT`），並更新 YAML、.env.example。
- 需要更新 3 處呼叫端（`runner.py` 組 `ScriptGeneratorConfig`、
  `prompt_builder.py` 組 script `LLMRequest`、`project_agent/agent.py`
  組 decide `LLMRequest`）分別傳入對應 timeout。
- Spec delta 會跨 3 個 capability 且大幅改寫 Requirement 內文，超出「修復
  default」的範圍。

**否決原因**：此 change 僅為修復驗收暴露的 default 錯誤。方案 B 是一項正當
的重構，但應以獨立 change 呈現，避免 scope creep。

## Component Design

### 改動的檔案與欄位

| 檔案 | 欄位 / 行 | 原值 | 新值 |
|------|-----------|------|------|
| `configs/default.yaml` | L38 `llm_timeout_seconds` | `30` | `180` |
| `configs/default.yaml` | L47 `project_agent_model` | `"claude-sonnet-4-7"` | `"claude-sonnet-4-6"` |
| `.env.example` | `PROJECT_AGENT_MODEL=` | `claude-sonnet-4-7` | `claude-sonnet-4-6` |
| `.env.example` | （新增示例） | — | `# CLAUDE_CLI_TIMEOUT_SECONDS=180` |
| `src/ring_of_hands/scenario_runner/types.py` | L50 `llm_timeout_seconds` default | `30.0` | `180.0` |
| `src/ring_of_hands/scenario_runner/types.py` | L53 `project_agent_model` default | `"claude-sonnet-4-7"` | `"claude-sonnet-4-6"` |
| `src/ring_of_hands/scenario_runner/config_loader.py` | L110 fallback | `"claude-sonnet-4-7"` | `"claude-sonnet-4-6"` |
| `src/ring_of_hands/scenario_runner/config_loader.py` | L121 fallback | `30.0` | `180.0` |
| `src/ring_of_hands/script_generator/types.py` | L98 `model` default | `"claude-sonnet-4-7"` | `"claude-sonnet-4-6"` |
| `src/ring_of_hands/script_generator/types.py` | L102 `llm_timeout_seconds` default | `30.0` | `180.0` |
| `src/ring_of_hands/llm/claude_cli_client.py` | `ClaudeCLIClient.__init__` `timeout_seconds` | `30.0` | `180.0` |
| `src/ring_of_hands/llm/claude_cli_client.py` | docstring 說明文字 | 提及 `30 秒` 若有 | 同步為 `180 秒` |
| `src/ring_of_hands/llm/base.py` | `LLMRequest.timeout_seconds` default | `30.0` | `180.0` |

### 介面 / 契約變更

- **無對外 API 變動**：所有改動皆是欄位的 default value。呼叫端若顯式傳
  `timeout_seconds=30.0` 者，行為不變；未傳者取新 default 180.0。
- **無 schema 變動**：`LLMRequest`、`ScenarioConfig`、`ScriptGeneratorConfig`
  欄位集合不變，僅 default 改變。
- **`.env.example`** 新增（選擇性）示例註解 `# CLAUDE_CLI_TIMEOUT_SECONDS=180`，
  說明如何覆寫 CLI client 級別的 timeout。實際實作讀取邏輯不在本 change 範圍
  （若目前 `ClaudeCLIClient` 初始化時並未讀 `CLAUDE_CLI_TIMEOUT_SECONDS`，
  此 env 僅為文件示例，不啟動讀取；`.env.example` 的註解為「預留 hook」）。

### 資料流向

不變。沿用：

```
configs/default.yaml + .env
  → config_loader.load_config() → ScenarioConfig
    → ScenarioRunner.__init__()
      → ScriptGeneratorConfig(llm_timeout_seconds=...)
      → ProjectAgent(llm_timeout=...)
        → LLMRequest(timeout_seconds=...)
          → ClaudeCLIClient.call()
```

## Dependencies

- **外部套件**：無新增、無升級。
- **內部模組相依**：無變動。
- **執行環境**：無（仍為 Docker container 內 Python 3.11+）。

## Migration

- **資料遷移**：不需要。
- **向下相容**：對顯式傳入 timeout 或 model 的 caller 完全相容。對使用
  default 的 caller，行為從「30 秒逾時、404 模型錯誤」改為「180 秒逾時、
  合法模型」——此為修復，無相容性風險。
- **使用者本機 `.env`**：若使用者本機 `.env` 仍含 `PROJECT_AGENT_MODEL=
  claude-sonnet-4-7` 的舊 override，系統會因 `project-agent` Requirement
  「模型版本可配置」的通配規則（`claude-sonnet-4-*`）**而通過 config 驗
  證**，但實際 CLI 呼叫仍會 404。Specialist 於 Final Report 提醒使用者
  移除過期 override；不修改 `.env`（屬本機檔）。

## Test Strategy

- **單元測試**（必填）：
  1. `tests/scenario_runner/test_config_loader.py`（既有檔補 case 或新建 case）：
     - `test_default_model_is_sonnet_4_6`：無 env、YAML 無 `project_agent_model`
       → `config.project_agent_model == "claude-sonnet-4-6"`。
     - `test_default_timeout_is_180`：無 env、YAML 無 `llm_timeout_seconds`
       → `config.llm_timeout_seconds == 180.0`。
     - `test_env_overrides_model`：`PROJECT_AGENT_MODEL=claude-opus-4-7` →
       override 生效。
     - `test_yaml_overrides_timeout`：YAML 指定 `llm_timeout_seconds: 60`
       → `config.llm_timeout_seconds == 60.0`。
  2. `tests/llm/test_claude_cli_client.py`（既有）：
     - `test_default_timeout_is_180`：`ClaudeCLIClient()` 無參 →
       `_timeout_seconds == 180.0`。
  3. `tests/llm/test_base.py`（若有；若無則新建）：
     - `test_llm_request_default_timeout_is_180`：`LLMRequest(...)` 無傳
       timeout → `timeout_seconds == 180.0`。
  4. `tests/script_generator/test_types.py`（既有檔補）：
     - `test_script_generator_config_defaults`：`ScriptGeneratorConfig()`
       → `model == "claude-sonnet-4-6"`、`llm_timeout_seconds == 180.0`。

- **回歸測試**：執行 `docker compose run --rm app pytest` 全綠。

- **Smoke test（人工）**：在無 `.env` override 的環境執行 `./run.sh`，
  確認 script_generator 能產出第 1 份劇本，scenario-runner 進入 tick
  主迴圈並產生 `OutcomeEvent`（無需 WIN，只需不因 default 錯誤而失敗）。

## Open Questions

- `CLAUDE_CLI_TIMEOUT_SECONDS` 是否真的要在 `ClaudeCLIClient` 初始化時讀？
  本 change 採「僅於 `.env.example` 加註解、不實作讀取」的極小改動，避免
  scope 擴大。若未來需要，另開 change 處理。
