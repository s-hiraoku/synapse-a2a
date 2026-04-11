"""Spawn and team command handlers for Synapse CLI."""

from __future__ import annotations

import argparse
import subprocess
import sys

from synapse.agent_profiles import AgentProfileError, AgentProfileStore
from synapse.port_manager import PORT_RANGES
from synapse.registry import AgentRegistry

KNOWN_PROFILES = set(PORT_RANGES.keys())

_SYNAPSE_FLAGS = {
    "--port",
    "--name",
    "-n",
    "--role",
    "-r",
    "--skill-set",
    "-S",
    "--terminal",
    "--foreground",
    "-f",
    "--no-setup",
    "--headless",
    "--delegate-mode",
    "--ssl-cert",
    "--ssl-key",
    "--layout",
    "--all-new",
    "--worktree",
}


def _extract_tool_args(items: list[str]) -> tuple[list[str], list[str]]:
    """Split a list at the first ``--`` separator."""
    try:
        idx = items.index("--")
        return items[:idx], items[idx + 1 :]
    except ValueError:
        return items, []


def _warn_synapse_flags_in_tool_args(tool_args: list[str]) -> bool:
    """Warn if known Synapse flags appear after ``--``."""
    if not tool_args:
        return False

    found = [arg for arg in tool_args if arg in _SYNAPSE_FLAGS]
    if not found:
        return False

    flags_str = ", ".join(found)
    print(
        f"Warning: Synapse flag(s) {flags_str} found after '--' separator.\n"
        f"  These will be passed to the underlying CLI tool, not to Synapse.\n"
        f"  Move them before '--' or before the profile name.\n"
        f"  Example: synapse spawn --port 8100 claude -- --resume",
        file=sys.stderr,
    )
    return True


def _extract_team_agent_name(spec: str) -> str | None:
    """Extract custom name from team agent spec if present."""
    parts = spec.split(":")
    if len(parts) > 1 and parts[1]:
        return parts[1]
    return None


def _resolve_team_agent_spec(spec: str, store: AgentProfileStore) -> str:
    """Resolve team spec target as profile or saved agent ID/name."""
    parts = spec.split(":")
    target = parts[0]

    if target in KNOWN_PROFILES:
        return spec

    try:
        saved = store.resolve(target)
    except AgentProfileError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if saved is None:
        print(
            f"Error: Unknown profile or saved agent: {target}\n"
            "Run 'synapse agents list' to see saved agent IDs/names.",
            file=sys.stderr,
        )
        sys.exit(1)

    while len(parts) < 5:
        parts.append("")
    parts[0] = saved.profile
    if not parts[1]:
        parts[1] = saved.name
    if not parts[2] and saved.role:
        parts[2] = saved.role
    if not parts[3] and saved.skill_set:
        parts[3] = saved.skill_set
    return ":".join(parts)


