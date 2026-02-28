"""Tests for `synapse skills apply <target> <set_name>` command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.skills import SkillSetDefinition, save_skill_sets


def _create_skill(base_dir: Path, agent_dir: str, skill_name: str) -> None:
    """Create a minimal skill in the given agent directory."""
    skill_dir = base_dir / agent_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: {skill_name}\ndescription: "{skill_name} desc"\n---\nBody.'
    )


def _register_agent(
    registry_dir: Path,
    agent_id: str,
    agent_type: str,
    port: int,
    name: str | None = None,
    working_dir: str | None = None,
) -> None:
    """Write a minimal agent registry JSON file."""
    registry_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "port": port,
        "pid": 12345,
        "working_dir": working_dir or str(Path.cwd()),
    }
    if name:
        data["name"] = name
    (registry_dir / f"{agent_id}.json").write_text(json.dumps(data))


@pytest.fixture
def setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up environment with skills, skill sets, and a fake registry."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    synapse = tmp_path / "synapse"
    registry = tmp_path / "registry"

    # Point AgentRegistry to our temp dir
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(registry))

    # Create skills that belong to the "developer" skill set
    _create_skill(project, "plugins/myplugin", "synapse-a2a")
    _create_skill(project, "plugins/myplugin", "code-review")

    # Create a skill set definition
    sets_file = project / ".synapse" / "skill_sets.json"
    sets_file.parent.mkdir(parents=True, exist_ok=True)
    sets = {
        "developer": SkillSetDefinition(
            name="developer",
            description="Developer skills",
            skills=["synapse-a2a", "code-review"],
        ),
    }
    save_skill_sets(sets, sets_file)

    # Register a running agent
    _register_agent(
        registry,
        agent_id="synapse-claude-8100",
        agent_type="claude",
        port=8100,
        name="chouun",
        working_dir=str(project),
    )

    return home, project, synapse, registry, sets_file


class TestSkillsApplyHappyPath:
    """Normal case: apply skill set to a running agent."""

    def test_apply_copies_skills_and_updates_registry(self, setup_env, capsys) -> None:
        """Copies skill files, updates registry, sends A2A message."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        with patch(
            "synapse.commands.skill_manager._send_skill_set_message"
        ) as mock_send:
            mock_send.return_value = True
            result = cmd_skills_apply(
                target="chouun",
                set_name="developer",
                project_dir=project,
                user_dir=home,
                skill_sets_path=sets_file,
                synapse_dir=synapse,
            )

        assert result is True
        captured = capsys.readouterr()
        assert "developer" in captured.out
        # Skills should be copied to agent's skill directory
        assert (project / ".claude" / "skills" / "synapse-a2a").exists()
        assert (project / ".claude" / "skills" / "code-review").exists()

    def test_apply_updates_registry_skill_set(self, setup_env, capsys) -> None:
        """Registry file should be updated with the new skill set name."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        with patch(
            "synapse.commands.skill_manager._send_skill_set_message"
        ) as mock_send:
            mock_send.return_value = True
            cmd_skills_apply(
                target="chouun",
                set_name="developer",
                project_dir=project,
                user_dir=home,
                skill_sets_path=sets_file,
                synapse_dir=synapse,
            )

        # Check registry was updated
        reg_file = registry / "synapse-claude-8100.json"
        data = json.loads(reg_file.read_text())
        assert data["skill_set"] == "developer"

    def test_apply_sends_a2a_message(self, setup_env, capsys) -> None:
        """A2A message should be sent to the agent with skill set info."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        with patch(
            "synapse.commands.skill_manager._send_skill_set_message"
        ) as mock_send:
            mock_send.return_value = True
            cmd_skills_apply(
                target="chouun",
                set_name="developer",
                project_dir=project,
                user_dir=home,
                skill_sets_path=sets_file,
                synapse_dir=synapse,
            )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[1]["target"] == "synapse-claude-8100"
        assert "developer" in call_args[1]["message"]


