"""Terminal jump functionality for switching to agent terminal windows.

Supports macOS terminal emulators: iTerm2, Terminal.app, Ghostty, VS Code.
Also supports tmux sessions and Zellij (with limitations).
"""

from __future__ import annotations

import contextlib
import logging
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
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


def _get_spec_field(parts: list[str], index: int) -> str:
    """Return parts[index] if it exists and is non-empty, else empty string."""
    if index < len(parts):
        return parts[index]
    return ""


def _pane_title(agent_spec: str) -> str:
    """Return a tmux pane title like ``synapse(claude)`` or ``synapse(claude:Reviewer)``."""
    parts = agent_spec.split(":")
    profile = parts[0]
    name = _get_spec_field(parts, 1)
    label = f"{profile}:{name}" if name else profile
    return f"synapse({label})"


def _build_agent_command(
    agent_spec: str,
    *,
    use_exec: bool = False,
    tool_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    fallback_tool_args: list[str] | None = None,
) -> str:
    """Parse 'profile[:name[:role[:skill_set[:port]]]]' and build command.

    ``--no-setup`` and ``--headless`` are always added so that spawned
    agents skip interactive prompts (name/role setup and approval).

    Example: 'claude:Reviewer:code review:dev-set:8105'
    -> 'synapse claude --no-setup --headless --name Reviewer --role "code review" --skill-set dev-set --port 8105'

    Args:
        agent_spec: Colon-separated agent spec string.
        use_exec: If True, prefix command with ``exec`` so the shell process
            is replaced by the agent process.  When the agent exits the
            terminal session ends, which automatically closes the
            pane/tab/window in iTerm2 and Terminal.app.  Ghostty uses
            ``; exit`` instead (see ``create_ghostty_window``).
        tool_args: Extra arguments to pass through to the underlying CLI tool
            (e.g., ``["--dangerously-skip-permissions"]``).  Appended after
            a ``--`` separator.
        extra_env: Additional environment variables to set for the spawned
            agent (e.g., ``{"SYNAPSE_WORKTREE_PATH": "/path"}``).
        fallback_tool_args: If not None, produces a shell-level fallback
            that retries with these tool_args when the primary command
            fails within the first 10 seconds (e.g., resume session not
            found).  Failures after 10 seconds are not retried to avoid
            silently restarting long-running agents.
    """
    parts = agent_spec.split(":")
    profile = parts[0]
    # Use the same Python environment as the parent process to avoid
    # resolving a different globally-installed `synapse` executable.
    # Unset CLAUDECODE to prevent nested-session detection when spawning
    # from within a Claude Code session (PR #238).
    prefix = "exec " if use_exec else ""
    env_vars = ""
    if extra_env:
        env_vars = " ".join(f"{k}={shlex.quote(v)}" for k, v in extra_env.items()) + " "
    base_cmd = f"{prefix}env -u CLAUDECODE {env_vars}{shlex.quote(sys.executable)} -m synapse.cli {profile}"

    name = _get_spec_field(parts, 1)
    role = _get_spec_field(parts, 2)
    skill_set = _get_spec_field(parts, 3)
    port = _get_spec_field(parts, 4)

    # Always skip interactive prompts — spawned agents run unattended.
    base_cmd += " --no-setup --headless"

    if name:
        base_cmd += f" --name {shlex.quote(name)}"
    if role:
        base_cmd += f" --role {shlex.quote(role)}"
    if skill_set:
        base_cmd += f" --skill-set {shlex.quote(skill_set)}"
    if port:
        if not port.isdigit():
            raise ValueError(f"Port must be numeric: {port}")
        base_cmd += f" --port {port}"

    # Build main command with tool_args
    cmd = base_cmd
    if tool_args:
        cmd += " -- " + " ".join(shlex.quote(a) for a in tool_args)

    # Wrap with a time-guarded fallback (POSIX ``date +%s``).
    # Only retries if the primary command fails within 10 seconds.
    if fallback_tool_args is not None:
        fallback_cmd = base_cmd
        if fallback_tool_args:
            fallback_cmd += " -- " + " ".join(
                shlex.quote(a) for a in fallback_tool_args
            )
        cmd = (
            f"_st=$(date +%s); ({cmd}); "
            f"_ec=$?; _el=$(( $(date +%s) - _st )); "
            f"if [ $_ec -ne 0 ] && [ $_el -lt 10 ]; "
            f"then ({fallback_cmd}); fi"
        )

    return cmd


