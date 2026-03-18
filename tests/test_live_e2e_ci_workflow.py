"""Tests for the live E2E CI workflow configuration.

Validates that .github/workflows/live-e2e.yml is correctly structured:
- workflow_dispatch trigger with profile selection input
- per-agent jobs gated by secrets
- SYNAPSE_LIVE_E2E and SYNAPSE_LIVE_E2E_PROFILES env vars set correctly
"""

from __future__ import annotations

from pathlib import Path

import pytest
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


def test_each_job_installs_agent_cli():
    """Each job must have a step that installs the agent CLI binary."""
    wf = _load_workflow()
    for profile in EXPECTED_PROFILES:
        job = wf["jobs"][profile]
        steps = job.get("steps", [])
        install_steps = [
            s
            for s in steps
            if "install" in str(s.get("name", "")).lower()
            and (
                "cli" in str(s.get("name", "")).lower()
                or profile in str(s.get("name", "")).lower()
            )
        ]
        assert install_steps, f"{profile} job must have a step installing the agent CLI"


def test_copilot_job_installs_npm_package():
    """Copilot job must install @github/copilot (provides 'copilot' binary).

    The gh-copilot extension does NOT provide a standalone 'copilot' binary,
    which would cause shutil.which('copilot') to fail and tests to false-skip.
    """
    wf = _load_workflow()
    job = wf["jobs"]["copilot"]
    steps_text = str(job.get("steps", []))
    assert "@github/copilot" in steps_text, (
        "copilot job must install @github/copilot npm package "
        "(not gh-copilot extension)"
    )
    assert "gh extension" not in steps_text, (
        "copilot job must not use gh extension install "
        "(does not provide 'copilot' binary on PATH)"
    )


def test_no_pytest_timeout_flag():
    """Workflow must not use --timeout (pytest-timeout not in deps)."""
    content = WORKFLOW_PATH.read_text()
    assert "--timeout" not in content, (
        "must not use pytest --timeout flag (pytest-timeout is not a dependency)"
    )


def test_each_job_has_timeout_minutes():
    """Each job should set timeout-minutes at the job level."""
    wf = _load_workflow()
    for profile in EXPECTED_PROFILES:
        job = wf["jobs"][profile]
        assert "timeout-minutes" in job, f"{profile} job must set timeout-minutes"


# Map of profile → expected auth secret name used in the workflow.
EXPECTED_AUTH_SECRETS = {
    "claude": "ANTHROPIC_API_KEY",
    "codex": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "opencode": "OPENAI_API_KEY",
    "copilot": "GITHUB_TOKEN",
}


def test_secret_names_match_cli_auth():
    """Secret gate and env must use the correct auth env var per CLI."""
    wf = _load_workflow()
    for profile, expected_secret in EXPECTED_AUTH_SECRETS.items():
        job = wf["jobs"][profile]
        job_if = job.get("if", "")
        assert expected_secret in job_if, (
            f"{profile} job if-condition must reference {expected_secret}, "
            f"got: {job_if!r}"
        )


def test_missing_cli_fails_in_ci_not_skips():
    """In CI, a missing CLI must cause a test failure, not a silent skip."""
    import importlib
    import unittest.mock as mock

    import tests.test_live_e2e_agents as live_mod

    importlib.reload(live_mod)

    with (
        mock.patch.dict(
            "os.environ",
            {
                "SYNAPSE_LIVE_E2E": "1",
                "SYNAPSE_LIVE_E2E_PROFILES": "claude",
                "CI": "true",
            },
        ),
        mock.patch("shutil.which", return_value=None),
    ):
        with pytest.raises(pytest.fail.Exception, match="CLI 'claude' not found"):
            live_mod._require_live_profile("claude")


def test_missing_cli_skips_locally():
    """Locally (no CI env), a missing CLI should skip, not fail."""
    import importlib
    import unittest.mock as mock

    import tests.test_live_e2e_agents as live_mod

    importlib.reload(live_mod)

    with (
        mock.patch.dict(
            "os.environ",
            {"SYNAPSE_LIVE_E2E": "1", "SYNAPSE_LIVE_E2E_PROFILES": "claude", "CI": ""},
        ),
        mock.patch("shutil.which", return_value=None),
    ):
        with pytest.raises(pytest.skip.Exception):
            live_mod._require_live_profile("claude")
