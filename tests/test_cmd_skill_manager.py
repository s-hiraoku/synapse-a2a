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


# ──────────────────────────────────────────────────────────
# SYNAPSE Scope Operations via CLI
# ──────────────────────────────────────────────────────────


class TestSynapseScopeOperations:
    """Tests that CLI commands work correctly with SYNAPSE scope skills."""

    def test_list_shows_synapse_skills_with_synapse_dir(
        self, setup_env, capsys
    ) -> None:
        """synapse_dir must be passed for SYNAPSE skills to appear in list."""
        home, project, synapse = setup_env
        _create_synapse_skill(synapse, "central-tool")
        from synapse.commands.skill_manager import cmd_skills_list

        cmd_skills_list(user_dir=home, project_dir=project, synapse_dir=synapse)
        captured = capsys.readouterr()
        assert "central-tool" in captured.out

    def test_show_synapse_skill(self, setup_env, capsys) -> None:
        """Show details of a SYNAPSE scope skill."""
        home, project, synapse = setup_env
        _create_synapse_skill(synapse, "synapse-viewer")
        from synapse.commands.skill_manager import cmd_skills_show

        cmd_skills_show(
            "synapse-viewer", user_dir=home, project_dir=project, synapse_dir=synapse
        )
        captured = capsys.readouterr()
        assert "synapse-viewer" in captured.out
        assert "Synapse" in captured.out

    def test_delete_synapse_skill(self, setup_env, capsys) -> None:
        """Delete a SYNAPSE scope skill."""
        home, project, synapse = setup_env
        _create_synapse_skill(synapse, "del-central")
        from synapse.commands.skill_manager import cmd_skills_delete

        result = cmd_skills_delete(
            "del-central",
            user_dir=home,
            project_dir=project,
            synapse_dir=synapse,
            force=True,
        )
        assert result is True
        assert not (synapse / "skills" / "del-central").exists()

    def test_move_synapse_skill_reports_error(self, setup_env, capsys) -> None:
        """Moving a SYNAPSE skill should report a read-only error."""
        home, project, synapse = setup_env
        _create_synapse_skill(synapse, "immovable")
        from synapse.commands.skill_manager import cmd_skills_move

        result = cmd_skills_move(
            "immovable",
            target_scope="user",
            user_dir=home,
            project_dir=project,
            synapse_dir=synapse,
        )
        assert result is False
        captured = capsys.readouterr()
        assert (
            "read-only" in captured.out.lower() or "cannot move" in captured.out.lower()
        )


# ──────────────────────────────────────────────────────────
# Scope Validation
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# Manage Skills Deploy Status Display
# ──────────────────────────────────────────────────────────


