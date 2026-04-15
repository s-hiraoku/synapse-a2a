"""CLI handlers for ``synapse workflow`` subcommands."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import multiprocessing
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
from synapse.workflow_runner import (
    _DIR_MISMATCH_MARKER,
    _HELPER_ENV_MARKER,
    _NO_AGENT_MARKER,
)

logger = logging.getLogger(__name__)

_SPAWN_MAX_WAIT_SECONDS = 30
MAX_WORKFLOW_DEPTH = 10

# Retry a send when the target reports "Agent busy (working task)". Workflow
# steps are often long-running (minutes of model work), so the retry window
# must be generous: up to 10 checks at 30s intervals (~5 minutes total).
# Between checks we also poll the target's /tasks endpoint to detect the
# moment it becomes idle, so the retry fires as early as the target is ready
# rather than wasting full 30s sleeps when the lull is brief.
_BUSY_RETRY_MAX = 10
_BUSY_RETRY_INTERVAL = 30  # seconds between busy checks
_BUSY_MARKER = "Agent busy"


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
    except (ImportError, OSError) as e:
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
        except ImportError:
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
        except (ImportError, OSError) as e:
            logger.warning("Failed to remove workflow skill: %s", e)

        print(f"Workflow '{name}' deleted.")
    else:
        print(f"Error: Failed to delete workflow '{name}'.", file=sys.stderr)
        sys.exit(1)


# ── run ──────────────────────────────────────────────────────


def _should_auto_spawn(step: WorkflowStep, effective_auto_spawn: bool) -> bool:
    """Determine whether auto-spawn is enabled for a step."""
    return step.auto_spawn or effective_auto_spawn


def _workflow_spawn_tool_args(profile: str) -> list[str] | None:
    """Pick tool_args for a workflow-triggered spawn.

    Workflow runs typically batch many short-lived permission requests
    (``cp``, ``git``, ``gh``, ``pytest``) against a long-running child.
    The profile's default ``auto_approve.cli_flag`` (e.g. ``--full-auto``)
    leaves the child's sandbox in ``workspace-write`` mode, which prompts
    for approval on any action outside cwd/workspace. Those prompts drain
    the full runtime-approval budget — and the first regex miss leaves
    the child stuck waiting for a human who isn't coming.

    Prefer the profile's first ``alternative_flag`` when it exists (e.g.
    ``--dangerously-bypass-approvals-and-sandbox`` for codex) so a
    workflow-driven child just runs. A user starting an interactive agent
    via ``synapse spawn`` / ``synapse team start`` still gets the safer
    ``--full-auto`` default — nothing about those paths changes.

    Returns None when the profile has no auto-approve config or no
    alternative flags; in that case the caller falls through to the
    profile's default.
    """
    try:
        from synapse.server import load_profile

        profile_config = load_profile(profile)
    except Exception:  # broad: missing profile, yaml error, etc.
        return None
    if not isinstance(profile_config, dict):
        return None
    auto_approve_config = profile_config.get("auto_approve")
    if not isinstance(auto_approve_config, dict):
        return None
    alternatives = auto_approve_config.get("alternative_flags")
    if not isinstance(alternatives, list) or not alternatives:
        return None
    flag = str(alternatives[0] or "").strip()
    if not flag:
        return None
    return [flag]


def _try_spawn_agent(profile: str) -> bool:
    """Spawn an agent by profile name. Returns True on success."""
    try:
        from synapse.spawn import spawn_agent

        tool_args = _workflow_spawn_tool_args(profile)
        result = spawn_agent(profile, tool_args=tool_args)
        if result.status == "submitted":
            suffix = f" with {' '.join(tool_args)}" if tool_args else ""
            print(f"  Spawned {profile} agent (port {result.port}){suffix}")
            return True
        print(
            f"  Warning: spawn {profile} returned status '{result.status}'",
            file=sys.stderr,
        )
        return False
    except (ImportError, OSError, RuntimeError) as e:
        print(f"  Warning: failed to spawn '{profile}': {e}", file=sys.stderr)
        return False


def _target_has_no_working_task(target: str) -> bool:
    """Return True when *target* currently has no working/input_required task.

    Uses the resolver with ``local_only=True`` so bare-type targets only
    match an agent in the caller's working directory. Returns False on any
    error (conservative — caller keeps waiting rather than racing into 409).
    """
    from synapse.registry import AgentRegistry
    from synapse.tools.a2a import _resolve_target_agent

    try:
        agents = AgentRegistry().list_agents()
        agent, _err = _resolve_target_agent(target, agents, local_only=True)
        if agent is None:
            return False
        endpoint = agent.get("endpoint")
        if not endpoint:
            return False
        import urllib.request

        with urllib.request.urlopen(
            f"{str(endpoint).rstrip('/')}/tasks", timeout=5
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tasks = data.get("tasks") if isinstance(data, dict) else data
        if not isinstance(tasks, list):
            return False
        for task in tasks:
            status = task.get("status") if isinstance(task, dict) else ""
            if isinstance(status, dict):
                status = status.get("state", "")
            if status in ("working", "input_required"):
                return False
        return True
    except Exception:  # broad: any transient HTTP/parse error → keep waiting
        return False


def _wait_for_agent(target: str, timeout: float = _SPAWN_MAX_WAIT_SECONDS) -> bool:
    """Poll registry until an agent matching *target* appears in the caller's
    working directory. Uses ``local_only=True`` so bare-type targets like
    ``codex`` are not satisfied by an instance running in a different repo —
    otherwise auto-spawn would think the spawn succeeded as soon as any
    codex registered anywhere on the machine, then immediately hit
    ``No agent found`` on the local retry."""
    from synapse.registry import AgentRegistry
    from synapse.tools.a2a import _resolve_target_agent

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        agents = AgentRegistry().list_agents()
        agent, _err = _resolve_target_agent(target, agents, local_only=True)
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
        except Exception as exc:  # broad catch: step execution may fail in many ways
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
        local_only=True,
    )

    # 409 Agent busy can occur transiently between back-to-back workflow
    # steps while the previous step's task is still finalizing in the
    # target's task store, or while the target is processing a large body
    # of work from the prior step. Poll the target's /tasks endpoint until
    # it drains; as soon as there is no working/input_required task, fire
    # the retry. This avoids wasting the full interval sleep when the lull
    # is short, while still bounding the total wait to ~5 minutes so a
    # genuinely stuck target still surfaces as a step failure.
    result = subprocess.run(cmd, capture_output=True, text=True)
    for attempt in range(_BUSY_RETRY_MAX):
        stderr_for_busy = result.stderr or ""
        if result.returncode == 0 or _BUSY_MARKER not in stderr_for_busy:
            break
        print(
            f"  Target agent busy; waiting up to {_BUSY_RETRY_INTERVAL}s for idle "
            f"(attempt {attempt + 1}/{_BUSY_RETRY_MAX})...",
            file=sys.stderr,
        )
        wait_deadline = time.monotonic() + _BUSY_RETRY_INTERVAL
        while time.monotonic() < wait_deadline:
            if _target_has_no_working_task(step.target):
                break
            time.sleep(2)
        result = subprocess.run(cmd, capture_output=True, text=True)

    # Check if agent not found (or only exists in a different working
    # directory) and auto-spawn is enabled. With --local-only the resolver
    # reports NO_AGENT when no same-dir candidate exists, but we still accept
    # DIR_MISMATCH as a spawn trigger defensively in case a future code path
    # relaxes local_only enforcement.
    stderr_text = result.stderr or ""
    if (
        result.returncode != 0
        and (_NO_AGENT_MARKER in stderr_text or _DIR_MISMATCH_MARKER in stderr_text)
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


def _workflow_background_worker(
    workflow_name: str,
    scope: Scope | None,
    continue_on_error: bool,
    sender_info: dict[str, str],
    cwd: str,
    conn: multiprocessing.connection.Connection,
) -> None:
    """Run a workflow in a separate process and report the run ID back."""
    try:
        os.chdir(cwd)
        store = _get_workflow_store()
        wf = store.load(workflow_name, scope=scope)
        if wf is None:
            raise WorkflowError(f"Workflow '{workflow_name}' not found.")

        async def _run() -> None:
            from synapse.workflow_runner import get_run, run_workflow

            run_id = await run_workflow(
                wf,
                continue_on_error=continue_on_error,
                sender_info=sender_info,
            )
            conn.send(("ok", run_id))
            while True:
                run = get_run(run_id)
                if run is None or run.status != "running":
                    return
                await asyncio.sleep(0.1)

        asyncio.run(_run())
    except (
        Exception
    ) as exc:  # broad catch: defensive worker must report all errors to parent
        with contextlib.suppress(Exception):
            conn.send(("error", str(exc)))
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def _start_background_workflow(
    workflow_name: str,
    scope: Scope | None,
    continue_on_error: bool,
) -> str:
    """Start a workflow in a background process and return its run ID."""
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    sender_info = {
        "agent_id": os.getenv("SYNAPSE_AGENT_ID", ""),
        "agent_type": os.getenv("SYNAPSE_AGENT_TYPE", ""),
        "working_dir": str(Path.cwd()),
    }
    process = ctx.Process(
        target=_workflow_background_worker,
        args=(
            workflow_name,
            scope,
            continue_on_error,
            sender_info,
            str(Path.cwd()),
            child_conn,
        ),
        daemon=False,
    )
    process.start()
    child_conn.close()

    if not parent_conn.poll(5):
        process.terminate()
        process.join(timeout=1)
        raise WorkflowError("Timed out starting background workflow.")

    status, payload = parent_conn.recv()
    parent_conn.close()

    if status != "ok":
        process.join(timeout=1)
        raise WorkflowError(payload)

    return str(payload)


def cmd_workflow_run(args: argparse.Namespace) -> None:
    """Execute workflow steps sequentially."""
    if os.environ.get(_HELPER_ENV_MARKER):
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
    run_async = getattr(args, "run_async", False)

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

    if run_async:
        try:
            run_id = _start_background_workflow(name, scope, continue_on_error)
        except WorkflowError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Workflow '{name}' started in background.")
        print(f"  run_id: {run_id}")
        print(f"  Track: synapse workflow status {run_id}")
        return

    # Create a helper for self-target steps (lazy spawn — only used if needed)
    from synapse.workflow_runner import _is_self_target, _WorkflowHelper

    sender_info = {
        "agent_id": os.getenv("SYNAPSE_AGENT_ID", ""),
        "agent_type": os.getenv("SYNAPSE_AGENT_TYPE", ""),
        "working_dir": str(Path.cwd()),
    }

    def _has_self_steps_recursive(workflow: Workflow, store: WorkflowStore) -> bool:
        for s in workflow.steps:
            if s.kind == "send" and _is_self_target(s.target, sender_info):
                return True
            if s.kind == "subworkflow":
                child = store.load(s.workflow)
                if child and _has_self_steps_recursive(child, store):
                    return True
        return False

    has_self_steps = _has_self_steps_recursive(wf, store)
    helper: _WorkflowHelper | None = None
    if has_self_steps:
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


def cmd_workflow_status(args: argparse.Namespace) -> None:
    """Show status for a background workflow run."""
    from synapse.workflow_runner import get_run

    run = get_run(args.run_id)
    if run is None:
        print(f"Run '{args.run_id}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Workflow: {run.workflow_name}")
    print(f"Run ID:   {run.run_id}")
    print(f"Status:   {run.status}")
    for step in run.steps:
        data = step.to_dict()
        print(
            f"  Step {data['step_index']}: {data['status']} | "
            f"{data['target']} | {data['message'][:60]}"
        )


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
