"""Git worktree management for Synapse.

Provides agent-agnostic worktree isolation so that any CLI agent
(Claude, Gemini, Codex, OpenCode, Copilot) can work in its own
checkout without file conflicts.

Worktrees are placed under ``.synapse/worktrees/<name>/`` with a
branch named ``worktree-<name>``.
"""

from __future__ import annotations

import logging
import random
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# Data
# ============================================================


@dataclass
class WorktreeInfo:
    """Metadata for a created worktree."""

    name: str  # e.g., "bright-falcon"
    path: Path  # e.g., /repo/.synapse/worktrees/bright-falcon
    branch: str  # e.g., "worktree-bright-falcon"
    base_branch: str  # e.g., "origin/main"
    created_at: float


# ============================================================
# Name generation (adjective-noun)
# ============================================================

_ADJECTIVES = [
    "bold",
    "brave",
    "bright",
    "calm",
    "cool",
    "crisp",
    "dark",
    "deep",
    "fair",
    "fast",
    "firm",
    "glad",
    "gold",
    "grand",
    "keen",
    "kind",
    "late",
    "lean",
    "live",
    "long",
    "mild",
    "neat",
    "nice",
    "pale",
    "pure",
    "rare",
    "rich",
    "safe",
    "slim",
    "soft",
    "sure",
    "tall",
    "thin",
    "true",
    "vast",
    "warm",
    "wide",
    "wild",
    "wise",
    "young",
]

_NOUNS = [
    "ant",
    "bat",
    "bear",
    "bird",
    "bull",
    "cat",
    "colt",
    "crow",
    "deer",
    "dove",
    "duck",
    "fawn",
    "fish",
    "fox",
    "frog",
    "goat",
    "hare",
    "hawk",
    "jay",
    "lark",
    "lion",
    "lynx",
    "mole",
    "moth",
    "newt",
    "owl",
    "puma",
    "ram",
    "seal",
    "swan",
    "toad",
    "vole",
    "wasp",
    "wolf",
    "wren",
    "yak",
    "ape",
    "elk",
    "emu",
    "koi",
]


def generate_worktree_name() -> str:
    """Generate a random adjective-noun name for a worktree."""
    adj = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    return f"{adj}-{noun}"


# ============================================================
# Git helpers
# ============================================================


def get_git_root() -> Path:
    """Return the root directory of the current git repository.

    Raises:
        RuntimeError: If not inside a git repository.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Not a git repository")
    return Path(result.stdout.strip())


def _ref_exists(ref: str) -> bool:
    """Check if a git ref exists locally."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def get_default_remote_branch() -> str:
    """Detect the default remote branch (e.g., ``origin/main``).

    Falls back through: symbolic-ref → ``origin/main`` → ``HEAD``.
    Each candidate is verified to exist locally before returning.
    """
    # Try symbolic-ref first
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        # "refs/remotes/origin/main" -> "origin/main"
        ref = result.stdout.strip().replace("refs/remotes/", "")
        if _ref_exists(ref):
            return ref

    # Fallback to origin/main
    if _ref_exists("origin/main"):
        return "origin/main"

    # Last resort: use current HEAD
    return "HEAD"


# ============================================================
# Worktree lifecycle
# ============================================================


_WORKTREE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_WORKTREE_NAME_MAX_LEN = 100


def _validate_worktree_name(name: str) -> str:
    """Validate and return a safe worktree name.

    Raises:
        ValueError: If the name contains unsafe characters.
    """
    name = name.strip()
    if not name:
        raise ValueError("Worktree name must not be empty")
    if len(name) > _WORKTREE_NAME_MAX_LEN:
        raise ValueError(
            f"Worktree name too long ({len(name)} chars, max {_WORKTREE_NAME_MAX_LEN})"
        )
    if not _WORKTREE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid worktree name '{name}': "
            "only alphanumerics, hyphens, dots, and underscores are allowed"
        )
    return name


def create_worktree(
    name: str | None = None,
    base_branch: str | None = None,
) -> WorktreeInfo:
    """Create a new git worktree under ``.synapse/worktrees/``.

    Args:
        name: Worktree name. Auto-generated if None.
        base_branch: Git ref to base the worktree on (e.g. a remote branch).
            Defaults to ``get_default_remote_branch()`` when None.

    Returns:
        WorktreeInfo with path, branch, and metadata.

    Raises:
        RuntimeError: If not in a git repo, directory exists, or git fails.
        ValueError: If the provided name contains unsafe characters.
    """
    git_root = get_git_root()
    if base_branch is not None:
        base_branch = base_branch.strip()
        if not base_branch:
            raise ValueError("base_branch must not be empty")
        if base_branch.startswith("-"):
            raise ValueError(
                f"Invalid base_branch '{base_branch}': must not start with '-'"
            )
    else:
        base_branch = get_default_remote_branch()

    name = generate_worktree_name() if name is None else _validate_worktree_name(name)

    worktree_dir = git_root / ".synapse" / "worktrees" / name
    branch_name = f"worktree-{name}"

    if worktree_dir.exists():
        raise RuntimeError(f"Worktree directory already exists: {worktree_dir}")

    # Ensure parent directory exists
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_dir), "-b", branch_name, base_branch],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to create worktree '{name}': {result.stderr.strip()}"
        )

    logger.info(
        "event=worktree_created name=%s path=%s branch=%s base=%s",
        name,
        worktree_dir,
        branch_name,
        base_branch,
    )

    return WorktreeInfo(
        name=name,
        path=worktree_dir,
        branch=branch_name,
        base_branch=base_branch,
        created_at=time.time(),
    )