class TestManageSkillsDisplay:
    """Tests for _build_skill_label and _build_detail_header with agent dir indicators."""

    def test_skill_label_with_agent_dirs(self, tmp_path: Path) -> None:
        """Skill label shows [C✓ A✓ G·] based on which agent dirs exist."""
        home = tmp_path / "home"
        project = tmp_path / "project"
        synapse = tmp_path / "synapse"

        _create_skill(project, ".claude", "proj-tool")
        _create_skill(project, ".agents", "proj-tool")

        from synapse.commands.skill_manager import SkillManagerCommand
        from synapse.skills import SkillScope, discover_skills

        mgr = SkillManagerCommand(
            user_dir=home, project_dir=project, synapse_dir=synapse
        )
        skills = discover_skills(
            project_dir=project, user_dir=home, synapse_dir=synapse
        )
        proj_skills = [s for s in skills if s.scope == SkillScope.PROJECT]
        label = mgr._build_skill_label(proj_skills[0])
        assert "C✓" in label
        assert "A✓" in label
        assert "G·" in label

    def test_skill_label_all_dirs(self, tmp_path: Path) -> None:
        """Skill in all three agent dirs shows [C✓ A✓ G✓]."""
        home = tmp_path / "home"
        project = tmp_path / "project"
        synapse = tmp_path / "synapse"

        _create_skill(project, ".claude", "full-tool")
        _create_skill(project, ".agents", "full-tool")
        _create_skill(project, ".gemini", "full-tool")

        from synapse.commands.skill_manager import SkillManagerCommand
        from synapse.skills import SkillScope, discover_skills

        mgr = SkillManagerCommand(
            user_dir=home, project_dir=project, synapse_dir=synapse
        )
        skills = discover_skills(
            project_dir=project, user_dir=home, synapse_dir=synapse
        )
        proj_skills = [s for s in skills if s.scope == SkillScope.PROJECT]
        label = mgr._build_skill_label(proj_skills[0])
        assert "C✓" in label
        assert "A✓" in label
        assert "G✓" in label

    def test_synapse_skill_label_no_dirs(self, tmp_path: Path) -> None:
        """SYNAPSE skill not deployed anywhere shows [C· A· G·]."""
        home = tmp_path / "home"
        project = tmp_path / "project"
        synapse = tmp_path / "synapse"

        _create_synapse_skill(synapse, "central-only")

        from synapse.commands.skill_manager import SkillManagerCommand
        from synapse.skills import SkillScope, discover_skills

        mgr = SkillManagerCommand(
            user_dir=home, project_dir=project, synapse_dir=synapse
        )
        skills = discover_skills(
            project_dir=project, user_dir=home, synapse_dir=synapse
        )
        synapse_skills = [s for s in skills if s.scope == SkillScope.SYNAPSE]
        label = mgr._build_skill_label(synapse_skills[0])
        assert "C·" in label
        assert "A·" in label
        assert "G·" in label

    def test_scope_menu_excludes_plugin(self, tmp_path: Path) -> None:
        """PLUGIN scope is excluded from scope selection menu."""
        home = tmp_path / "home"
        project = tmp_path / "project"
        synapse = tmp_path / "synapse"

        _create_skill(project, ".claude", "proj-tool")
        plugin_dir = project / "plugins" / "p1" / "skills" / "plug-tool"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "SKILL.md").write_text(
            '---\nname: plug-tool\ndescription: "plugin"\n---\nBody.'
        )

        from synapse.commands.skill_manager import SkillManagerCommand
        from synapse.skills import SkillScope, discover_skills

        mgr = SkillManagerCommand(
            user_dir=home, project_dir=project, synapse_dir=synapse
        )
        all_skills = discover_skills(
            project_dir=project, user_dir=home, synapse_dir=synapse
        )
        skills = [s for s in all_skills if s.scope != SkillScope.PLUGIN]
        items, scopes = mgr._build_scope_menu_items(skills)
        assert SkillScope.PLUGIN not in scopes
        labels = " ".join(items)
        assert "Plugin" not in labels

    def test_detail_header_shows_deploy_status(self, tmp_path: Path) -> None:
        """_build_detail_header shows Deploy Status with per-agent info."""
        home = tmp_path / "home"
        project = tmp_path / "project"
        synapse = tmp_path / "synapse"

        _create_skill(project, ".claude", "detail-tool")
        _create_skill(home, ".claude", "detail-tool")

        from synapse.commands.skill_manager import SkillManagerCommand
        from synapse.skills import SkillScope, discover_skills

        mgr = SkillManagerCommand(
            user_dir=home, project_dir=project, synapse_dir=synapse
        )
        skills = discover_skills(
            project_dir=project, user_dir=home, synapse_dir=synapse
        )
        proj_skills = [s for s in skills if s.scope == SkillScope.PROJECT]
        header = mgr._build_detail_header(proj_skills[0])
        assert "Deploy Status" in header
        assert "claude" in header
        assert "✓" in header

    def test_scope_menu_shows_counts(self, tmp_path: Path) -> None:
        """_build_scope_menu_items returns items with skill counts."""
        home = tmp_path / "home"
        project = tmp_path / "project"
        synapse = tmp_path / "synapse"

        _create_skill(home, ".claude", "user-a")
        _create_skill(project, ".claude", "proj-a")
        _create_skill(project, ".claude", "proj-b")

        from synapse.commands.skill_manager import SkillManagerCommand
        from synapse.skills import discover_skills

        mgr = SkillManagerCommand(
            user_dir=home, project_dir=project, synapse_dir=synapse
        )
        skills = discover_skills(
            project_dir=project, user_dir=home, synapse_dir=synapse
        )
        items, scopes = mgr._build_scope_menu_items(skills)
        # Should have entries for USER (1) and PROJECT (2), plus Back
        labels = " ".join(items)
        assert "User" in labels
        assert "Project" in labels
        assert "(1)" in labels  # 1 user skill
        assert "(2)" in labels  # 2 project skills


class TestScopeValidation:
    """Tests that invalid scope values produce clear error messages."""

    def test_show_invalid_scope(self, setup_env, capsys) -> None:
        """Invalid scope in show prints 'Unknown scope' message."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_show

        cmd_skills_show(
            "user-skill-a", user_dir=home, project_dir=project, scope="bogus"
        )
        captured = capsys.readouterr()
        assert "unknown scope" in captured.out.lower()

    def test_delete_invalid_scope(self, setup_env, capsys) -> None:
        """Invalid scope in delete prints 'Unknown scope' message."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_delete

        result = cmd_skills_delete(
            "user-skill-a",
            user_dir=home,
            project_dir=project,
            scope="bogus",
            force=True,
        )
        assert result is False
        captured = capsys.readouterr()
        assert "unknown scope" in captured.out.lower()

    def test_import_invalid_scope(self, setup_env, capsys) -> None:
        """Invalid scope in import prints 'Unknown scope' message."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_import

        result = cmd_skills_import(
            "user-skill-a",
            from_scope="bogus",
            user_dir=home,
            project_dir=project,
            synapse_dir=synapse,
        )
        assert result is False
        captured = capsys.readouterr()
        assert "unknown scope" in captured.out.lower()


# ──────────────────────────────────────────────────────────
# --dry-run support
# ──────────────────────────────────────────────────────────


class TestDryRun:
    """Tests for --dry-run option on delete and move commands."""

    def test_delete_dry_run(self, setup_env, capsys) -> None:
        """--dry-run shows what would be deleted without actually deleting."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_delete

        result = cmd_skills_delete(
            "user-skill-b",
            user_dir=home,
            project_dir=project,
            force=True,
            dry_run=True,
        )
        assert result is False  # dry_run does not actually delete
        captured = capsys.readouterr()
        assert (
            "dry-run" in captured.out.lower() or "would delete" in captured.out.lower()
        )
        # File should still exist
        assert (home / ".claude" / "skills" / "user-skill-b").exists()

    def test_move_dry_run(self, setup_env, capsys) -> None:
        """--dry-run shows what would be moved without actually moving."""
        home, project, synapse = setup_env
        from synapse.commands.skill_manager import cmd_skills_move

        result = cmd_skills_move(
            "user-skill-b",
            target_scope="project",
            user_dir=home,
            project_dir=project,
            dry_run=True,
        )
        assert result is False  # dry_run does not actually move
        captured = capsys.readouterr()
        assert "dry-run" in captured.out.lower() or "would move" in captured.out.lower()
        # Source should still exist
        assert (home / ".claude" / "skills" / "user-skill-b").exists()
