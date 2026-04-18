"""Script Generator capability.

依序 (pov_1 → pov_5) 透過 LLM 產生閉環劇本, 每份輸出立即對照 prior_life
驗證時間一致性; 驗證失敗則 retry, 超過上限寫 issues.md 並 raise.
"""

from ring_of_hands.script_generator.generator import (
    ScriptGenerationError,
    ScriptGenerator,
    ScriptValidationError,
)
from ring_of_hands.script_generator.types import (
    DeathCause,
    Persona,
    Script,
    ScriptConfig,
    ScriptEvent,
)
from ring_of_hands.script_generator.validator import ValidationResult, validate_closure

__all__ = [
    "DeathCause",
    "Persona",
    "Script",
    "ScriptConfig",
    "ScriptEvent",
    "ScriptGenerationError",
    "ScriptGenerator",
    "ScriptValidationError",
    "ValidationResult",
    "validate_closure",
]
