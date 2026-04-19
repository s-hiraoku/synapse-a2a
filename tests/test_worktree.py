"""Tests for synapse.worktree module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.worktree import (
    WorktreeInfo,
    _ref_exists,
    _validate_worktree_name,
    cleanup_worktree,
    create_worktree,
    generate_worktree_name,
    get_default_remote_branch,
    get_git_root,
    get_main_repo_root,
    has_new_commits,
    has_uncommitted_changes,
    has_worktree_changes,
    merge_worktree,
    prune_worktrees,
    remove_worktree,
    worktree_info_from_registry,
)

# ============================================================
# get_git_root
# ============================================================


class TestGetGitRoot:
    def test_returns_path(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n", stderr="")
            result = get_git_root()
            assert result == Path("/repo")
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd == ["git", "rev-parse", "--show-toplevel"]

    def test_raises_when_not_git_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="fatal: not a git repository"
            )
            with pytest.raises(RuntimeError, match="Not a git repository"):
                get_git_root()


# ============================================================
# get_main_repo_root  (issue #546)
# ============================================================


class TestGetMainRepoRoot:
    """`get_main_repo_root` must always return the original repo root.

    Even when called from inside a git worktree, the function should
    resolve to the directory that owns ``.git/`` (the main checkout),
    not the current worktree's toplevel. This prevents nested worktrees
    being created at ``<wt>/.synapse/worktrees/<wt2>``.
    """

    def test_main_repo_detection_uses_git_common_dir(self) -> None:
        """Function must invoke ``git rev-parse --git-common-dir``."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="/repo/.git\n", stderr=""
            )
            result = get_main_repo_root()
            assert result == Path("/repo")
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd == ["git", "rev-parse", "--git-common-dir"]

    def test_resolves_relative_common_dir(self, tmp_path: Path) -> None:
        """When git returns ``.git`` (relative), resolve it via ``cwd``."""
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=".git\n", stderr="")
            with patch("pathlib.Path.cwd", return_value=repo):
                result = get_main_repo_root()
            assert result == repo

    def test_strips_worktrees_subpath(self) -> None:
        """When invoked inside a worktree, ``--git-common-dir`` returns
        the main ``.git`` directory regardless. Its parent is the main
        repo root."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="/repo/.git\n",
                stderr="",
            )
            result = get_main_repo_root()
            # Parent of /repo/.git is /repo (the main checkout), NOT
            # /repo/.synapse/worktrees/rich-elk (the current worktree).
            assert result == Path("/repo")

    def test_raises_when_not_git_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="fatal: not a git repository"
            )
            with pytest.raises(RuntimeError, match="Not a git repository"):
                get_main_repo_root()


# ============================================================
# get_default_remote_branch
# ============================================================


class TestRefExists:
    def test_ref_exists_true(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert _ref_exists("origin/main") is True

    def test_ref_exists_false(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128)
            assert _ref_exists("origin/nonexistent") is False


class TestGetDefaultRemoteBranch:
    def test_parses_origin_main(self) -> None:
        """symbolic-ref returns origin/main and it exists locally."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="refs/remotes/origin/main\n", stderr=""),
                MagicMock(returncode=0),  # _ref_exists("origin/main") -> True
            ]
            result = get_default_remote_branch()
            assert result == "origin/main"

    def test_parses_origin_master(self) -> None:
        """symbolic-ref returns origin/master and it exists locally."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0, stdout="refs/remotes/origin/master\n", stderr=""
                ),
                MagicMock(returncode=0),  # _ref_exists("origin/master") -> True
            ]
            result = get_default_remote_branch()
            assert result == "origin/master"

    def test_fallback_to_origin_main_on_failure(self) -> None:
        """symbolic-ref fails, falls back to origin/main which exists."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=128, stdout="", stderr="fatal: ref not found"),
                MagicMock(returncode=0),  # _ref_exists("origin/main") -> True
            ]
            result = get_default_remote_branch()
            assert result == "origin/main"

    def test_symbolic_ref_points_to_nonexistent_branch(self) -> None:
        """symbolic-ref succeeds but ref doesn't exist locally — fall back to origin/main."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0, stdout="refs/remotes/origin/feature/gone\n", stderr=""
                ),
                MagicMock(
                    returncode=128
                ),  # _ref_exists("origin/feature/gone") -> False
                MagicMock(returncode=0),  # _ref_exists("origin/main") -> True
            ]
            result = get_default_remote_branch()
            assert result == "origin/main"

    def test_fallback_to_head_when_no_remote(self) -> None:
        """Both symbolic-ref and origin/main fail — fall back to HEAD."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=128, stdout="", stderr="fatal"
                ),  # symbolic-ref fails
                MagicMock(returncode=128),  # _ref_exists("origin/main") -> False
            ]
            result = get_default_remote_branch()
            assert result == "HEAD"


