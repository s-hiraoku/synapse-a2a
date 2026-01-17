"""
Error Detection for CLI Output

Detects error patterns in CLI output and determines task status.
"""

import re
from dataclasses import dataclass


@dataclass
class TaskError:
    """A2A-compatible error structure"""

    code: str
    message: str
    data: dict | None = None


# Error patterns with their codes
# Order matters: more specific patterns should come first
ERROR_PATTERNS: list[tuple[str, str, str]] = [
    # System errors (specific)
    (r"command not found", "COMMAND_NOT_FOUND", "Command not found"),
    (r"permission denied", "PERMISSION_DENIED", "Permission denied"),
    (r"no such file or directory", "FILE_NOT_FOUND", "File or directory not found"),
    (r"connection refused", "CONNECTION_REFUSED", "Connection refused"),
    (r"timeout|timed out", "TIMEOUT", "Operation timed out"),
    # API/Network errors (before generic error patterns)
    (r"rate limit|too many requests", "RATE_LIMITED", "Rate limit exceeded"),
    (r"unauthorized|authentication failed", "AUTH_ERROR", "Authentication failed"),
    (r"api error|api failure", "API_ERROR", "API error"),
    # Agent refusal patterns (AI-specific)
    (
        r"I cannot|I can't|I'm unable to|I am unable to",
        "AGENT_REFUSED",
        "Agent refused the request",
    ),
    (
        r"I don't have|I do not have",
        "AGENT_CAPABILITY_MISSING",
        "Agent lacks required capability",
    ),
    (r"not allowed|not permitted", "NOT_PERMITTED", "Action not permitted"),
    # Generic error patterns (last - catch-all)
    (r"\bfatal\b[:\s]", "FATAL_ERROR", "Fatal error occurred"),
    (r"\bexception\b[:\s]", "EXCEPTION", "Exception occurred"),
    (r"\bfailed\b[:\s]", "EXECUTION_FAILED", "Execution failed"),
    (r"\berror\b[:\s]", "CLI_ERROR", "CLI reported an error"),
]


def detect_error(output: str | None) -> TaskError | None:
    """
    Detect error patterns in CLI output.

    Args:
        output: CLI output text to analyze

    Returns:
        TaskError if error detected, None otherwise
    """
    if not output:
        return None

    # Analyze last portion of output (most recent content)
    # This helps avoid false positives from earlier error mentions
    recent_output = output[-3000:] if len(output) > 3000 else output

    for pattern, code, message in ERROR_PATTERNS:
        match = re.search(pattern, recent_output, re.IGNORECASE)
        if match:
            # Get surrounding context (50 chars before and after)
            start = max(0, match.start() - 50)
            end = min(len(recent_output), match.end() + 50)
            context = recent_output[start:end].strip()

            return TaskError(
                code=code,
                message=message,
                data={"context": context, "pattern": pattern},
            )

    return None


def detect_task_status(output: str) -> tuple[str, TaskError | None]:
    """
    Determine task status based on output analysis.

    Args:
        output: CLI output text

    Returns:
        Tuple of (status, error) where status is 'completed' or 'failed'
    """
    error = detect_error(output)

    if error:
        return "failed", error

    return "completed", None


INPUT_REQUIRED_PATTERNS = [
    r"\?\s*$",  # Ends with ?
    r"\[y/n\]\s*$",  # y/n confirmation
    r"\[yes/no\]\s*$",  # yes/no confirmation
    r"enter\s+.*:\s*$",  # Enter X:
    r"please\s+(provide|enter|input|specify)",  # Please provide/enter
    r"waiting\s+for\s+input",  # Waiting for input
    r"press\s+(enter|any key)",  # Press enter
    r"continue\?\s*$",  # Continue?
]


def is_input_required(output: str) -> bool:
    """
    Detect if the CLI is waiting for user input.

    Args:
        output: CLI output text

    Returns:
        True if input appears to be required
    """
    if not output:
        return False

    last_lines = output.strip().split("\n")[-3:]
    last_content = "\n".join(last_lines)

    return any(
        re.search(pattern, last_content, re.IGNORECASE)
        for pattern in INPUT_REQUIRED_PATTERNS
    )
