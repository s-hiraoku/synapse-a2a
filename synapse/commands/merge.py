"""Merge command implementation for worktree agents."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.worktree import (
    WorktreeInfo,
    get_git_root,
    has_worktree_changes,
    merge_worktree,
    worktree_info_from_registry,
)

if TYPE_CHECKING:
    from synapse.registry import AgentRegistry


def _get_worktree_info_from_agent(agent_info: dict[str, Any]) -> WorktreeInfo | None:
    """Reconstruct worktree metadata from registry info."""
    wt_path = agent_info.get("worktree_path")
    wt_branch = agent_info.get("worktree_branch")
    if not wt_path or not wt_branch:
        return None

    return worktree_info_from_registry(
        str(wt_path),
        str(wt_branch),
        str(agent_info.get("worktree_base_branch", "")),
    )


def merge_single(
    agent_info: dict[str, Any],
    *,
    dry_run: bool = False,
    resolve_with: str | None = None,
    registry: AgentRegistry | None = None,
) -> bool:
    """Merge a single worktree agent branch into the current branch."""
    wt_info = _get_worktree_info_from_agent(agent_info)
    display_name = str(agent_info.get("name") or agent_info.get("agent_id") or "agent")

    if wt_info is None:
        print(f"Agent '{display_name}' does not have a worktree branch to merge.")
        return False

    if dry_run:
        if has_worktree_changes(wt_info):
            print(f"Would merge {wt_info.branch} from {display_name}.")
        else:
            print(f"Nothing to merge for {display_name}.")
        return True

    if merge_worktree(wt_info):
        print(f"Merged {wt_info.branch} from {display_name}.")
        return True

    if (
        resolve_with
        and _delegate_conflict_resolution(wt_info, agent_info, resolve_with, registry)
        and merge_worktree(wt_info)
    ):
        print(
            f"Merged {wt_info.branch} from {display_name} after {resolve_with} resolved conflicts."
        )
        return True

    print(f"Resolve manually: git merge {wt_info.branch}")
    return False


def merge_all(
    registry: AgentRegistry,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Merge all live agents that have worktree metadata."""
    agents = list(registry.get_live_agents().values())
    worktree_agents = [
        info for info in agents if _get_worktree_info_from_agent(info) is not None
    ]

    if not worktree_agents:
        print("No worktree agents to merge.")
        return (0, 0)

    success_count = 0
    failure_count = 0
    for agent_info in worktree_agents:
        if merge_single(agent_info, dry_run=dry_run, registry=registry):
            success_count += 1
        else:
            failure_count += 1

    if len(worktree_agents) > 1 or failure_count:
        if dry_run:
            print(
                f"Dry run summary: {success_count} mergeable, {failure_count} with issues."
            )
        else:
            print(f"Merge summary: {success_count} succeeded, {failure_count} failed.")

    return (success_count, failure_count)


def _delegate_conflict_resolution(
    wt_info: WorktreeInfo,
    agent_info: dict[str, Any],
    resolve_with: str,
    registry: AgentRegistry | None,
) -> bool:
    """Delegate merge-conflict resolution to another agent via A2A."""
    if registry is None:
        print("Cannot delegate conflict resolution without an agent registry.")
        return False

    resolver = registry.resolve_agent(resolve_with)
    if resolver is None:
        print(f"Resolver agent not found: {resolve_with}")
        return False

    from synapse.cli import _build_a2a_cmd, _run_a2a_command

    git_root = get_git_root()
    diff_text = _get_conflict_diff(wt_info.branch, git_root)
    target = str(resolver.get("name") or resolver.get("agent_id") or resolve_with)
    sender = os.environ.get("SYNAPSE_AGENT_ID")
    display_name = str(agent_info.get("name") or agent_info.get("agent_id") or "agent")
    message = (
        f"Please resolve merge conflicts for worktree branch '{wt_info.branch}'.\n"
        f"Agent: {display_name}\n"
        f"Worktree: {wt_info.path}\n"
        f"Base branch: {wt_info.base_branch or '(unknown)'}\n"
        "After resolving, reply with completion status."
    )

    attachments: list[str] = []
    if diff_text:
        diff_dir = Path(tempfile.gettempdir()) / "synapse-a2a" / "merge-diffs"
        diff_dir.mkdir(parents=True, exist_ok=True)
        diff_path = diff_dir / f"{wt_info.name}-merge.diff"
        diff_path.write_text(diff_text, encoding="utf-8")
        attachments.append(str(diff_path))

    cmd = _build_a2a_cmd(
        "send",
        message,
        target=target,
        sender=sender,
        response_mode="wait",
        attachments=attachments or None,
    )
    try:
        _run_a2a_command(cmd, exit_on_error=True)
    except SystemExit:
        return False
    return True


def _get_conflict_diff(branch: str, git_root: Path) -> str:
    """Return a diff for the worktree branch relative to the current branch."""
    result = subprocess.run(
        ["git", "diff", f"HEAD...{branch}"],
        capture_output=True,
        text=True,
        cwd=str(git_root),
    )
    if result.returncode != 0:
        return ""
    return result.stdout
