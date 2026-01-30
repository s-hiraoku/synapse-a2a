"""
Initial Instruction Approval Module.

Handles the approval prompt for initial instructions before agent startup.
"""

import contextlib
from typing import Literal

ApprovalResponse = Literal["approve", "abort", "skip"]


def parse_approval_response(response: str) -> ApprovalResponse:
    """
    Parse user response from approval prompt.

    Args:
        response: User input from the approval prompt.

    Returns:
        "approve" - Continue with sending instructions
        "abort" - Cancel agent startup
        "skip" - Start agent without sending instructions
    """
    response = response.strip().lower()

    # Empty input (just Enter) = approve
    if not response:
        return "approve"

    # Yes responses
    if response in ("y", "yes"):
        return "approve"

    # No responses
    if response in ("n", "no"):
        return "abort"

    # Skip responses
    if response in ("s", "skip"):
        return "skip"

    # Default to approve for unrecognized input
    return "approve"


def format_approval_prompt(
    agent_id: str,
    port: int,
) -> str:
    """
    Format the approval prompt to display to the user.

    Args:
        agent_id: The agent ID (e.g., "synapse-claude-8100").
        port: The port number.

    Returns:
        Formatted prompt string.
    """
    lines = [
        "",
        f"\x1b[32m[Synapse]\x1b[0m Agent: {agent_id} | Port: {port}",
        "\x1b[32m[Synapse]\x1b[0m Initial instructions will be sent to configure A2A communication.",
        "",
        "Proceed? [Y/n/s(skip)]: ",
    ]

    return "\n".join(lines)


def prompt_for_approval(
    agent_id: str,
    port: int,
) -> ApprovalResponse:
    """
    Display approval prompt and get user response.

    Args:
        agent_id: The agent ID (e.g., "synapse-claude-8100").
        port: The port number.

    Returns:
        User's approval response.
    """
    import sys
    import termios

    prompt = format_approval_prompt(
        agent_id=agent_id,
        port=port,
    )

    # Print prompt (without the final question line)
    prompt_lines = prompt.split("\n")
    for line in prompt_lines[:-1]:
        print(line)

    # Save terminal settings before input
    stdin_fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(stdin_fd)
        settings_saved = True
    except termios.error:
        settings_saved = False

    # Get user input
    try:
        response = input(prompt_lines[-1])
    except (EOFError, KeyboardInterrupt):
        return "abort"
    finally:
        # Restore terminal settings after input
        if settings_saved:
            with contextlib.suppress(termios.error):
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
        # Flush stdin to clear any buffered input
        with contextlib.suppress(termios.error):
            termios.tcflush(stdin_fd, termios.TCIFLUSH)

    return parse_approval_response(response)
