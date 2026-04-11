"""CLI handlers for ``synapse multiagent`` (``synapse map``) subcommands."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

import yaml

from synapse.patterns.base import PatternError
from synapse.patterns.runner import PatternRunner, get_runner
from synapse.patterns.store import PatternStore, Scope


def _get_pattern_store() -> PatternStore:
    """Create a PatternStore with default directories."""
    return PatternStore()


def _get_pattern_runner() -> PatternRunner:
    """Return the shared PatternRunner singleton."""
    return get_runner()
    return PatternRunner()


def _resolve_scope(args: argparse.Namespace) -> Scope | None:
    """Extract scope from parsed CLI args."""
    if getattr(args, "user", False):
        return "user"
    if getattr(args, "project", False):
        return "project"
    return None


def _resolve_write_scope(args: argparse.Namespace) -> Scope:
    """Extract scope for write operations (default: project)."""
    if getattr(args, "user", False):
        return "user"
    return "project"


_PATTERN_TEMPLATES: dict[str, dict[str, Any]] = {
    "generator-verifier": {
        "pattern": "generator-verifier",
        "description": "Generate output and verify against criteria",
        "generator": {
            "profile": "claude",
            "name": "Generator",
            "worktree": True,
        },
        "verifier": {
            "profile": "claude",
            "name": "Verifier",
            "criteria": [{"command": "pytest", "expect": "exit-0"}],
        },
        "max_iterations": 3,
        "on_failure": "escalate",
    },
    "orchestrator-subagent": {
        "pattern": "orchestrator-subagent",
        "description": "Decompose task and delegate to subagents",
        "orchestrator": {"profile": "claude", "name": "Lead"},
        "subtasks": [
            {"name": "subtask-1", "message": "First subtask"},
            {"name": "subtask-2", "message": "Second subtask"},
        ],
        "parallel": True,
    },
    "agent-teams": {
        "pattern": "agent-teams",
        "description": "Parallel workers processing a task queue",
        "team": {"count": 3, "profile": "claude", "worktree": True},
        "task_queue": {
            "source": "inline",
            "tasks": ["Task 1", "Task 2", "Task 3"],
        },
        "completion": {"mode": "all-done", "timeout": 3600},
    },
    "message-bus": {
        "pattern": "message-bus",
        "description": "Event-driven agent coordination via pub/sub",
        "topics": [
            {
                "name": "events",
                "subscribers": [
                    {"profile": "claude", "name": "Handler-1"},
                    {"profile": "claude", "name": "Handler-2"},
                ],
            }
        ],
        "router": {"profile": "claude", "name": "Router"},
    },
    "shared-state": {
        "pattern": "shared-state",
        "description": "Agents collaborate through shared wiki",
        "agents": [
            {"profile": "claude", "name": "Researcher-1", "role": "Research aspect A"},
            {"profile": "claude", "name": "Researcher-2", "role": "Research aspect B"},
        ],
        "shared_store": "wiki",
        "termination": {"mode": "time-budget", "budget": 600},
    },
}


def _build_template(pattern_type: str, name: str) -> dict[str, Any]:
    """Build a concrete template config for a built-in pattern type."""
    try:
        template = _PATTERN_TEMPLATES[pattern_type]
    except KeyError as exc:
        valid = ", ".join(sorted(_PATTERN_TEMPLATES))
        raise PatternError(
            f"Unknown pattern type '{pattern_type}'. Valid types: {valid}"
        ) from exc
    return {"name": name, **template}


def _coerce_run_id(result: Any) -> str | None:
    """Extract a run id from a runner result object."""
    if isinstance(result, dict):
        run_id = result.get("run_id")
    else:
        run_id = getattr(result, "run_id", None)
    return run_id if isinstance(run_id, str) and run_id else None


def _print_run_status(run: Any) -> None:
    """Print a normalized run status view."""
    if isinstance(run, dict):
        status = run.get("status", "unknown")
        output = run.get("output")
        agents = run.get("agents") or []
    else:
        status = getattr(run, "status", "unknown")
        output = getattr(run, "output", None)
        agents = getattr(run, "agents", []) or []

    print(f"Status: {status}")
    if output:
        print(f"Output: {output}")
    if agents:
        print("Agents:")
        for agent in agents:
            print(f"  - {agent}")


def cmd_multiagent_init(args: argparse.Namespace) -> None:
    """Create a new multi-agent pattern template YAML."""
    pattern_type: str = args.pattern_type
    name: str = args.name or pattern_type
    scope = _resolve_write_scope(args)
    force = getattr(args, "force", False)

    store = _get_pattern_store()
    try:
        if hasattr(store, "_validate_name"):
            store._validate_name(name)
        if not force and store.exists(name, scope=scope):
            print(
                f"Error: Pattern '{name}' already exists. Use --force to overwrite.",
                file=sys.stderr,
            )
            sys.exit(1)

        template = _build_template(pattern_type, name)
        path = store.save(template, scope=scope)
    except PatternError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(path)


def cmd_multiagent_list(args: argparse.Namespace) -> None:
    """List saved multi-agent patterns."""
    scope = _resolve_scope(args)
    store = _get_pattern_store()
    patterns = store.list_patterns(scope=scope)

    if not patterns:
        print("No saved patterns.")
        return

    print(f"{'NAME':<25} {'PATTERN':<24} {'DESCRIPTION':<40} {'SCOPE'}")
    print("-" * 100)
    for pattern in patterns:
        print(
            f"{pattern.get('name', ''):<25} "
            f"{pattern.get('pattern', ''):<24} "
            f"{(pattern.get('description') or ''):<40} "
            f"{pattern.get('scope', '')}"
        )


def cmd_multiagent_show(args: argparse.Namespace) -> None:
    """Show pattern YAML details."""
    name: str = args.pattern_name
    scope = _resolve_scope(args)
    store = _get_pattern_store()
    try:
        pattern = store.load(name, scope=scope)
    except PatternError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if pattern is None:
        print(f"Error: Pattern '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    print(yaml.safe_dump(pattern, sort_keys=False))


def cmd_multiagent_run(args: argparse.Namespace) -> None:
    """Execute a saved multi-agent pattern."""
    name: str = args.pattern_name
    scope = _resolve_scope(args)
    store = _get_pattern_store()
    try:
        pattern = store.load(name, scope=scope)
    except PatternError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if pattern is None:
        print(f"Error: Pattern '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "dry_run", False):
        print("DRY RUN")
        print(f"Pattern: {pattern.get('name', name)}")
        print(f"Task: {args.task}")
        print(yaml.safe_dump(pattern, sort_keys=False))
        return

    runner = _get_pattern_runner()
    try:
        pattern_type = pattern.get("pattern", name)
        result = asyncio.run(
            runner.run_pattern(pattern_type, args.task, config=pattern)
        )
        run_id = _coerce_run_id(result)
        if run_id is None:
            print("Error: Pattern runner did not return a run id.", file=sys.stderr)
            sys.exit(1)

        print(f"Run started: {run_id}")
        if getattr(args, "run_async", False):
            return

        wait_for_run = getattr(runner, "wait_for_run", None)
        final_result = asyncio.run(wait_for_run(run_id)) if wait_for_run else result
    except PatternError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _print_run_status(final_result)


def cmd_multiagent_status(args: argparse.Namespace) -> None:
    """Show the current status of a pattern run."""
    runner = _get_pattern_runner()
    run = runner.get_run(args.run_id)
    if run is None:
        print(f"Error: Run '{args.run_id}' not found.", file=sys.stderr)
        sys.exit(1)
    _print_run_status(run)


def cmd_multiagent_stop(args: argparse.Namespace) -> None:
    """Stop a running pattern execution."""
    runner = _get_pattern_runner()
    stopped = asyncio.run(runner.stop_run(args.run_id))
    if not stopped:
        print(f"Error: Run '{args.run_id}' not found.", file=sys.stderr)
        sys.exit(1)
    print(f"Stopped run: {args.run_id}")
