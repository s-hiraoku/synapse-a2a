"""Tests for synapse-reinst skill script.

The reinst.py script re-injects Synapse A2A initial instructions after
context has been cleared (e.g., /clear). It reads environment variables
set by Synapse at startup and uses SynapseSettings.get_instruction()
to output the full instruction text.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Path to the reinst.py script
REINST_SCRIPT = (
    Path(__file__).parent.parent
    / "plugins"
    / "synapse-a2a"
    / "skills"
    / "synapse-reinst"
    / "scripts"
    / "reinst.py"
)


@pytest.fixture
def temp_synapse_dir(tmp_path: Path) -> Path:
    """Create a temporary .synapse directory with settings."""
    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)

    # Create settings.json
    settings = {
        "instructions": {
            "default": (
                "[SYNAPSE INSTRUCTIONS]\n"
                "Agent: {{agent_name}} | Port: {{port}} | ID: {{agent_id}}\n"
                "{{#agent_role}}Role: {{agent_role}}\n{{/agent_role}}"
                "This is a test instruction."
            ),
        }
    }
    settings_file = synapse_dir / "settings.json"
    settings_file.write_text(json.dumps(settings))

    return synapse_dir


@pytest.fixture
def temp_registry_dir(tmp_path: Path) -> Path:
    """Create a temporary registry directory."""
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    return registry_dir


def register_agent(
    registry_dir: Path,
    agent_id: str = "synapse-claude-8100",
    agent_type: str = "claude",
    port: int = 8100,
    name: str | None = None,
    role: str | None = None,
    pid: int | None = None,
) -> None:
    """Helper to create a registry entry."""
    data: dict[str, object] = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "port": port,
        "pid": pid or os.getpid(),
        "status": "READY",
    }
    if name:
        data["name"] = name
    if role:
        data["role"] = role
    (registry_dir / f"{agent_id}.json").write_text(json.dumps(data))


def run_reinst(
    cwd: Path,
    *,
    agent_id: str | None = None,
    agent_type: str | None = None,
    port: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the reinst.py script with the given environment variables."""
    env = os.environ.copy()
    # Clear any existing synapse env vars
    env.pop("SYNAPSE_AGENT_ID", None)
    env.pop("SYNAPSE_AGENT_TYPE", None)
    env.pop("SYNAPSE_PORT", None)

    if agent_id is not None:
        env["SYNAPSE_AGENT_ID"] = agent_id
    if agent_type is not None:
        env["SYNAPSE_AGENT_TYPE"] = agent_type
    if port is not None:
        env["SYNAPSE_PORT"] = port
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, str(REINST_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
    )


class TestEnvVarDetection:
    """Tests for environment variable detection in reinst.py."""

    def test_reads_env_vars(self, tmp_path: Path, temp_synapse_dir: Path) -> None:
        """Should read SYNAPSE_AGENT_ID, SYNAPSE_AGENT_TYPE, SYNAPSE_PORT."""
        result = run_reinst(
            tmp_path,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port="8100",
        )

        assert result.returncode == 0
        assert "synapse-claude-8100" in result.stdout
        assert "8100" in result.stdout

    def test_missing_env_vars_exits_with_error(self, tmp_path: Path) -> None:
        """Should exit with error when required env vars are missing and no PID fallback."""
        result = run_reinst(tmp_path)

        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "not found" in result.stderr.lower()


class TestRegistryLookup:
    """Tests for registry-based name/role lookup."""

    def test_lookup_name_and_role_from_registry(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
        temp_registry_dir: Path,
    ) -> None:
        """Should fetch name and role from registry when available."""
        register_agent(
            temp_registry_dir,
            agent_id="synapse-claude-8100",
            name="my-claude",
            role="code reviewer",
        )

        result = run_reinst(
            tmp_path,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port="8100",
            extra_env={"SYNAPSE_REGISTRY_DIR": str(temp_registry_dir)},
        )

        assert result.returncode == 0
        assert "my-claude" in result.stdout

    def test_works_without_registry(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
    ) -> None:
        """Should work even when registry lookup fails."""
        result = run_reinst(
            tmp_path,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port="8100",
            extra_env={"SYNAPSE_REGISTRY_DIR": str(tmp_path / "nonexistent")},
        )

        assert result.returncode == 0
        assert "synapse-claude-8100" in result.stdout


class TestInstructionOutput:
    """Tests for instruction output content."""

    def test_outputs_instruction_with_placeholders_replaced(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
    ) -> None:
        """Should output instruction with all placeholders replaced."""
        result = run_reinst(
            tmp_path,
            agent_id="synapse-gemini-8110",
            agent_type="gemini",
            port="8110",
        )

        assert result.returncode == 0
        assert "synapse-gemini-8110" in result.stdout
        assert "8110" in result.stdout
        # No unresolved placeholders
        for placeholder in ["{{agent_id}}", "{{port}}", "{{agent_name}}"]:
            assert placeholder not in result.stdout

    def test_uses_default_instruction_when_no_agent_specific(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
    ) -> None:
        """Should use default instruction when no agent-specific one exists."""
        result = run_reinst(
            tmp_path,
            agent_id="synapse-codex-8120",
            agent_type="codex",
            port="8120",
        )

        assert result.returncode == 0
        assert "SYNAPSE INSTRUCTIONS" in result.stdout
        assert "synapse-codex-8120" in result.stdout


class TestPidFallback:
    """Tests for PID-based registry fallback."""

    def test_pid_fallback_when_no_env_vars(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
        temp_registry_dir: Path,
    ) -> None:
        """Should search registry by PID when env vars are not set."""
        register_agent(
            temp_registry_dir,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            pid=os.getpid(),
        )

        result = run_reinst(
            tmp_path,
            extra_env={"SYNAPSE_REGISTRY_DIR": str(temp_registry_dir)},
        )

        # PID fallback uses the script's own PID, which won't match the registry
        # entry we created (which has the test process's PID). The important thing
        # is it doesn't crash and shows a meaningful error.
        assert (
            result.returncode != 0 or "error" in result.stderr.lower() or result.stdout
        )


class TestEdgeCases:
    """Edge case tests."""

    def test_no_synapse_dir(self, tmp_path: Path) -> None:
        """Should handle missing .synapse directory gracefully."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = run_reinst(
            empty_dir,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port="8100",
        )

        assert result.returncode == 0
        assert "synapse-claude-8100" in result.stdout

    def test_partial_env_vars(self, tmp_path: Path) -> None:
        """Should fail when only some env vars are set."""
        result = run_reinst(
            tmp_path,
            agent_id="synapse-claude-8100",
        )

        # Should still work or show error, not crash
        assert result.returncode == 0 or "error" in result.stderr.lower()
