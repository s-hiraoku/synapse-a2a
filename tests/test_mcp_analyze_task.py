"""Tests for MCP analyze_task suggestions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from synapse.mcp.server import SynapseMCPServer
from synapse.settings import SynapseSettings


def _create_settings(root: Path) -> SynapseSettings:
    synapse_dir = root / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)
    (synapse_dir / "default.md").write_text("Base bootstrap text.", encoding="utf-8")
    (synapse_dir / "settings.json").write_text(
        json.dumps({"instructions": {"default": "default.md"}}),
        encoding="utf-8",
    )
    return SynapseSettings.load(
        user_path=synapse_dir / "settings.json",
        project_path=synapse_dir / "settings.json",
        local_path=synapse_dir / "settings.local.json",
    )


def _create_server(root: Path) -> SynapseMCPServer:
    settings = _create_settings(root)
    return SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )


def test_list_tools_includes_analyze_task(tmp_path: Path) -> None:
    server = _create_server(tmp_path)

    tools = {tool.name: tool for tool in server.list_tools()}

    assert "analyze_task" in tools
    assert tools["analyze_task"].inputSchema == {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "User instruction to analyze for team/task split suggestions.",
            }
        },
        "required": ["prompt"],
    }


def test_analyze_task_returns_no_suggestion_when_no_trigger_matches(
    tmp_path: Path,
) -> None:
    server = _create_server(tmp_path)

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch("synapse.mcp.server.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status", "--porcelain"],
                returncode=0,
                stdout="",
                stderr="",
            )
            payload = server.call_tool("analyze_task", {"prompt": "Fix typo."})

    assert payload == {"suggestion": None, "reason": "no_trigger_matched"}


def test_analyze_task_returns_keyword_suggestion(tmp_path: Path) -> None:
    server = _create_server(tmp_path)

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch("synapse.mcp.server.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status", "--porcelain"],
                returncode=0,
                stdout="",
                stderr="",
            )
            payload = server.call_tool(
                "analyze_task", {"prompt": "認証基盤をOAuth2に移行してください。"}
            )

    assert payload["suggestion"] is not None
    assert "keyword:移行" in payload["triggered_by"]
    assert payload["suggestion"]["tasks"]
    assert payload["suggestion"]["type"] == "team_split"


def test_analyze_task_honors_suggest_yaml_prompt_length(tmp_path: Path) -> None:
    server = _create_server(tmp_path)
    (tmp_path / ".synapse" / "suggest.yaml").write_text(
        "suggest:\n  enabled: true\n  triggers:\n    min_prompt_length: 20\n",
        encoding="utf-8",
    )

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch("synapse.mcp.server.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status", "--porcelain"],
                returncode=0,
                stdout="",
                stderr="",
            )
            payload = server.call_tool(
                "analyze_task",
                {"prompt": "This prompt is longer than twenty chars."},
            )

    assert payload["suggestion"] is not None
    assert "prompt_length" in payload["triggered_by"]


def test_analyze_task_uses_git_status_for_file_count_and_directories(
    tmp_path: Path,
) -> None:
    server = _create_server(tmp_path)
    (tmp_path / ".synapse" / "suggest.yaml").write_text(
        "suggest:\n"
        "  enabled: true\n"
        "  triggers:\n"
        "    min_files: 2\n"
        "    multi_directory: true\n",
        encoding="utf-8",
    )

    git_output = "\n".join(
        [
            " M src/auth/service.py",
            " M tests/test_auth_service.py",
            " M docs/auth.md",
        ]
    )

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch("synapse.mcp.server.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status", "--porcelain"],
                returncode=0,
                stdout=git_output,
                stderr="",
            )
            payload = server.call_tool("analyze_task", {"prompt": "Update auth flow."})

    assert payload["suggestion"] is not None
    assert "changed_files" in payload["triggered_by"]
    assert "multi_directory" in payload["triggered_by"]


def test_analyze_task_detects_missing_tests_from_changed_files(tmp_path: Path) -> None:
    server = _create_server(tmp_path)
    (tmp_path / ".synapse" / "suggest.yaml").write_text(
        "suggest:\n  enabled: true\n  triggers:\n    missing_tests: true\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "service.py").write_text(
        "def login():\n    return True\n",
        encoding="utf-8",
    )

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch("synapse.mcp.server.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status", "--porcelain"],
                returncode=0,
                stdout=" M src/auth/service.py\n",
                stderr="",
            )
            payload = server.call_tool("analyze_task", {"prompt": "Implement auth."})

    assert payload["suggestion"] is not None
    assert "missing_tests" in payload["triggered_by"]


def test_analyze_task_respects_disabled_config(tmp_path: Path) -> None:
    server = _create_server(tmp_path)
    (tmp_path / ".synapse" / "suggest.yaml").write_text(
        "suggest:\n  enabled: false\n",
        encoding="utf-8",
    )

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch("synapse.mcp.server.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status", "--porcelain"],
                returncode=0,
                stdout="",
                stderr="",
            )
            payload = server.call_tool(
                "analyze_task", {"prompt": "認証基盤をOAuth2に移行してください。"}
            )

    assert payload == {"suggestion": None, "reason": "disabled"}


def test_default_instruction_resource_mentions_analyze_task(tmp_path: Path) -> None:
    server = _create_server(tmp_path)

    with patch("synapse.settings.Path.cwd", return_value=tmp_path):
        text = server.read_resource("synapse://instructions/default")

    assert "analyze_task" in text
    assert "new task" in text.lower()