def cmd_team_start(args: argparse.Namespace) -> None:
    """Start multiple agents with split panes."""
    from synapse.spawn import execute_spawn, prepare_spawn
    from synapse.terminal_jump import detect_terminal_app

    agents, embedded_tool_args = _extract_tool_args(args.agents)
    tool_args = getattr(args, "tool_args", []) or embedded_tool_args
    layout = getattr(args, "layout", "split")
    all_new = getattr(args, "all_new", False)
    auto_approve = not getattr(args, "no_auto_approve", False)

    store = AgentProfileStore()
    agents = [_resolve_team_agent_spec(spec, store) for spec in agents]

    registry = AgentRegistry()
    seen_names: set[str] = set()
    for spec in agents:
        custom_name = _extract_team_agent_name(spec)
        if not custom_name:
            continue
        if custom_name in seen_names:
            print(
                f"Error: Duplicate custom name '{custom_name}' in team specs.",
                file=sys.stderr,
            )
            sys.exit(1)
        seen_names.add(custom_name)
        if not registry.is_name_unique(custom_name):
            print(
                f"Error: Name '{custom_name}' is already taken by another agent.",
                file=sys.stderr,
            )
            sys.exit(1)

    worktree_opt = getattr(args, "worktree", None)
    branch_opt = getattr(args, "branch", None)

    terminal = detect_terminal_app()
    if not terminal:
        print(
            "Could not detect terminal. Supported: tmux, iTerm2, Terminal.app, zellij"
        )
        print("Falling back to sequential start...")
        for i, agent_spec in enumerate(agents):
            parts = agent_spec.split(":")
            profile = parts[0]
            name = parts[1] if len(parts) > 1 and parts[1] else None
            role = parts[2] if len(parts) > 2 and parts[2] else None
            skill_set = parts[3] if len(parts) > 3 and parts[3] else None
            try:
                port: int | None = (
                    int(parts[4]) if len(parts) > 4 and parts[4] else None
                )
            except ValueError:
                print(
                    f"Error: Invalid port in team spec '{agent_spec}': {parts[4]}",
                    file=sys.stderr,
                )
                sys.exit(1)

            print(f"Starting {agent_spec}...")
            fallback_cmd = ["synapse", "team", "start", profile]
            if port:
                fallback_cmd += ["--port", str(port)]
            if name:
                fallback_cmd += ["--name", name]
            if role:
                fallback_cmd += ["--role", role]
            if skill_set:
                fallback_cmd += ["--skill-set", skill_set]
            if not auto_approve:
                fallback_cmd.append("--no-auto-approve")
            if worktree_opt:
                fallback_cmd.append("--worktree")
                if isinstance(worktree_opt, str):
                    fallback_cmd.append(f"{worktree_opt}-{profile}-{i}")
            if branch_opt:
                fallback_cmd += ["--branch", branch_opt]
            if tool_args:
                fallback_cmd += ["--"] + tool_args
            subprocess.Popen(
                fallback_cmd,
                start_new_session=True,
            )
        return

    if worktree_opt is None and len(agents) >= 2:
        worktree_opt = True

    prepared_agents = []
    for i, agent_spec in enumerate(agents):
        parts = agent_spec.split(":")
        profile = parts[0]
        name = parts[1] if len(parts) > 1 and parts[1] else None
        role = parts[2] if len(parts) > 2 and parts[2] else None
        skill_set = parts[3] if len(parts) > 3 and parts[3] else None
        port = int(parts[4]) if len(parts) > 4 and parts[4] else None

        wt: str | bool | None = None
        if worktree_opt:
            if isinstance(worktree_opt, str):
                wt = f"{worktree_opt}-{profile}-{i}"
            else:
                wt = True

        try:
            prepared = prepare_spawn(
                profile=profile,
                port=port,
                name=name,
                role=role,
                skill_set=skill_set,
                tool_args=tool_args or None,
                worktree=wt,
                auto_approve=auto_approve,
                branch=branch_opt,
            )
            prepared_agents.append(prepared)
        except (RuntimeError, ValueError, FileNotFoundError) as e:
            print(f"Error preparing {profile}: {e}", file=sys.stderr)
            sys.exit(1)

    if not prepared_agents:
        print("No agents were prepared.", file=sys.stderr)
        sys.exit(1)

    try:
        results = execute_spawn(
            prepared_agents,
            layout=layout,
            terminal=terminal,
            all_new=all_new,
            replace_first=not all_new,
        )
    except RuntimeError as e:
        print(f"Error starting agents: {e}", file=sys.stderr)
        sys.exit(1)

    if worktree_opt:
        launched = [r for r in results if r.status == "submitted"]
        for r in launched:
            profile = r.agent_id.split("-")[1]
            print(f"  {profile}: {r.worktree_path} ({r.worktree_branch})")
        if launched:
            names = [r.agent_id.split("-")[1] for r in launched]
            print(f"Started {len(launched)} agents in worktrees: {', '.join(names)}")
        else:
            print("No agents were launched.", file=sys.stderr)
            sys.exit(1)
    else:
        display_names = [a.profile for a in prepared_agents]
        if all_new:
            print(f"Started {len(prepared_agents)} agents: {', '.join(display_names)}")
        else:
            print(f"Handing over terminal to {display_names[0]}...")


def cmd_spawn(args: argparse.Namespace) -> None:
    """Spawn a single agent in a new terminal pane."""
    from synapse.commands.messaging import (
        _build_a2a_cmd,
        _resolve_task_message,
        _run_a2a_command,
    )
    from synapse.spawn import spawn_agent, wait_for_agent

    tool_args = getattr(args, "tool_args", [])
    task_message = _resolve_task_message(args)
    target = args.profile
    resolved_profile = target
    resolved_name = args.name
    resolved_role = args.role
    resolved_skill_set = args.skill_set

    if target not in KNOWN_PROFILES:
        store = AgentProfileStore()
        try:
            saved = store.resolve(target)
        except AgentProfileError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        if saved is None:
            print(
                f"Error: Unknown profile or saved agent: {target}\n"
                "Run 'synapse agents list' to see saved agent IDs/names.",
                file=sys.stderr,
            )
            sys.exit(1)
        resolved_profile = saved.profile
        resolved_name = resolved_name or saved.name
        resolved_role = resolved_role or saved.role
        resolved_skill_set = resolved_skill_set or saved.skill_set

    if resolved_name:
        registry = AgentRegistry()
        if not registry.is_name_unique(resolved_name):
            print(
                f"Error: Name '{resolved_name}' is already taken by another agent.",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        result = spawn_agent(
            profile=resolved_profile,
            port=args.port,
            name=resolved_name,
            role=resolved_role,
            skill_set=resolved_skill_set,
            terminal=args.terminal,
            tool_args=tool_args or None,
            worktree=getattr(args, "worktree", None),
            auto_approve=not getattr(args, "no_auto_approve", False),
            branch=getattr(args, "branch", None),
        )
        print(f"{result.agent_id} {result.port}")
        if result.worktree_path:
            print(f"  worktree: {result.worktree_path} ({result.worktree_branch})")

        wait_timeout = getattr(args, "task_timeout", 30) if task_message else 3.0
        info = wait_for_agent(result.agent_id, timeout=wait_timeout, poll_interval=0.5)
        if info is None:
            print(
                f"Warning: {result.agent_id} not yet registered after spawn.\n"
                f"  The agent may still be starting up.\n"
                f"  Use the full agent ID for reliable targeting:\n"
                f'    synapse send {result.agent_id} "<message>" --wait',
                file=sys.stderr,
            )
            return

        if task_message is not None:
            cmd = _build_a2a_cmd(
                "send",
                task_message,
                target=result.agent_id,
                response_mode=getattr(args, "response_mode", None),
                force=bool(result.worktree_path),
            )
            _run_a2a_command(cmd, exit_on_error=True)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
