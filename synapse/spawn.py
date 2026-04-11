"""Spawn agents in terminal panes.

Provides ``prepare_spawn()`` and ``execute_spawn()`` as the two-phase
spawn API, plus the legacy ``spawn_agent()`` wrapper used by both
the ``synapse spawn`` CLI command and the ``POST /spawn`` API endpoint.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.worktree import WorktreeInfo

from synapse.port_manager import PortManager, is_port_available
from synapse.registry import AgentRegistry
from synapse.server import load_profile
from synapse.terminal_jump import (
    _get_tmux_spawn_panes,
    create_panes,
    detect_terminal_app,
)


def _get_tmux_pane_ids() -> set[str]:
    """Return the set of current tmux pane IDs."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return set(result.stdout.strip().splitlines())
    except (OSError, subprocess.SubprocessError):
        pass
    return set()


def _set_tmux_spawn_panes(value: str) -> None:
    """Write SYNAPSE_SPAWN_PANES to the tmux session environment."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            ["tmux", "set-environment", "SYNAPSE_SPAWN_PANES", value],
            capture_output=True,
            timeout=5,
        )


@dataclass
class SpawnResult:
    """Result of a spawn_agent() call."""

    agent_id: str
    port: int
    terminal_used: str
    status: str  # "submitted" | "failed"
    worktree_path: str | None = None
    worktree_branch: str | None = None


@dataclass
class PreparedAgent:
    """Pre-validated agent ready for pane creation.

    Created by ``prepare_spawn()``, consumed by ``execute_spawn()``.
    Holds all resolved parameters (port, worktree, agent_spec, etc.)
    so that ``execute_spawn()`` can batch multiple agents into a single
    ``create_panes()`` call for proper tile layout.
    """

    profile: str
    port: int
    agent_spec: str
    cwd: str
    tool_args: list[str] | None = None
    extra_env: dict[str, str] | None = None
    fallback_tool_args: list[str] | None = None
    worktree_path: str | None = None
    worktree_branch: str | None = None
    #: Internal: worktree info for rollback on failure
    _worktree_info: WorktreeInfo | None = field(default=None, repr=False)

    def to_result(self, terminal_used: str, status: str) -> SpawnResult:
        """Build a SpawnResult from this prepared agent."""
        return SpawnResult(
            agent_id=f"synapse-{self.profile}-{self.port}",
            port=self.port,
            terminal_used=terminal_used,
            status=status,
            worktree_path=self.worktree_path,
            worktree_branch=self.worktree_branch,
        )


def prepare_spawn(
    profile: str,
    port: int | None = None,
    name: str | None = None,
    role: str | None = None,
    skill_set: str | None = None,
    tool_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    worktree: str | bool | None = None,
    fallback_tool_args: list[str] | None = None,
    auto_approve: bool = True,
    branch: str | None = None,
) -> PreparedAgent:
    """Prepare a single agent for spawning (Phase 1: validate & allocate).

    Resolves port, creates worktree if requested, injects auto-approve
    flags, and builds the agent spec string.  Does NOT create any terminal
    panes — that is done by ``execute_spawn()``.

    Args:
        profile: Agent profile name (claude, gemini, codex, etc.).
        port: Explicit port number. Auto-assigned if None.
        name: Custom agent name.
        role: Agent role description.
        skill_set: Skill set to activate.
        tool_args: Extra arguments passed through to the underlying CLI tool.
        extra_env: Extra environment variables injected into the spawned agent.
        worktree: If True, create a worktree with auto-generated name.
            If a string, use it as the worktree name. If None/False, no worktree.
        fallback_tool_args: Shell-level fallback command args on failure.
        auto_approve: If True (default), inject the profile's auto-approve
            CLI flag and set SYNAPSE_AUTO_APPROVE=true in the environment.
        branch: Base branch for worktree creation (e.g. ``renovate/foo``).
            Only used when ``worktree`` is truthy. Defaults to the remote
            default branch when None.

    Returns:
        PreparedAgent ready for execute_spawn().

    Raises:
        FileNotFoundError: If profile is invalid.
        RuntimeError: If port unavailable or ports exhausted.
    """
    # 1. Validate profile and load auto-approve config
    profile_config = load_profile(profile)

    # 2. Resolve port
    if port is not None:
        if not is_port_available(port):
            raise RuntimeError(f"Port {port} is already in use")
    else:
        registry = AgentRegistry()
        pm = PortManager(registry)
        port = pm.get_available_port(profile)
        if port is None:
            raise RuntimeError(pm.format_exhaustion_error(profile))

    # 3. Create worktree if requested (--branch implies --worktree unless opted out)
    if branch and worktree is None:
        worktree = True

    worktree_info = None
    cwd = os.getcwd()
    resolved_extra_env = dict(extra_env or {})

    if worktree:
        from synapse.worktree import create_worktree

        wt_name = worktree if isinstance(worktree, str) else None
        worktree_info = create_worktree(name=wt_name, base_branch=branch)
        cwd = str(worktree_info.path)
        resolved_extra_env.update(
            {
                "SYNAPSE_WORKTREE_PATH": str(worktree_info.path),
                "SYNAPSE_WORKTREE_BRANCH": worktree_info.branch,
                "SYNAPSE_WORKTREE_BASE_BRANCH": worktree_info.base_branch,
            }
        )

    # 4. Auto-approve flag injection
    resolved_tool_args = list(tool_args) if tool_args else []
    auto_approve_config = profile_config.get("auto_approve", {})

    if auto_approve and auto_approve_config:
        # Inject CLI flag if not already present
        cli_flag = auto_approve_config.get("cli_flag")
        if cli_flag and cli_flag not in resolved_tool_args:
            resolved_tool_args.insert(0, cli_flag)

        # Inject environment variable flag (e.g., OpenCode)
        env_flag = auto_approve_config.get("env_flag")
        if env_flag and "=" in env_flag:
            key, value = env_flag.split("=", 1)
            resolved_extra_env[key] = value

        resolved_extra_env["SYNAPSE_AUTO_APPROVE"] = "true"
    elif not auto_approve:
        resolved_extra_env["SYNAPSE_AUTO_APPROVE"] = "false"

    # 5. Build agent spec: profile:name:role:skill_set:port
    agent_spec = ":".join(
        [
            profile,
            name or "",
            role or "",
            skill_set or "",
            str(port),
        ]
    )

    return PreparedAgent(
        profile=profile,
        port=port,
        agent_spec=agent_spec,
        cwd=cwd,
        tool_args=resolved_tool_args or None,
        extra_env=resolved_extra_env or None,
        fallback_tool_args=fallback_tool_args,
        worktree_path=str(worktree_info.path) if worktree_info else None,
        worktree_branch=worktree_info.branch if worktree_info else None,
        _worktree_info=worktree_info,
    )


def execute_spawn(
    agents: list[PreparedAgent],
    *,
    layout: str = "auto",
    terminal: str | None = None,
    all_new: bool = True,
    replace_first: bool = False,
) -> list[SpawnResult]:
    """Execute spawning for one or more prepared agents (Phase 2: create panes).

    Calls ``create_panes()`` with all agents at once to maintain proper
    tile layout (``-h``/``-v`` alternation for tmux split mode).

    Args:
        agents: List of PreparedAgent from prepare_spawn().
        layout: Pane layout ("auto", "split", "horizontal", "vertical").
        terminal: Terminal app to use. Auto-detected if None.
        all_new: If True, all agents start in new panes.
            If False and replace_first is True, first agent uses current pane.
        replace_first: If True and all_new is False, the first agent replaces
            the current process via os.execvp (team start default behavior).

    Returns:
        List of SpawnResult for each agent.

    Raises:
        RuntimeError: If no terminal detected or pane creation fails.
    """
    if not agents:
        return []

    terminal_used = terminal or detect_terminal_app()
    if terminal_used is None:
        raise RuntimeError(
            "No supported terminal detected. "
            "Supported: tmux, iTerm2, Terminal.app, Ghostty, zellij"
        )

    # When replace_first is True, the first agent runs in the current pane.
    # We split remote agents (new panes) from the local agent (current pane).
    local_agent: PreparedAgent | None = None
    if replace_first and not all_new and len(agents) >= 1:
        local_agent = agents[0]
        remote_agents = agents[1:]
    else:
        remote_agents = list(agents)

    results: list[SpawnResult] = []
    pane_delay = _TERMINAL_SPLIT_DELAY.get(terminal_used, 0.0)

    # --- Worktree mode: each agent has its own cwd/env, spawn individually ---
    # Check if any agent uses a worktree (different cwd per agent)
    has_worktrees = any(a.worktree_path for a in remote_agents)

    if has_worktrees:
        # Worktree agents must be spawned individually (different cwd per agent)
        for prepared in remote_agents:
            commands = create_panes(
                [prepared.agent_spec],
                layout=layout,
                terminal_app=terminal_used,
                all_new=True,
                tool_args=prepared.tool_args,
                cwd=prepared.cwd,
                extra_env=prepared.extra_env,
                fallback_tool_args=prepared.fallback_tool_args,
            )
            if not commands:
                # Rollback worktree on failure
                if prepared._worktree_info:
                    from synapse.worktree import remove_worktree

                    remove_worktree(
                        prepared._worktree_info.path,
                        prepared._worktree_info.branch,
                        force=True,
                    )
                results.append(prepared.to_result(terminal_used, "failed"))
                continue
            _run_pane_commands(commands, check=True, delay=pane_delay)
            results.append(prepared.to_result(terminal_used, "submitted"))
        _post_spawn_tile(
            terminal_used,
            sum(1 for result in results if result.status == "submitted"),
        )
    elif remote_agents:
        first = remote_agents[0]
        # create_panes() takes a single tool_args for all agents, so when
        # per-agent args differ (e.g., different auto-approve flags), we
        # fall back to individual spawning.
        all_same_args = all(
            a.tool_args == first.tool_args and a.extra_env == first.extra_env
            for a in remote_agents
        )

        if all_same_args:
            # All agents have the same args — batch call for proper tiling
            specs = [a.agent_spec for a in remote_agents]
            commands = create_panes(
                specs,
                layout=layout,
                terminal_app=terminal_used,
                all_new=True if local_agent else all_new,
                tool_args=first.tool_args,
                cwd=first.cwd,
                extra_env=first.extra_env,
                fallback_tool_args=first.fallback_tool_args,
            )
            if not commands:
                raise RuntimeError(
                    f"No commands generated by create_panes for terminal "
                    f"'{terminal_used}'"
                )

            # Track tmux spawn zone panes
            panes_before: set[str] = set()
            if terminal_used == "tmux":
                panes_before = _get_tmux_pane_ids()

            try:
                _run_pane_commands(commands, check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to spawn agent: {e}") from e

            # Track new panes
            if terminal_used == "tmux" and panes_before:
                after = _get_tmux_pane_ids()
                new_panes = after - panes_before
                if new_panes:
                    existing = _get_tmux_spawn_panes()
                    all_panes = (
                        f"{existing},{','.join(new_panes)}"
                        if existing
                        else ",".join(new_panes)
                    )
                    _set_tmux_spawn_panes(all_panes)

            for prepared in remote_agents:
                results.append(prepared.to_result(terminal_used, "submitted"))
        else:
            for prepared in remote_agents:
                commands = create_panes(
                    [prepared.agent_spec],
                    layout=layout,
                    terminal_app=terminal_used,
                    all_new=True,
                    tool_args=prepared.tool_args,
                    cwd=prepared.cwd,
                    extra_env=prepared.extra_env,
                    fallback_tool_args=prepared.fallback_tool_args,
                )
                if not commands:
                    raise RuntimeError(
                        f"No commands generated by create_panes for terminal "
                        f"'{terminal_used}'"
                    )
                _run_pane_commands(commands, check=True, delay=pane_delay)
                results.append(prepared.to_result(terminal_used, "submitted"))
            _post_spawn_tile(
                terminal_used,
                sum(1 for result in results if result.status == "submitted"),
            )

    # Handle local agent (replace current process)

    if local_agent:
        from synapse.terminal_jump import _build_agent_command

        full_cmd = _build_agent_command(
            local_agent.agent_spec,
            tool_args=local_agent.tool_args,
            extra_env=local_agent.extra_env,
        )
        cmd_args = shlex.split(full_cmd)
        # os.execvp replaces the current process — this does not return
        os.execvp(cmd_args[0], cmd_args)

    return results


_TERMINAL_SPLIT_DELAY: dict[str, float] = {"tmux": 0.1, "zellij": 0.1}


def _run_pane_commands(
    commands: list[str],
    *,
    check: bool = False,
    delay: float = 0.0,
) -> None:
    """Execute a list of shell commands generated by create_panes."""
    for index, cmd in enumerate(commands):
        if index > 0 and delay > 0:
            time.sleep(delay)
        subprocess.run(shlex.split(cmd), check=check, timeout=10)


def _post_spawn_tile(terminal: str, count: int) -> None:
    """Apply caller-level tiling for terminals that need it after individual spawns.

    For tmux, also considers the total number of panes in the spawn zone
    (tracked via ``SYNAPSE_SPAWN_PANES``).  This allows ``synapse spawn``
    called multiple times to trigger tiling once a second pane exists,
    even though each invocation only spawns one agent.
    """
    if terminal == "tmux":
        spawn_panes = _get_tmux_spawn_panes()
        total = len(spawn_panes.split(",")) if spawn_panes else 0
        # total counts *spawned* panes only (the original caller pane is
        # not tracked).  Tile when 2+ spawned panes exist, i.e. 3+ visible
        # panes — the first spawn should not trigger a re-tile.
        if total >= 2:
            subprocess.run(
                ["tmux", "select-layout", "tiled"],
                check=False,
                timeout=5,
            )
            return
    # Non-tmux fallback: use count as before
    if count < 2:
        return


def spawn_agent(
    profile: str,
    port: int | None = None,
    name: str | None = None,
    role: str | None = None,
    skill_set: str | None = None,
    terminal: str | None = None,
    tool_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    worktree: str | bool | None = None,
    fallback_tool_args: list[str] | None = None,
    auto_approve: bool = True,
    branch: str | None = None,
) -> SpawnResult:
    """Spawn a single agent in a new terminal pane.

    This is a convenience wrapper around ``prepare_spawn()`` +
    ``execute_spawn()``.

    Args:
        profile: Agent profile name (claude, gemini, codex, etc.).
        port: Explicit port number. Auto-assigned if None.
        name: Custom agent name.
        role: Agent role description.
        skill_set: Skill set to activate.
        terminal: Terminal app to use. Auto-detected if None.
        tool_args: Extra arguments passed through to the underlying CLI tool
            (e.g., ``["--dangerously-skip-permissions"]``).
        extra_env: Extra environment variables injected into the spawned agent.
        worktree: If True, create a worktree with auto-generated name.
            If a string, use it as the worktree name. If None/False, no worktree.
        fallback_tool_args: Shell-level fallback command args on failure.
        auto_approve: If True (default), inject the profile's auto-approve
            CLI flag and set SYNAPSE_AUTO_APPROVE=true.
        branch: Base branch for worktree creation. Only used when
            ``worktree`` is truthy. Defaults to remote default branch.

    Returns:
        SpawnResult with agent_id, port, terminal_used, status.

    Raises:
        FileNotFoundError: If profile is invalid.
        RuntimeError: If port unavailable, ports exhausted, or no terminal.
    """
    prepared = prepare_spawn(
        profile=profile,
        port=port,
        name=name,
        role=role,
        skill_set=skill_set,
        tool_args=tool_args,
        extra_env=extra_env,
        worktree=worktree,
        fallback_tool_args=fallback_tool_args,
        auto_approve=auto_approve,
        branch=branch,
    )

    results = execute_spawn(
        [prepared],
        layout="auto",
        terminal=terminal,
        all_new=True,
    )

    # Re-tile the spawn zone for consecutive individual spawns (#507).
    terminal_used = results[0].terminal_used
    _post_spawn_tile(terminal_used, 1)

    return results[0]


def wait_for_agent(
    agent_id: str,
    timeout: float = 30.0,
    poll_interval: float = 0.5,
) -> dict | None:
    """Wait for a spawned agent to register and become alive.

    Uses fixed-interval polling against the file-based registry.
    Fixed interval is preferred over exponential backoff here because
    registry reads are cheap (single file read) and agent boot times
    are unpredictable — we want consistent responsiveness.

    Args:
        agent_id: The agent ID to wait for (e.g. "synapse-claude-8100").
        timeout: Maximum seconds to wait (default 30s).
        poll_interval: Seconds between polls (default 0.5s).

    Returns:
        Agent info dict if found and alive, or None if timed out.
    """
    from synapse.registry import is_process_running

    registry = AgentRegistry()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        agents = registry.list_agents()
        if agent_id in agents:
            info = agents[agent_id]
            pid = info.get("pid")
            if pid and is_process_running(pid):
                return info
        time.sleep(poll_interval)

    return None
