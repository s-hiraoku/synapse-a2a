"""Tests for WorkflowStore core (synapse/workflow.py)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def workflow_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Return (project_dir, user_dir) under tmp_path."""
    project = tmp_path / "project" / ".synapse" / "workflows"
    user = tmp_path / "home" / ".synapse" / "workflows"
    return project, user


@pytest.fixture()
def store(workflow_dirs: tuple[Path, Path]):
    from synapse.workflow import WorkflowStore

    project_dir, user_dir = workflow_dirs
    return WorkflowStore(project_dir=project_dir, user_dir=user_dir)


# ── save / load round-trip ──────────────────────────────────


def test_save_and_load_roundtrip(store) -> None:
    """Saving a workflow and loading it back should preserve all fields."""
    from synapse.workflow import Workflow, WorkflowStep

    steps = [
        WorkflowStep(
            target="claude", message="Review code", priority=4, response_mode="wait"
        ),
        WorkflowStep(target="gemini", message="Write tests", response_mode="silent"),
    ]
    wf = Workflow(
        name="review-and-test",
        steps=steps,
        description="Review then test",
        scope="project",
    )
    store.save(wf)
    loaded = store.load("review-and-test")
    assert loaded is not None
    assert loaded.name == "review-and-test"
    assert loaded.description == "Review then test"
    assert loaded.step_count == 2
    assert len(loaded.steps) == 2
    assert loaded.steps[0].target == "claude"
    assert loaded.steps[0].message == "Review code"
    assert loaded.steps[0].priority == 4
    assert loaded.steps[0].response_mode == "wait"
    assert loaded.steps[1].target == "gemini"
    assert loaded.steps[1].message == "Write tests"
    assert loaded.steps[1].priority == 3  # default
    assert loaded.steps[1].response_mode == "silent"
    assert loaded.scope == "project"


def test_save_creates_directory(store, workflow_dirs: tuple[Path, Path]) -> None:
    """save() should create workflow directory if it doesn't exist."""
    from synapse.workflow import Workflow, WorkflowStep

    project_dir, _ = workflow_dirs
    assert not project_dir.exists()
    wf = Workflow(
        name="test",
        steps=[WorkflowStep(target="claude", message="hello")],
        scope="project",
    )
    store.save(wf)
    assert project_dir.exists()
    assert (project_dir / "test.yaml").exists()


def test_save_overwrites_existing(store) -> None:
    """Saving with the same name should overwrite (upsert)."""
    from synapse.workflow import Workflow, WorkflowStep

    wf1 = Workflow(
        name="wf",
        steps=[WorkflowStep(target="claude", message="v1")],
        scope="project",
    )
    store.save(wf1)
    wf2 = Workflow(
        name="wf",
        steps=[
            WorkflowStep(target="claude", message="v2"),
            WorkflowStep(target="gemini", message="v2b"),
        ],
        scope="project",
    )
    store.save(wf2)
    loaded = store.load("wf")
    assert loaded is not None
    assert loaded.step_count == 2
    assert loaded.steps[0].message == "v2"


# ── list (scope filtering) ──────────────────────────────────


def test_list_project_scope(store) -> None:
    """list_workflows('project') returns only project workflows."""
    from synapse.workflow import Workflow, WorkflowStep

    store.save(
        Workflow(
            name="proj",
            steps=[WorkflowStep(target="claude", message="x")],
            scope="project",
        )
    )
    store.save(
        Workflow(
            name="usr", steps=[WorkflowStep(target="gemini", message="y")], scope="user"
        )
    )
    workflows = store.list_workflows(scope="project")
    names = [w.name for w in workflows]
    assert "proj" in names
    assert "usr" not in names


def test_list_user_scope(store) -> None:
    """list_workflows('user') returns only user workflows."""
    from synapse.workflow import Workflow, WorkflowStep

    store.save(
        Workflow(
            name="usr", steps=[WorkflowStep(target="gemini", message="y")], scope="user"
        )
    )
    workflows = store.list_workflows(scope="user")
    assert len(workflows) == 1
    assert workflows[0].name == "usr"


def test_list_both_scopes(store) -> None:
    """list_workflows(scope=None) returns merged results from both scopes."""
    from synapse.workflow import Workflow, WorkflowStep

    store.save(
        Workflow(
            name="proj",
            steps=[WorkflowStep(target="claude", message="x")],
            scope="project",
        )
    )
    store.save(
        Workflow(
            name="usr", steps=[WorkflowStep(target="gemini", message="y")], scope="user"
        )
    )
    workflows = store.list_workflows(scope=None)
    names = [w.name for w in workflows]
    assert "proj" in names
    assert "usr" in names


def test_list_empty(store) -> None:
    """list_workflows on empty store returns empty list."""
    assert store.list_workflows(scope="project") == []
    assert store.list_workflows(scope="user") == []
    assert store.list_workflows(scope=None) == []


