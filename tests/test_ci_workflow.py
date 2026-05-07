"""Tests for the default CI workflow quality gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "test.yml"
)


def _load_workflow() -> dict[str, Any]:
    assert WORKFLOW_PATH.exists(), f"workflow not found: {WORKFLOW_PATH}"
    raw = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    if True in raw and "on" not in raw:
        raw["on"] = raw.pop(True)
    return raw


def _test_job_steps(wf: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if wf is None:
        wf = _load_workflow()
    assert "jobs" in wf, "test.yml must define jobs"
    jobs = wf["jobs"]
    assert "test" in jobs, "test.yml must define a 'test' job"
    return jobs["test"]["steps"]


def test_mypy_is_required_in_default_ci() -> None:
    """Type checking should block merges once mypy is kept green."""
    mypy_steps = [
        step
        for step in _test_job_steps()
        if "mypy" in step.get("name", "").lower()
        or "uv run mypy synapse/" in str(step.get("run", ""))
    ]
    assert mypy_steps, "test.yml must run mypy"
    assert mypy_steps[0].get("continue-on-error") is not True


def test_default_ci_builds_package() -> None:
    """PR CI should catch packaging metadata and wheel/sdist regressions."""
    steps_text = "\n".join(str(step.get("run", "")) for step in _test_job_steps())
    assert "uv build" in steps_text


def test_default_ci_requires_test_job_name() -> None:
    with pytest.raises(AssertionError, match="test.yml must define a 'test' job"):
        _test_job_steps({"jobs": {"renamed": {"steps": []}}})
