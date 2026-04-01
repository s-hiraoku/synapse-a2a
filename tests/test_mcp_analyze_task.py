"""Tests for MCP analyze_task suggestions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from synapse.mcp.server import GitDiffStats, SynapseMCPServer
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


def _create_server(
    root: Path, agent_type: str = "codex", agent_id: str = "synapse-codex-8120"
) -> SynapseMCPServer:
    settings = _create_settings(root)
    return SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type=agent_type,
        agent_id=agent_id,
        port=8120,
    )


def _git_run_side_effect(
    status_stdout: str = "",
    numstat_stdout: str = "",
) -> object:
    """Create a side_effect for subprocess.run that returns different results
    for git status vs git diff --numstat."""

    def _side_effect(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "status" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=status_stdout, stderr=""
            )
        if "diff" in cmd and "--numstat" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=numstat_stdout, stderr=""
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    return _side_effect


def test_list_tools_includes_analyze_task(tmp_path: Path) -> None:
    server = _create_server(tmp_path)

    tools = {tool.name: tool for tool in server.list_tools()}

    assert "analyze_task" in tools
    schema = tools["analyze_task"].inputSchema
    assert "prompt" in schema["properties"]
    assert "files" in schema["properties"]
    assert "agent_type" in schema["properties"]
    assert schema["required"] == ["prompt"]


def test_analyze_task_returns_no_suggestion_when_no_trigger_matches(
    tmp_path: Path,
) -> None:
    server = _create_server(tmp_path)

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch(
            "synapse.mcp.server.subprocess.run",
            side_effect=_git_run_side_effect(),
        ):
            payload = server.call_tool("analyze_task", {"prompt": "Fix typo."})

    assert payload["suggestion"] is None
    assert payload["reason"] == "no_trigger_matched"
    assert "delegation_strategy" in payload


def test_analyze_task_returns_keyword_trigger(tmp_path: Path) -> None:
    server = _create_server(tmp_path)

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch(
            "synapse.mcp.server.subprocess.run",
            side_effect=_git_run_side_effect(),
        ):
            payload = server.call_tool(
                "analyze_task", {"prompt": "認証基盤をOAuth2に移行してください。"}
            )

    assert "keyword:移行" in payload["triggered_by"]
    assert "delegation_strategy" in payload


def test_analyze_task_keyword_with_large_diff_returns_spawn_suggestion(
    tmp_path: Path,
) -> None:
    """When keyword triggers AND diff is large enough for spawn, suggestion is returned."""
    server = _create_server(tmp_path, agent_type="claude")
    numstat = "\n".join(f"30\t10\tdir{i}/mod{i}.py" for i in range(12))
    status = "\n".join(f" M dir{i}/mod{i}.py" for i in range(12))

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch(
            "synapse.mcp.server.subprocess.run",
            side_effect=_git_run_side_effect(
                status_stdout=status, numstat_stdout=numstat
            ),
        ):
            payload = server.call_tool(
                "analyze_task", {"prompt": "認証基盤をOAuth2に移行してください。"}
            )

    assert payload["delegation_strategy"] == "spawn"
    assert payload["suggestion"] is not None
    assert payload["suggestion"]["type"] == "team_split"


def test_analyze_task_honors_suggest_yaml_prompt_length(tmp_path: Path) -> None:
    server = _create_server(tmp_path)
    (tmp_path / ".synapse" / "suggest.yaml").write_text(
        "suggest:\n  enabled: true\n  triggers:\n    min_prompt_length: 20\n",
        encoding="utf-8",
    )

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch(
            "synapse.mcp.server.subprocess.run",
            side_effect=_git_run_side_effect(),
        ):
            payload = server.call_tool(
                "analyze_task",
                {"prompt": "This prompt is longer than twenty chars."},
            )

    assert "prompt_length" in payload["triggered_by"]
    assert "delegation_strategy" in payload


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

    status_output = "\n".join(
        [
            " M src/auth/service.py",
            " M tests/test_auth_service.py",
            " M docs/auth.md",
        ]
    )

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch(
            "synapse.mcp.server.subprocess.run",
            side_effect=_git_run_side_effect(status_stdout=status_output),
        ):
            payload = server.call_tool("analyze_task", {"prompt": "Update auth flow."})

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
        with patch(
            "synapse.mcp.server.subprocess.run",
            side_effect=_git_run_side_effect(status_stdout=" M src/auth/service.py\n"),
        ):
            payload = server.call_tool("analyze_task", {"prompt": "Implement auth."})

    assert "missing_tests" in payload["triggered_by"]


def test_analyze_task_respects_disabled_config(tmp_path: Path) -> None:
    server = _create_server(tmp_path)
    (tmp_path / ".synapse" / "suggest.yaml").write_text(
        "suggest:\n  enabled: false\n",
        encoding="utf-8",
    )

    with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
        with patch(
            "synapse.mcp.server.subprocess.run",
            side_effect=_git_run_side_effect(),
        ):
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


def test_default_instruction_mentions_delegation_strategy(tmp_path: Path) -> None:
    """The Smart Suggest instructions should mention delegation_strategy."""
    server = _create_server(tmp_path)

    with patch("synapse.settings.Path.cwd", return_value=tmp_path):
        text = server.read_resource("synapse://instructions/default")

    assert "delegation_strategy" in text
    assert "subagent" in text.lower()
    assert "spawn" in text.lower()


# ---------------------------------------------------------------------------
# Phase 1: GitDiffStats + delegation_strategy tests
# ---------------------------------------------------------------------------


class TestParseGitNumstat:
    """Unit tests for _parse_git_numstat."""

    def test_parse_standard_numstat_output(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path)
        numstat_output = (
            "10\t5\tsrc/auth/service.py\n120\t30\tsrc/api/handler.py\n3\t1\tREADME.md\n"
        )
        stats = server._parse_git_numstat(numstat_output)

        assert isinstance(stats, GitDiffStats)
        assert stats.files_changed == 3
        assert stats.insertions == 133
        assert stats.deletions == 36
        assert stats.directory_spread == 2  # src, .
        assert len(stats.file_paths) == 3
        assert "src/api/handler.py" in stats.large_files  # 150 lines > 100

    def test_parse_empty_numstat(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path)
        stats = server._parse_git_numstat("")

        assert stats.files_changed == 0
        assert stats.insertions == 0
        assert stats.deletions == 0
        assert stats.file_paths == []

    def test_parse_binary_file_in_numstat(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path)
        # Binary files show as "-\t-\tfilename" in numstat
        numstat_output = "-\t-\timage.png\n5\t2\tsrc/main.py\n"
        stats = server._parse_git_numstat(numstat_output)

        assert stats.files_changed == 2
        assert stats.insertions == 5
        assert stats.deletions == 2


class TestDelegationStrategy:
    """Tests for _determine_delegation_strategy."""

    def test_strategy_self_for_small_change(self, tmp_path: Path) -> None:
        """2 files, 45 lines, 1 directory → self."""
        server = _create_server(tmp_path, agent_type="claude")
        diff_stats = GitDiffStats(
            files_changed=2,
            insertions=30,
            deletions=15,
            directory_spread=1,
            file_paths=["src/foo.py", "src/bar.py"],
            large_files=[],
        )
        strategy, reason = server._determine_delegation_strategy(
            diff_stats, "Fix a small bug.", "claude"
        )
        assert strategy == "self"

    def test_strategy_subagent_for_medium_change_claude(self, tmp_path: Path) -> None:
        """5 files, 150 lines, 2 dirs, claude → subagent."""
        server = _create_server(tmp_path, agent_type="claude")
        diff_stats = GitDiffStats(
            files_changed=5,
            insertions=100,
            deletions=50,
            directory_spread=2,
            file_paths=[f"src/mod{i}.py" for i in range(5)],
            large_files=[],
        )
        strategy, reason = server._determine_delegation_strategy(
            diff_stats, "Refactor the auth module.", "claude"
        )
        assert strategy == "subagent"

    def test_strategy_spawn_for_large_change(self, tmp_path: Path) -> None:
        """15 files, 500 lines, 3+ dirs → spawn."""
        server = _create_server(tmp_path, agent_type="claude")
        diff_stats = GitDiffStats(
            files_changed=15,
            insertions=350,
            deletions=150,
            directory_spread=4,
            file_paths=[f"dir{i}/mod.py" for i in range(15)],
            large_files=["dir0/mod.py", "dir1/mod.py", "dir2/mod.py"],
        )
        strategy, reason = server._determine_delegation_strategy(
            diff_stats, "Migrate database schema.", "claude"
        )
        assert strategy == "spawn"

    def test_strategy_spawn_when_review_keyword(self, tmp_path: Path) -> None:
        """Review keyword → spawn (different model needed)."""
        server = _create_server(tmp_path, agent_type="claude")
        diff_stats = GitDiffStats(
            files_changed=5,
            insertions=80,
            deletions=20,
            directory_spread=2,
            file_paths=[f"src/mod{i}.py" for i in range(5)],
            large_files=[],
        )
        strategy, reason = server._determine_delegation_strategy(
            diff_stats, "Review the authentication changes.", "claude"
        )
        assert strategy == "spawn"

    def test_non_subagent_capable_skips_subagent(self, tmp_path: Path) -> None:
        """Gemini has no subagent capability → never returns 'subagent'."""
        server = _create_server(
            tmp_path, agent_type="gemini", agent_id="synapse-gemini-8110"
        )
        diff_stats = GitDiffStats(
            files_changed=5,
            insertions=100,
            deletions=50,
            directory_spread=2,
            file_paths=[f"src/mod{i}.py" for i in range(5)],
            large_files=[],
        )
        strategy, reason = server._determine_delegation_strategy(
            diff_stats, "Refactor the auth module.", "gemini"
        )
        assert strategy != "subagent"

    def test_diff_stats_included_in_context(self, tmp_path: Path) -> None:
        """analyze_task output includes context.diff_stats."""
        server = _create_server(tmp_path, agent_type="claude")
        numstat = "\n".join(f"30\t10\tdir{i}/mod.py" for i in range(12))
        status = "\n".join(f" M dir{i}/mod.py" for i in range(12))

        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(
                    status_stdout=status, numstat_stdout=numstat
                ),
            ):
                payload = server.call_tool(
                    "analyze_task",
                    {
                        "prompt": "Large refactor across many dirs.",
                        "agent_type": "claude",
                    },
                )

        assert "context" in payload
        assert "diff_stats" in payload["context"]
        ds = payload["context"]["diff_stats"]
        assert ds["files"] == 12
        assert ds["insertions"] == 360
        assert ds["deletions"] == 120

    def test_analyze_task_returns_delegation_strategy(self, tmp_path: Path) -> None:
        """analyze_task output always includes delegation_strategy."""
        server = _create_server(tmp_path, agent_type="claude")

        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(),
            ):
                payload = server.call_tool(
                    "analyze_task", {"prompt": "Fix typo.", "agent_type": "claude"}
                )

        assert "delegation_strategy" in payload
        assert payload["delegation_strategy"] in ("self", "subagent", "spawn")

    def test_inputschema_includes_optional_params(self, tmp_path: Path) -> None:
        """analyze_task inputSchema includes optional files and agent_type params."""
        server = _create_server(tmp_path)
        tools = {tool.name: tool for tool in server.list_tools()}
        schema = tools["analyze_task"].inputSchema

        assert "files" in schema["properties"]
        assert "agent_type" in schema["properties"]
        assert schema["required"] == ["prompt"]


class TestFileConflicts:
    """Tests for file conflict detection."""

    def test_detect_no_conflict_when_no_locks(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path)
        server._file_safety_factory = lambda: type(
            "FakeFileSafetyManager",
            (),
            {"list_locks": lambda self: []},
        )()

        report = server._detect_file_conflicts(
            ["synapse/mcp/server.py", "tests/test_mcp_analyze_task.py"]
        )

        assert report == {"locked_by_others": {}, "risk": "none"}

    def test_detect_conflict_when_file_locked_by_other(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path, agent_id="synapse-codex-8120")
        server._file_safety_factory = lambda: type(
            "FakeFileSafetyManager",
            (),
            {
                "list_locks": lambda self: [
                    {
                        "file_path": "synapse/mcp/server.py",
                        "agent_name": "synapse-claude-8101",
                    },
                    {
                        "file_path": "docs/guide.md",
                        "agent_name": "synapse-gemini-8110",
                    },
                ]
            },
        )()

        report = server._detect_file_conflicts(
            ["synapse/mcp/server.py", "tests/test_mcp_analyze_task.py"]
        )

        assert report == {
            "locked_by_others": {"synapse/mcp/server.py": "synapse-claude-8101"},
            "risk": "low",
        }

    def test_high_conflict_forces_spawn_strategy(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path, agent_type="claude")
        server._file_safety_factory = lambda: type(
            "FakeFileSafetyManager",
            (),
            {
                "list_locks": lambda self: [
                    {
                        "file_path": "synapse/mcp/server.py",
                        "agent_name": "synapse-claude-8101",
                    },
                    {
                        "file_path": "tests/test_mcp_analyze_task.py",
                        "agent_name": "synapse-gemini-8110",
                    },
                    {
                        "file_path": "synapse/registry.py",
                        "agent_name": "synapse-opencode-8115",
                    },
                ]
            },
        )()

        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(),
            ):
                payload = server.call_tool(
                    "analyze_task",
                    {
                        "prompt": (
                            "Update synapse/mcp/server.py, synapse/registry.py, "
                            "and tests/test_mcp_analyze_task.py."
                        ),
                        "agent_type": "claude",
                    },
                )

        assert payload["delegation_strategy"] == "spawn"
        assert payload["context"]["file_conflicts"]["risk"] == "high"
        assert payload["warnings"]

    def test_file_paths_extracted_from_prompt(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path)

        paths = server._extract_file_paths_from_prompt(
            "fix synapse/mcp/server.py and tests/test_mcp.py"
        )

        assert paths == ["synapse/mcp/server.py", "tests/test_mcp.py"]


class TestDependencyDetection:
    """Tests for sequential dependency detection."""

    def test_import_dependency_detected(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path)
        (tmp_path / "synapse").mkdir()
        (tmp_path / "synapse" / "registry.py").write_text(
            "class AgentRegistry:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "synapse" / "mcp").mkdir()
        (tmp_path / "synapse" / "mcp" / "server.py").write_text(
            "from synapse.registry import AgentRegistry\n",
            encoding="utf-8",
        )

        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            dependencies = server._detect_dependencies(
                ["synapse/registry.py", "synapse/mcp/server.py"],
            )

        assert dependencies == [
            {
                "from": "synapse/registry.py",
                "to": "synapse/mcp/server.py",
                "reason": "import",
            }
        ]

    def test_naming_convention_ordering(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path)

        dependencies = server._detect_dependencies(
            [
                "db/user_migration.py",
                "services/user_service.py",
                "tests/test_user_service.py",
            ],
        )

        assert dependencies == [
            {
                "from": "db/user_migration.py",
                "to": "services/user_service.py",
                "reason": "naming_convention",
            },
            {
                "from": "services/user_service.py",
                "to": "tests/test_user_service.py",
                "reason": "naming_convention",
            },
        ]

    def test_parallel_tasks_when_no_dependencies(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path, agent_type="claude")

        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(),
            ):
                payload = server.call_tool(
                    "analyze_task",
                    {
                        "prompt": "Update docs/readme.md and scripts/lint.sh.",
                        "files": ["docs/readme.md", "scripts/lint.sh"],
                        "agent_type": "claude",
                    },
                )

        assert payload["context"]["dependencies"] == []
        assert payload["context"]["parallelizable"] is True

    def test_sequential_dependency_forces_self_strategy(self, tmp_path: Path) -> None:
        server = _create_server(tmp_path, agent_type="claude")
        (tmp_path / "synapse").mkdir()
        (tmp_path / "synapse" / "registry.py").write_text(
            "class AgentRegistry:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "synapse" / "mcp").mkdir()
        (tmp_path / "synapse" / "mcp" / "server.py").write_text(
            "from synapse.registry import AgentRegistry\n",
            encoding="utf-8",
        )
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_server.py").write_text(
            "from synapse.mcp.server import SynapseMCPServer\n",
            encoding="utf-8",
        )

        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(),
            ):
                payload = server.call_tool(
                    "analyze_task",
                    {
                        "prompt": (
                            "Update synapse/registry.py, synapse/mcp/server.py, "
                            "and tests/test_server.py."
                        ),
                        "files": [
                            "synapse/registry.py",
                            "synapse/mcp/server.py",
                            "tests/test_server.py",
                        ],
                        "agent_type": "claude",
                    },
                )

        assert payload["context"]["parallelizable"] is False
        assert payload["delegation_strategy"] == "self"


class TestRecommendedWorktree:
    """Tests for recommended_worktree field in analyze_task results."""

    def test_recommended_worktree_true_when_spawn_strategy(
        self, tmp_path: Path
    ) -> None:
        """delegation_strategy=spawn → recommended_worktree=True."""
        server = _create_server(tmp_path, agent_type="claude")
        numstat = "\n".join(f"50\t10\tdir{i}/file{i}.py" for i in range(10))
        status = "\n".join(f" M dir{i}/file{i}.py" for i in range(10))
        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(
                    status_stdout=status, numstat_stdout=numstat
                ),
            ):
                payload = server.call_tool(
                    "analyze_task",
                    {"prompt": "Refactor 10 files across 10 directories"},
                )

        assert payload["delegation_strategy"] == "spawn"
        assert payload["recommended_worktree"] is True

    def test_recommended_worktree_true_when_high_file_conflicts(
        self, tmp_path: Path
    ) -> None:
        """file_conflicts.risk=high → recommended_worktree=True."""
        server = _create_server(tmp_path, agent_type="claude")

        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(),
            ):
                with patch.object(
                    server,
                    "_detect_file_conflicts",
                    return_value={
                        "locked_by_others": {"src/main.py": "synapse-gemini-8110"},
                        "risk": "high",
                    },
                ):
                    payload = server.call_tool(
                        "analyze_task",
                        {
                            "prompt": "Fix bug in src/main.py",
                            "files": ["src/main.py"],
                        },
                    )

        assert payload["context"]["file_conflicts"]["risk"] == "high"
        assert payload["recommended_worktree"] is True

    def test_recommended_worktree_false_when_self_strategy_no_conflicts(
        self, tmp_path: Path
    ) -> None:
        """delegation_strategy=self, no conflicts → recommended_worktree=False."""
        server = _create_server(tmp_path, agent_type="claude")
        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            with patch(
                "synapse.mcp.server.subprocess.run",
                side_effect=_git_run_side_effect(),
            ):
                payload = server.call_tool(
                    "analyze_task",
                    {"prompt": "Fix a typo in README"},
                )

        assert payload["delegation_strategy"] == "self"
        assert payload["recommended_worktree"] is False
