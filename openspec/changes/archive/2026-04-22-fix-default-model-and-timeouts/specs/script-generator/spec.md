# Delta for script-generator

本 delta 對應 change `fix-default-model-and-timeouts`，新增「`ScriptGenerator
Config` 預設值鎖定」的 Requirement，確保劇本生成在無任何 override 的情況下：

1. 使用合法存在的模型（`claude-sonnet-4-6`）。
2. 獲得足以完成長 prompt + 結構化 JSON 產出的 timeout（180 秒；pov_1 實測
   上限 180 秒）。

此 delta 不更動既有 Requirement 的本文（`script-generator/spec.md` 既有
Requirement 未出現相關字面值），僅追加一條新 Requirement 鎖定 default。

## ADDED Requirements

### Requirement: ScriptGeneratorConfig 預設值鎖定

The system SHALL 保證 `ScriptGeneratorConfig` 在未顯式指定欄位時，預設值
為：

- `model = "claude-sonnet-4-6"`
- `llm_timeout_seconds = 180.0`

此預設值反映 2026-04 Anthropic 服務上實際存在的 Sonnet 4.X 模型名稱，以
及 pov_1 劇本生成的實測延遲上界（60–180 秒）。對應的 baseline
「LLM 呼叫介面抽象」Requirement 未變，Script generation 仍透過 `LLMClient`
介面委派。

#### Scenario: 無參建立 ScriptGeneratorConfig 採用預設模型

- **WHEN** 呼叫 `ScriptGeneratorConfig()`（不傳任何欄位）
- **THEN** `config.model == "claude-sonnet-4-6"`

#### Scenario: 無參建立 ScriptGeneratorConfig 採用預設 timeout

- **WHEN** 呼叫 `ScriptGeneratorConfig()`（不傳任何欄位）
- **THEN** `config.llm_timeout_seconds == 180.0`

#### Scenario: 顯式覆寫 timeout 不受預設影響

- **WHEN** 呼叫 `ScriptGeneratorConfig(llm_timeout_seconds=90.0)`
- **THEN** `config.llm_timeout_seconds == 90.0`
- **AND** `config.model == "claude-sonnet-4-6"`（未傳的欄位仍採預設）
