"""Tests for MCP bootstrap instruction resources."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.mcp.server import SynapseMCPServer, UnknownMCPResourceError
from synapse.settings import SynapseSettings


def _create_settings(root: Path) -> SynapseSettings:
    synapse_dir = root / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)
    (synapse_dir / "default.md").write_text(
        "Agent {{agent_id}} on {{port}}\n\nHOW TO SEND MESSAGES TO OTHER AGENTS",
        encoding="utf-8",
    )
    (synapse_dir / "file-safety.md").write_text("Lock before edit.", encoding="utf-8")
    (synapse_dir / "shared-memory.md").write_text(
        "Use shared memory.", encoding="utf-8"
    )
    (synapse_dir / "settings.json").write_text(
        json.dumps(
            {
                "instructions": {"default": "default.md"},
                "env": {
                    "SYNAPSE_FILE_SAFETY_ENABLED": "true",
                    "SYNAPSE_SHARED_MEMORY_ENABLED": "true",
                },
            }
        ),
        encoding="utf-8",
    )
    return SynapseSettings.load(
        user_path=synapse_dir / "settings.json",
        project_path=synapse_dir / "settings.json",
        local_path=synapse_dir / "settings.local.json",
    )


def test_list_resources_includes_instruction_uris(tmp_path: Path) -> None:
    settings = _create_settings(tmp_path)
    server = SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )

    with patch("synapse.settings.Path.cwd", return_value=tmp_path):
        resources = server.list_resources()

    uris = {item.uri for item in resources}
    assert "synapse://instructions/default" in uris
    assert "synapse://instructions/file-safety" in uris
    assert "synapse://instructions/shared-memory" in uris


def test_read_default_instruction_resource_uses_settings_resolution(
    tmp_path: Path,
) -> None:
    settings = _create_settings(tmp_path)
    server = SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )

    with patch("synapse.settings.Path.cwd", return_value=tmp_path):
        text = server.read_resource("synapse://instructions/default")

    assert "synapse-codex-8120" in text
    assert "8120" in text
    assert "{{agent_id}}" not in text
    assert "{{port}}" not in text
    assert "HOW TO SEND MESSAGES TO OTHER AGENTS" in text


def test_read_optional_resource_uses_same_user_dir_resolution(tmp_path: Path) -> None:
    user_dir = tmp_path / "user-home"
    settings = _create_settings(user_dir)
    server = SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
        user_dir=user_dir,
    )

    with patch("synapse.settings.Path.cwd", return_value=tmp_path / "project"):
        resources = server.list_resources()
        text = server.read_resource("synapse://instructions/file-safety")

    assert any(item.uri == "synapse://instructions/file-safety" for item in resources)
    assert text == "Lock before edit."


def test_read_resource_rejects_unknown_uri(tmp_path: Path) -> None:
    settings = _create_settings(tmp_path)
    server = SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )

    with pytest.raises(UnknownMCPResourceError):
        server.read_resource("synapse://instructions/unknown")


def test_list_tools_includes_bootstrap_agent(tmp_path: Path) -> None:
    settings = _create_settings(tmp_path)
    server = SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )

    tools = server.list_tools()

    assert any(tool.name == "bootstrap_agent" for tool in tools)


def test_bootstrap_agent_returns_runtime_context(tmp_path: Path) -> None:
    settings = _create_settings(tmp_path)
    server = SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )

    with patch("synapse.settings.Path.cwd", return_value=tmp_path):
        payload = server.call_tool("bootstrap_agent", {})

    assert payload["agent_id"] == "synapse-codex-8120"
    assert payload["agent_type"] == "codex"
    assert payload["port"] == 8120
    assert payload["working_dir"] == str(tmp_path)
    assert "synapse://instructions/default" in payload["instruction_resources"]


def test_list_resources_returns_default_when_file_safety_manager_unavailable() -> None:
    server = SynapseMCPServer(
        file_safety_factory=lambda: (_ for _ in ()).throw(OSError())
    )

    resources = server.list_resources()

    assert any(item.uri == "synapse://instructions/default" for item in resources)


def test_bootstrap_agent_wraps_settings_load_value_error() -> None:
    server = SynapseMCPServer(
        settings_factory=lambda: (_ for _ in ()).throw(ValueError("bad settings"))
    )

    with pytest.raises(RuntimeError, match="Failed to load settings: bad settings"):
        server.call_tool("bootstrap_agent", {})


def test_handle_request_supports_tools_call(tmp_path: Path) -> None:
    settings = _create_settings(tmp_path)
    server = SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )

    with patch("synapse.settings.Path.cwd", return_value=tmp_path):
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "bootstrap_agent", "arguments": {}},
            }
        )

    result = response["result"]
    assert result["content"][0]["type"] == "text"
    payload = json.loads(result["content"][0]["text"])
    assert payload["agent_id"] == "synapse-codex-8120"


def test_initialize_advertises_resource_and_tool_capabilities() -> None:
    server = SynapseMCPServer()

    response = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )

    capabilities = response["result"]["capabilities"]
    assert "resources" in capabilities
    assert "tools" in capabilities


def test_initialized_notification_is_ignored_without_error() -> None:
    server = SynapseMCPServer()

    response = server.handle_request(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    )

    assert response is None


def test_mcp_module_serves_clean_stdio_response() -> None:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "synapse.mcp",
            "--agent-id",
            "synapse-codex-8120",
            "--agent-type",
            "codex",
            "--port",
            "8120",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        proc.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            )
            + "\n"
        )
        proc.stdin.flush()

        assert proc.stdout is not None
        first_line = proc.stdout.readline()
        payload = json.loads(first_line)
        assert payload["result"]["protocolVersion"] == "2024-11-05"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_mcp_module_ignores_initialized_notification_over_stdio() -> None:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "synapse.mcp",
            "--agent-id",
            "synapse-codex-8120",
            "--agent-type",
            "codex",
            "--port",
            "8120",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
            + "\n"
        )
        proc.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )
            + "\n"
        )
        proc.stdin.flush()

        assert proc.stdout is not None
        payload = json.loads(proc.stdout.readline())
        assert payload["result"]["tools"][0]["name"] == "bootstrap_agent"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_stdio_helpers_use_json_line_protocol() -> None:
    """Verify MCP server uses JSON-line protocol, not HTTP-style Content-Length framing."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "synapse.mcp",
            "--agent-id",
            "synapse-codex-8120",
            "--agent-type",
            "codex",
            "--port",
            "8120",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        proc.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            )
            + "\n"
        )
        proc.stdin.flush()

        assert proc.stdout is not None
        first_line = proc.stdout.readline()

        # Must NOT use HTTP-style Content-Length framing
        assert not first_line.startswith("Content-Length:")
        # Must be valid JSON (JSON-line protocol)
        payload = json.loads(first_line)
        assert payload.get("jsonrpc") == "2.0"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_module_entrypoint_uses_env_defaults_for_agent_context() -> None:
    env = dict(os.environ)
    env["SYNAPSE_AGENT_ID"] = "synapse-claude-8100"
    proc = subprocess.Popen(
        [sys.executable, "-m", "synapse.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    try:
        assert proc.stdin is not None
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "bootstrap_agent", "arguments": {}},
                }
            )
            + "\n"
        )
        proc.stdin.flush()

        assert proc.stdout is not None
        payload = json.loads(proc.stdout.readline())
        result = json.loads(payload["result"]["content"][0]["text"])
        assert result["agent_id"] == "synapse-claude-8100"
        assert result["agent_type"] == "claude"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
