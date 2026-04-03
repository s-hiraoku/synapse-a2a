"""Tests for synapse merge command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.worktree import WorktreeInfo


def _make_worktree_info() -> WorktreeInfo:
    return WorktreeInfo(
        name="test-wt",
        path=Path("/repo/.synapse/worktrees/test-wt"),
        branch="worktree-test-wt",
        base_branch="origin/main",
        created_at=1000.0,
    )


def _make_agent_info(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "agent_id": "synapse-claude-8100",
        "agent_type": "claude",
        "name": "my-agent",
        "port": 8100,
        "worktree_path": "/repo/.synapse/worktrees/test-wt",
        "worktree_branch": "worktree-test-wt",
        "worktree_base_branch": "origin/main",
    }
    base.update(overrides)
    return base


class TestMergeCLIParsing:
    @patch("synapse.cli.cmd_merge")
    @patch("synapse.cli.install_skills")
    def test_merge_accepts_agent_target(
        self,
        mock_install_skills: MagicMock,
        mock_cmd_merge: MagicMock,
    ) -> None:
        from synapse.cli import main

        with patch.object(sys, "argv", ["synapse", "merge", "my-agent"]):
            main()

        args = mock_cmd_merge.call_args[0][0]
        assert args.target == "my-agent"
        assert args.all is False
        assert args.dry_run is False
        assert args.resolve_with is None

    @patch("synapse.cli.cmd_merge")
    @patch("synapse.cli.install_skills")
    def test_merge_accepts_all_flag(
        self,
        mock_install_skills: MagicMock,
        mock_cmd_merge: MagicMock,
    ) -> None:
        from synapse.cli import main

        with patch.object(sys, "argv", ["synapse", "merge", "--all"]):
            main()

        args = mock_cmd_merge.call_args[0][0]
        assert args.target is None
        assert args.all is True

    @patch("synapse.cli.cmd_merge")
    @patch("synapse.cli.install_skills")
    def test_merge_accepts_dry_run(
        self,
        mock_install_skills: MagicMock,
        mock_cmd_merge: MagicMock,
    ) -> None:
        from synapse.cli import main

        with patch.object(sys, "argv", ["synapse", "merge", "my-agent", "--dry-run"]):
            main()

        args = mock_cmd_merge.call_args[0][0]
        assert args.dry_run is True

    @patch("synapse.cli.cmd_merge")
    @patch("synapse.cli.install_skills")
    def test_merge_accepts_resolve_with(
        self,
        mock_install_skills: MagicMock,
        mock_cmd_merge: MagicMock,
    ) -> None:
        from synapse.cli import main

        with patch.object(
            sys,
            "argv",
            ["synapse", "merge", "my-agent", "--resolve-with", "resolver"],
        ):
            main()

        args = mock_cmd_merge.call_args[0][0]
        assert args.resolve_with == "resolver"

    def test_merge_requires_target_or_all(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from synapse.cli import cmd_merge

        args = argparse.Namespace(
            target=None,
            all=False,
            dry_run=False,
            resolve_with=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_merge(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "target" in captured.out.lower()
        assert "--all" in captured.out

    def test_merge_rejects_resolve_with_all(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.cli import cmd_merge

        args = argparse.Namespace(
            target=None,
            all=True,
            dry_run=False,
            resolve_with="resolver",
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_merge(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--resolve-with" in captured.out
        assert "--all" in captured.out


class TestMergeSingleAgent:
    @patch("synapse.commands.merge.merge_worktree", return_value=True)
    def test_merge_single_worktree_agent_success(
        self,
        mock_merge_worktree: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_single

        agent_info = _make_agent_info()

        result = merge_single(agent_info)

        assert result is True
        mock_merge_worktree.assert_called_once()
        captured = capsys.readouterr()
        assert "merged" in captured.out.lower()
        assert "my-agent" in captured.out

    def test_merge_agent_without_worktree_errors(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_single

        result = merge_single(
            _make_agent_info(worktree_path=None, worktree_branch=None)
        )

        assert result is False
        captured = capsys.readouterr()
        assert "worktree" in captured.out.lower()

    def test_merge_agent_not_found_errors(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.cli import cmd_merge

        registry = MagicMock()
        registry.resolve_agent.return_value = None
        args = argparse.Namespace(
            target="missing-agent",
            all=False,
            dry_run=False,
            resolve_with=None,
        )

        with (
            patch("synapse.cli.AgentRegistry", return_value=registry),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_merge(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    @patch("synapse.commands.merge.merge_worktree", return_value=False)
    def test_merge_conflict_prints_instructions(
        self,
        mock_merge_worktree: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_single

        result = merge_single(_make_agent_info())

        assert result is False
        mock_merge_worktree.assert_called_once()
        captured = capsys.readouterr()
        assert "resolve manually" in captured.out.lower()
        assert "git merge worktree-test-wt" in captured.out


class TestMergeAll:
    @patch("synapse.commands.merge.merge_single", side_effect=[True, True])
    def test_merge_all_merges_worktree_agents(
        self,
        mock_merge_single: MagicMock,
    ) -> None:
        from synapse.commands.merge import merge_all

        registry = MagicMock()
        registry.get_live_agents.return_value = {
            "agent-1": _make_agent_info(agent_id="agent-1", name="agent-1"),
            "agent-2": _make_agent_info(agent_id="agent-2", name="agent-2"),
        }

        success_count, failure_count = merge_all(registry)

        assert (success_count, failure_count) == (2, 0)
        assert mock_merge_single.call_count == 2

    @patch("synapse.commands.merge.merge_single", return_value=True)
    def test_merge_all_skips_non_worktree_agents(
        self,
        mock_merge_single: MagicMock,
    ) -> None:
        from synapse.commands.merge import merge_all

        registry = MagicMock()
        registry.get_live_agents.return_value = {
            "agent-1": _make_agent_info(agent_id="agent-1"),
            "agent-2": _make_agent_info(
                agent_id="agent-2",
                name="plain-agent",
                worktree_path=None,
                worktree_branch=None,
            ),
        }

        success_count, failure_count = merge_all(registry)

        assert (success_count, failure_count) == (1, 0)
        mock_merge_single.assert_called_once()

    def test_merge_all_no_worktree_agents(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_all

        registry = MagicMock()
        registry.get_live_agents.return_value = {
            "agent-1": _make_agent_info(
                agent_id="agent-1",
                worktree_path=None,
                worktree_branch=None,
            )
        }

        success_count, failure_count = merge_all(registry)

        assert (success_count, failure_count) == (0, 0)
        captured = capsys.readouterr()
        assert "no worktree agents" in captured.out.lower()

    @patch("synapse.commands.merge.merge_single", side_effect=[True, False])
    def test_merge_all_partial_failure(
        self,
        mock_merge_single: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_all

        registry = MagicMock()
        registry.get_live_agents.return_value = {
            "agent-1": _make_agent_info(agent_id="agent-1", name="agent-1"),
            "agent-2": _make_agent_info(agent_id="agent-2", name="agent-2"),
        }

        success_count, failure_count = merge_all(registry)

        assert (success_count, failure_count) == (1, 1)
        assert mock_merge_single.call_count == 2
        captured = capsys.readouterr()
        assert "1 succeeded" in captured.out.lower()
        assert "1 failed" in captured.out.lower()


class TestMergeDryRun:
    @patch("synapse.commands.merge.merge_worktree")
    @patch("synapse.commands.merge.has_worktree_changes", return_value=True)
    def test_dry_run_checks_for_changes(
        self,
        mock_has_changes: MagicMock,
        mock_merge_worktree: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_single

        result = merge_single(_make_agent_info(), dry_run=True)

        assert result is True
        mock_has_changes.assert_called_once()
        mock_merge_worktree.assert_not_called()
        captured = capsys.readouterr()
        assert "would merge" in captured.out.lower()

    @patch("synapse.commands.merge.has_worktree_changes", return_value=True)
    def test_dry_run_reports_mergeable(
        self,
        mock_has_changes: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_single

        merge_single(_make_agent_info(), dry_run=True)

        captured = capsys.readouterr()
        assert "would merge" in captured.out.lower()
        assert "my-agent" in captured.out

    @patch("synapse.commands.merge.has_worktree_changes", return_value=False)
    def test_dry_run_reports_nothing_to_merge(
        self,
        mock_has_changes: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.commands.merge import merge_single

        merge_single(_make_agent_info(), dry_run=True)

        captured = capsys.readouterr()
        assert "nothing to merge" in captured.out.lower()


class TestMergeResolveWith:
    @patch("synapse.commands.merge._delegate_conflict_resolution", return_value=False)
    @patch("synapse.commands.merge.merge_worktree", return_value=False)
    def test_resolve_with_sends_conflict_to_resolver(
        self,
        mock_merge_worktree: MagicMock,
        mock_delegate: MagicMock,
    ) -> None:
        from synapse.commands.merge import merge_single

        registry = MagicMock()
        result = merge_single(
            _make_agent_info(),
            resolve_with="resolver",
            registry=registry,
        )

        assert result is False
        mock_merge_worktree.assert_called_once()
        mock_delegate.assert_called_once()
        assert mock_delegate.call_args.args[2] == "resolver"

    @patch("synapse.commands.merge._delegate_conflict_resolution", return_value=True)
    @patch("synapse.commands.merge.merge_worktree", side_effect=[False, True])
    def test_resolve_with_retries_merge_after_resolution(
        self,
        mock_merge_worktree: MagicMock,
        mock_delegate: MagicMock,
    ) -> None:
        from synapse.commands.merge import merge_single

        registry = MagicMock()
        result = merge_single(
            _make_agent_info(),
            resolve_with="resolver",
            registry=registry,
        )

        assert result is True
        assert mock_merge_worktree.call_count == 2
        mock_delegate.assert_called_once()

    def test_resolve_with_resolver_not_found_errors(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse.cli import cmd_merge

        registry = MagicMock()
        registry.resolve_agent.side_effect = [
            _make_agent_info(),
            None,
        ]
        args = argparse.Namespace(
            target="my-agent",
            all=False,
            dry_run=False,
            resolve_with="resolver",
        )

        with (
            patch("synapse.cli.AgentRegistry", return_value=registry),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_merge(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "resolver" in captured.out.lower()
        assert "not found" in captured.out.lower()