def _is_tty_in_tmux(tty_device: str) -> bool:
    """Check if a TTY device belongs to a tmux pane."""
    if not tty_device or not shutil.which("tmux"):
        return False
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_tty}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return tty_device in result.stdout.strip().split("\n")
    except (subprocess.TimeoutExpired, OSError):
        pass
    return False


def _detect_agent_terminal(agent_info: dict[str, Any]) -> str | None:
    """Detect the terminal application for a specific agent.

    Walks the agent's parent process chain to determine which terminal
    app launched it, rather than relying on the current process env.

    Args:
        agent_info: Agent info with optional tty_device and pid.

    Returns:
        Terminal app name or None.
    """
    pid = agent_info.get("pid")

    # Walk parent process chain to find the launching terminal
    if pid:
        terminal = _detect_terminal_from_pid_chain(int(pid))
        if terminal:
            return terminal

    # Fallback: check if TTY is in tmux (TTY already resolved by caller)
    tty = agent_info.get("tty_device") or ""
    if tty and _is_tty_in_tmux(tty):
        return "tmux"

    # Last resort: env-based detection
    return detect_terminal_app()


def _detect_terminal_from_pid_chain(pid: int) -> str | None:
    """Walk the parent process chain to find the terminal application.

    Args:
        pid: Process ID to start from.

    Returns:
        Terminal app name or None.
    """
    # Map of process name patterns to terminal app names
    patterns = {
        "tmux": "tmux",
        "Visual Studio Code": "VSCode",
        "Code Helper": "VSCode",
        "Electron": None,  # Too generic, skip
        "iTerm2": "iTerm2",
        "iTermServer": "iTerm2",
        "ghostty": "Ghostty",
        "Terminal": "Terminal",
        "zellij": "zellij",
    }

    try:
        current_pid = pid
        visited: set[int] = set()
        while current_pid > 1 and current_pid not in visited:
            visited.add(current_pid)
            result = subprocess.run(
                ["ps", "-p", str(current_pid), "-o", "ppid=,comm="],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                break
            line = result.stdout.strip()
            parts = line.split(None, 1)
            if len(parts) < 2:
                break
            ppid_str, comm = parts
            try:
                ppid = int(ppid_str)
            except ValueError:
                break

            for pattern, terminal in patterns.items():
                if pattern in comm:
                    if terminal is not None:
                        return terminal
                    break

            current_pid = ppid
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _resolve_tty_from_pid(pid: int) -> str:
    """Resolve TTY device from a process PID by walking up the process tree.

    Uses `ps` to find the controlling TTY for the given PID or its ancestors.
    This is useful when tty_device was not stored in the registry.

    Returns:
        TTY device path (e.g., '/dev/ttys003') or empty string if not found.
    """
    try:
        # Get the TTY for this PID and its parent chain
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        tty = result.stdout.strip()
        if tty and tty != "??" and tty != "-":
            # ps returns short form like 'ttys003', convert to /dev/ path
            if not tty.startswith("/dev/"):
                tty = f"/dev/{tty}"
            return tty
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return ""


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
    # Resolve TTY once upfront and enrich agent_info for all downstream use
    tty_device = agent_info.get("tty_device") or ""
    if not tty_device:
        pid = agent_info.get("pid")
        if pid:
            tty_device = _resolve_tty_from_pid(int(pid))
            if tty_device:
                agent_info = {**agent_info, "tty_device": tty_device}

    if terminal_app is None:
        terminal_app = _detect_agent_terminal(agent_info)

    if terminal_app is None:
        logger.warning("Could not detect terminal application")
        return False

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


def _classify_terminal_string(term: str) -> str | None:
    """Classify a terminal identifier string to an app name.

    Args:
        term: Lowercased terminal identifier (e.g., from TERM_PROGRAM or tmux client_termname).

    Returns:
        Canonical terminal app name or None.
    """
    if "ghostty" in term:
        return "Ghostty"
    if "iterm" in term:
        return "iTerm2"
    if "apple_terminal" in term or term == "xterm-256color":
        return "Terminal"
    return None


def _detect_tmux_host_terminal() -> str | None:
    """Detect the terminal application hosting tmux.

    Queries tmux clients to determine the outer terminal app.

    Returns:
        Canonical app name (e.g., 'Ghostty', 'iTerm2'), or None if unknown.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-clients", "-F", "#{client_termname}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                classified = _classify_terminal_string(line.strip().lower())
                if classified:
                    return classified
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: check TERM_PROGRAM from the launching environment
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    return _classify_terminal_string(term_program)


def _activate_app(app_name: str) -> None:
    """Bring a macOS application to the foreground."""
    if sys.platform != "darwin":
        return
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        subprocess.run(
            ["open", "-a", app_name],
            capture_output=True,
            timeout=5,
        )


def _switch_terminal_tab(terminal_app: str, session_id: str) -> None:
    """Switch the terminal tab to match the tmux session.

    For Ghostty: clicks the radio button in the tab bar whose name
    starts with the tmux session ID.
    For iTerm2: uses AppleScript to select the tab matching the session.
    """
    if sys.platform != "darwin":
        return

    escaped_session = _escape_applescript_string(session_id)

    if terminal_app == "Ghostty":
        script = f'''
tell application "System Events"
    tell process "ghostty"
        set tg to tab group 1 of window 1
        repeat with r in (every radio button of tg)
            if name of r starts with "{escaped_session}" then
                click r
                exit repeat
            end if
        end repeat
    end tell
end tell
'''
        _run_applescript(script)
    elif terminal_app == "iTerm2":
        script = f'''
tell application "iTerm2"
    activate
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                if name of s starts with "{escaped_session}" then
                    select t
                    return
                end if
            end repeat
        end repeat
    end repeat
end tell
'''
        _run_applescript(script)


def _jump_tmux(agent_info: dict[str, Any]) -> bool:
    """Jump to tmux window/pane containing the agent.

    Uses tmux pane TTY tracking to find the right pane,
    then activates the host terminal application.

    Args:
        agent_info: Agent info with tty_device and agent_id.

    Returns:
        True if successful, False otherwise.
    """
    if not shutil.which("tmux"):
        logger.warning("tmux not found")
        return False

    # TTY should already be resolved by jump_to_terminal(); use as-is
    tty_device = agent_info.get("tty_device") or ""

    if not tty_device:
        logger.warning(
            f"No TTY device for agent {agent_info.get('agent_id')} "
            f"(pid={agent_info.get('pid')})"
        )
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

                # Activate the host terminal and switch to the correct tab
                session_id = pane_id.split(":")[0]
                host_terminal = _detect_tmux_host_terminal()
                if host_terminal:
                    _activate_app(host_terminal)
                    _switch_terminal_tab(host_terminal, session_id)

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


# ============================================================
# Pane Creation Functions (B6: Auto-Spawn Split Panes)
# ============================================================


@dataclass
class _TmuxAutoSplit:
    """Result of auto-split analysis for tmux."""

    target_pane: str  # pane ID to split (e.g. "%0")
    flag: str  # "-h" or "-v"


def _get_tmux_spawn_panes() -> str:
    """Read SYNAPSE_SPAWN_PANES from the tmux session environment.

    Falls back to os.environ for testing / non-tmux contexts.
    """
    try:
        result = subprocess.run(
            ["tmux", "show-environment", "SYNAPSE_SPAWN_PANES"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip()
            if "=" in line:
                return line.split("=", 1)[1]
    except Exception:
        pass
    # Fallback to process env (for tests)
    return os.environ.get("SYNAPSE_SPAWN_PANES", "")


def _get_tmux_auto_split() -> _TmuxAutoSplit | None:
    """Determine the best pane to split and the direction for tiling.

    Finds the largest pane by area and splits it along its longer axis:
    - Wider than tall → "-h" (split horizontally, side-by-side)
    - Taller than wide → "-v" (split vertically, stacked)

    Returns None if detection fails.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-F", "#{pane_id} #{pane_width} #{pane_height}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Filter by spawn zone if set
        spawn_panes_str = _get_tmux_spawn_panes()
        spawn_panes = set(spawn_panes_str.split(",")) if spawn_panes_str else None

        pane_rows: list[tuple[str, int, int]] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) != 3:
                continue
            pane_id, w_str, h_str = parts
            pane_rows.append((pane_id, int(w_str), int(h_str)))

        # Ignore stale spawn-zone state when it does not match the current tmux panes.
        if spawn_panes and not any(
            pane_id in spawn_panes for pane_id, _, _ in pane_rows
        ):
            spawn_panes = None

        best_pane = None
        best_area = -1
        best_w = 0
        best_h = 0
        for pane_id, w, h in pane_rows:
            # Only consider spawn zone panes when zone exists
            if spawn_panes and pane_id not in spawn_panes:
                continue
            area = w * h
            if area > best_area:
                best_area = area
                best_pane = pane_id
                best_w = w
                best_h = h

        if best_pane is None:
            return None

        # Split along the longer axis for balanced tiling
        # tmux cells are roughly 2:1 (width:height), so adjust
        flag = "-h" if best_w >= best_h * 2 else "-v"
        return _TmuxAutoSplit(target_pane=best_pane, flag=flag)
    except Exception:
        return None


