"""Tests for Canvas multi-agent pattern routes and viewer assets."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse.canvas import CANVAS_JS_FILES


@pytest.fixture
def client(tmp_path) -> TestClient:
    """Create a Canvas test client."""
    from synapse.canvas.server import create_app

    app = create_app(db_path=str(tmp_path / "canvas.db"))
    return TestClient(app)


def _install_pattern_store(monkeypatch, patterns: list[dict]) -> None:
    """Install a fake synapse.patterns.store module for lazy route imports."""
    patterns_pkg = types.ModuleType("synapse.patterns")
    store_mod = types.ModuleType("synapse.patterns.store")

    class PatternStore:
        def list_patterns(self) -> list[dict]:
            return patterns

        def load(self, name: str) -> dict | None:
            for pattern in patterns:
                if pattern.get("name") == name:
                    return pattern
            return None

    store_mod.PatternStore = PatternStore
    monkeypatch.setitem(sys.modules, "synapse.patterns", patterns_pkg)
    monkeypatch.setitem(sys.modules, "synapse.patterns.store", store_mod)


def _install_pattern_runner(monkeypatch, runs: list[object]) -> None:
    """Install a fake synapse.patterns.runner module for lazy route imports."""
    patterns_pkg = sys.modules.get(
        "synapse.patterns", types.ModuleType("synapse.patterns")
    )
    runner_mod = types.ModuleType("synapse.patterns.runner")

    class PatternRunner:
        def get_runs(self) -> list[object]:
            return runs

        def get_run(self, run_id: str) -> object | None:
            for run in runs:
                if getattr(run, "run_id", None) == run_id:
                    return run
            return None

    runner_mod.PatternRunner = PatternRunner
    monkeypatch.setitem(sys.modules, "synapse.patterns", patterns_pkg)
    monkeypatch.setitem(sys.modules, "synapse.patterns.runner", runner_mod)


def test_multiagent_list_empty(client, monkeypatch) -> None:
    """GET /api/multiagent should return an empty pattern list."""
    _install_pattern_store(monkeypatch, [])

    resp = client.get("/api/multiagent")

    assert resp.status_code == 200
    data = resp.json()
    assert data["patterns"] == []
    assert isinstance(data["project_dir"], str)
    assert data["project_dir"]


def test_multiagent_list_with_patterns(client, monkeypatch) -> None:
    """GET /api/multiagent should return saved patterns."""
    patterns = [
        {
            "name": "review-loop",
            "pattern": "generator-verifier",
            "description": "Generator and verifier pair",
            "scope": "project",
        }
    ]
    _install_pattern_store(monkeypatch, patterns)

    resp = client.get("/api/multiagent")

    assert resp.status_code == 200
    assert resp.json()["patterns"] == patterns


def test_multiagent_show_existing(client, monkeypatch) -> None:
    """GET /api/multiagent/{name} should return the saved pattern."""
    pattern = {
        "name": "parallel-team",
        "pattern": "agent-teams",
        "description": "Workers pull from queue",
        "scope": "project",
    }
    _install_pattern_store(monkeypatch, [pattern])

    resp = client.get("/api/multiagent/parallel-team")

    assert resp.status_code == 200
    assert resp.json() == {"pattern": pattern}


def test_multiagent_show_nonexistent(client, monkeypatch) -> None:
    """GET /api/multiagent/{name} should return 404 for missing patterns."""
    _install_pattern_store(monkeypatch, [])

    resp = client.get("/api/multiagent/missing-pattern")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Pattern 'missing-pattern' not found"


def test_multiagent_runs_empty(client, monkeypatch) -> None:
    """GET /api/multiagent/runs should return an empty run list."""
    _install_pattern_runner(monkeypatch, [])

    resp = client.get("/api/multiagent/runs")

    assert resp.status_code == 200
    assert resp.json() == {"runs": []}


def test_multiagent_nav_and_view_exist_in_html() -> None:
    """Canvas HTML should contain the multiagent nav link and view section."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")

    assert 'data-route="multiagent"' in html
    assert 'id="multiagent-view"' in html
    assert "Patterns" in html


def test_canvas_js_files_include_multiagent_viewer() -> None:
    """Canvas asset manifest should include the multiagent viewer script."""
    assert "canvas-multiagent.js" in CANVAS_JS_FILES


def test_canvas_js_handles_multiagent_route() -> None:
    """Canvas JS should expose multiagent route handling and viewer hooks."""
    js = "\n".join(
        Path(f"synapse/canvas/static/{name}").read_text(encoding="utf-8")
        for name in CANVAS_JS_FILES
    )

    assert 'document.getElementById("multiagent-view")' in js
    assert 'document.getElementById("pattern-list-panel")' in js
    assert 'document.getElementById("pattern-detail-empty")' in js
    assert 'document.getElementById("pattern-detail-content")' in js
    assert 'multiagent: "Patterns"' in js
    assert 'currentRoute === "multiagent"' in js
    assert "loadPatterns();" in js
    assert "function renderPatternList(patterns)" in js
    assert "function renderPatternDetail(pattern)" in js