class TestSkillsApplyPartialFailure:
    """Partial failure: registry or send fails → returns False."""

    def test_returns_false_when_registry_update_fails(self, setup_env, capsys) -> None:
        """cmd_skills_apply should return False when registry update fails."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        with (
            patch(
                "synapse.commands.skill_manager._send_skill_set_message"
            ) as mock_send,
            patch(
                "synapse.registry.AgentRegistry.update_skill_set",
                return_value=False,
            ),
        ):
            mock_send.return_value = True
            result = cmd_skills_apply(
                target="chouun",
                set_name="developer",
                project_dir=project,
                user_dir=home,
                skill_sets_path=sets_file,
                synapse_dir=synapse,
            )

        assert result is False
        captured = capsys.readouterr()
        assert "partially applied" in captured.out.lower()

    def test_returns_false_when_send_fails(self, setup_env, capsys) -> None:
        """cmd_skills_apply should return False when A2A send fails."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        with patch(
            "synapse.commands.skill_manager._send_skill_set_message"
        ) as mock_send:
            mock_send.return_value = False
            result = cmd_skills_apply(
                target="chouun",
                set_name="developer",
                project_dir=project,
                user_dir=home,
                skill_sets_path=sets_file,
                synapse_dir=synapse,
            )

        assert result is False
        captured = capsys.readouterr()
        assert "partially applied" in captured.out.lower()


class TestSkillsApplyErrors:
    """Error cases."""

    def test_nonexistent_skill_set(self, setup_env, capsys) -> None:
        """Non-existent skill set name should produce an error."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        result = cmd_skills_apply(
            target="chouun",
            set_name="nonexistent",
            project_dir=project,
            user_dir=home,
            skill_sets_path=sets_file,
            synapse_dir=synapse,
        )

        assert result is False
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_nonexistent_agent(self, setup_env, capsys) -> None:
        """Non-existent agent target should produce an error."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        result = cmd_skills_apply(
            target="no-such-agent",
            set_name="developer",
            project_dir=project,
            user_dir=home,
            skill_sets_path=sets_file,
            synapse_dir=synapse,
        )

        assert result is False
        captured = capsys.readouterr()
        assert "no agent found" in captured.out.lower()


class TestSkillsApplyDryRun:
    """--dry-run option: preview only, no changes."""

    def test_dry_run_does_not_copy_skills(self, setup_env, capsys) -> None:
        """Skills should NOT be copied in dry-run mode."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        result = cmd_skills_apply(
            target="chouun",
            set_name="developer",
            project_dir=project,
            user_dir=home,
            skill_sets_path=sets_file,
            synapse_dir=synapse,
            dry_run=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "dry run" in captured.out.lower()
        # Skills should NOT have been copied
        assert not (project / ".claude" / "skills" / "synapse-a2a").exists()

    def test_dry_run_does_not_update_registry(self, setup_env, capsys) -> None:
        """Registry should NOT be updated in dry-run mode."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        cmd_skills_apply(
            target="chouun",
            set_name="developer",
            project_dir=project,
            user_dir=home,
            skill_sets_path=sets_file,
            synapse_dir=synapse,
            dry_run=True,
        )

        # Registry should NOT have skill_set key
        reg_file = registry / "synapse-claude-8100.json"
        data = json.loads(reg_file.read_text())
        assert "skill_set" not in data

    def test_dry_run_does_not_send_message(self, setup_env, capsys) -> None:
        """No A2A message should be sent in dry-run mode."""
        home, project, synapse, registry, sets_file = setup_env

        from synapse.commands.skill_manager import cmd_skills_apply

        with patch(
            "synapse.commands.skill_manager._send_skill_set_message"
        ) as mock_send:
            cmd_skills_apply(
                target="chouun",
                set_name="developer",
                project_dir=project,
                user_dir=home,
                skill_sets_path=sets_file,
                synapse_dir=synapse,
                dry_run=True,
            )

        mock_send.assert_not_called()