def remove_worktree(path: Path, branch: str, force: bool = False) -> bool:
    """Remove a worktree and its branch.

    Args:
        path: Worktree directory path.
        branch: Branch name to delete.
        force: If True, use ``--force`` for removal and ``-D`` for branch.

    Returns:
        True if removal succeeded, False otherwise.
    """
    force_flag = ["--force"] if force else []
    result = subprocess.run(
        ["git", "worktree", "remove", *force_flag, str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(
            "event=worktree_remove_failed path=%s error=%s",
            path,
            result.stderr.strip(),
        )
        return False

    # Delete the branch
    branch_flag = "-D" if force else "-d"
    branch_result = subprocess.run(
        ["git", "branch", branch_flag, branch],
        capture_output=True,
        text=True,
    )
    if branch_result.returncode != 0:
        logger.warning(
            "event=worktree_branch_delete_failed branch=%s error=%s",
            branch,
            branch_result.stderr.strip(),
        )
        # Worktree was removed, branch deletion is best-effort
    else:
        logger.info("event=worktree_removed path=%s branch=%s", path, branch)

    return True


def has_uncommitted_changes(path: Path) -> bool:
    """Check if a worktree directory has uncommitted changes.

    Returns True on subprocess failure to avoid accidental cleanup.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(path),
        )
    except OSError:
        logger.warning("git status failed for %s", path, exc_info=True)
        return True
    if result.returncode != 0:
        logger.warning(
            "git status returned %d for %s: %s",
            result.returncode,
            path,
            result.stderr.strip(),
        )
        return True
    return bool(result.stdout.strip())


def has_new_commits(path: Path, base_branch: str) -> bool:
    """Check if a worktree branch has commits beyond the base branch.

    Returns True on subprocess failure to avoid accidental cleanup.
    """
    if not base_branch:
        logger.warning("Missing base_branch for %s, treating as modified", path)
        return True
    try:
        result = subprocess.run(
            ["git", "log", f"{base_branch}..HEAD", "--oneline"],
            capture_output=True,
            text=True,
            cwd=str(path),
        )
    except OSError:
        logger.warning("git log failed for %s", path, exc_info=True)
        return True
    if result.returncode != 0:
        logger.warning(
            "git log returned %d for %s: %s",
            result.returncode,
            path,
            result.stderr.strip(),
        )
        return True
    return bool(result.stdout.strip())


def has_worktree_changes(info: WorktreeInfo) -> bool:
    """Check if a worktree has uncommitted changes OR new commits.

    This matches Claude Code's behavior: cleanup prompts when there are
    either uncommitted changes or commits beyond the base branch.
    """
    return has_uncommitted_changes(info.path) or has_new_commits(
        info.path, info.base_branch
    )


def merge_worktree(
    info: WorktreeInfo,
    auto_commit_wip: bool = True,
    *,
    _has_uncommitted: bool | None = None,
    _has_commits: bool | None = None,
) -> bool:
    """Merge a worktree branch into the current branch.

    Args:
        info: WorktreeInfo for the worktree to merge.
        auto_commit_wip: If True, auto-commit uncommitted changes before merge.
        _has_uncommitted: Pre-computed result from has_uncommitted_changes().
            If None, will be checked. Used by cleanup_worktree to avoid
            redundant subprocess calls.
        _has_commits: Pre-computed result from has_new_commits().
            If None, will be checked.
    """
    uncommitted = (
        _has_uncommitted
        if _has_uncommitted is not None
        else has_uncommitted_changes(info.path)
    )
    commits = (
        _has_commits
        if _has_commits is not None
        else has_new_commits(info.path, info.base_branch)
    )

    if auto_commit_wip and uncommitted:
        add_result = subprocess.run(
            ["git", "add", "-u"],
            capture_output=True,
            text=True,
            cwd=str(info.path),
        )
        if add_result.returncode != 0:
            logger.warning(
                "git add failed for %s: %s",
                info.path,
                add_result.stderr.strip(),
            )
            return False

        commit_result = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"wip: uncommitted changes from {info.name}",
            ],
            capture_output=True,
            text=True,
            cwd=str(info.path),
        )
        if commit_result.returncode != 0:
            logger.warning(
                "git commit failed for %s: %s",
                info.path,
                commit_result.stderr.strip(),
            )
            return False
        # After WIP commit, there are now new commits to merge
        commits = True

    if not commits:
        return True

    git_root = get_git_root()
    merge_result = subprocess.run(
        ["git", "merge", info.branch, "--no-edit"],
        capture_output=True,
        text=True,
        cwd=str(git_root),
    )
    if merge_result.returncode == 0:
        return True

    abort_result = subprocess.run(
        ["git", "merge", "--abort"],
        capture_output=True,
        text=True,
        cwd=str(git_root),
    )
    if abort_result.returncode != 0:
        logger.warning("git merge --abort failed: %s", abort_result.stderr.strip())
    print(f"[Synapse] Merge conflict for {info.branch}.")
    print(f"  Branch preserved: {info.branch}")
    print(f"  Resolve manually: git merge {info.branch}")
    logger.warning(
        "Merge conflict for %s: %s",
        info.branch,
        merge_result.stderr.strip(),
    )
    return False


def worktree_info_from_registry(
    worktree_path: str,
    worktree_branch: str,
    worktree_base_branch: str = "",
) -> WorktreeInfo:
    """Reconstruct a WorktreeInfo from registry metadata.

    Used when cleaning up worktrees for killed or exiting agents,
    where only the path, branch, and base branch are available from
    registry data.
    """
    return WorktreeInfo(
        name=Path(worktree_path).name,
        path=Path(worktree_path),
        branch=worktree_branch,
        base_branch=worktree_base_branch,
        created_at=0,
    )


def cleanup_worktree(
    info: WorktreeInfo,
    interactive: bool = False,
    merge: bool = False,
) -> bool:
    """Clean up a worktree, optionally prompting the user.

    - If no uncommitted changes or new commits: auto-remove.
    - If changes/commits exist and interactive: prompt user.
    - If changes/commits exist and non-interactive: keep worktree.

    Args:
        info: WorktreeInfo for the worktree to clean up.
        interactive: Whether to prompt the user.
        merge: If True, merge the worktree branch before removal.

    Returns:
        True if worktree was removed, False if kept.
    """
    uncommitted = has_uncommitted_changes(info.path)
    commits = has_new_commits(info.path, info.base_branch)

    if not uncommitted and not commits:
        return remove_worktree(info.path, info.branch, force=False)

    if merge:
        if merge_worktree(info, _has_uncommitted=uncommitted, _has_commits=commits):
            return remove_worktree(info.path, info.branch, force=False)
        return False

    # Changes or new commits exist
    if not interactive:
        logger.info(
            "event=worktree_kept_dirty name=%s path=%s",
            info.name,
            info.path,
        )
        print(
            f"\x1b[33m[Synapse]\x1b[0m Worktree '{info.name}' has unsaved work."
            f"\n  Path: {info.path}"
            f"\n  Branch: {info.branch}"
        )
        return False

    # Interactive: ask user
    try:
        answer = (
            input(
                f"Worktree '{info.name}' has unsaved work.\n"
                f"  Path: {info.path}\n"
                f"  Branch: {info.branch}\n"
                f"Remove anyway? [y/N]: "
            )
            .strip()
            .lower()
        )
        if answer == "y":
            return remove_worktree(info.path, info.branch, force=True)
    except (EOFError, KeyboardInterrupt):
        pass

    return False


# ============================================================
# Prune orphan worktrees
# ============================================================


def _parse_prunable_worktrees(
    porcelain_output: str, synapse_wt_prefix: str
) -> list[str]:
    """Parse ``git worktree list --porcelain`` and return prunable synapse worktree names."""
    prunable: list[str] = []
    current_path: str | None = None
    is_prunable = False

    for line in porcelain_output.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree ") :]
            is_prunable = False
        elif line.startswith("prunable"):
            is_prunable = True
        elif line == "":
            if (
                is_prunable
                and current_path
                and current_path.startswith(synapse_wt_prefix)
            ):
                name = current_path[len(synapse_wt_prefix) :]
                if name:
                    prunable.append(name)
            current_path = None
            is_prunable = False

    return prunable


def prune_worktrees() -> list[str]:
    """Remove orphan worktrees under ``.synapse/worktrees/``.

    Detects worktrees that git marks as *prunable* (directory missing),
    runs ``git worktree prune`` to clean up git's internal references,
    and deletes the corresponding ``worktree-<name>`` branches.

    Returns:
        List of pruned worktree names.
    """
    git_root = get_git_root()
    synapse_wt_prefix = str(git_root / ".synapse" / "worktrees") + "/"

    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("git worktree list failed: %s", result.stderr.strip())
        return []

    prunable = _parse_prunable_worktrees(result.stdout, synapse_wt_prefix)
    if not prunable:
        return []

    # Remove stale git worktree references
    prune_result = subprocess.run(
        ["git", "worktree", "prune"],
        capture_output=True,
        text=True,
    )
    if prune_result.returncode != 0:
        logger.warning("git worktree prune failed: %s", prune_result.stderr.strip())
        return []

    # Best-effort batch branch cleanup
    branches = [f"worktree-{name}" for name in prunable]
    branch_result = subprocess.run(
        ["git", "branch", "-d", *branches],
        capture_output=True,
        text=True,
    )
    if branch_result.returncode != 0:
        logger.warning(
            "event=prune_branch_delete_failed error=%s",
            branch_result.stderr.strip(),
        )

    logger.info("event=worktrees_pruned count=%d names=%s", len(prunable), prunable)
    return prunable
