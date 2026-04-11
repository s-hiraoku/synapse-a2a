"""Tests for CLI multiagent commands (synapse/commands/multiagent.py)."""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import yaml


def _make_args(**kwargs: Any) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults."""
    defaults = {
        "pattern_type": "generator-verifier",
        "pattern_name": "test-pattern",
        "name": None,
        "task": "Review the auth module",
        "run_id": "run-123",
        "user": False,
        "project": False,
        "force": False,
        "dry_run": False,
        "run_async": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture()
def pattern_dirs(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / ".synapse" / "patterns"
    user = tmp_path / "home" / ".synapse" / "patterns"
    return project, user


class FakePatternError(Exception):
    """Pattern store/runner error for isolated command tests."""


class FakePatternStore:
    """Minimal in-test store implementation for command tests."""

    _VALID_NAME_RE = r"^[A-Za-z0-9_-]+$"

    def __init__(self, project_dir: Path, user_dir: Path) -> None:
        self.project_dir = project_dir
        self.user_dir = user_dir

    @classmethod
    def _validate_name(cls, name: str) -> None:
        import re

        if not re.match(cls._VALID_NAME_RE, name):
            raise FakePatternError(f"Invalid pattern name: {name}")

    def _scope_dir(self, scope: str | None) -> Path:
        if scope == "user":
            return self.user_dir
        return self.project_dir

    def exists(self, name: str, scope: str | None = None) -> bool:
        self._validate_name(name)
        return (self._scope_dir(scope) / f"{name}.yaml").exists()

    def save(self, config: dict[str, Any], scope: str = "project") -> Path:
        name = config["name"]
        self._validate_name(name)
        target = self._scope_dir(scope)
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{name}.yaml"
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return path

    def load(self, name: str, scope: str | None = None) -> dict[str, Any] | None:
        self._validate_name(name)
        scopes = [scope] if scope else ["project", "user"]
        for candidate_scope in scopes:
            path = self._scope_dir(candidate_scope) / f"{name}.yaml"
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                data.setdefault("scope", candidate_scope)
                return data
        return None

    def list_patterns(self, scope: str | None = None) -> list[dict]:
        scopes = [scope] if scope else ["project", "user"]
        items: list[dict] = []
        for candidate_scope in scopes:
            base = self._scope_dir(candidate_scope)
            if not base.exists():
                continue
            for path in sorted(base.glob("*.yaml")):
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                data["scope"] = candidate_scope
                items.append(data)
        return items


class FakePatternRunner:
    """Minimal async runner implementation for isolated command tests."""

    runs: dict[str, SimpleNamespace] = {}

    def __init__(self) -> None:
        self.stop_calls: list[str] = []

    async def run_pattern(
        self,
        pattern_type: str,
        task: str,
        config: dict[str, Any] | None = None,
        on_update: Any = None,
    ) -> str:
        run_id = "run-123"
        run = SimpleNamespace(
            run_id=run_id,
            status="completed",
            output="ok",
            agents=["Generator", "Verifier"],
        )
        self.runs[run_id] = run
        return run_id

    async def wait_for_run(self, run_id: str) -> SimpleNamespace:
        return self.runs[run_id]

    def get_run(self, run_id: str) -> SimpleNamespace | None:
        return self.runs.get(run_id)

    async def stop_run(self, run_id: str) -> bool:
        self.stop_calls.append(run_id)
        return run_id in self.runs


def _load_multiagent_module(monkeypatch: pytest.MonkeyPatch):
    """Import the multiagent command module with fake pattern dependencies."""
    fake_patterns_pkg = ModuleType("synapse.patterns")
    fake_base_mod = ModuleType("synapse.patterns.base")
    fake_store_mod = ModuleType("synapse.patterns.store")
    fake_runner_mod = ModuleType("synapse.patterns.runner")

    fake_base_mod.PatternError = FakePatternError

    fake_store_mod.PatternStore = FakePatternStore
    fake_store_mod.Scope = str
    fake_store_mod.PatternError = FakePatternError

    fake_runner_mod.PatternRunner = FakePatternRunner
    fake_runner_mod.PatternError = FakePatternError
    fake_runner_mod.get_runner = lambda: FakePatternRunner()

    monkeypatch.setitem(sys.modules, "synapse.patterns", fake_patterns_pkg)
    monkeypatch.setitem(sys.modules, "synapse.patterns.base", fake_base_mod)
    monkeypatch.setitem(sys.modules, "synapse.patterns.store", fake_store_mod)
    monkeypatch.setitem(sys.modules, "synapse.patterns.runner", fake_runner_mod)
    sys.modules.pop("synapse.commands.multiagent", None)
    return importlib.import_module("synapse.commands.multiagent")


def _make_store(project_dir: Path, user_dir: Path) -> FakePatternStore:
    return FakePatternStore(project_dir=project_dir, user_dir=user_dir)


def test_init_creates_yaml(
    pattern_dirs: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """init should generate a template YAML file."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(name="my-review")

    with patch("synapse.commands.multiagent._get_pattern_store", return_value=store):
        multiagent.cmd_multiagent_init(args)

    captured = capsys.readouterr()
    path = project_dir / "my-review.yaml"
    assert str(path) in captured.out
    assert path.exists()

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["name"] == "my-review"
    assert data["pattern"] == "generator-verifier"
    assert "generator" in data
    assert "verifier" in data


