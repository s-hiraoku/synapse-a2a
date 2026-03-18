"""Tests for the live E2E CI workflow configuration.

Validates that .github/workflows/live-e2e.yml is correctly structured:
- workflow_dispatch trigger with profile selection input
- per-agent jobs gated by secrets
- SYNAPSE_LIVE_E2E and SYNAPSE_LIVE_E2E_PROFILES env vars set correctly
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "live-e2e.yml"
)
EXPECTED_PROFILES = {"claude", "codex", "gemini", "opencode", "copilot"}


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.exists(), f"workflow not found: {WORKFLOW_PATH}"
    # PyYAML parses bare `on:` as boolean True; normalise key access.
    raw = yaml.safe_load(WORKFLOW_PATH.read_text())
    # Re-key True → "on" so tests can use wf["on"] consistently.
    if True in raw and "on" not in raw:
        raw["on"] = raw.pop(True)
    return raw


def test_workflow_trigger_is_workflow_dispatch():
    wf = _load_workflow()
    assert "workflow_dispatch" in wf["on"], "must use workflow_dispatch trigger"


def test_workflow_dispatch_has_profiles_input():
    wf = _load_workflow()
    inputs = wf["on"]["workflow_dispatch"].get("inputs", {})
    assert "profiles" in inputs, "workflow_dispatch must have 'profiles' input"
    profiles_input = inputs["profiles"]
    assert profiles_input.get("type") == "string"
    assert profiles_input.get("required") is False


def test_all_agent_profiles_have_jobs():
    wf = _load_workflow()
    jobs = wf.get("jobs", {})
    for profile in EXPECTED_PROFILES:
        assert profile in jobs, f"missing job for profile '{profile}'"


def test_each_job_sets_live_e2e_env():
    wf = _load_workflow()
    for profile in EXPECTED_PROFILES:
        job = wf["jobs"][profile]
        env = job.get("env", {})
        # env may be at job level or step level; check job level first
        if "SYNAPSE_LIVE_E2E" in env:
            assert env["SYNAPSE_LIVE_E2E"] == "1"
        else:
            # check the pytest step
            test_steps = [s for s in job.get("steps", []) if "pytest" in str(s)]
            assert test_steps, f"no pytest step found in {profile} job"
            step_env = test_steps[0].get("env", {})
            assert step_env.get("SYNAPSE_LIVE_E2E") == "1", (
                f"{profile} job must set SYNAPSE_LIVE_E2E=1"
            )


def test_each_job_sets_profile_env():
    wf = _load_workflow()
    for profile in EXPECTED_PROFILES:
        job = wf["jobs"][profile]
        env = job.get("env", {})
        if "SYNAPSE_LIVE_E2E_PROFILES" in env:
            assert env["SYNAPSE_LIVE_E2E_PROFILES"] == profile
        else:
            test_steps = [s for s in job.get("steps", []) if "pytest" in str(s)]
            assert test_steps, f"no pytest step found in {profile} job"
            step_env = test_steps[0].get("env", {})
            assert step_env.get("SYNAPSE_LIVE_E2E_PROFILES") == profile


def test_each_job_has_secret_gate():
    """Each agent job should have an 'if' condition checking for its secret."""
    wf = _load_workflow()
    for profile in EXPECTED_PROFILES:
        job = wf["jobs"][profile]
        job_if = job.get("if", "")
        assert "secrets." in job_if, (
            f"{profile} job must be gated by a secret (has if: {job_if!r})"
        )


def test_existing_test_workflow_unchanged():
    """test.yml must NOT reference live E2E env vars."""
    test_yml = WORKFLOW_PATH.parent / "test.yml"
    assert test_yml.exists()
    content = test_yml.read_text()
    assert "SYNAPSE_LIVE_E2E" not in content, (
        "test.yml must not be modified for live E2E"
    )


def test_workflow_uses_uv_and_python():
    """Each job should install uv and Python."""
    wf = _load_workflow()
    for profile in EXPECTED_PROFILES:
        job = wf["jobs"][profile]
        steps_text = str(job.get("steps", []))
        assert "setup-uv" in steps_text, f"{profile} job must use setup-uv action"