# ============================================================
# generate_worktree_name
# ============================================================


class TestGenerateWorktreeName:
    def test_format_adjective_noun(self) -> None:
        name = generate_worktree_name()
        parts = name.split("-")
        assert len(parts) == 2, f"Expected adjective-noun format, got: {name}"

    def test_unique_names(self) -> None:
        names = {generate_worktree_name() for _ in range(50)}
        # With ~1600 combinations, 50 samples should have very few collisions
        assert len(names) >= 40


# ============================================================
# create_worktree
# ============================================================


class TestCreateWorktree:
    @patch("synapse.worktree.get_default_remote_branch", return_value="origin/main")
    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    def test_create_worktree_auto_name(
        self,
        mock_mkdir: MagicMock,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
        mock_remote: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch(
            "synapse.worktree.generate_worktree_name", return_value="bright-falcon"
        ):
            with patch("pathlib.Path.exists", return_value=False):
                info = create_worktree()

        assert info.name == "bright-falcon"
        assert info.branch == "worktree-bright-falcon"
        assert info.path == Path("/repo/.synapse/worktrees/bright-falcon")
        assert info.base_branch == "origin/main"

        # Verify git worktree add was called
        calls = mock_run.call_args_list
        add_call = [c for c in calls if "worktree" in str(c)]
        assert len(add_call) >= 1

    @patch("synapse.worktree.get_default_remote_branch", return_value="origin/main")
    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    def test_create_worktree_with_name(
        self,
        mock_mkdir: MagicMock,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
        mock_remote: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch("pathlib.Path.exists", return_value=False):
            info = create_worktree(name="feature-auth")

        assert info.name == "feature-auth"
        assert info.branch == "worktree-feature-auth"
        assert info.path == Path("/repo/.synapse/worktrees/feature-auth")

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    def test_create_worktree_with_custom_base_branch(
        self,
        mock_mkdir: MagicMock,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """When base_branch is provided, it should be used instead of get_default_remote_branch."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch("synapse.worktree.generate_worktree_name", return_value="keen-owl"):
            with patch("pathlib.Path.exists", return_value=False):
                info = create_worktree(base_branch="renovate/major-eslint-monorepo")

        assert info.name == "keen-owl"
        assert info.branch == "worktree-keen-owl"
        assert info.base_branch == "renovate/major-eslint-monorepo"

        # Verify git worktree add used the custom base branch
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "renovate/major-eslint-monorepo"

    @patch("synapse.worktree.get_default_remote_branch", return_value="origin/main")
    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    def test_create_worktree_base_branch_none_uses_default(
        self,
        mock_mkdir: MagicMock,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
        mock_remote: MagicMock,
    ) -> None:
        """When base_branch is None, get_default_remote_branch is used."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch("synapse.worktree.generate_worktree_name", return_value="bold-fox"):
            with patch("pathlib.Path.exists", return_value=False):
                info = create_worktree(base_branch=None)

        assert info.base_branch == "origin/main"
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "origin/main"

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    def test_create_worktree_empty_base_branch_raises(
        self, mock_git_root: MagicMock
    ) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            create_worktree(base_branch="")

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    def test_create_worktree_dash_base_branch_raises(
        self, mock_git_root: MagicMock
    ) -> None:
        with pytest.raises(ValueError, match="must not start with"):
            create_worktree(base_branch="--malicious")

    @patch("synapse.worktree.get_git_root")
    def test_create_worktree_not_in_git_repo(self, mock_git_root: MagicMock) -> None:
        mock_git_root.side_effect = RuntimeError("Not a git repository")
        with pytest.raises(RuntimeError, match="Not a git repository"):
            create_worktree()

    @patch("synapse.worktree.get_default_remote_branch", return_value="origin/main")
    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    def test_create_worktree_duplicate_name(
        self,
        mock_git_root: MagicMock,
        mock_remote: MagicMock,
    ) -> None:
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises(RuntimeError, match="already exists"):
                create_worktree(name="existing-wt")

    @patch("synapse.worktree.get_default_remote_branch", return_value="origin/main")
    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    def test_create_worktree_git_command_fails(
        self,
        mock_mkdir: MagicMock,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
        mock_remote: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: branch already exists"
        )
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(RuntimeError, match="Failed to create worktree"):
                create_worktree(name="bad-wt")

    # --- Issue #546: nested worktree path resolution -------------------

    @patch("synapse.worktree.get_default_remote_branch", return_value="origin/main")
    @patch("synapse.worktree.get_main_repo_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    def test_nested_worktree_resolves_to_main_repo_root(
        self,
        mock_mkdir: MagicMock,
        mock_run: MagicMock,
        mock_main_root: MagicMock,
        mock_remote: MagicMock,
    ) -> None:
        """When invoked from inside a worktree, the new worktree must
        be created under the main repo root, not under the parent
        worktree (issue #546).

        The test mocks ``get_main_repo_root`` to return ``/repo`` (i.e.
        what would be returned even if cwd is
        ``/repo/.synapse/worktrees/rich-elk``). The created worktree
        path must be ``/repo/.synapse/worktrees/<name>`` — *not* nested.
        """
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch("synapse.worktree.generate_worktree_name", return_value="live-swan"):
            with patch("pathlib.Path.exists", return_value=False):
                info = create_worktree()

        assert info.path == Path("/repo/.synapse/worktrees/live-swan")
        # Must NOT be nested under a parent worktree
        assert ".synapse/worktrees/rich-elk" not in str(info.path)
        # Verify git worktree add was called with the un-nested path
        cmd = mock_run.call_args[0][0]
        assert str(Path("/repo/.synapse/worktrees/live-swan")) in cmd

    @patch("synapse.worktree.get_default_remote_branch", return_value="origin/main")
    @patch("synapse.worktree.get_main_repo_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    def test_worktree_creation_from_repo_root_is_unchanged(
        self,
        mock_mkdir: MagicMock,
        mock_run: MagicMock,
        mock_main_root: MagicMock,
        mock_remote: MagicMock,
    ) -> None:
        """Creating a worktree from the main repo root must continue to
        place it under ``<repo>/.synapse/worktrees/<name>`` exactly as
        before. This guards against regressions from the issue #546
        fix (no double-resolution, no path drift)."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch(
            "synapse.worktree.generate_worktree_name", return_value="bright-falcon"
        ):
            with patch("pathlib.Path.exists", return_value=False):
                info = create_worktree()

        assert info.name == "bright-falcon"
        assert info.branch == "worktree-bright-falcon"
        assert info.path == Path("/repo/.synapse/worktrees/bright-falcon")
        assert info.base_branch == "origin/main"


# ============================================================
# _validate_worktree_name
# ============================================================


class TestValidateWorktreeName:
    def test_valid_names(self) -> None:
        assert _validate_worktree_name("bold-fox") == "bold-fox"
        assert _validate_worktree_name("feature.1") == "feature.1"
        assert _validate_worktree_name("my_task") == "my_task"
        assert _validate_worktree_name("a") == "a"

    def test_strips_whitespace(self) -> None:
        assert _validate_worktree_name("  bold-fox  ") == "bold-fox"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            _validate_worktree_name("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            _validate_worktree_name("   ")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="too long"):
            _validate_worktree_name("a" * 101)

    def test_path_traversal_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid worktree name"):
            _validate_worktree_name("../escape")

    def test_slash_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid worktree name"):
            _validate_worktree_name("foo/bar")

    def test_starts_with_hyphen_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid worktree name"):
            _validate_worktree_name("-bad")

    def test_spaces_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid worktree name"):
            _validate_worktree_name("has space")


# ============================================================
# remove_worktree
# ============================================================


class TestRemoveWorktree:
    @patch("subprocess.run")
    def test_remove_worktree(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = remove_worktree(
            Path("/repo/.synapse/worktrees/test-wt"), "worktree-test-wt"
        )
        assert result is True

        calls = mock_run.call_args_list
        # Should call: git worktree remove, git branch -d
        assert len(calls) == 2
        assert "worktree" in str(calls[0])
        assert "branch" in str(calls[1])

    @patch("subprocess.run")
    def test_remove_worktree_force(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = remove_worktree(
            Path("/repo/.synapse/worktrees/test-wt"), "worktree-test-wt", force=True
        )
        assert result is True

        calls = mock_run.call_args_list
        # worktree remove --force, branch -D
        remove_cmd = calls[0][0][0]
        assert "--force" in remove_cmd
        branch_cmd = calls[1][0][0]
        assert "-D" in branch_cmd

    @patch("subprocess.run")
    def test_remove_worktree_failure_returns_false(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = remove_worktree(Path("/nonexistent"), "worktree-nope")
        assert result is False


# ============================================================
# has_uncommitted_changes
# ============================================================


class TestHasUncommittedChanges:
    @patch("subprocess.run")
    def test_has_changes_true(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=" M src/main.py\n", stderr=""
        )
        assert has_uncommitted_changes(Path("/repo")) is True

    @patch("subprocess.run")
    def test_has_changes_false(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert has_uncommitted_changes(Path("/repo")) is False

    @patch("subprocess.run")
    def test_has_changes_whitespace_only(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="  \n", stderr="")
        assert has_uncommitted_changes(Path("/repo")) is False


# ============================================================
# has_new_commits
# ============================================================


class TestHasNewCommits:
    @patch("subprocess.run")
    def test_has_commits_true(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="abc1234 Add feature\n", stderr=""
        )
        assert has_new_commits(Path("/repo"), "origin/main") is True

    @patch("subprocess.run")
    def test_has_commits_false(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert has_new_commits(Path("/repo"), "origin/main") is False

    def test_empty_base_branch_returns_true(self) -> None:
        """Missing base_branch is treated as modified (defensive)."""
        assert has_new_commits(Path("/repo"), "") is True


# ============================================================
# has_worktree_changes
# ============================================================


class TestHasWorktreeChanges:
    def _make_info(self, base_branch: str = "origin/main") -> WorktreeInfo:
        return WorktreeInfo(
            name="test-wt",
            path=Path("/repo/.synapse/worktrees/test-wt"),
            branch="worktree-test-wt",
            base_branch=base_branch,
            created_at=1000.0,
        )

    @patch("synapse.worktree.has_new_commits", return_value=False)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    def test_no_changes_no_commits(
        self, mock_uc: MagicMock, mock_nc: MagicMock
    ) -> None:
        assert has_worktree_changes(self._make_info()) is False

    @patch("synapse.worktree.has_new_commits", return_value=False)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=True)
    def test_uncommitted_changes_only(
        self, mock_uc: MagicMock, mock_nc: MagicMock
    ) -> None:
        assert has_worktree_changes(self._make_info()) is True

    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    def test_new_commits_only(self, mock_uc: MagicMock, mock_nc: MagicMock) -> None:
        assert has_worktree_changes(self._make_info()) is True

    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=True)
    def test_both_changes_and_commits(
        self, mock_uc: MagicMock, mock_nc: MagicMock
    ) -> None:
        assert has_worktree_changes(self._make_info()) is True


# ============================================================
# worktree_info_from_registry
# ============================================================


class TestWorktreeInfoFromRegistry:
    def test_basic_reconstruction(self) -> None:
        info = worktree_info_from_registry(
            "/repo/.synapse/worktrees/test-wt", "worktree-test-wt"
        )
        assert info.name == "test-wt"
        assert info.path == Path("/repo/.synapse/worktrees/test-wt")
        assert info.branch == "worktree-test-wt"
        assert info.base_branch == ""

    def test_with_base_branch(self) -> None:
        info = worktree_info_from_registry(
            "/repo/.synapse/worktrees/test-wt", "worktree-test-wt", "origin/main"
        )
        assert info.base_branch == "origin/main"


# ============================================================
# cleanup_worktree
# ============================================================


class TestCleanupWorktree:
    def _make_info(self) -> WorktreeInfo:
        return WorktreeInfo(
            name="test-wt",
            path=Path("/repo/.synapse/worktrees/test-wt"),
            branch="worktree-test-wt",
            base_branch="origin/main",
            created_at=1000.0,
        )

    @patch("synapse.worktree.remove_worktree", return_value=True)
    @patch("synapse.worktree.has_new_commits", return_value=False)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    def test_cleanup_auto_remove_when_clean(
        self,
        mock_uncommitted: MagicMock,
        mock_commits: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        info = self._make_info()
        result = cleanup_worktree(info, interactive=False)
        assert result is True
        mock_remove.assert_called_once_with(info.path, info.branch, force=False)

    @patch("synapse.worktree.remove_worktree")
    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    def test_cleanup_keeps_dirty_non_interactive(
        self,
        mock_uncommitted: MagicMock,
        mock_commits: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        info = self._make_info()
        result = cleanup_worktree(info, interactive=False)
        assert result is False
        mock_remove.assert_not_called()

    @patch("synapse.worktree.remove_worktree", return_value=True)
    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    @patch("builtins.input", return_value="y")
    def test_cleanup_interactive_confirms_removal(
        self,
        mock_input: MagicMock,
        mock_uncommitted: MagicMock,
        mock_commits: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        info = self._make_info()
        result = cleanup_worktree(info, interactive=True)
        assert result is True
        mock_remove.assert_called_once_with(info.path, info.branch, force=True)

    @patch("synapse.worktree.remove_worktree")
    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    @patch("builtins.input", return_value="n")
    def test_cleanup_interactive_declines_removal(
        self,
        mock_input: MagicMock,
        mock_uncommitted: MagicMock,
        mock_commits: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        info = self._make_info()
        result = cleanup_worktree(info, interactive=True)
        assert result is False
        mock_remove.assert_not_called()

    @patch("synapse.worktree.remove_worktree", return_value=True)
    @patch("synapse.worktree.merge_worktree", return_value=True)
    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    def test_cleanup_with_merge_success(
        self,
        mock_uncommitted: MagicMock,
        mock_commits: MagicMock,
        mock_merge: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        """When merge=True and merge succeeds, worktree should be removed."""
        info = self._make_info()
        result = cleanup_worktree(info, merge=True)
        assert result is True
        mock_merge.assert_called_once_with(
            info, _has_uncommitted=False, _has_commits=True
        )
        mock_remove.assert_called_once_with(info.path, info.branch, force=False)

    @patch("synapse.worktree.remove_worktree")
    @patch("synapse.worktree.merge_worktree")
    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    def test_cleanup_with_merge_conflict(
        self,
        mock_uncommitted: MagicMock,
        mock_commits: MagicMock,
        mock_merge: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        """When merge=True but merge fails (conflict), worktree should be kept."""
        mock_merge.return_value = False
        info = self._make_info()
        result = cleanup_worktree(info, merge=True)
        assert result is False
        mock_merge.assert_called_once()
        mock_remove.assert_not_called()

    @patch("synapse.worktree.remove_worktree")
    @patch("synapse.worktree.merge_worktree")
    @patch("synapse.worktree.has_new_commits", return_value=True)
    @patch("synapse.worktree.has_uncommitted_changes", return_value=False)
    def test_cleanup_with_merge_false(
        self,
        mock_uncommitted: MagicMock,
        mock_commits: MagicMock,
        mock_merge: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        """When merge=False, should use existing behavior (no merge attempted)."""
        info = self._make_info()
        result = cleanup_worktree(info, merge=False)
        assert result is False
        mock_merge.assert_not_called()


# ============================================================
# merge_worktree
# ============================================================


class TestMergeWorktree:
    def _make_info(self) -> WorktreeInfo:
        return WorktreeInfo(
            name="test-wt",
            path=Path("/repo/.synapse/worktrees/test-wt"),
            branch="worktree-test-wt",
            base_branch="origin/main",
            created_at=1000.0,
        )

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_merge_success(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """Successful merge should return True."""
        info = self._make_info()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = merge_worktree(info, _has_uncommitted=False, _has_commits=True)
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "merge" in call_args[0][0]
        assert info.branch in call_args[0][0]
        assert "--no-edit" in call_args[0][0]
        assert call_args[1].get("cwd") == str(Path("/repo"))

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_merge_auto_commit_wip(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """Should auto-commit uncommitted changes before merging."""
        info = self._make_info()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = merge_worktree(
            info, auto_commit_wip=True, _has_uncommitted=True, _has_commits=False
        )
        assert result is True
        # Should have: git add -u, git commit, git merge (3 calls)
        assert mock_run.call_count == 3
        first_call = mock_run.call_args_list[0]
        assert "add" in first_call[0][0]
        assert "-u" in first_call[0][0]
        assert first_call[1].get("cwd") == str(info.path)

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_merge_skip_wip_when_disabled(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """Should not auto-commit when auto_commit_wip=False."""
        info = self._make_info()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = merge_worktree(
            info, auto_commit_wip=False, _has_uncommitted=True, _has_commits=True
        )
        assert result is True
        # Should only have git merge call, no git add/commit
        assert mock_run.call_count == 1
        assert "merge" in mock_run.call_args[0][0]

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_merge_conflict(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """On conflict, should abort merge and return False."""
        info = self._make_info()
        merge_result = MagicMock(returncode=1, stdout="", stderr="CONFLICT")
        abort_result = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = [merge_result, abort_result]

        result = merge_worktree(info, _has_uncommitted=False, _has_commits=True)
        assert result is False
        assert mock_run.call_count == 2
        abort_call = mock_run.call_args_list[1]
        assert "--abort" in abort_call[0][0]

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    def test_merge_no_new_commits(
        self,
        mock_git_root: MagicMock,
    ) -> None:
        """When no new commits and no uncommitted changes, should return True without merging."""
        info = self._make_info()
        result = merge_worktree(info, _has_uncommitted=False, _has_commits=False)
        assert result is True


# ============================================================
# prune_worktrees
# ============================================================


class TestPruneWorktrees:
    """Tests for orphan worktree detection and cleanup."""

    # Sample `git worktree list --porcelain` output with prunable entries
    _PORCELAIN_WITH_PRUNABLE = (
        "worktree /repo\n"
        "HEAD abc1234\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /repo/.synapse/worktrees/bold-newt\n"
        "HEAD def5678\n"
        "branch refs/heads/worktree-bold-newt\n"
        "prunable gitdir file points to non-existent location\n"
        "\n"
        "worktree /repo/.synapse/worktrees/lean-wren\n"
        "HEAD aaa1111\n"
        "branch refs/heads/worktree-lean-wren\n"
        "prunable gitdir file points to non-existent location\n"
        "\n"
    )

    _PORCELAIN_NO_PRUNABLE = (
        "worktree /repo\n"
        "HEAD abc1234\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /repo/.synapse/worktrees/active-fox\n"
        "HEAD bbb2222\n"
        "branch refs/heads/worktree-active-fox\n"
        "\n"
    )

    _PORCELAIN_ONLY_MAIN = "worktree /repo\nHEAD abc1234\nbranch refs/heads/main\n\n"

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_prune_removes_orphan_worktrees(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """Prunable worktrees under .synapse/worktrees/ should be cleaned up."""
        mock_run.side_effect = [
            # git worktree list --porcelain
            MagicMock(returncode=0, stdout=self._PORCELAIN_WITH_PRUNABLE, stderr=""),
            # git worktree prune
            MagicMock(returncode=0, stdout="", stderr=""),
            # git branch -d (batched)
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        pruned = prune_worktrees()
        assert pruned == ["bold-newt", "lean-wren"]

        calls = mock_run.call_args_list
        # 1) list, 2) prune, 3) batch branch -d
        assert calls[1][0][0] == ["git", "worktree", "prune"]
        assert calls[2][0][0] == [
            "git",
            "branch",
            "-d",
            "worktree-bold-newt",
            "worktree-lean-wren",
        ]

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_prune_nothing_to_prune(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """When no prunable worktrees exist, return empty list and skip prune."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=self._PORCELAIN_NO_PRUNABLE, stderr=""
        )

        pruned = prune_worktrees()
        assert pruned == []
        # Only the list command should have been called
        assert mock_run.call_count == 1

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_prune_only_main_worktree(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """When only the main worktree exists, return empty list."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=self._PORCELAIN_ONLY_MAIN, stderr=""
        )

        pruned = prune_worktrees()
        assert pruned == []

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_prune_skips_non_synapse_worktrees(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """Prunable worktrees outside .synapse/worktrees/ should be ignored."""
        porcelain = (
            "worktree /repo\n"
            "HEAD abc1234\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /other/path/my-wt\n"
            "HEAD ccc3333\n"
            "branch refs/heads/my-wt\n"
            "prunable gitdir file points to non-existent location\n"
            "\n"
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=porcelain, stderr="")

        pruned = prune_worktrees()
        assert pruned == []

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_prune_branch_delete_failure_is_non_fatal(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """Branch deletion failure should not prevent reporting pruned worktrees."""
        mock_run.side_effect = [
            # git worktree list --porcelain
            MagicMock(returncode=0, stdout=self._PORCELAIN_WITH_PRUNABLE, stderr=""),
            # git worktree prune
            MagicMock(returncode=0, stdout="", stderr=""),
            # git branch -d (batched) -> partial failure
            MagicMock(returncode=1, stdout="", stderr="error: branch not found"),
        ]

        pruned = prune_worktrees()
        # Both are still reported as pruned (git worktree prune already removed them)
        assert pruned == ["bold-newt", "lean-wren"]

    @patch("synapse.worktree.get_git_root", return_value=Path("/repo"))
    @patch("subprocess.run")
    def test_prune_git_worktree_list_fails(
        self,
        mock_run: MagicMock,
        mock_git_root: MagicMock,
    ) -> None:
        """If git worktree list fails, return empty list."""
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: not a git repository"
        )

        pruned = prune_worktrees()
        assert pruned == []
