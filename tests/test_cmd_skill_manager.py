"""Tests for synapse/commands/skill_manager.py - Skill Manager TUI command."""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse.skills import SkillSetDefinition, save_skill_sets


def _create_skill(base_dir: Path, agent_dir: str, skill_name: str) -> None:
    skill_dir = base_dir / agent_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: {skill_name}\ndescription: "{skill_name} desc"\n---\nBody.'
    )


def _create_synapse_skill(synapse_dir: Path, skill_name: str) -> None:
    skill_dir = synapse_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: {skill_name}\ndescription: "{skill_name} desc"\n---\nBody.'
    )


@pytest.fixture
def setup_env(tmp_path: Path):
    """Set up environment with skills in various scopes."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    synapse = tmp_path / "synapse"
    _create_skill(home, ".claude", "user-skill-a")
    _create_skill(home, ".claude", "user-skill-b")
    _create_skill(home, ".agents", "user-skill-a")  # dedup with .claude
    _create_skill(project, ".claude", "proj-skill")

    # Plugin skill
    plugin_dir = project / "plugins" / "myplugin" / "skills" / "plugin-skill"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "SKILL.md").write_text(
        '---\nname: plugin-skill\ndescription: "plugin desc"\n---\nBody.'
    )

    return home, project, synapse


class TestSkillManagerListSkills:
    def test_manager_list_skills(self, setup_env, capsys) -> None:
        """List all skills across scopes."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_list

        cmd_skills_list(user_dir=home, project_dir=project)
        captured = capsys.readouterr()
        assert "user-skill-a" in captured.out
        assert "user-skill-b" in captured.out
        assert "proj-skill" in captured.out
        assert "plugin-skill" in captured.out

    def test_manager_scope_filter(self, setup_env, capsys) -> None:
        """Filter skills by scope."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_list

        cmd_skills_list(user_dir=home, project_dir=project, scope_filter="user")
        captured = capsys.readouterr()
        assert "user-skill-a" in captured.out
        assert "proj-skill" not in captured.out

    def test_manager_show_detail(self, setup_env, capsys) -> None:
        """Show details of a specific skill."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_show

        cmd_skills_show("user-skill-a", user_dir=home, project_dir=project)
        captured = capsys.readouterr()
        assert "user-skill-a" in captured.out
        assert "user" in captured.out.lower()

    def test_manager_show_not_found(self, setup_env, capsys) -> None:
        """Show unknown skill reports error."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_show

        cmd_skills_show("nonexistent", user_dir=home, project_dir=project)
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_list_includes_synapse_scope(self, setup_env, capsys) -> None:
        """Synapse scope skills show in list output."""
        home, project, synapse = setup_env
        _create_synapse_skill(synapse, "central-skill")
        from synapse.commands.skill_manager import cmd_skills_list

        cmd_skills_list(user_dir=home, project_dir=project, synapse_dir=synapse)
        captured = capsys.readouterr()
        assert "central-skill" in captured.out
        assert "Synapse" in captured.out


class TestSkillManagerDelete:
    def test_manager_delete(self, setup_env, capsys) -> None:
        """Delete a user skill."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_delete

        result = cmd_skills_delete(
            "user-skill-b", user_dir=home, project_dir=project, force=True
        )
        assert result is True
        assert not (home / ".claude" / "skills" / "user-skill-b").exists()

    def test_plugin_no_delete(self, setup_env, capsys) -> None:
        """Plugin skills cannot be deleted."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_delete

        result = cmd_skills_delete(
            "plugin-skill", user_dir=home, project_dir=project, force=True
        )
        assert result is False
        captured = capsys.readouterr()
        assert "plugin" in captured.out.lower() or "read-only" in captured.out.lower()


class TestSkillManagerMove:
    def test_manager_move(self, setup_env, capsys) -> None:
        """Move a skill from user to project scope."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_move

        result = cmd_skills_move(
            "user-skill-b",
            target_scope="project",
            user_dir=home,
            project_dir=project,
        )
        assert result is True
        # Source removed
        assert not (home / ".claude" / "skills" / "user-skill-b").exists()
        # Target created
        assert (project / ".claude" / "skills" / "user-skill-b" / "SKILL.md").exists()


class TestSkillManagerDeploy:
    def test_cmd_skills_deploy(self, setup_env, capsys) -> None:
        """Deploy a synapse skill to agent dir."""
        home, project, synapse = setup_env
        _create_synapse_skill(synapse, "deploy-test")
        from synapse.commands.skill_manager import cmd_skills_deploy

        result = cmd_skills_deploy(
            "deploy-test",
            agents=["claude"],
            scope="user",
            user_dir=home,
            project_dir=project,
            synapse_dir=synapse,
        )
        assert result is True
        assert (home / ".claude" / "skills" / "deploy-test" / "SKILL.md").exists()


class TestSkillManagerImport:
    def test_cmd_skills_import(self, setup_env, capsys) -> None:
        """Import a user-scope skill to synapse store."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_import

        result = cmd_skills_import(
            "user-skill-a",
            from_scope="user",
            user_dir=home,
            project_dir=project,
            synapse_dir=synapse,
        )
        assert result is True
        assert (synapse / "skills" / "user-skill-a" / "SKILL.md").exists()


class TestSkillManagerCreate:
    def test_cmd_skills_create(self, setup_env, capsys) -> None:
        """Create a new skill in synapse store."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_create

        result = cmd_skills_create(
            name="new-skill",
            synapse_dir=synapse,
        )
        assert result is True
        assert (synapse / "skills" / "new-skill" / "SKILL.md").exists()


class TestSkillManagerCreateGuided:
    def test_cmd_skills_create_guided_shows_guidance(self, setup_env, capsys) -> None:
        """cmd_skills_create_guided prints anthropic-skill-creator guidance."""
        from synapse.commands.skill_manager import cmd_skills_create_guided

        cmd_skills_create_guided()
        captured = capsys.readouterr()
        # Should mention the skill to invoke
        assert "anthropic-skill-creator" in captured.out
        # Should show deploy command
        assert "synapse skills deploy" in captured.out
        # Should show agent start command
        assert "synapse claude" in captured.out


class TestSkillManagerSetCommands:
    def test_cmd_skills_set_list(self, setup_env, capsys) -> None:
        """List skill sets."""
        home, project, synapse = setup_env
        sets_file = project / ".synapse" / "skill_sets.json"
        sets_file.parent.mkdir(parents=True, exist_ok=True)
        sets = {
            "reviewer": SkillSetDefinition(
                name="reviewer",
                description="Code review skills",
                skills=["user-skill-a"],
            )
        }
        save_skill_sets(sets, sets_file)

        from synapse.commands.skill_manager import cmd_skills_set_list

        cmd_skills_set_list(sets_path=sets_file)
        captured = capsys.readouterr()
        assert "reviewer" in captured.out
        assert "Code review skills" in captured.out

    def test_cmd_skills_set_show(self, setup_env, capsys) -> None:
        """Show skill set details."""
        home, project, synapse = setup_env
        sets_file = project / ".synapse" / "skill_sets.json"
        sets_file.parent.mkdir(parents=True, exist_ok=True)
        sets = {
            "reviewer": SkillSetDefinition(
                name="reviewer",
                description="Code review skills",
                skills=["user-skill-a", "user-skill-b"],
            )
        }
        save_skill_sets(sets, sets_file)

        from synapse.commands.skill_manager import cmd_skills_set_show

        cmd_skills_set_show("reviewer", sets_path=sets_file)
        captured = capsys.readouterr()
        assert "reviewer" in captured.out
        assert "user-skill-a" in captured.out
        assert "user-skill-b" in captured.out
