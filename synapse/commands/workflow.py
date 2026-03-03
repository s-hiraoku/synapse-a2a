"""CLI handlers for ``synapse workflow`` subcommands."""

from __future__ import annotations

import argparse
import subprocess
import sys

from synapse.workflow import (
    Scope,
    Workflow,
    WorkflowError,
    WorkflowStep,
    WorkflowStore,
)


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
        # Check for existing workflow (load() validates the name)
        if not force and store.load(name, scope=scope) is not None:
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
    wf = store.load(name, scope=scope)

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
        print(
            f"  {i}. target={step.target}  priority={step.priority}  mode={step.response_mode}"
        )
        # Truncate long messages for display
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
    wf = store.load(name, scope=scope)
    if wf is None:
        print(f"Error: Workflow '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    if not force:
        answer = input(f"Delete workflow '{name}' ({wf.step_count} steps)? [y/N] ")
        if answer.lower() not in ("y", "yes"):
            print("Cancelled.")
            return

    deleted = store.delete(name, scope=wf.scope)
    if deleted:
        print(f"Workflow '{name}' deleted.")
    else:
        print(f"Error: Failed to delete workflow '{name}'.", file=sys.stderr)
        sys.exit(1)


# ── run ──────────────────────────────────────────────────────


def cmd_workflow_run(args: argparse.Namespace) -> None:
    """Execute workflow steps sequentially."""
    name: str = args.workflow_name
    scope = _resolve_scope(args)
    dry_run = getattr(args, "dry_run", False)
    continue_on_error = getattr(args, "continue_on_error", False)

    store = _get_workflow_store()
    wf = store.load(name, scope=scope)

    if wf is None:
        print(f"Error: Workflow '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"DRY RUN: Workflow '{name}' ({wf.step_count} steps)")
        print()
        for i, step in enumerate(wf.steps, 1):
            print(f"  Step {i}: send to {step.target}")
            print(f"    message:  {step.message}")
            print(f"    priority: {step.priority}")
            print(f"    mode:     {step.response_mode}")
            print()
        return

    print(f"Running workflow '{name}' ({wf.step_count} steps)...")

    from synapse.cli import _build_a2a_cmd

    failures = 0
    for i, step in enumerate(wf.steps, 1):
        print(f"  Step {i}/{wf.step_count}: → {step.target} ({step.response_mode})")

        cmd = _build_a2a_cmd(
            "send",
            step.message,
            target=step.target,
            priority=step.priority,
            response_mode=step.response_mode,
        )

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        if result.returncode != 0:
            failures += 1
            print(f"  Step {i} failed (exit {result.returncode}).", file=sys.stderr)
            if not continue_on_error:
                sys.exit(1)

    if failures:
        print(f"Done with {failures} failure(s).", file=sys.stderr)
        sys.exit(1)

    print("Done.")
