"""CLI handlers for ``synapse session`` subcommands."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from synapse.registry import AgentRegistry
from synapse.session import (
    Session,
    SessionAgent,
    SessionError,
    SessionStore,
    resolve_scope_filter,
)
from synapse.spawn import spawn_agent


def _get_session_store(workdir: str | None = None) -> SessionStore:
    """Create a SessionStore, optionally rooted at --workdir project scope."""
    if workdir:
        return SessionStore(project_dir=Path(workdir) / ".synapse" / "sessions")
    return SessionStore()


# ── save ─────────────────────────────────────────────────────


def _filter_agents(
    all_agents: dict[str, dict],
    *,
    user_scope: bool,
    workdir_filter: str | None,
) -> dict[str, dict]:
    """Filter registry agents by scope/working-dir."""
    if user_scope:
        return all_agents

    match_dir = workdir_filter or os.getcwd()
    return {k: v for k, v in all_agents.items() if v.get("working_dir") == match_dir}


def cmd_session_save(args: argparse.Namespace) -> None:
    """Save running agents as a named session."""
    name: str = args.session_name
    scope, workdir_filter = resolve_scope_filter(args)
    save_scope = scope or "project"

    registry = AgentRegistry()
    all_agents = registry.get_live_agents()
    filtered = _filter_agents(
        all_agents,
        user_scope=getattr(args, "user", False),
        workdir_filter=workdir_filter,
    )

    if not filtered:
        print(
            "Error: No running agents found matching the scope filter.", file=sys.stderr
        )
        sys.exit(1)

    agents = [
        SessionAgent(
            profile=info.get("agent_type", ""),
            name=info.get("name"),
            role=info.get("role"),
            skill_set=info.get("skill_set"),
            worktree=bool(info.get("worktree_path")),
        )
        for info in filtered.values()
    ]

    working_dir = workdir_filter or os.getcwd()

    session = Session(
        session_name=name,
        agents=agents,
        working_dir=working_dir,
        created_at=time.time(),
        scope=save_scope,
    )

    store = _get_session_store(workdir_filter)
    try:
        path = store.save(session)
    except SessionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Session '{name}' saved ({len(agents)} agents) → {path}")


# ── list ─────────────────────────────────────────────────────


def cmd_session_list(args: argparse.Namespace) -> None:
    """List saved sessions."""
    scope, workdir = resolve_scope_filter(args)
    store = _get_session_store(workdir)
    sessions = store.list_sessions(scope=scope)

    if not sessions:
        print("No saved sessions.")
        return

    if sys.stdout.isatty():
        try:
            from rich import box
            from rich.console import Console
            from rich.table import Table

            table = Table(
                title="Saved Sessions",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("NAME", style="green")
            table.add_column("AGENTS", justify="right")
            table.add_column("SCOPE", style="yellow")
            table.add_column("WORKING_DIR")
            table.add_column("CREATED")
            for s in sessions:
                created = datetime.fromtimestamp(s.created_at).strftime(
                    "%Y-%m-%d %H:%M"
                )
                table.add_row(
                    s.session_name,
                    str(s.agent_count),
                    s.scope,
                    s.working_dir,
                    created,
                )
            Console().print(table)
            return
        except Exception:
            pass

    # Plain text fallback
    print(f"{'NAME':<20} {'AGENTS':>6} {'SCOPE':<8} {'WORKING_DIR'}")
    print("-" * 60)
    for s in sessions:
        print(f"{s.session_name:<20} {s.agent_count:>6} {s.scope:<8} {s.working_dir}")


# ── show ─────────────────────────────────────────────────────


def cmd_session_show(args: argparse.Namespace) -> None:
    """Show session details."""
    name: str = args.session_name
    scope, workdir = resolve_scope_filter(args)
    store = _get_session_store(workdir)
    session = store.load(name, scope=scope)

    if session is None:
        print(f"Error: Session '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    created = datetime.fromtimestamp(session.created_at).strftime("%Y-%m-%d %H:%M:%S")

    print(f"Session: {session.session_name}")
    print(f"Scope:   {session.scope}")
    print(f"Dir:     {session.working_dir}")
    print(f"Created: {created}")
    print(f"Agents:  {session.agent_count}")
    print()

    for i, a in enumerate(session.agents, 1):
        parts = [f"  {i}. {a.profile}"]
        if a.name:
            parts.append(f"name={a.name}")
        if a.role:
            parts.append(f"role={a.role}")
        if a.skill_set:
            parts.append(f"skill_set={a.skill_set}")
        if a.worktree:
            parts.append("worktree=yes")
        print("  ".join(parts))


# ── restore ──────────────────────────────────────────────────


def _agent_label(agent: SessionAgent) -> str:
    """Return a display label like 'claude (Reviewer)' or just 'claude'."""
    if agent.name:
        return f"{agent.profile} ({agent.name})"
    return agent.profile


def cmd_session_restore(args: argparse.Namespace) -> None:
    """Restore a saved session by spawning agents."""
    name: str = args.session_name
    scope, workdir = resolve_scope_filter(args)
    store = _get_session_store(workdir)
    session = store.load(name, scope=scope)

    if session is None:
        print(f"Error: Session '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    worktree_flag = getattr(args, "worktree", None)
    tool_args = getattr(args, "tool_args", []) or []

    print(f"Restoring session '{name}' ({session.agent_count} agents)...")

    failures = 0
    for agent in session.agents:
        wt = worktree_flag if worktree_flag is not None else agent.worktree
        label = _agent_label(agent)

        try:
            result = spawn_agent(
                profile=agent.profile,
                name=agent.name,
                role=agent.role,
                skill_set=agent.skill_set,
                worktree=wt,
                tool_args=tool_args or None,
            )
            wt_info = (
                f" (worktree: {result.worktree_path})" if result.worktree_path else ""
            )
            print(
                f"  Spawned {label} → {result.agent_id} [{result.terminal_used}]{wt_info}"
            )
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            print(f"  Failed to spawn {label}: {e}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"Done with {failures} failure(s).", file=sys.stderr)
        sys.exit(1)
    print("Done.")


# ── delete ───────────────────────────────────────────────────


def cmd_session_delete(args: argparse.Namespace) -> None:
    """Delete a saved session."""
    name: str = args.session_name
    scope, workdir = resolve_scope_filter(args)
    force = getattr(args, "force", False)
    store = _get_session_store(workdir)

    # Check existence first
    session = store.load(name, scope=scope)
    if session is None:
        print(f"Error: Session '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    if not force:
        answer = input(
            f"Delete session '{name}' ({session.agent_count} agents)? [y/N] "
        )
        if answer.lower() not in ("y", "yes"):
            print("Cancelled.")
            return

    deleted = store.delete(name, scope=session.scope)
    if deleted:
        print(f"Session '{name}' deleted.")
    else:
        print(f"Error: Failed to delete session '{name}'.", file=sys.stderr)
        sys.exit(1)
