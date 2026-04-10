"""CLI handlers for ``synapse workflow`` subcommands."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.workflow_runner import _WorkflowHelper

from synapse.workflow import (
    Scope,
    Workflow,
    WorkflowError,
    WorkflowStep,
    WorkflowStore,
)

logger = logging.getLogger(__name__)

_NO_AGENT_MARKER = "No agent found matching"
_SPAWN_WAIT_SECONDS = 5
_SPAWN_MAX_WAIT_SECONDS = 30
MAX_WORKFLOW_DEPTH = 10
_HELPER_ENV_MARKER = "SYNAPSE_WORKFLOW_HELPER"
_HELPER_DEPTH_ENV = "SYNAPSE_WORKFLOW_HELPER_DEPTH"
_MAX_HELPER_DEPTH = 1


def _get_workflow_store() -> WorkflowStore:
    """Create a WorkflowStore with default directories."""
    return WorkflowStore()


def _resolve_scope(args: argparse.Namespace) -> Scope | None:
    """Extract scope from parsed CLI args.

    Returns explicit scope if --project or --user is set, else None (auto).
    """
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


# ── create ───────────────────────────────────────────────────


_TEMPLATE_DESCRIPTION = "Describe what this workflow does"
_TEMPLATE_STEPS = [
    WorkflowStep(target="claude", message="Your message here"),
]


def cmd_workflow_create(args: argparse.Namespace) -> None:
    """Create a new workflow template YAML."""
    name: str = args.workflow_name
    scope = _resolve_write_scope(args)
    force = getattr(args, "force", False)

    store = _get_workflow_store()
    try:
        # Check for existing file (not load() — corrupted YAML should still block overwrite)
        WorkflowStore._validate_name(name)
        if not force and store.exists(name, scope=scope):
            print(
                f"Error: Workflow '{name}' already exists. Use --force to overwrite.",
                file=sys.stderr,
            )
            sys.exit(1)

        template = Workflow(
            name=name,
            steps=list(_TEMPLATE_STEPS),
            description=_TEMPLATE_DESCRIPTION,
            scope=scope,
        )
        path = store.save(template)
    except WorkflowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Auto-generate skill from the new workflow
    try:
        from synapse.workflow_skill_sync import sync_workflow_skill

        project_dir = Path.cwd()
        sync_workflow_skill(template, project_dir)
    except Exception as e:
        logger.warning("Failed to sync workflow skill: %s", e)

    print(f"Workflow template created: {path}")
    print(f"Edit the file and run: synapse workflow run {name}")


# ── list ─────────────────────────────────────────────────────


def cmd_workflow_list(args: argparse.Namespace) -> None:
    """List saved workflows."""
    scope = _resolve_scope(args)
    store = _get_workflow_store()
    workflows = store.list_workflows(scope=scope)

    if not workflows:
        print("No saved workflows.")
        return

    if sys.stdout.isatty():
        try:
            from rich import box
            from rich.console import Console
            from rich.table import Table

            table = Table(
                title="Saved Workflows",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("NAME", style="green")
            table.add_column("STEPS", justify="right")
            table.add_column("SCOPE", style="yellow")
            table.add_column("DESCRIPTION")
            for w in workflows:
                table.add_row(
                    w.name,
                    str(w.step_count),
                    w.scope,
                    w.description or "",
                )
            Console().print(table)
            return
        except Exception:
            pass

    # Plain text fallback
    print(f"{'NAME':<25} {'STEPS':>5} {'SCOPE':<8} {'DESCRIPTION'}")
    print("-" * 70)
    for w in workflows:
        print(f"{w.name:<25} {w.step_count:>5} {w.scope:<8} {w.description or ''}")


# ── show ─────────────────────────────────────────────────────


def cmd_workflow_show(args: argparse.Namespace) -> None:
    """Show workflow details."""
    name: str = args.workflow_name
    scope = _resolve_scope(args)
    store = _get_workflow_store()
    try:
        wf = store.load(name, scope=scope)
    except WorkflowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if wf is None:
        print(f"Error: Workflow '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Workflow: {wf.name}")
    print(f"Scope:    {wf.scope}")
    if wf.description:
        print(f"Desc:     {wf.description}")
    print(f"Steps:    {wf.step_count}")
    print()

    for i, step in enumerate(wf.steps, 1):
        if step.kind == "subworkflow":
            print(f"  {i}. kind=subworkflow  workflow={step.workflow}")
        else:
            print(
                f"  {i}. target={step.target}  priority={step.priority}  mode={step.response_mode}"
            )
            msg = step.message if len(step.message) <= 80 else step.message[:77] + "..."
            print(f"     message: {msg}")


# ── delete ───────────────────────────────────────────────────


def cmd_workflow_delete(args: argparse.Namespace) -> None:
    """Delete a saved workflow."""
    name: str = args.workflow_name
    scope = _resolve_scope(args)
    force = getattr(args, "force", False)

    store = _get_workflow_store()

    # Check existence first
    try:
        wf = store.load(name, scope=scope)
    except WorkflowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if wf is None:
        print(f"Error: Workflow '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    if not force:
        try:
            answer = input(f"Delete workflow '{name}' ({wf.step_count} steps)? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return

    deleted = store.delete(name, scope=wf.scope)
    if deleted:
        # Remove auto-generated skill
        try:
            from synapse.workflow_skill_sync import remove_workflow_skill

            remove_workflow_skill(name, Path.cwd())
        except Exception as e:
            logger.warning("Failed to remove workflow skill: %s", e)

        print(f"Workflow '{name}' deleted.")
    else:
        print(f"Error: Failed to delete workflow '{name}'.", file=sys.stderr)
        sys.exit(1)


# ── run ──────────────────────────────────────────────────────


def _should_auto_spawn(step: WorkflowStep, effective_auto_spawn: bool) -> bool:
    """Determine whether auto-spawn is enabled for a step."""
    return step.auto_spawn or effective_auto_spawn


def _try_spawn_agent(profile: str) -> bool:
    """Spawn an agent by profile name. Returns True on success."""
    try:
        from synapse.spawn import spawn_agent

        result = spawn_agent(profile)
        if result.status == "submitted":
            print(f"  Spawned {profile} agent (port {result.port})")
            return True
        print(
            f"  Warning: spawn {profile} returned status '{result.status}'",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(f"  Warning: failed to spawn '{profile}': {e}", file=sys.stderr)
        return False


def _wait_for_agent(target: str, timeout: float = _SPAWN_MAX_WAIT_SECONDS) -> bool:
    """Poll registry until target agent appears or timeout."""
    from synapse.registry import AgentRegistry
    from synapse.tools.a2a import _resolve_target_agent

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        agents = AgentRegistry().list_agents()
        agent, _err = _resolve_target_agent(target, agents)
        if agent is not None:
            return True
        time.sleep(1)
    return False


def _run_step(
    step: WorkflowStep,
    step_num: int,
    total: int,
    *,
    auto_spawn: bool,
    helper: _WorkflowHelper | None = None,
) -> bool:
    """Execute a single workflow step. Returns True on success."""
    import asyncio

    from synapse.cli import _build_a2a_cmd
    from synapse.workflow_runner import StepResult, _is_self_target

    print(f"  Step {step_num}/{total}: → {step.target} ({step.response_mode})")

    sender_info = {
        "agent_id": os.getenv("SYNAPSE_AGENT_ID", ""),
        "agent_type": os.getenv("SYNAPSE_AGENT_TYPE", ""),
        "working_dir": str(Path.cwd()),
    }
    if _is_self_target(step.target, sender_info):
        if helper is None:
            print(
                "  self-target detected but no helper available.",
                file=sys.stderr,
            )
            return False
        step_result = StepResult(
            step_index=step_num - 1, target=step.target, message=step.message
        )
        try:
            asyncio.run(helper.execute_step(step, step_result))
        except Exception as exc:
            print(f"  Helper execution failed: {exc}", file=sys.stderr)
            return False
        if step_result.status == "failed":
            print(
                f"  Step {step_num} failed: {step_result.error}",
                file=sys.stderr,
            )
            return False
        if step_result.output:
            print(step_result.output)
        return True

    cmd = _build_a2a_cmd(
        "send",
        step.message,
        target=step.target,
        priority=step.priority,
        response_mode=step.response_mode,
        sender=os.getenv("SYNAPSE_AGENT_ID"),
    )

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Check if agent not found and auto-spawn is enabled
    if (
        result.returncode != 0
        and _NO_AGENT_MARKER in (result.stderr or "")
        and _should_auto_spawn(step, auto_spawn)
    ):
        print(f"  Agent '{step.target}' not found. Spawning...")
        if _try_spawn_agent(step.target):
            print(
                f"  Waiting for agent to register (up to {_SPAWN_MAX_WAIT_SECONDS}s)..."
            )
            if _wait_for_agent(step.target):
                # Retry the send
                result = subprocess.run(cmd, capture_output=True, text=True)
            else:
                print(
                    f"  Warning: agent '{step.target}' did not register in time.",
                    file=sys.stderr,
                )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        print(
            f"  Step {step_num} failed (exit {result.returncode}).",
            file=sys.stderr,
        )
        return False
    return True


def _load_nested_workflow(
    store: WorkflowStore,
    workflow_name: str,
    stack: list[str],
) -> tuple[Workflow, list[str]]:
    """Load a nested workflow and enforce cycle/depth checks."""
    next_stack = [*stack, workflow_name]
    if workflow_name in stack:
        raise WorkflowError(f"Workflow cycle detected: {' -> '.join(next_stack)}")
    if len(next_stack) > MAX_WORKFLOW_DEPTH:
        raise WorkflowError(
            f"Workflow nesting exceeds maximum depth {MAX_WORKFLOW_DEPTH}: "
            f"{' -> '.join(next_stack)}"
        )
    child = store.load(workflow_name)
    if child is None:
        raise WorkflowError(f"Workflow '{workflow_name}' not found.")
    return child, next_stack


def _count_send_steps(
    workflow: Workflow,
    store: WorkflowStore,
    stack: list[str],
) -> int:
    """Count executable send steps across nested workflows."""
    count = 0
    for step in workflow.steps:
        if step.kind == "subworkflow":
            child, child_stack = _load_nested_workflow(store, step.workflow, stack)
            count += _count_send_steps(child, store, child_stack)
        else:
            count += 1
    return count


def _print_dry_run(
    workflow: Workflow,
    store: WorkflowStore,
    effective_auto_spawn: bool,
    stack: list[str],
    counter: list[int],
) -> None:
    """Print a dry-run preview including nested workflows."""
    for step in workflow.steps:
        if step.kind == "subworkflow":
            print(f"  Step {counter[0]}: subworkflow '{step.workflow}'")
            child, child_stack = _load_nested_workflow(store, step.workflow, stack)
            counter[0] += 1
            _print_dry_run(child, store, effective_auto_spawn, child_stack, counter)
            continue

        spawn_tag = (
            " [auto-spawn]" if _should_auto_spawn(step, effective_auto_spawn) else ""
        )
        print(f"  Step {counter[0]}: send to {step.target}{spawn_tag}")
        print(f"    message:  {step.message}")
        print(f"    priority: {step.priority}")
        print(f"    mode:     {step.response_mode}")
        print()
        counter[0] += 1


def _run_nested_workflow(
    workflow: Workflow,
    store: WorkflowStore,
    *,
    auto_spawn: bool,
    continue_on_error: bool,
    stack: list[str],
    counter: list[int],
    total: int,
    helper: _WorkflowHelper | None = None,
) -> int:
    """Execute workflow send steps recursively."""
    failures = 0
    for step in workflow.steps:
        if step.kind == "subworkflow":
            print(f"  Entering subworkflow '{step.workflow}'...")
            child, child_stack = _load_nested_workflow(store, step.workflow, stack)
            failures += _run_nested_workflow(
                child,
                store,
                auto_spawn=auto_spawn,
                continue_on_error=continue_on_error,
                stack=child_stack,
                counter=counter,
                total=total,
                helper=helper,
            )
            if failures and not continue_on_error:
                return failures
            continue

        counter[0] += 1
        ok = _run_step(step, counter[0], total, auto_spawn=auto_spawn, helper=helper)
        if not ok:
            failures += 1
            if not continue_on_error:
                return failures
    return failures


def cmd_workflow_run(args: argparse.Namespace) -> None:
    """Execute workflow steps sequentially."""
    if os.environ.get(_HELPER_ENV_MARKER):
        raw_depth = os.environ.get(_HELPER_DEPTH_ENV, "1")
        try:
            depth = int(raw_depth)
        except ValueError:
            depth = _MAX_HELPER_DEPTH + 1
        if depth > _MAX_HELPER_DEPTH or depth >= 1:
            print(
                "Error: Nested workflow execution is forbidden inside a helper agent.",
                file=sys.stderr,
            )
            sys.exit(1)

    name: str = args.workflow_name
    scope = _resolve_scope(args)
    dry_run = getattr(args, "dry_run", False)
    continue_on_error = getattr(args, "continue_on_error", False)
    auto_spawn = getattr(args, "auto_spawn", False)

    store = _get_workflow_store()
    try:
        wf = store.load(name, scope=scope)
    except WorkflowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if wf is None:
        print(f"Error: Workflow '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    effective_auto_spawn = auto_spawn or wf.auto_spawn

    try:
        total_steps = _count_send_steps(wf, store, [wf.name])
    except WorkflowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"DRY RUN: Workflow '{name}' ({wf.step_count} steps)")
        print()
        try:
            _print_dry_run(wf, store, effective_auto_spawn, [wf.name], [1])
        except WorkflowError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Create a helper for self-target steps (lazy spawn — only used if needed)
    from synapse.workflow_runner import _WorkflowHelper

    has_self_steps = any(s.target == "self" for s in wf.steps if s.kind == "send")
    helper: _WorkflowHelper | None = None
    if has_self_steps:
        sender_info = {
            "agent_id": os.getenv("SYNAPSE_AGENT_ID", ""),
            "agent_type": os.getenv("SYNAPSE_AGENT_TYPE", ""),
            "working_dir": str(Path.cwd()),
        }
        helper = _WorkflowHelper(
            workflow_name=name,
            sender_info=sender_info,
        )

    print(f"Running workflow '{name}' ({wf.step_count} steps)...")
    try:
        failures = _run_nested_workflow(
            wf,
            store,
            auto_spawn=effective_auto_spawn,
            continue_on_error=continue_on_error,
            stack=[wf.name],
            counter=[0],
            total=total_steps,
            helper=helper,
        )
    except WorkflowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if helper is not None:
            helper.kill()

    if failures:
        print(f"Done with {failures} failure(s).", file=sys.stderr)
        sys.exit(1)

    print("Done.")


# ── sync ────────────────────────────────────────────────────


def cmd_workflow_sync(args: argparse.Namespace) -> None:
    """Sync all workflow YAMLs to skill directories."""
    from synapse.workflow_skill_sync import sync_all_workflows

    project_dir = Path.cwd()
    written, removed = sync_all_workflows(project_dir)

    if written:
        print(f"Synced {len(written)} skill file(s):")
        for p in written:
            print(f"  {p}")
    if removed:
        print(f"Removed {len(removed)} orphan skill(s):")
        for p in removed:
            print(f"  {p}")
    if not written and not removed:
        print("Nothing to sync.")
