"""Terminal jump functionality for switching to agent terminal windows.

Supports macOS terminal emulators: iTerm2, Terminal.app, Ghostty, VS Code.
Also supports tmux sessions and Zellij (with limitations).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _escape_applescript_string(value: str) -> str:
    """Escape a string for safe interpolation into AppleScript.

    Escapes backslashes and double quotes to prevent injection attacks.

    Args:
        value: The string to escape.

    Returns:
        Escaped string safe for use in AppleScript string literals.
    """
    # Escape backslashes first (so we don't double-escape the quote escapes)
    value = value.replace("\\", "\\\\")
    # Escape double quotes
    value = value.replace('"', '\\"')
    return value


def detect_terminal_app() -> str | None:
    """Detect the current terminal application.

    Returns:
        Terminal app name ('iTerm2', 'Terminal', 'Ghostty', 'VSCode', 'tmux')
        or None.
    """
    # Check for tmux first (works across platforms)
    if os.environ.get("TMUX"):
        return "tmux"

    # Check for Zellij
    if os.environ.get("ZELLIJ"):
        return "zellij"

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
    return ["iTerm2", "Terminal", "Ghostty", "VSCode", "tmux", "zellij"]


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
    elif terminal_app == "zellij":
        return _jump_zellij(agent_info)
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


def _run_applescript(script: str, expected_token: str | None = None) -> bool:
    """Run an AppleScript and return success status.

    Args:
        script: AppleScript code to execute.
        expected_token: Optional token to verify in stdout (e.g., "found").
            If provided and not present in output, returns False.

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

        # If expected_token is specified, verify it's in the output
        if expected_token is not None and expected_token not in result.stdout:
            logger.warning(
                f"AppleScript did not return expected token '{expected_token}': "
                f"got {result.stdout.strip()!r}"
            )
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

    # Escape tty_device to prevent AppleScript injection
    safe_tty = _escape_applescript_string(tty_device)

    # AppleScript to find and activate iTerm2 session by TTY
    script = f"""
    tell application "iTerm2"
        activate
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if tty of s is "{safe_tty}" then
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

    return _run_applescript(script, expected_token="found")


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

    # Escape tty_device to prevent AppleScript injection
    safe_tty = _escape_applescript_string(tty_device)

    # AppleScript to find and activate Terminal.app tab by TTY
    script = f"""
    tell application "Terminal"
        activate
        repeat with w in windows
            repeat with t in tabs of w
                if tty of t is "{safe_tty}" then
                    set selected of t to true
                    set index of w to 1
                    return "found"
                end if
            end repeat
        end repeat
        return "not found"
    end tell
    """

    return _run_applescript(script, expected_token="found")


def _jump_ghostty(tty_device: str | None, agent_id: str) -> bool:
    """Jump to Ghostty window containing the agent.

    Ghostty has limited AppleScript support - it doesn't support
    window enumeration or TTY access via AppleScript.

    Note: If running inside tmux, we'll use tmux commands instead
    which can properly switch to the correct pane by TTY.

    Args:
        tty_device: TTY device path (used if tmux is detected).
        agent_id: Agent identifier for logging.

    Returns:
        True if successful, False otherwise.
    """
    # Check if we're inside tmux - if so, use tmux pane switching
    if os.environ.get("TMUX") and tty_device:
        logger.info(f"Ghostty+tmux detected, using tmux for {agent_id}")
        return _jump_tmux({"tty_device": tty_device, "agent_id": agent_id})

    # Ghostty standalone - just activate the app
    # Unfortunately, there's no way to switch to a specific tab via AppleScript
    script = """
    tell application "Ghostty"
        activate
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
                result = subprocess.run(
                    ["wmctrl", "-a", "Visual Studio Code"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return True
                logger.warning(
                    f"wmctrl failed (returncode={result.returncode}): "
                    f"stdout={result.stdout!r}, stderr={result.stderr!r}"
                )
            except subprocess.TimeoutExpired:
                logger.warning("wmctrl command timed out")
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
                pane_result = subprocess.run(
                    ["tmux", "select-pane", "-t", pane_id],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if pane_result.returncode != 0:
                    logger.warning(
                        f"tmux select-pane failed for {pane_id}: {pane_result.stderr}"
                    )
                    return False

                # Select the window
                window_id = pane_id.rsplit(".", 1)[0]
                window_result = subprocess.run(
                    ["tmux", "select-window", "-t", window_id],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if window_result.returncode != 0:
                    logger.warning(
                        f"tmux select-window failed for {window_id}: "
                        f"{window_result.stderr}"
                    )
                    return False

                return True

        logger.warning(f"No tmux pane found with TTY {tty_device}")
        return False

    except subprocess.TimeoutExpired:
        logger.warning("tmux command timed out")
        return False
    except Exception as e:
        logger.warning(f"tmux error: {e}")
        return False


def _jump_zellij(agent_info: dict[str, Any]) -> bool:
    """Jump to Zellij pane containing the agent.

    Note: Zellij CLI does not support focusing a specific pane by ID.
    This function activates the terminal application as a fallback.
    The pane ID is logged for manual navigation reference.

    Args:
        agent_info: Agent info with zellij_pane_id and agent_id.

    Returns:
        True if successful, False otherwise.
    """
    pane_id = agent_info.get("zellij_pane_id")
    agent_id = agent_info.get("agent_id", "unknown")

    # Zellij CLI doesn't support focus-pane-by-id (proposal was rejected).
    # Best we can do is activate the terminal app and log the pane ID.
    if pane_id:
        logger.info(
            f"Zellij pane ID for {agent_id}: {pane_id} "
            "(direct pane focus not supported via CLI)"
        )

    # Try to activate the terminal app (Ghostty, iTerm2, etc.)
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program == "ghostty":
        return _run_applescript('tell application "Ghostty" to activate')
    elif term_program == "iTerm.app":
        return _run_applescript('tell application "iTerm2" to activate')
    elif term_program == "Apple_Terminal":
        return _run_applescript('tell application "Terminal" to activate')

    # No known terminal to activate
    logger.warning(
        f"Zellij detected but cannot focus pane for {agent_id}. "
        f"Pane ID: {pane_id or 'unknown'}"
    )
    return False


def can_jump() -> bool:
    """Check if terminal jump is supported in the current environment.

    Returns:
        True if terminal jump is available, False otherwise.
    """
    terminal = detect_terminal_app()
    return terminal is not None