def _get_iterm2_session_count() -> int | None:
    """Return the number of sessions (panes) in the current iTerm2 tab.

    Returns None if not inside iTerm2 or if the command fails.
    """
    script = (
        'tell application "iTerm2" to tell current window to '
        "return count of sessions of current tab"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except Exception:
        pass
    return None


def _get_ghostty_split_direction(layout: str = "auto") -> str:
    """Return the split direction for the next Ghostty pane.

    For layout="auto", alternates between "right" and "down" based on
    the number of existing panes (tracked via SYNAPSE_GHOSTTY_PANE_COUNT
    env var, since Ghostty has no pane query API).

    Returns "right" or "down".
    """
    if layout != "auto":
        return "right"
    # Ghostty has no CLI to query pane count; use env counter.
    try:
        count = int(os.environ.get("SYNAPSE_GHOSTTY_PANE_COUNT", "1"))
    except (ValueError, TypeError):
        count = 1
    # Update counter for next spawn in same shell session
    os.environ["SYNAPSE_GHOSTTY_PANE_COUNT"] = str(count + 1)
    return "right" if count % 2 == 1 else "down"


def _get_zellij_pane_count() -> int:
    """Return a best-effort pane count using an env-backed counter."""
    try:
        return max(1, int(os.environ.get("SYNAPSE_ZELLIJ_PANE_COUNT", "1")))
    except (TypeError, ValueError):
        return 1


def _bump_zellij_pane_count(added: int = 1) -> None:
    """Increment the env-backed Zellij pane counter by *added* panes."""
    current = _get_zellij_pane_count() or 1
    os.environ["SYNAPSE_ZELLIJ_PANE_COUNT"] = str(current + added)


def create_tmux_panes(
    agents: list[str],
    layout: str = "split",
    all_new: bool = False,
    tool_args: list[str] | None = None,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
    fallback_tool_args: list[str] | None = None,
) -> list[str]:
    """Generate tmux commands to create split panes for each agent.

    Args:
        agents: List of agent specs.
        layout: Layout style ("split", "horizontal", "vertical", "auto").
        all_new: If True, even the first agent gets a new pane.
        tool_args: Extra arguments passed through to underlying CLI tools.
        cwd: Working directory for new panes. Defaults to os.getcwd().
        extra_env: Additional environment variables for spawned agents.

    Returns:
        List of tmux command strings to execute.
    """
    if not agents:
        return []

    cwd = cwd or os.getcwd()
    safe_cwd = shlex.quote(cwd)

    commands: list[str] = []

    def _set_title(agent_spec: str) -> None:
        """Append a ``select-pane -T`` command that labels the current pane."""
        commands.append(f"tmux select-pane -T {shlex.quote(_pane_title(agent_spec))}")

    # Enable pane border with title display so pane names are visible.
    # Use window-level option to avoid affecting other tmux sessions.
    commands.append("tmux set-option -q pane-border-status top")
    commands.append('tmux set-option -q pane-border-format "#{pane_title}"')
    # Prevent spawned processes from overwriting pane titles via OSC escapes.
    commands.append("tmux set-option -q allow-rename off")

    # For "auto" layout, use spawn zone tiling:
    # - First spawn (no SYNAPSE_SPAWN_PANES): split current pane with -h
    # - Subsequent spawns: find largest pane in spawn zone and split it
    auto_split: _TmuxAutoSplit | None = None
    if layout == "auto":
        spawn_panes = _get_tmux_spawn_panes()
        if spawn_panes:
            auto_split = _get_tmux_auto_split()
            split_flag = auto_split.flag if auto_split else "-h"
        else:
            split_flag = "-h"
    elif layout == "horizontal":
        split_flag = "-h"
    else:
        split_flag = "-v"

    effective_count = len(agents) + (1 if all_new else 0)

    # Resolve the pane to split into.
    # For "auto" layout, target the largest pane (for balanced tiling).
    # For other layouts, target the current pane (TMUX_PANE).
    if auto_split:
        target_flag = f"-t {auto_split.target_pane} "
    else:
        pane_target = os.environ.get("TMUX_PANE", "")
        target_flag = f"-t {pane_target} " if pane_target else ""

    if all_new:
        # Everyone gets a new pane
        for i, agent_spec in enumerate(agents):
            cmd = _build_agent_command(
                agent_spec,
                tool_args=tool_args,
                extra_env=extra_env,
                fallback_tool_args=fallback_tool_args,
            )
            safe_cmd = shlex.quote(cmd)
            # For "split" layout with 3+ agents, alternate -h/-v for tiling
            if layout == "split" and effective_count > 2:
                flag = "-h" if i % 2 == 0 else "-v"
            else:
                flag = split_flag
            commands.append(
                f"tmux split-window {flag} {target_flag}-c {safe_cwd} {safe_cmd}"
            )
            _set_title(agent_spec)
    else:
        # First agent runs in current pane (via terminal input buffer)
        first_cmd = _build_agent_command(
            agents[0],
            tool_args=tool_args,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )
        safe_first = shlex.quote(f"cd {shlex.quote(cwd)} && {first_cmd}")
        commands.append(f"tmux send-keys {safe_first} Enter")
        _set_title(agents[0])

        # Remaining agents get new panes, scoped to source pane
        for i, agent_spec in enumerate(agents[1:]):
            cmd = _build_agent_command(
                agent_spec,
                tool_args=tool_args,
                extra_env=extra_env,
                fallback_tool_args=fallback_tool_args,
            )
            safe_cmd = shlex.quote(cmd)
            if layout == "split" and effective_count > 2:
                flag = "-h" if i % 2 == 0 else "-v"
            else:
                flag = split_flag
            commands.append(
                f"tmux split-window {flag} {target_flag}-c {safe_cwd} {safe_cmd}"
            )
            _set_title(agent_spec)

    return commands


def create_iterm2_panes(
    agents: list[str],
    all_new: bool = False,
    tool_args: list[str] | None = None,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
    fallback_tool_args: list[str] | None = None,
    layout: str = "vertical",
) -> str:
    """Generate AppleScript to create iTerm2 panes for each agent.

    Args:
        agents: List of agent specs.
        all_new: If True, even the first agent gets a new pane.
        tool_args: Extra arguments passed through to underlying CLI tools.
        cwd: Working directory for new panes. Defaults to os.getcwd().
        extra_env: Additional environment variables for spawned agents.
        layout: Layout style. "auto" alternates split direction based on
            existing session count. "vertical"/"horizontal" force direction.

    Returns:
        AppleScript string.
    """
    if not agents:
        return ""

    # Determine split direction per agent for balanced tiling.
    # Query session count once (for "auto" layout) and use index offset.
    base_session_count = _get_iterm2_session_count() if layout == "auto" else None

    def _split_dir_for(index: int) -> str:
        if layout == "auto":
            effective = (base_session_count or 1) + index
            return "horizontally" if effective % 2 == 0 else "vertically"
        if layout == "horizontal":
            return "horizontally"
        if layout == "vertical":
            return "vertically"
        return "vertically" if index % 2 == 0 else "horizontally"

    cwd = cwd or os.getcwd()
    quoted_cwd = shlex.quote(cwd)

    def _cd_prefix(cmd: str) -> str:
        return f"cd {quoted_cwd} && {cmd}"

    if all_new:
        lines = [
            'tell application "iTerm2"',
            "  tell current window",
            "    tell current session of current tab",
        ]
        for i, agent_spec in enumerate(agents):
            full_cmd = _build_agent_command(
                agent_spec,
                use_exec=True,
                tool_args=tool_args,
                extra_env=extra_env,
                fallback_tool_args=fallback_tool_args,
            )
            escaped = _escape_applescript_string(_cd_prefix(full_cmd))
            split_direction = _split_dir_for(i)
            lines.extend(
                [
                    f"      set newSession to (split {split_direction} with default profile)",
                    "      tell newSession",
                    f'        write text "{escaped}"',
                    "      end tell",
                ]
            )
        lines.append("    end tell")
        lines.append("  end tell")
        lines.append("end tell")
    else:
        first_cmd = _build_agent_command(
            agents[0],
            use_exec=True,
            tool_args=tool_args,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )
        lines = [
            'tell application "iTerm2"',
            "  tell current window",
            "    tell current session",
            f'      write text "{_escape_applescript_string(_cd_prefix(first_cmd))}"',
        ]

        for i, agent_spec in enumerate(agents[1:], start=1):
            full_cmd = _build_agent_command(
                agent_spec,
                use_exec=True,
                tool_args=tool_args,
                extra_env=extra_env,
                fallback_tool_args=fallback_tool_args,
            )
            escaped = _escape_applescript_string(_cd_prefix(full_cmd))
            split_direction = _split_dir_for(i)
            lines.extend(
                [
                    "    end tell",
                    f"    set newSession to (split {split_direction} with default profile)",
                    "    tell newSession",
                    f'      write text "{escaped}"',
                ]
            )

        lines.extend(
            [
                "    end tell",
                "  end tell",
                "end tell",
            ]
        )

    return "\n".join(lines)


def create_terminal_app_tabs(
    agents: list[str],
    all_new: bool = False,
    tool_args: list[str] | None = None,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
    fallback_tool_args: list[str] | None = None,
) -> list[str]:
    """Generate commands to open Terminal.app tabs for each agent.

    Terminal.app doesn't support split panes, so we use tabs.

    Args:
        agents: List of agent specs.
        all_new: If True, even the first agent gets a new tab.
        tool_args: Extra arguments passed through to underlying CLI tools.
        cwd: Working directory for new tabs. Defaults to os.getcwd().
        extra_env: Additional environment variables for spawned agents.

    Returns:
        List of osascript command strings.
    """
    cwd = cwd or os.getcwd()
    commands: list[str] = []

    for i, agent_spec in enumerate(agents):
        full_cmd = _build_agent_command(
            agent_spec,
            use_exec=True,
            tool_args=tool_args,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )
        escaped = _escape_applescript_string(f"cd {shlex.quote(cwd)} && {full_cmd}")
        target = "" if (i == 0 and not all_new) else " in front window"
        commands.append(
            f'osascript -e \'tell application "Terminal" to '
            f'do script "{escaped}"{target}\''
        )

    return commands


def create_zellij_panes(
    agents: list[str],
    layout: str = "split",
    all_new: bool = False,
    tool_args: list[str] | None = None,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
    fallback_tool_args: list[str] | None = None,
) -> list[str]:
    """Generate zellij commands to create panes for each agent.

    Args:
        agents: List of agent specs.
        layout: Layout style ("split", "horizontal", "vertical", "auto").
        all_new: Ignored for zellij as it always opens new panes.
        tool_args: Extra arguments passed through to underlying CLI tools.
        cwd: Working directory for new panes. Defaults to os.getcwd().
        extra_env: Additional environment variables for spawned agents.

    Returns:
        List of zellij command strings to execute.
    """
    if not agents:
        return []

    cwd = cwd or os.getcwd()
    safe_cwd = shlex.quote(cwd)

    commands: list[str] = []

    # For "auto" layout, query existing pane count for direction
    auto_pane_count = None
    if layout == "auto":
        auto_pane_count = _get_zellij_pane_count()

    def _direction_for(index: int) -> str:
        if layout == "auto":
            # Use existing pane count + index offset for alternation
            effective = (auto_pane_count or 1) + index
            return "right" if effective % 2 == 1 else "down"
        if layout == "horizontal":
            return "right"
        if layout == "vertical":
            return "down"
        # split: alternate for balanced tiling (index 0 is skipped by caller)
        return "right" if index % 2 == 1 else "down"

    for i, agent_spec in enumerate(agents):
        profile = agent_spec.split(":")[0]
        full_cmd = _build_agent_command(
            agent_spec,
            tool_args=tool_args,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )

        if i == 0 and layout != "auto":
            commands.append(
                f"zellij run --close-on-exit --cwd {safe_cwd} --name synapse-{profile} -- {full_cmd}"
            )
            continue

        direction = _direction_for(i)
        commands.append(
            f"zellij run --close-on-exit --cwd {safe_cwd} --direction {direction} --name synapse-{profile} -- {full_cmd}"
        )

    # Update pane counter by the number of agents actually spawned
    _bump_zellij_pane_count(len(agents))

    return commands


def create_ghostty_window(
    agents: list[str],
    tool_args: list[str] | None = None,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
    fallback_tool_args: list[str] | None = None,
    layout: str = "right",
) -> list[str]:
    """Generate commands to create Ghostty split panes for each agent.

    Uses AppleScript to trigger Ghostty's ``Cmd+D`` keybinding
    (``new_split:right``) or ``Cmd+Shift+D`` (``new_split:down``).

    Note:
        ``open -na Ghostty`` must NOT be used — it spawns a separate
        process which can close or disrupt existing windows/tabs.

    Args:
        agents: List of agent specs.
        tool_args: Extra arguments passed through to underlying CLI tools.
        cwd: Working directory for new panes. Defaults to os.getcwd().
        extra_env: Additional environment variables for spawned agents.
        layout: "auto" alternates right/down based on pane count.
            "right" always splits right, anything else splits down.

    Returns:
        List of osascript command strings to execute.
    """
    cwd = cwd or os.getcwd()

    commands: list[str] = []

    for i, agent_spec in enumerate(agents):
        if layout == "auto":
            direction = _get_ghostty_split_direction(layout)
        elif layout in ("right", "horizontal"):
            direction = "right"
        elif layout in ("down", "vertical"):
            direction = "down"
        elif layout == "split":
            direction = "right" if i % 2 == 0 else "down"
        else:
            direction = "right"

        if direction == "right":
            split_keystroke = '    keystroke "d" using {command down}'
        else:
            split_keystroke = '    keystroke "d" using {command down, shift down}'
        # Do NOT use exec here — Ghostty injects commands via clipboard
        # paste (Cmd+V), and exec is unreliable with this method.
        full_cmd = _build_agent_command(
            agent_spec,
            use_exec=False,
            tool_args=tool_args,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )
        cd_cmd = f"cd {shlex.quote(cwd)} && {full_cmd}; exit"
        escaped = _escape_applescript_string(cd_cmd)
        # Trigger Ghostty split, then paste command via clipboard.
        # Using clipboard + Cmd+V instead of keystroke for the command
        # because keystroke can mangle characters (e.g. hyphens in
        # --no-setup) when typing long strings.
        script = (
            'tell application "Ghostty" to activate\n'
            'tell application "System Events" to tell process "Ghostty"\n'
            f"{split_keystroke}\n"
            "end tell\n"
            "delay 0.5\n"
            f'set the clipboard to "{escaped}"\n'
            'tell application "System Events" to tell process "Ghostty"\n'
            '    keystroke "v" using {command down}\n'
            "    keystroke return\n"
            "end tell"
        )
        commands.append(f"osascript -e {shlex.quote(script)}")

    return commands


def create_panes(
    agents: list[str],
    layout: str = "split",
    terminal_app: str | None = None,
    all_new: bool = False,
    tool_args: list[str] | None = None,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
    fallback_tool_args: list[str] | None = None,
) -> list[str]:
    """Create panes for multiple agents using the detected terminal.

    Args:
        agents: List of agent specs.
        layout: Layout style.
        terminal_app: Terminal to use. Auto-detected if None.
        all_new: If True, all agents start in new panes/tabs.
        tool_args: Extra arguments passed through to underlying CLI tools.
        cwd: Working directory for new panes. Defaults to os.getcwd().
        extra_env: Additional environment variables for spawned agents
            (e.g., worktree metadata).
        fallback_tool_args: If not None, shell-level fallback tool_args
            used when the primary command fails (e.g., resume session
            not found).

    Returns:
        List of commands to execute.
    """
    if terminal_app is None:
        terminal_app = detect_terminal_app()

    if terminal_app == "tmux":
        return create_tmux_panes(
            agents,
            layout,
            all_new=all_new,
            tool_args=tool_args,
            cwd=cwd,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )
    elif terminal_app == "iTerm2":
        script = create_iterm2_panes(
            agents,
            all_new=all_new,
            tool_args=tool_args,
            cwd=cwd,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
            layout=layout,
        )
        if not script:
            return []
        return [f"osascript -e {shlex.quote(script)}"]
    elif terminal_app == "Terminal":
        return create_terminal_app_tabs(
            agents,
            all_new=all_new,
            tool_args=tool_args,
            cwd=cwd,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )
    elif terminal_app == "zellij":
        return create_zellij_panes(
            agents,
            layout,
            all_new=all_new,
            tool_args=tool_args,
            cwd=cwd,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
        )
    elif terminal_app == "Ghostty":
        return create_ghostty_window(
            agents,
            tool_args=tool_args,
            cwd=cwd,
            extra_env=extra_env,
            fallback_tool_args=fallback_tool_args,
            layout=layout,
        )

    # Unsupported terminal - return empty list
    logger.warning(
        f"Terminal '{terminal_app or 'unknown'}' does not support pane creation. "
        f"Supported: tmux, iTerm2, Terminal.app, Ghostty, zellij"
    )
    return []