@pytest.mark.parametrize(
    ("pattern_type", "expected_keys"),
    [
        ("generator-verifier", {"generator", "verifier", "max_iterations"}),
        ("orchestrator-subagent", {"orchestrator", "subtasks", "parallel"}),
        ("agent-teams", {"team", "task_queue", "completion"}),
        ("message-bus", {"topics", "router"}),
        ("shared-state", {"agents", "shared_store", "termination"}),
    ],
)
def test_init_all_pattern_types(
    pattern_type: str,
    expected_keys: set[str],
    pattern_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """each built-in pattern type should generate valid YAML."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(pattern_type=pattern_type, name=pattern_type)

    with patch("synapse.commands.multiagent._get_pattern_store", return_value=store):
        multiagent.cmd_multiagent_init(args)

    data = yaml.safe_load((project_dir / f"{pattern_type}.yaml").read_text("utf-8"))
    assert data["pattern"] == pattern_type
    assert expected_keys.issubset(data.keys())


def test_init_custom_name(
    pattern_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """--name should control the output filename and YAML name."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(pattern_type="message-bus", name="event-router")

    with patch("synapse.commands.multiagent._get_pattern_store", return_value=store):
        multiagent.cmd_multiagent_init(args)

    path = project_dir / "event-router.yaml"
    assert path.exists()
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["name"] == "event-router"


def test_init_force_overwrite(
    pattern_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """--force should overwrite an existing pattern file."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    path = store.save({"name": "test-pattern", "pattern": "message-bus"})
    path.write_text("name: old\npattern: old\n", encoding="utf-8")
    args = _make_args(pattern_type="shared-state", name="test-pattern", force=True)

    with patch("synapse.commands.multiagent._get_pattern_store", return_value=store):
        multiagent.cmd_multiagent_init(args)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["pattern"] == "shared-state"


def test_init_no_overwrite_without_force(
    pattern_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """init should fail if the pattern already exists and --force is missing."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    store.save({"name": "test-pattern", "pattern": "message-bus"})
    args = _make_args(pattern_type="shared-state", name="test-pattern")

    with (
        patch("synapse.commands.multiagent._get_pattern_store", return_value=store),
        pytest.raises(SystemExit, match="1"),
    ):
        multiagent.cmd_multiagent_init(args)


def test_list_empty(
    pattern_dirs: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list should show a no-patterns message when the store is empty."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)

    with patch("synapse.commands.multiagent._get_pattern_store", return_value=store):
        multiagent.cmd_multiagent_list(_make_args())

    captured = capsys.readouterr()
    assert "No saved patterns" in captured.out


def test_list_shows_patterns(
    pattern_dirs: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list should display pattern name, kind, description, and scope."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        {
            "name": "review-flow",
            "pattern": "generator-verifier",
            "description": "Generate output and verify against criteria",
        }
    )

    with patch("synapse.commands.multiagent._get_pattern_store", return_value=store):
        multiagent.cmd_multiagent_list(_make_args())

    captured = capsys.readouterr()
    assert "NAME" in captured.out
    assert "PATTERN" in captured.out
    assert "DESCRIPTION" in captured.out
    assert "SCOPE" in captured.out
    assert "review-flow" in captured.out
    assert "generator-verifier" in captured.out


def test_show_displays_yaml(
    pattern_dirs: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """show should print the stored YAML content."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        {
            "name": "review-flow",
            "pattern": "generator-verifier",
            "description": "Generate output and verify against criteria",
            "generator": {"profile": "claude", "name": "Generator"},
            "verifier": {"profile": "claude", "name": "Verifier"},
        }
    )

    with patch("synapse.commands.multiagent._get_pattern_store", return_value=store):
        multiagent.cmd_multiagent_show(_make_args(pattern_name="review-flow"))

    captured = capsys.readouterr()
    assert "name: review-flow" in captured.out
    assert "pattern: generator-verifier" in captured.out
    assert "generator:" in captured.out


def test_show_nonexistent(
    pattern_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """show should exit with error when the pattern is missing."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)

    with (
        patch("synapse.commands.multiagent._get_pattern_store", return_value=store),
        pytest.raises(SystemExit, match="1"),
    ):
        multiagent.cmd_multiagent_show(_make_args(pattern_name="ghost"))


def test_run_dry_run(
    pattern_dirs: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run --dry-run should print the plan without invoking the runner."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        {
            "name": "review-flow",
            "pattern": "generator-verifier",
            "description": "Generate output and verify against criteria",
            "generator": {"profile": "claude", "name": "Generator"},
            "verifier": {"profile": "claude", "name": "Verifier"},
        }
    )

    with (
        patch("synapse.commands.multiagent._get_pattern_store", return_value=store),
        patch("synapse.commands.multiagent.PatternRunner") as mock_runner_cls,
    ):
        multiagent.cmd_multiagent_run(
            _make_args(pattern_name="review-flow", dry_run=True)
        )

    mock_runner_cls.assert_not_called()
    captured = capsys.readouterr()
    assert "DRY RUN" in captured.out
    assert "review-flow" in captured.out
    assert "Review the auth module" in captured.out


def test_run_async_prints_run_id(
    pattern_dirs: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run --async should print the run id and skip waiting."""
    multiagent = _load_multiagent_module(monkeypatch)
    project_dir, user_dir = pattern_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        {
            "name": "review-flow",
            "pattern": "generator-verifier",
            "description": "Generate output and verify against criteria",
        }
    )

    runner = FakePatternRunner()

    with (
        patch("synapse.commands.multiagent._get_pattern_store", return_value=store),
        patch("synapse.commands.multiagent.PatternRunner", return_value=runner),
        patch.object(runner, "wait_for_run") as mock_wait,
    ):
        multiagent.cmd_multiagent_run(
            _make_args(pattern_name="review-flow", run_async=True)
        )

    mock_wait.assert_not_called()
    captured = capsys.readouterr()
    assert "run-123" in captured.out


def test_status_nonexistent_run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """status should exit with an error for an unknown run id."""
    multiagent = _load_multiagent_module(monkeypatch)
    FakePatternRunner.runs.clear()
    runner = FakePatternRunner()

    with (
        patch("synapse.commands.multiagent.PatternRunner", return_value=runner),
        pytest.raises(SystemExit, match="1"),
    ):
        multiagent.cmd_multiagent_status(_make_args())

    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()


def test_stop_nonexistent_run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop should exit with an error for an unknown run id."""
    multiagent = _load_multiagent_module(monkeypatch)
    FakePatternRunner.runs.clear()
    runner = FakePatternRunner()

    with (
        patch("synapse.commands.multiagent.PatternRunner", return_value=runner),
        pytest.raises(SystemExit, match="1"),
    ):
        multiagent.cmd_multiagent_stop(_make_args())

    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()


def test_cli_registration() -> None:
    """multiagent help should be registered on the top-level CLI."""
    result = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "multiagent", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Multi-agent coordination patterns" in result.stdout
    assert "synapse map init generator-verifier --name my-review" in result.stdout


def test_cli_alias() -> None:
    """map should behave as an alias for multiagent."""
    result = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "map", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Multi-agent coordination patterns" in result.stdout
    assert "synapse map list" in result.stdout
