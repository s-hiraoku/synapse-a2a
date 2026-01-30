"""
Startup TUI animation for Synapse A2A.

Displays an animated banner and startup information when launching an agent.
"""

import sys
import time

# Synapse ASCII art logo
SYNAPSE_LOGO = r"""
 ███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ███████╗███████╗
 ██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗██╔════╝██╔════╝
 ███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝███████╗█████╗
 ╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝ ╚════██║██╔══╝
 ███████║   ██║   ██║ ╚████║██║  ██║██║     ███████║███████╗
 ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝
"""

# Smaller logo for narrow terminals
SYNAPSE_LOGO_SMALL = r"""
 ╔═╗╦ ╦╔╗╔╔═╗╔═╗╔═╗╔═╗
 ╚═╗╚╦╝║║║╠═╣╠═╝╚═╗║╣
 ╚═╝ ╩ ╝╚╝╩ ╩╩  ╚═╝╚═╝
"""

# Colors
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"


def get_terminal_width() -> int:
    """Get terminal width, default to 80 if unable to detect."""
    try:
        import shutil

        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def print_animated_logo() -> None:
    """Print the Synapse logo with left-to-right sweep animation."""
    width = get_terminal_width()

    # Choose logo based on terminal width
    logo = SYNAPSE_LOGO if width >= 70 else SYNAPSE_LOGO_SMALL

    lines = logo.strip().split("\n")
    max_len = max(len(line) for line in lines)

    # Sweep from left to right
    for col in range(max_len + 1):
        # Move cursor to top of logo area
        if col > 0:
            sys.stdout.write(f"\x1b[{len(lines)}A")  # Move up

        for line in lines:
            # Print characters up to current column
            visible = line[:col]
            sys.stdout.write(f"\r{CYAN}{visible}{RESET}\x1b[K\n")

        sys.stdout.flush()
        time.sleep(0.008)  # Fast but visible sweep

    # Brief pause after logo completes
    time.sleep(0.3)


def print_startup_info(
    agent_type: str,
    agent_id: str,
    port: int,
    animate: bool = True,
) -> None:
    """
    Print startup information with optional animation.

    Args:
        agent_type: Type of agent (claude, gemini, etc.)
        agent_id: Full agent ID
        port: Port number
        animate: Whether to animate the output
    """
    width = get_terminal_width()

    def print_line(text: str, color: str = "", indent: int = 1) -> None:
        """Print a line (no character animation, just instant)."""
        prefix = " " * indent
        print(f"{color}{prefix}{text}{RESET}" if color else f"{prefix}{text}")

    # Print logo
    if animate:
        print_animated_logo()
    else:
        logo = SYNAPSE_LOGO if width >= 70 else SYNAPSE_LOGO_SMALL
        for line in logo.strip().split("\n"):
            print(f"{CYAN}{line}{RESET}")

    print()

    # Subtitle
    subtitle = "Agent-to-Agent Communication Framework"
    print_line(f"{DIM}{subtitle}{RESET}")
    print()

    # Separator
    separator = "─" * min(60, width - 4)
    print_line(f"{DIM}{separator}{RESET}")
    print()

    # Agent info box
    print_line(f"{BOLD}Agent Configuration{RESET}")
    print_line(f"  Type:     {GREEN}{agent_type}{RESET}")
    print_line(f"  ID:       {GREEN}{agent_id}{RESET}")
    print_line(f"  Port:     {GREEN}{port}{RESET}")
    print()

    # A2A Endpoints
    print_line(f"{BOLD}A2A Endpoints{RESET}")
    print_line(
        f"  Agent Card: {DIM}http://localhost:{port}/.well-known/agent.json{RESET}"
    )
    print_line(f"  Tasks API:  {DIM}http://localhost:{port}/tasks/send{RESET}")
    print()

    # Quick reference
    print_line(f"{BOLD}Quick Reference{RESET}")
    print_line(f"  {YELLOW}synapse list{RESET}              Show running agents")
    print_line(
        f'  {YELLOW}synapse send{RESET} {DIM}<agent> "msg"{RESET}  Send message to agent'
    )
    print_line(f"  {YELLOW}Ctrl+C{RESET} {DIM}(twice){RESET}            Exit")
    print()

    # Final separator
    print_line(f"{DIM}{separator}{RESET}")
    print()


def show_startup_animation(
    agent_type: str,
    agent_id: str,
    port: int,
    skip_animation: bool = False,
) -> None:
    """
    Show the full startup animation sequence.

    Args:
        agent_type: Type of agent
        agent_id: Full agent ID
        port: Port number
        skip_animation: If True, skip animation effects
    """
    # Clear screen for clean start (optional)
    # sys.stdout.write("\x1b[2J\x1b[H")

    print_startup_info(
        agent_type=agent_type,
        agent_id=agent_id,
        port=port,
        animate=not skip_animation,
    )


if __name__ == "__main__":
    # Demo
    show_startup_animation(
        agent_type="claude",
        agent_id="synapse-claude-8100",
        port=8100,
    )