# ── delete ───────────────────────────────────────────────────


def test_delete_existing(store) -> None:
    """Deleting an existing workflow returns True."""
    from synapse.workflow import Workflow, WorkflowStep

    store.save(
        Workflow(
            name="victim",
            steps=[WorkflowStep(target="claude", message="x")],
            scope="project",
        )
    )
    assert store.delete("victim", scope="project") is True
    assert store.load("victim", scope="project") is None


def test_delete_nonexistent(store) -> None:
    """Deleting a non-existent workflow returns False."""
    assert store.delete("ghost", scope="project") is False


def test_delete_project_first_resolution(store) -> None:
    """delete without scope should resolve project-first."""
    from synapse.workflow import Workflow, WorkflowStep

    store.save(
        Workflow(
            name="shared",
            steps=[WorkflowStep(target="claude", message="x")],
            scope="project",
        )
    )
    store.save(
        Workflow(
            name="shared",
            steps=[WorkflowStep(target="gemini", message="y")],
            scope="user",
        )
    )
    # Should delete project copy first
    assert store.delete("shared") is True
    # User copy should still exist
    loaded = store.load("shared", scope="user")
    assert loaded is not None
    assert loaded.steps[0].target == "gemini"


# ── name validation ──────────────────────────────────────────


def test_valid_workflow_names() -> None:
    """Valid names should pass validation."""
    from synapse.workflow import WorkflowStore

    for name in ["review-team", "my.workflow", "test_123", "A-b.C_d"]:
        WorkflowStore._validate_name(name)  # Should not raise


def test_invalid_workflow_names() -> None:
    """Invalid names should raise WorkflowError."""
    from synapse.workflow import WorkflowError, WorkflowStore

    invalid_names = [
        "",  # empty
        "-start",  # starts with dash
        ".dotstart",  # starts with dot
        "has space",
        "has/slash",
        "../traversal",
    ]
    for name in invalid_names:
        with pytest.raises(WorkflowError, match="Invalid workflow name"):
            WorkflowStore._validate_name(name)


# ── path traversal prevention ────────────────────────────────


def test_load_rejects_traversal(store) -> None:
    """load() should reject path-traversal names."""
    from synapse.workflow import WorkflowError

    for bad_name in ["../escape", "../../etc", "has/slash"]:
        with pytest.raises(WorkflowError, match="Invalid workflow name"):
            store.load(bad_name)


def test_delete_rejects_traversal(store) -> None:
    """delete() should reject path-traversal names."""
    from synapse.workflow import WorkflowError

    for bad_name in ["../escape", "../../etc", "has/slash"]:
        with pytest.raises(WorkflowError, match="Invalid workflow name"):
            store.delete(bad_name)


# ── broken YAML handling ────────────────────────────────────


def test_list_skips_broken_yaml(store, workflow_dirs: tuple[Path, Path]) -> None:
    """Broken YAML files should be skipped with a warning, not crash."""
    from synapse.workflow import Workflow, WorkflowStep

    project_dir, _ = workflow_dirs
    store.save(
        Workflow(
            name="valid",
            steps=[WorkflowStep(target="claude", message="x")],
            scope="project",
        )
    )
    # Write a broken YAML file manually
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "broken.yaml").write_text("{invalid yaml: [", encoding="utf-8")

    workflows = store.list_workflows(scope="project")
    names = [w.name for w in workflows]
    assert "valid" in names
    assert len(workflows) == 1  # broken file skipped


def test_load_broken_yaml_returns_none(store, workflow_dirs: tuple[Path, Path]) -> None:
    """Loading a broken YAML file should return None."""
    project_dir, _ = workflow_dirs
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "broken.yaml").write_text("not: [valid: yaml", encoding="utf-8")
    assert store.load("broken", scope="project") is None


# ── step validation ──────────────────────────────────────────


def test_step_invalid_priority() -> None:
    """Priority outside 1-5 should raise WorkflowError."""
    from synapse.workflow import WorkflowError, WorkflowStep

    with pytest.raises(WorkflowError, match="priority"):
        WorkflowStep(target="claude", message="hi", priority=0)
    with pytest.raises(WorkflowError, match="priority"):
        WorkflowStep(target="claude", message="hi", priority=6)


def test_step_invalid_response_mode() -> None:
    """Invalid response_mode should raise WorkflowError."""
    from synapse.workflow import WorkflowError, WorkflowStep

    with pytest.raises(WorkflowError, match="response_mode"):
        WorkflowStep(target="claude", message="hi", response_mode="invalid")


def test_step_empty_target() -> None:
    """Empty target should raise WorkflowError."""
    from synapse.workflow import WorkflowError, WorkflowStep

    with pytest.raises(WorkflowError, match="target"):
        WorkflowStep(target="", message="hi")


