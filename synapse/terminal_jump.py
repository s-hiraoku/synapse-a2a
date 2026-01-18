"""Terminal jump functionality for switching to agent terminal windows.

Supports macOS terminal emulators: iTerm2, Terminal.app, Ghostty.
Also supports tmux sessions.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)


def detect_terminal_app() -> str | None:
    """Detect the current terminal application.

    Returns:
        Terminal app name ('iTerm2', 'Terminal', 'Ghostty', 'VSCode', 'tmux')
        or None.
    """
    # Check for tmux first (works across platforms)
    if os.environ.get("TMUX"):
        return "tmux"

    # Check TERM_PROGRAM environment variable (set by most terminals)
    term_program = os.environ.get("TERM_PROGRAM", "")

    # Map TERM_PROGRAM values to terminal names
    term_map = {
        "vscode": "VSCode",
        "iTerm.app": "iTerm2",
        "Apple_Terminal": "Terminal",
        "ghostty": "Ghostty",
    }

    return term_map.get(term_program)


def get_supported_terminals() -> list[str]:
    """Get list of supported terminal applications.

    Returns:
        List of supported terminal app names.
    """
    return ["iTerm2", "Terminal", "Ghostty", "VSCode", "tmux"]


def jump_to_terminal(
    agent_info: dict[str, Any],
    terminal_app: str | None = None,
) -> bool:
    """Jump to the terminal window running the specified agent.

    Args:
        agent_info: Agent info dictionary containing:
            - tty_device: TTY device path (e.g., /dev/ttys001)
            - agent_id: Agent identifier
            - pid: Process ID (optional, for tmux)
        terminal_app: Terminal app to use. If None, auto-detect.

    Returns:
        True if jump was successful, False otherwise.
    """
    if terminal_app is None:
        terminal_app = detect_terminal_app()

    if terminal_app is None:
        logger.warning("Could not detect terminal application")
        return False

    tty_device = agent_info.get("tty_device")
    agent_id = agent_info.get("agent_id", "unknown")

    if terminal_app == "tmux":
        return _jump_tmux(agent_info)
    elif terminal_app == "iTerm2":
        return _jump_iterm2(tty_device, agent_id)
    elif terminal_app == "Terminal":
        return _jump_terminal_app(tty_device, agent_id)
    elif terminal_app == "Ghostty":
        return _jump_ghostty(tty_device, agent_id)
    elif terminal_app == "VSCode":
        return _jump_vscode(tty_device, agent_id)
    else:
        logger.warning(f"Unsupported terminal app: {terminal_app}")
        return False


def _run_applescript(script: str) -> bool:
    """Run an AppleScript and return success status.

    Args:
        script: AppleScript code to execute.

    Returns:
        True if script executed successfully, False otherwise.
    """
    if not shutil.which("osascript"):
        logger.warning("osascript not found - AppleScript not available")
        return False

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning(f"AppleScript failed: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("AppleScript timed out")
        return False
    except Exception as e:
        logger.warning(f"AppleScript error: {e}")
        return False


def _jump_iterm2(tty_device: str | None, agent_id: str) -> bool:
    """Jump to iTerm2 window/tab containing the agent.

    Uses AppleScript to find the session with matching TTY.

    Args:
        tty_device: TTY device path (e.g., /dev/ttys001).
        agent_id: Agent identifier for logging.

    Returns:
        True if successful, False otherwise.
    """
    if not tty_device:
        logger.warning(f"No TTY device for agent {agent_id}")
        return False

    # AppleScript to find and activate iTerm2 session by TTY
    script = f"""
    tell application "iTerm2"
        activate
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if tty of s is "{tty_device}" then
                        select t
                        select s
                        return "found"
                    end if
                end repeat
            end repeat
        end repeat
        return "not found"
    end tell
    """

    return _run_applescript(script)


def _jump_terminal_app(tty_device: str | None, agent_id: str) -> bool:
    """Jump to Terminal.app window/tab containing the agent.

    Uses AppleScript to find the tab with matching TTY.

    Args:
        tty_device: TTY device path (e.g., /dev/ttys001).
        agent_id: Agent identifier for logging.

    Returns:
        True if successful, False otherwise.
    """
    if not tty_device:
        logger.warning(f"No TTY device for agent {agent_id}")
        return False

    # AppleScript to find and activate Terminal.app tab by TTY
    script = f"""
    tell application "Terminal"
        activate
        repeat with w in windows
            repeat with t in tabs of w
                if tty of t is "{tty_device}" then
                    set selected of t to true
                    set index of w to 1
                    return "found"
                end if
            end repeat
        end repeat
        return "not found"
    end tell
    """

    return _run_applescript(script)


def _jump_ghostty(tty_device: str | None, agent_id: str) -> bool:
    """Jump to Ghostty window containing the agent.

    Ghostty doesn't expose TTY per window via AppleScript,
    so we just activate the app and rely on window title matching
    or let the user find the right window.

    Args:
        tty_device: TTY device path (unused for Ghostty).
        agent_id: Agent identifier for window title matching.

    Returns:
        True if successful, False otherwise.
    """
    # Ghostty AppleScript support is limited
    # We can activate the app and try to find by window name
    script = f"""
    tell application "Ghostty"
        activate
        -- Try to find window by name containing agent_id
        repeat with w in windows
            if name of w contains "{agent_id}" then
                set index of w to 1
                return "found"
            end if
        end repeat
        return "activated"
    end tell
    """

    return _run_applescript(script)


def _jump_vscode(tty_device: str | None, agent_id: str) -> bool:
    """Jump to VS Code terminal containing the agent.

    VS Code terminals are harder to switch programmatically.
    We try to use the 'code' CLI to focus VS Code window.

    Args:
        tty_device: TTY device path (not used directly).
        agent_id: Agent identifier for logging.

    Returns:
        True if successful, False otherwise.
    """
    if sys.platform == "darwin":
        # On macOS, use AppleScript to activate VS Code
        script = """
        tell application "Visual Studio Code"
            activate
        end tell
        """
        return _run_applescript(script)
    else:
        # On other platforms, try wmctrl or xdotool for X11
        if shutil.which("wmctrl"):
            try:
                subprocess.run(
                    ["wmctrl", "-a", "Visual Studio Code"],
                    capture_output=True,
                    timeout=5,
                )
                return True
            except Exception as e:
                logger.warning(f"wmctrl failed: {e}")

        logger.warning("VS Code terminal jump not supported on this platform")
        return False


def _jump_tmux(agent_info: dict[str, Any]) -> bool:
    """Jump to tmux window/pane containing the agent.

    Uses tmux pane TTY tracking to find the right pane.

    Args:
        agent_info: Agent info with tty_device and agent_id.

    Returns:
        True if successful, False otherwise.
    """
    if not shutil.which("tmux"):
        logger.warning("tmux not found")
        return False

    tty_device = agent_info.get("tty_device")
    if not tty_device:
        logger.warning(f"No TTY device for agent {agent_info.get('agent_id')}")
        return False

    try:
        # List all panes with their TTY
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{session_name}:#{window_index}.#{pane_index} #{pane_tty}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            logger.warning(f"tmux list-panes failed: {result.stderr}")
            return False

        # Find pane with matching TTY
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            pane_id, pane_tty = parts
            if pane_tty == tty_device:
                # Select the pane
                subprocess.run(
                    ["tmux", "select-pane", "-t", pane_id],
                    capture_output=True,
                    timeout=5,
                )
                subprocess.run(
                    ["tmux", "select-window", "-t", pane_id.rsplit(".", 1)[0]],
                    capture_output=True,
                    timeout=5,
                )
                return True

        logger.warning(f"No tmux pane found with TTY {tty_device}")
        return False

    except subprocess.TimeoutExpired:
        logger.warning("tmux command timed out")
        return False
    except Exception as e:
        logger.warning(f"tmux error: {e}")
        return False


def can_jump() -> bool:
    """Check if terminal jump is supported in the current environment.

    Returns:
        True if terminal jump is available, False otherwise.
    """
    terminal = detect_terminal_app()
    return terminal is not None
