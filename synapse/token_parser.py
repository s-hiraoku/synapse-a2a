"""Token/Cost Tracking skeleton for Synapse A2A.

Provides a registry-based architecture for parsing token usage from
agent PTY output. Parsers are registered per agent type in _PARSERS.
Initial release ships with no parsers (skeleton only).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class TokenUsage:
    """Token usage data extracted from agent output."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


# Registry of agent-type → parser function.
# Each parser takes raw PTY output and returns TokenUsage or None.
# Initially empty — parsers will be added per agent as TUI formats stabilise.
_PARSERS: dict[str, Callable[[str], TokenUsage | None]] = {}


def parse_tokens(agent_type: str | None, output: Any) -> TokenUsage | None:
    """Parse token usage from agent output.

    Args:
        agent_type: Agent type identifier (e.g. "claude", "gemini").
        output: Raw PTY output text.

    Returns:
        TokenUsage if parsing succeeded, None otherwise.
        Never raises — all exceptions are caught and logged to stderr.
    """
    try:
        if not agent_type or not isinstance(output, str) or not output:
            return None

        parser = _PARSERS.get(agent_type)
        if parser is None:
            return None

        return parser(output)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        print(
            f"Warning: token parsing failed for {agent_type}: {e}",
            file=sys.stderr,
        )
        return None
