"""Tests for CLI workflow commands (synapse/commands/workflow.py)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_args(**kwargs: Any) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults."""
    defaults = {
        "workflow_name": "test-wf",
        "user": False,
        "project": False,
        "force": False,
        "dry_run": False,
        "continue_on_error": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture()
def workflow_dirs(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / ".synapse" / "workflows"
    user = tmp_path / "home" / ".synapse" / "workflows"
    return project, user


def _make_store(project_dir: Path, user_dir: Path):
    """Create a WorkflowStore with custom directories."""
    from synapse.workflow import WorkflowStore

    return WorkflowStore(project_dir=project_dir, user_dir=user_dir)


def _save_sample_workflow(store, name: str = "test-wf", scope: str = "project") -> None:
    """Save a simple two-step workflow for testing."""
    from synapse.workflow import Workflow, WorkflowStep

    store.save(
        Workflow(
            name=name,
            steps=[
                WorkflowStep(
                    target="claude",
                    message="Review code",
                    priority=4,
                    response_mode="wait",
                ),
                WorkflowStep(
                    target="gemini", message="Write tests", response_mode="silent"
                ),
            ],
            description="Test workflow",
            scope=scope,
        )
    )


# ── cmd_workflow_create ──────────────────────────────────────


def test_create_generates_template(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """create should generate a template YAML file."""
    from synapse.commands.workflow import cmd_workflow_create

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(workflow_name="my-review")

    with patch("synapse.commands.workflow._get_workflow_store", return_value=store):
        cmd_workflow_create(args)

    captured = capsys.readouterr()
    assert "my-review" in captured.out
    assert (project_dir / "my-review.yaml").exists()

    # Verify template content is valid YAML
    import yaml

    content = yaml.safe_load((project_dir / "my-review.yaml").read_text())
    assert content["name"] == "my-review"
    assert len(content["steps"]) >= 1


def test_create_refuses_overwrite(
    tmp_path: Path, workflow_dirs: tuple[Path, Path]
) -> None:
    """create should refuse to overwrite existing workflow without --force."""
    from synapse.commands.workflow import cmd_workflow_create

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf")
    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_workflow_create(args)


def test_create_force_overwrites(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """create --force should overwrite existing workflow."""
    from synapse.commands.workflow import cmd_workflow_create

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf", force=True)
    with patch("synapse.commands.workflow._get_workflow_store", return_value=store):
        cmd_workflow_create(args)

    captured = capsys.readouterr()
    assert "test-wf" in captured.out


def test_create_user_scope(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """create --user should create in user scope."""
    from synapse.commands.workflow import cmd_workflow_create

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(workflow_name="user-wf", user=True)

    with patch("synapse.commands.workflow._get_workflow_store", return_value=store):
        cmd_workflow_create(args)

    assert (user_dir / "user-wf.yaml").exists()
    assert not (project_dir / "user-wf.yaml").exists()


# ── cmd_workflow_list ────────────────────────────────────────


def test_list_shows_workflows(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """list should display saved workflows."""
    from synapse.commands.workflow import cmd_workflow_list

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store, name="review-wf")

    args = _make_args()
    with patch("synapse.commands.workflow._get_workflow_store", return_value=store):
        cmd_workflow_list(args)

    captured = capsys.readouterr()
    assert "review-wf" in captured.out
    assert "2" in captured.out  # step count


def test_list_empty(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """list on empty store should show 'No saved workflows' message."""
    from synapse.commands.workflow import cmd_workflow_list

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args()

    with patch("synapse.commands.workflow._get_workflow_store", return_value=store):
        cmd_workflow_list(args)

    captured = capsys.readouterr()
    assert "No saved workflows" in captured.out


# ── cmd_workflow_show ────────────────────────────────────────


def test_show_displays_details(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """show should display workflow step details."""
    from synapse.commands.workflow import cmd_workflow_show

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf")
    with patch("synapse.commands.workflow._get_workflow_store", return_value=store):
        cmd_workflow_show(args)

    captured = capsys.readouterr()
    assert "test-wf" in captured.out
    assert "claude" in captured.out
    assert "gemini" in captured.out
    assert "Review code" in captured.out


def test_show_not_found(tmp_path: Path, workflow_dirs: tuple[Path, Path]) -> None:
    """show should exit with error for non-existent workflow."""
    from synapse.commands.workflow import cmd_workflow_show

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(workflow_name="ghost")

    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_workflow_show(args)


# ── cmd_workflow_delete ──────────────────────────────────────


def test_delete_removes_workflow(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """delete --force should remove the workflow file."""
    from synapse.commands.workflow import cmd_workflow_delete

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf", force=True)
    with patch("synapse.commands.workflow._get_workflow_store", return_value=store):
        cmd_workflow_delete(args)

    assert store.load("test-wf") is None
    captured = capsys.readouterr()
    assert "deleted" in captured.out


def test_delete_not_found(tmp_path: Path, workflow_dirs: tuple[Path, Path]) -> None:
    """delete should exit with error for non-existent workflow."""
    from synapse.commands.workflow import cmd_workflow_delete

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(workflow_name="ghost", force=True)

    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_workflow_delete(args)


# ── cmd_workflow_run ─────────────────────────────────────────


def test_run_sends_steps_sequentially(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """run should send messages for each step in order."""
    from synapse.commands.workflow import cmd_workflow_run

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf")
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        patch(
            "synapse.commands.workflow.subprocess.run", return_value=mock_result
        ) as mock_run,
    ):
        cmd_workflow_run(args)

    # Should be called once per step
    assert mock_run.call_count == 2

    # Verify step order via target args
    call_args_list = mock_run.call_args_list
    first_cmd = call_args_list[0][0][0]
    second_cmd = call_args_list[1][0][0]
    assert "--target" in first_cmd
    assert "claude" in first_cmd
    assert "--target" in second_cmd
    assert "gemini" in second_cmd


def test_run_aborts_on_failure(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """run should abort on first failure by default."""
    from synapse.commands.workflow import cmd_workflow_run

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf")
    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stdout = ""
    fail_result.stderr = "Connection refused"

    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        patch("synapse.commands.workflow.subprocess.run", return_value=fail_result),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_workflow_run(args)


def test_run_continue_on_error(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """run --continue-on-error should proceed despite failures."""
    from synapse.commands.workflow import cmd_workflow_run

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf", continue_on_error=True)

    call_count = 0

    def _side_effect(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        result.stdout = ""
        result.stderr = "err" if call_count == 1 else ""
        result.returncode = 1 if call_count == 1 else 0
        return result

    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        patch(
            "synapse.commands.workflow.subprocess.run", side_effect=_side_effect
        ) as mock_run,
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_workflow_run(args)

    # Both steps should have been attempted
    assert mock_run.call_count == 2


def test_run_dry_run(
    tmp_path: Path, workflow_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """run --dry-run should print steps without sending."""
    from synapse.commands.workflow import cmd_workflow_run

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    _save_sample_workflow(store)

    args = _make_args(workflow_name="test-wf", dry_run=True)

    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        patch("synapse.commands.workflow.subprocess.run") as mock_run,
    ):
        cmd_workflow_run(args)

    # Should NOT call subprocess
    mock_run.assert_not_called()

    captured = capsys.readouterr()
    assert "claude" in captured.out
    assert "gemini" in captured.out
    assert "dry run" in captured.out.lower() or "DRY RUN" in captured.out


def test_run_not_found(tmp_path: Path, workflow_dirs: tuple[Path, Path]) -> None:
    """run should exit with error for non-existent workflow."""
    from synapse.commands.workflow import cmd_workflow_run

    project_dir, user_dir = workflow_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(workflow_name="ghost")

    with (
        patch("synapse.commands.workflow._get_workflow_store", return_value=store),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_workflow_run(args)
