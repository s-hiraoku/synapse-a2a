"""Multi-agent coordination patterns.

Declarative coordination patterns that let agents act autonomously
within defined rules. Unlike workflows (imperative step sequences),
patterns define *how agents should behave* rather than *what to do*.

Storage:
- Project scope: ``.synapse/patterns/<name>.yaml``
- User scope: ``~/.synapse/patterns/<name>.yaml``
"""

from __future__ import annotations

from synapse.patterns.base import (
    AgentHandle,
    CoordinationPattern,
    PatternConfig,
    PatternError,
    TaskResult,
)

__all__ = [
    "AgentHandle",
    "CoordinationPattern",
    "PatternConfig",
    "PatternError",
    "TaskResult",
    "BUILTIN_PATTERNS",
    "register_pattern",
]

# Registry of built-in pattern types.
# Each pattern module registers itself here on import.
# Key: pattern type name (e.g. "generator-verifier")
# Value: CoordinationPattern subclass
BUILTIN_PATTERNS: dict[str, type[CoordinationPattern]] = {}


def register_pattern(cls: type[CoordinationPattern]) -> type[CoordinationPattern]:
    """Decorator to register a built-in pattern class."""
    BUILTIN_PATTERNS[cls.name] = cls
    return cls
