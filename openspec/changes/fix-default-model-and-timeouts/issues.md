# Issues: fix-default-model-and-timeouts

## [Verifier] 2026-04-22T00:00:00 [嚴重度: LOW] 缺少 script-generator「顯式覆寫 timeout 不受預設影響」Scenario 的單元測試

### 問題描述

`openspec/changes/fix-default-model-and-timeouts/specs/script-generator/spec.md`
的 ADDED Requirement「ScriptGeneratorConfig 預設值鎖定」下，第三個
Scenario「顯式覆寫 timeout 不受預設影響」要求：

- `ScriptConfig(llm_timeout_seconds=90.0)` → `config.llm_timeout_seconds == 90.0`
- `AND` `config.model == "claude-sonnet-4-6"`（未傳欄位仍採預設）

目前 `tests/script_generator/test_types.py` 僅覆蓋無參 default
(`test_script_generator_config_defaults`)，未覆蓋「顯式覆寫單一欄位、
其他欄位仍取 default」的行為。

Verifier PASS 條件之一為「每個 scenario 都有對應的測試」，故即使
Pydantic 的覆寫行為屬 framework-level 已保證，仍需補一條顯式測試
以與 spec 鎖定一致。

### 修正清單

#### [MUST FIX] 1. 於 `tests/script_generator/test_types.py` 新增 `test_script_generator_config_override_timeout`

- **檔案**: `tests/script_generator/test_types.py`
- **內容**: 新增一個測試，驗證 `ScriptConfig(llm_timeout_seconds=90.0)` 後：
  - `cfg.llm_timeout_seconds == 90.0`
  - `cfg.model == "claude-sonnet-4-6"`
- **對應 Scenario**: script-generator spec「顯式覆寫 timeout 不受預設影響」

### 其他 Scope / 品質觀察（非阻擋，僅紀錄）

- 工作區 `.claude/commands/opsx/*`、`.claude/skills/openspec-*` 有未 commit
  的本機修改，但與本 change 範圍無關（proposal.md 已明確排除），非 scope
  creep。
- `notes/progress-2026-04-18.md` 為 untracked，屬本機筆記，非 scope creep。
- 3 個 commit message 皆合 Conventional Commits + 50/72 規範。
