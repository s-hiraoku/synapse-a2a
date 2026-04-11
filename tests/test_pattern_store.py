"""Tests for pattern definition storage."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def pattern_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Return (project_dir, user_dir) for pattern storage."""
    project = tmp_path / "project" / ".synapse" / "patterns"
    user = tmp_path / "home" / ".synapse" / "patterns"
    return project, user


@pytest.fixture()
def store(pattern_dirs: tuple[Path, Path]):
    from synapse.patterns.store import PatternStore

    project_dir, user_dir = pattern_dirs
    return PatternStore(project_dir=project_dir, user_dir=user_dir)


def test_save_and_load(store) -> None:
    """Saving a config and loading it should round-trip the YAML data."""
    config = {
        "name": "review-loop",
        "pattern_type": "generator-verifier",
        "max_rounds": 2,
    }

    saved_path = store.save(config)

    assert saved_path.name == "review-loop.yaml"
    assert store.load("review-loop") == config


def test_save_atomic_write(store, monkeypatch: pytest.MonkeyPatch) -> None:
    """save() should use a temp file and replace it into place."""
    from synapse.patterns import store as store_module

    calls: dict[str, Path] = {}
    original_mkstemp = store_module.tempfile.mkstemp
    original_replace = Path.replace

    def tracking_mkstemp(*args, **kwargs):
        fd, tmp_name = original_mkstemp(*args, **kwargs)
        calls["tmp"] = Path(tmp_name)
        return fd, tmp_name

    def tracking_replace(self: Path, target: Path) -> Path:
        calls["replace_src"] = self
        calls["replace_target"] = Path(target)
        return original_replace(self, target)

    monkeypatch.setattr(store_module.tempfile, "mkstemp", tracking_mkstemp)
    monkeypatch.setattr(Path, "replace", tracking_replace)

    target = store.save({"name": "atomic", "pattern_type": "generator-verifier"})

    assert calls["replace_src"] == calls["tmp"]
    assert calls["replace_target"] == target
    assert not calls["tmp"].exists()
    assert target.exists()


def test_save_invalid_name(store) -> None:
    """Invalid pattern names should be rejected."""
    with pytest.raises(ValueError, match="Invalid pattern name"):
        store.save({"name": "../bad", "pattern_type": "generator-verifier"})


def test_load_project_first(store) -> None:
    """load() should prefer the project scope when scope is omitted."""
    store.save({"name": "shared", "value": "project"}, scope="project")
    store.save({"name": "shared", "value": "user"}, scope="user")

    loaded = store.load("shared")

    assert loaded == {"name": "shared", "value": "project"}


def test_load_explicit_scope(store) -> None:
    """load() should respect an explicit scope."""
    store.save({"name": "shared", "value": "project"}, scope="project")
    store.save({"name": "shared", "value": "user"}, scope="user")

    assert store.load("shared", scope="project") == {
        "name": "shared",
        "value": "project",
    }
    assert store.load("shared", scope="user") == {
        "name": "shared",
        "value": "user",
    }


def test_load_nonexistent(store) -> None:
    """load() should return None for missing patterns."""
    assert store.load("missing") is None


def test_list_patterns_empty(store) -> None:
    """list_patterns() should return an empty list when no files exist."""
    assert store.list_patterns() == []


def test_list_patterns_multiple(store) -> None:
    """list_patterns() should return patterns sorted by name."""
    store.save({"name": "zeta", "scope_value": "project"}, scope="project")
    store.save({"name": "alpha", "scope_value": "project"}, scope="project")
    store.save({"name": "beta", "scope_value": "user"}, scope="user")

    patterns = store.list_patterns()

    assert [pattern["name"] for pattern in patterns] == ["alpha", "beta", "zeta"]


def test_list_patterns_skips_invalid_yaml(
    store, pattern_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed YAML files should be skipped with a warning."""
    project_dir, _ = pattern_dirs
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "broken.yaml").write_text("name: broken: [", encoding="utf-8")
    store.save({"name": "valid", "pattern_type": "generator-verifier"})

    warnings: list[str] = []
    monkeypatch.setattr(
        "synapse.patterns.store.logger",
        type("_L", (), {"warning": staticmethod(lambda fmt, *a: warnings.append(fmt % a))})(),
    )

    patterns = store.list_patterns(scope="project")

    assert [pattern["name"] for pattern in patterns] == ["valid"]
    assert any("Skipping invalid pattern file" in w for w in warnings)


def test_delete_existing(store) -> None:
    """delete() should remove an existing pattern file."""
    store.save({"name": "victim", "pattern_type": "generator-verifier"})

    deleted = store.delete("victim")

    assert deleted is True
    assert store.load("victim") is None


def test_delete_nonexistent(store) -> None:
    """delete() should return False when the file is missing."""
    assert store.delete("ghost") is False


def test_exists_true_and_false(store) -> None:
    """exists() should report basic presence correctly."""
    store.save({"name": "present", "pattern_type": "generator-verifier"})

    assert store.exists("present") is True
    assert store.exists("missing") is False


def test_scope_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Default directories should resolve to project and user pattern paths."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)

    from synapse.patterns.store import PatternStore

    store = PatternStore()

    assert store.project_dir == (tmp_path / "project" / ".synapse" / "patterns")
    assert store.user_dir == (home / ".synapse" / "patterns")