def test_step_empty_message() -> None:
    """Empty message should raise WorkflowError."""
    from synapse.workflow import WorkflowError, WorkflowStep

    with pytest.raises(WorkflowError, match="message"):
        WorkflowStep(target="claude", message="")


def test_step_defaults() -> None:
    """Default priority and response_mode should be applied."""
    from synapse.workflow import WorkflowStep

    step = WorkflowStep(target="claude", message="hello")
    assert step.priority == 3
    assert step.response_mode == "notify"


# ── step_count auto-calculation ──────────────────────────────


def test_step_count_auto() -> None:
    """step_count should be auto-calculated from steps list length."""
    from synapse.workflow import Workflow, WorkflowStep

    wf = Workflow(
        name="counted",
        steps=[
            WorkflowStep(target="claude", message="a"),
            WorkflowStep(target="gemini", message="b"),
            WorkflowStep(target="codex", message="c"),
        ],
        scope="project",
    )
    assert wf.step_count == 3


def test_step_count_persists_through_save_load(store) -> None:
    """step_count should survive serialization round-trip."""
    from synapse.workflow import Workflow, WorkflowStep

    wf = Workflow(
        name="persist",
        steps=[
            WorkflowStep(target="claude", message="a"),
            WorkflowStep(target="gemini", message="b"),
        ],
        scope="project",
    )
    store.save(wf)
    loaded = store.load("persist")
    assert loaded is not None
    assert loaded.step_count == 2


# ── path attribute ───────────────────────────────────────────


def test_loaded_workflow_has_path(store, workflow_dirs: tuple[Path, Path]) -> None:
    """Loaded workflow should have path attribute set."""
    from synapse.workflow import Workflow, WorkflowStep

    project_dir, _ = workflow_dirs
    store.save(
        Workflow(
            name="pathed",
            steps=[WorkflowStep(target="claude", message="x")],
            scope="project",
        )
    )
    loaded = store.load("pathed")
    assert loaded is not None
    assert loaded.path == project_dir / "pathed.yaml"


# ── load with auto-scope resolution ─────────────────────────


def test_load_auto_scope_project_first(store) -> None:
    """load() without scope should find project first, then user."""
    from synapse.workflow import Workflow, WorkflowStep

    # Only in user scope
    store.save(
        Workflow(
            name="shared",
            steps=[WorkflowStep(target="gemini", message="u")],
            scope="user",
        )
    )
    loaded = store.load("shared")
    assert loaded is not None
    assert loaded.scope == "user"

    # Now save in project scope too
    store.save(
        Workflow(
            name="shared",
            steps=[WorkflowStep(target="claude", message="p")],
            scope="project",
        )
    )
    loaded = store.load("shared")
    assert loaded is not None
    assert loaded.scope == "project"  # project takes priority


# ── workflow with empty steps ────────────────────────────────


def test_workflow_requires_at_least_one_step() -> None:
    """Workflow with empty steps should raise WorkflowError."""
    from synapse.workflow import Workflow, WorkflowError

    with pytest.raises(WorkflowError, match="at least one step"):
        Workflow(name="empty", steps=[], scope="project")


# ── bool priority rejection ──────────────────────────────────


def test_step_rejects_bool_priority() -> None:
    """Boolean values should be rejected as priority even though bool is subclass of int."""
    from synapse.workflow import WorkflowError, WorkflowStep

    with pytest.raises(WorkflowError, match="priority"):
        WorkflowStep(target="claude", message="hi", priority=True)
    with pytest.raises(WorkflowError, match="priority"):
        WorkflowStep(target="claude", message="hi", priority=False)


# ── _parse_file validation ───────────────────────────────────


def test_load_empty_yaml_returns_none(store, workflow_dirs: tuple[Path, Path]) -> None:
    """Empty YAML file should return None (not crash)."""
    project_dir, _ = workflow_dirs
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "empty.yaml").write_text("", encoding="utf-8")
    assert store.load("empty", scope="project") is None


def test_load_yaml_without_steps_returns_none(
    store, workflow_dirs: tuple[Path, Path]
) -> None:
    """YAML without 'steps' key should return None."""
    project_dir, _ = workflow_dirs
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "nosteps.yaml").write_text("name: test\n", encoding="utf-8")
    assert store.load("nosteps", scope="project") is None


def test_load_yaml_with_empty_steps_returns_none(
    store, workflow_dirs: tuple[Path, Path]
) -> None:
    """YAML with empty steps list should return None."""
    project_dir, _ = workflow_dirs
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "emptysteps.yaml").write_text(
        "name: test\nsteps: []\n", encoding="utf-8"
    )
    assert store.load("emptysteps", scope="project") is None
