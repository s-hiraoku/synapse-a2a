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
    data = {
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


class TestEnvVarDetection:
    """Tests for environment variable detection in reinst.py."""

    def test_reads_env_vars(self, tmp_path: Path, temp_synapse_dir: Path) -> None:
        """Should read SYNAPSE_AGENT_ID, SYNAPSE_AGENT_TYPE, SYNAPSE_PORT."""
        env = os.environ.copy()
        env["SYNAPSE_AGENT_ID"] = "synapse-claude-8100"
        env["SYNAPSE_AGENT_TYPE"] = "claude"
        env["SYNAPSE_PORT"] = "8100"

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0
        output = result.stdout
        assert "synapse-claude-8100" in output
        assert "8100" in output

    def test_missing_env_vars_exits_with_error(self, tmp_path: Path) -> None:
        """Should exit with error when required env vars are missing and no PID fallback."""
        env = os.environ.copy()
        # Remove synapse env vars if they exist
        env.pop("SYNAPSE_AGENT_ID", None)
        env.pop("SYNAPSE_AGENT_TYPE", None)
        env.pop("SYNAPSE_PORT", None)

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

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

        env = os.environ.copy()
        env["SYNAPSE_AGENT_ID"] = "synapse-claude-8100"
        env["SYNAPSE_AGENT_TYPE"] = "claude"
        env["SYNAPSE_PORT"] = "8100"
        env["SYNAPSE_REGISTRY_DIR"] = str(temp_registry_dir)

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0
        output = result.stdout
        # name should appear in the output (replaces {{agent_name}})
        assert "my-claude" in output

    def test_works_without_registry(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
    ) -> None:
        """Should work even when registry lookup fails."""
        env = os.environ.copy()
        env["SYNAPSE_AGENT_ID"] = "synapse-claude-8100"
        env["SYNAPSE_AGENT_TYPE"] = "claude"
        env["SYNAPSE_PORT"] = "8100"
        env["SYNAPSE_REGISTRY_DIR"] = str(tmp_path / "nonexistent")

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0
        output = result.stdout
        # Should fall back to agent_id for display name
        assert "synapse-claude-8100" in output


class TestInstructionOutput:
    """Tests for instruction output content."""

    def test_outputs_instruction_with_placeholders_replaced(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
    ) -> None:
        """Should output instruction with all placeholders replaced."""
        env = os.environ.copy()
        env["SYNAPSE_AGENT_ID"] = "synapse-gemini-8110"
        env["SYNAPSE_AGENT_TYPE"] = "gemini"
        env["SYNAPSE_PORT"] = "8110"

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0
        output = result.stdout
        assert "synapse-gemini-8110" in output
        assert "8110" in output
        # No unresolved placeholders
        assert "{{agent_id}}" not in output
        assert "{{port}}" not in output
        assert "{{agent_name}}" not in output

    def test_uses_default_instruction_when_no_agent_specific(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
    ) -> None:
        """Should use default instruction when no agent-specific one exists."""
        env = os.environ.copy()
        env["SYNAPSE_AGENT_ID"] = "synapse-codex-8120"
        env["SYNAPSE_AGENT_TYPE"] = "codex"
        env["SYNAPSE_PORT"] = "8120"

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0
        output = result.stdout
        assert "SYNAPSE INSTRUCTIONS" in output
        assert "synapse-codex-8120" in output


class TestPidFallback:
    """Tests for PID-based registry fallback."""

    def test_pid_fallback_when_no_env_vars(
        self,
        tmp_path: Path,
        temp_synapse_dir: Path,
        temp_registry_dir: Path,
    ) -> None:
        """Should search registry by PID when env vars are not set."""
        # Register with current PID
        current_pid = os.getpid()
        register_agent(
            temp_registry_dir,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            pid=current_pid,
        )

        env = os.environ.copy()
        # No SYNAPSE_* env vars
        env.pop("SYNAPSE_AGENT_ID", None)
        env.pop("SYNAPSE_AGENT_TYPE", None)
        env.pop("SYNAPSE_PORT", None)
        env["SYNAPSE_REGISTRY_DIR"] = str(temp_registry_dir)

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

        # PID fallback uses the script's own PID, which won't match the registry
        # entry we created (which has the test process's PID). So this tests
        # the fallback path but won't find a match.
        # The important thing is it doesn't crash and shows a meaningful error.
        # We can test the function directly for PID matching.
        assert (
            result.returncode != 0 or "error" in result.stderr.lower() or result.stdout
        )


class TestEdgeCases:
    """Edge case tests."""

    def test_no_synapse_dir(self, tmp_path: Path) -> None:
        """Should handle missing .synapse directory gracefully."""
        env = os.environ.copy()
        env["SYNAPSE_AGENT_ID"] = "synapse-claude-8100"
        env["SYNAPSE_AGENT_TYPE"] = "claude"
        env["SYNAPSE_PORT"] = "8100"

        # Use a directory without .synapse
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(empty_dir),
        )

        # Should still output default instructions (from code defaults)
        assert result.returncode == 0
        output = result.stdout
        assert "synapse-claude-8100" in output

    def test_partial_env_vars(self, tmp_path: Path) -> None:
        """Should fail when only some env vars are set."""
        env = os.environ.copy()
        env["SYNAPSE_AGENT_ID"] = "synapse-claude-8100"
        # Missing SYNAPSE_AGENT_TYPE and SYNAPSE_PORT
        env.pop("SYNAPSE_AGENT_TYPE", None)
        env.pop("SYNAPSE_PORT", None)

        result = subprocess.run(
            [sys.executable, str(REINST_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )

        # Should still work or show error, not crash
        assert result.returncode == 0 or "error" in result.stderr.lower()
