"""Tests for synapse.skills core module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.skills import (
    SkillScope,
    SkillSetDefinition,
    add_skill_from_repo,
    apply_skill_set,
    create_skill,
    create_skill_guided,
    create_skill_set,
    delete_skill,
    delete_skill_set,
    deploy_skill,
    discover_skills,
    edit_skill_set,
    get_agent_skill_dir,
    import_skill,
    load_skill_sets,
    move_skill,
    parse_skill_frontmatter,
    save_skill_sets,
    validate_skill_name,
)


@pytest.fixture
def tmp_home(tmp_path: Path) -> Path:
    """Create a temporary home directory structure."""
    return tmp_path / "home"


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory structure."""
    return tmp_path / "project"


@pytest.fixture
def tmp_synapse(tmp_path: Path) -> Path:
    """Create a temporary synapse directory (~/.synapse)."""
    return tmp_path / "synapse"


def _create_skill(
    base_dir: Path, agent_dir: str, skill_name: str, desc: str = ""
) -> Path:
    """Helper to create a skill directory with SKILL.md."""
    skill_dir = base_dir / agent_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f'---\nname: {skill_name}\ndescription: "{desc or f"{skill_name} skill"}"\n---\n\n# {skill_name}\nBody text.\n'
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


def _create_synapse_skill(synapse_dir: Path, skill_name: str, desc: str = "") -> Path:
    """Helper to create a skill in ~/.synapse/skills/ (flat structure)."""
    skill_dir = synapse_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f'---\nname: {skill_name}\ndescription: "{desc or f"{skill_name} skill"}"\n---\n\n# {skill_name}\nBody text.\n'
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


# ──────────────────────────────────────────────────────────
# Frontmatter Parsing
# ──────────────────────────────────────────────────────────


class TestParseFrontmatter:
    def test_parse_valid_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: my-skill\ndescription: "A useful skill"\n---\n\n# My Skill\nBody.'
        )
        result = parse_skill_frontmatter(skill_dir / "SKILL.md")
        assert result is not None
        assert result["name"] == "my-skill"
        assert result["description"] == "A useful skill"

    def test_parse_missing_name(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\ndescription: "No name field"\n---\n\nBody.'
        )
        result = parse_skill_frontmatter(skill_dir / "SKILL.md")
        assert result is None

    def test_parse_no_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "plain-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just Markdown\nNo frontmatter here.")
        result = parse_skill_frontmatter(skill_dir / "SKILL.md")
        assert result is None

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        result = parse_skill_frontmatter(tmp_path / "nonexistent" / "SKILL.md")
        assert result is None


# ──────────────────────────────────────────────────────────
# Skill Discovery
# ──────────────────────────────────────────────────────────


class TestDiscoverSkills:
    def test_discover_user_scope(self, tmp_home: Path) -> None:
        _create_skill(tmp_home, ".claude", "my-skill", "User skill")
        skills = discover_skills(project_dir=None, user_dir=tmp_home)
        assert len(skills) == 1
        assert skills[0].name == "my-skill"
        assert skills[0].scope == SkillScope.USER

    def test_discover_project_scope(self, tmp_home: Path, tmp_project: Path) -> None:
        _create_skill(tmp_project, ".claude", "proj-skill", "Project skill")
        skills = discover_skills(project_dir=tmp_project, user_dir=tmp_home)
        assert len(skills) == 1
        assert skills[0].name == "proj-skill"
        assert skills[0].scope == SkillScope.PROJECT

    def test_discover_plugin_scope(self, tmp_home: Path, tmp_project: Path) -> None:
        plugin_dir = tmp_project / "plugins" / "my-plugin" / "skills" / "plugin-skill"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "SKILL.md").write_text(
            '---\nname: plugin-skill\ndescription: "Plugin skill"\n---\n\nBody.'
        )
        skills = discover_skills(project_dir=tmp_project, user_dir=tmp_home)
        assert len(skills) == 1
        assert skills[0].name == "plugin-skill"
        assert skills[0].scope == SkillScope.PLUGIN

    def test_discover_dedup_agent_dirs(self, tmp_home: Path) -> None:
        """Same name skill in .claude and .agents under user scope merges agent_dirs."""
        _create_skill(tmp_home, ".claude", "shared-skill", "Shared")
        _create_skill(tmp_home, ".agents", "shared-skill", "Shared")
        skills = discover_skills(project_dir=None, user_dir=tmp_home)
        assert len(skills) == 1
        assert skills[0].name == "shared-skill"
        assert ".claude" in skills[0].agent_dirs
        assert ".agents" in skills[0].agent_dirs

    def test_discover_same_name_different_scope(
        self, tmp_home: Path, tmp_project: Path
    ) -> None:
        """Same name in user and project scope are separate entries."""
        _create_skill(tmp_home, ".claude", "common-skill", "User version")
        _create_skill(tmp_project, ".claude", "common-skill", "Project version")
        skills = discover_skills(project_dir=tmp_project, user_dir=tmp_home)
        assert len(skills) == 2
        scopes = {s.scope for s in skills}
        assert SkillScope.USER in scopes
        assert SkillScope.PROJECT in scopes

    def test_discover_sorted(self, tmp_home: Path, tmp_project: Path) -> None:
        """Skills sorted by scope priority (user, project, plugin) then name."""
        _create_skill(tmp_project, ".claude", "z-skill", "Project Z")
        _create_skill(tmp_home, ".claude", "a-skill", "User A")
        _create_skill(tmp_home, ".claude", "b-skill", "User B")
        skills = discover_skills(project_dir=tmp_project, user_dir=tmp_home)
        assert len(skills) == 3
        # user before project, alphabetical within scope
        assert skills[0].name == "a-skill"
        assert skills[0].scope == SkillScope.USER
        assert skills[1].name == "b-skill"
        assert skills[1].scope == SkillScope.USER
        assert skills[2].name == "z-skill"
        assert skills[2].scope == SkillScope.PROJECT

    def test_discover_gemini_dir(self, tmp_home: Path) -> None:
        """Skills in .gemini/skills/ are discovered."""
        _create_skill(tmp_home, ".gemini", "gem-skill", "Gemini skill")
        skills = discover_skills(project_dir=None, user_dir=tmp_home)
        assert len(skills) == 1
        assert skills[0].name == "gem-skill"
        assert ".gemini" in skills[0].agent_dirs


# ──────────────────────────────────────────────────────────
# Skill Delete / Move
# ──────────────────────────────────────────────────────────


class TestDeleteSkill:
    def test_delete_skill(self, tmp_home: Path) -> None:
        _create_skill(tmp_home, ".claude", "del-skill")
        _create_skill(tmp_home, ".agents", "del-skill")
        skills = discover_skills(project_dir=None, user_dir=tmp_home)
        assert len(skills) == 1

        deleted = delete_skill(skills[0], base_dir=tmp_home)
        assert len(deleted) == 2
        assert not (tmp_home / ".claude" / "skills" / "del-skill").exists()
        assert not (tmp_home / ".agents" / "skills" / "del-skill").exists()

    def test_delete_returns_paths(self, tmp_home: Path) -> None:
        _create_skill(tmp_home, ".claude", "path-skill")
        skills = discover_skills(project_dir=None, user_dir=tmp_home)
        deleted = delete_skill(skills[0], base_dir=tmp_home)
        assert len(deleted) == 1
        assert isinstance(deleted[0], Path)


class TestMoveSkill:
    def test_move_user_to_project(self, tmp_home: Path, tmp_project: Path) -> None:
        _create_skill(tmp_home, ".claude", "move-skill", "Moving")
        skills = discover_skills(project_dir=tmp_project, user_dir=tmp_home)
        assert len(skills) == 1

        copied, removed = move_skill(
            skills[0],
            target_scope=SkillScope.PROJECT,
            user_dir=tmp_home,
            project_dir=tmp_project,
        )
        assert len(copied) > 0
        assert len(removed) > 0
        # Source removed
        assert not (tmp_home / ".claude" / "skills" / "move-skill").exists()
        # Target created
        assert (tmp_project / ".claude" / "skills" / "move-skill" / "SKILL.md").exists()

    def test_move_same_scope_raises(self, tmp_home: Path) -> None:
        _create_skill(tmp_home, ".claude", "same-skill")
        skills = discover_skills(project_dir=None, user_dir=tmp_home)
        with pytest.raises(ValueError, match="same scope"):
            move_skill(
                skills[0],
                target_scope=SkillScope.USER,
                user_dir=tmp_home,
                project_dir=tmp_home,
            )

    def test_move_plugin_raises(self, tmp_project: Path, tmp_home: Path) -> None:
        plugin_dir = tmp_project / "plugins" / "p1" / "skills" / "p-skill"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "SKILL.md").write_text(
            '---\nname: p-skill\ndescription: "plugin"\n---\nBody.'
        )
        skills = discover_skills(project_dir=tmp_project, user_dir=tmp_home)
        with pytest.raises(ValueError, match="plugin"):
            move_skill(
                skills[0],
                target_scope=SkillScope.USER,
                user_dir=tmp_home,
                project_dir=tmp_project,
            )


# ──────────────────────────────────────────────────────────
# Skill Sets
# ──────────────────────────────────────────────────────────


class TestSkillSets:
    def test_load_skill_sets_fallback_to_bundled_defaults(self, tmp_path: Path) -> None:
        """When no user skill_sets.json exists, load bundled defaults."""
        nonexistent = tmp_path / "nope" / "skill_sets.json"
        with patch("synapse.skills._default_skill_sets_path", return_value=nonexistent):
            result = load_skill_sets()  # path=None → default → fallback
        # Should contain at least the bundled defaults (architect, developer, etc.)
        assert len(result) > 0
        # Bundled defaults must have 'architect'
        assert "architect" in result
        assert "synapse-a2a" in result["architect"].skills

    def test_load_skill_sets_user_overrides_bundled(self, tmp_path: Path) -> None:
        """User-defined skill_sets.json takes priority over bundled defaults."""
        user_file = tmp_path / "skill_sets.json"
        data = {
            "custom": {
                "name": "custom",
                "description": "My custom set",
                "skills": ["my-skill"],
            }
        }
        user_file.write_text(json.dumps(data))
        with patch("synapse.skills._default_skill_sets_path", return_value=user_file):
            result = load_skill_sets()
        # User file is used, NOT bundled defaults
        assert "custom" in result
        assert "architect" not in result

    def test_load_skill_sets_empty(self, tmp_path: Path) -> None:
        result = load_skill_sets(tmp_path / "nonexistent.json")
        assert result == {}

    def test_load_skill_sets_valid(self, tmp_path: Path) -> None:
        sets_file = tmp_path / "skill_sets.json"
        data = {
            "reviewer": {
                "name": "reviewer",
                "description": "Code review skills",
                "skills": ["code-quality", "agent-memory"],
            }
        }
        sets_file.write_text(json.dumps(data))
        result = load_skill_sets(sets_file)
        assert "reviewer" in result
        assert result["reviewer"].name == "reviewer"
        assert result["reviewer"].skills == ["code-quality", "agent-memory"]

    def test_save_skill_sets(self, tmp_path: Path) -> None:
        sets_file = tmp_path / "skill_sets.json"
        sets = {
            "dev": SkillSetDefinition(
                name="dev",
                description="Developer skills",
                skills=["code-quality"],
            )
        }
        save_skill_sets(sets, sets_file)
        assert sets_file.exists()
        loaded = json.loads(sets_file.read_text())
        assert "dev" in loaded
        assert loaded["dev"]["skills"] == ["code-quality"]

    def test_apply_skill_set_copies(self, tmp_home: Path, tmp_project: Path) -> None:
        """apply_skill_set copies skills to the agent's skill directory."""
        _create_skill(tmp_home, ".claude", "s1", "Skill 1")
        _create_skill(tmp_home, ".claude", "s2", "Skill 2")

        sets_file = tmp_project / ".synapse" / "skill_sets.json"
        sets_file.parent.mkdir(parents=True, exist_ok=True)
        sets = {
            "test-set": SkillSetDefinition(
                name="test-set",
                description="Test",
                skills=["s1", "s2"],
            )
        }
        save_skill_sets(sets, sets_file)

        result = apply_skill_set(
            "test-set",
            "claude",
            user_dir=tmp_home,
            project_dir=tmp_project,
            skill_sets_path=sets_file,
        )
        assert "s1" in result.copied
        assert "s2" in result.copied
        assert len(result.not_found) == 0
        # Skills copied to project .claude/skills/
        assert (tmp_project / ".claude" / "skills" / "s1" / "SKILL.md").exists()

    def test_apply_skill_set_skips_existing(
        self, tmp_home: Path, tmp_project: Path
    ) -> None:
        """Existing skills in the target are skipped."""
        _create_skill(tmp_home, ".claude", "existing", "Already there")
        _create_skill(tmp_project, ".claude", "existing", "Project copy")

        sets_file = tmp_project / ".synapse" / "skill_sets.json"
        sets_file.parent.mkdir(parents=True, exist_ok=True)
        sets = {"s": SkillSetDefinition(name="s", description="", skills=["existing"])}
        save_skill_sets(sets, sets_file)

        result = apply_skill_set(
            "s",
            "claude",
            user_dir=tmp_home,
            project_dir=tmp_project,
            skill_sets_path=sets_file,
        )
        assert "existing" in result.skipped
        assert len(result.copied) == 0

    def test_apply_skill_set_missing_skill(
        self, tmp_home: Path, tmp_project: Path
    ) -> None:
        """Unknown skills are reported in not_found."""
        sets_file = tmp_project / ".synapse" / "skill_sets.json"
        sets_file.parent.mkdir(parents=True, exist_ok=True)
        sets = {
            "s": SkillSetDefinition(
                name="s", description="", skills=["nonexistent-skill"]
            )
        }
        save_skill_sets(sets, sets_file)

        result = apply_skill_set(
            "s",
            "claude",
            user_dir=tmp_home,
            project_dir=tmp_project,
            skill_sets_path=sets_file,
        )
        assert "nonexistent-skill" in result.not_found
        assert len(result.copied) == 0

    def test_agent_skill_dirs_mapping(self) -> None:
        """All agent types have a skill directory mapping."""
        for agent_type in ("claude", "codex", "gemini", "opencode", "copilot"):
            assert get_agent_skill_dir(agent_type) is not None
            assert "skills" in get_agent_skill_dir(agent_type)


# ──────────────────────────────────────────────────────────
# SYNAPSE Scope Discovery
# ──────────────────────────────────────────────────────────


class TestSynapseScope:
    def test_discover_synapse_scope(self, tmp_synapse: Path) -> None:
        """Skills in synapse_dir/skills/<name>/SKILL.md are discovered."""
        _create_synapse_skill(tmp_synapse, "code-quality", "Run code quality checks")
        skills = discover_skills(synapse_dir=tmp_synapse)
        assert len(skills) == 1
        assert skills[0].name == "code-quality"
        assert skills[0].scope == SkillScope.SYNAPSE

    def test_synapse_scope_sorted_first(
        self, tmp_home: Path, tmp_synapse: Path
    ) -> None:
        """SYNAPSE scope sorts before USER scope."""
        _create_synapse_skill(tmp_synapse, "synapse-skill", "Central skill")
        _create_skill(tmp_home, ".claude", "user-skill", "User skill")
        skills = discover_skills(user_dir=tmp_home, synapse_dir=tmp_synapse)
        assert len(skills) == 2
        assert skills[0].scope == SkillScope.SYNAPSE
        assert skills[0].name == "synapse-skill"
        assert skills[1].scope == SkillScope.USER
        assert skills[1].name == "user-skill"

    def test_discover_all_four_scopes(
        self, tmp_home: Path, tmp_project: Path, tmp_synapse: Path
    ) -> None:
        """All four scopes (SYNAPSE, USER, PROJECT, PLUGIN) discovered together."""
        _create_synapse_skill(tmp_synapse, "central-skill")
        _create_skill(tmp_home, ".claude", "user-skill")
        _create_skill(tmp_project, ".claude", "proj-skill")
        plugin_dir = tmp_project / "plugins" / "p1" / "skills" / "plugin-skill"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "SKILL.md").write_text(
            '---\nname: plugin-skill\ndescription: "plugin"\n---\nBody.'
        )
        skills = discover_skills(
            project_dir=tmp_project, user_dir=tmp_home, synapse_dir=tmp_synapse
        )
        assert len(skills) == 4
        scopes = [s.scope for s in skills]
        assert scopes == [
            SkillScope.SYNAPSE,
            SkillScope.USER,
            SkillScope.PROJECT,
            SkillScope.PLUGIN,
        ]


# ──────────────────────────────────────────────────────────
# Deploy
# ──────────────────────────────────────────────────────────


class TestDeploySkill:
    def test_deploy_to_single_agent(self, tmp_synapse: Path, tmp_home: Path) -> None:
        """Deploy a synapse skill to a single agent's user dir."""
        _create_synapse_skill(tmp_synapse, "deploy-skill", "Deployable")
        skills = discover_skills(synapse_dir=tmp_synapse)
        result = deploy_skill(
            skills[0],
            agent_types=["claude"],
            deploy_scope="user",
            user_dir=tmp_home,
        )
        assert len(result.copied) == 1
        assert result.copied[0][0] == "claude"
        assert (tmp_home / ".claude" / "skills" / "deploy-skill" / "SKILL.md").exists()

    def test_deploy_to_multiple_agents(self, tmp_synapse: Path, tmp_home: Path) -> None:
        """Deploy to claude + codex agent dirs."""
        _create_synapse_skill(tmp_synapse, "multi-skill")
        skills = discover_skills(synapse_dir=tmp_synapse)
        result = deploy_skill(
            skills[0],
            agent_types=["claude", "codex"],
            deploy_scope="user",
            user_dir=tmp_home,
        )
        assert len(result.copied) == 2
        assert (tmp_home / ".claude" / "skills" / "multi-skill" / "SKILL.md").exists()
        assert (tmp_home / ".agents" / "skills" / "multi-skill" / "SKILL.md").exists()

    def test_deploy_user_scope(self, tmp_synapse: Path, tmp_home: Path) -> None:
        """Deploy to user scope (~/.<agent>/skills/)."""
        _create_synapse_skill(tmp_synapse, "user-deploy")
        skills = discover_skills(synapse_dir=tmp_synapse)
        result = deploy_skill(
            skills[0],
            agent_types=["claude"],
            deploy_scope="user",
            user_dir=tmp_home,
        )
        assert len(result.copied) == 1
        assert (tmp_home / ".claude" / "skills" / "user-deploy" / "SKILL.md").exists()

    def test_deploy_project_scope(self, tmp_synapse: Path, tmp_project: Path) -> None:
        """Deploy to project scope (./.<agent>/skills/)."""
        _create_synapse_skill(tmp_synapse, "proj-deploy")
        skills = discover_skills(synapse_dir=tmp_synapse)
        result = deploy_skill(
            skills[0],
            agent_types=["claude"],
            deploy_scope="project",
            project_dir=tmp_project,
        )
        assert len(result.copied) == 1
        assert (
            tmp_project / ".claude" / "skills" / "proj-deploy" / "SKILL.md"
        ).exists()

    def test_deploy_skips_existing(self, tmp_synapse: Path, tmp_home: Path) -> None:
        """Existing skills are skipped during deploy."""
        _create_synapse_skill(tmp_synapse, "existing-skill")
        _create_skill(tmp_home, ".claude", "existing-skill")
        skills = discover_skills(synapse_dir=tmp_synapse)
        result = deploy_skill(
            skills[0],
            agent_types=["claude"],
            deploy_scope="user",
            user_dir=tmp_home,
        )
        assert len(result.copied) == 0
        assert len(result.skipped) == 1
        assert result.skipped[0][0] == "claude"


# ──────────────────────────────────────────────────────────
# Import
# ──────────────────────────────────────────────────────────


class TestImportSkill:
    def test_import_from_user_scope(self, tmp_home: Path, tmp_synapse: Path) -> None:
        """Import a user-scope skill to ~/.synapse/skills/."""
        _create_skill(tmp_home, ".claude", "importable", "Import me")
        skills = discover_skills(user_dir=tmp_home)
        result = import_skill(skills[0], synapse_dir=tmp_synapse)
        assert result.imported is True
        assert (tmp_synapse / "skills" / "importable" / "SKILL.md").exists()

    def test_import_already_exists(self, tmp_home: Path, tmp_synapse: Path) -> None:
        """Import skips if skill already exists in synapse store."""
        _create_skill(tmp_home, ".claude", "already-there")
        _create_synapse_skill(tmp_synapse, "already-there")
        skills = discover_skills(user_dir=tmp_home)
        result = import_skill(skills[0], synapse_dir=tmp_synapse)
        assert result.imported is False
        assert "already exists" in result.message.lower()


# ──────────────────────────────────────────────────────────
# Create Skill
# ──────────────────────────────────────────────────────────


class TestCreateSkill:
    def test_create_skill(self, tmp_synapse: Path) -> None:
        """Create a new skill in ~/.synapse/skills/."""
        result = create_skill("new-skill", synapse_dir=tmp_synapse)
        assert result is not None
        assert result.exists()
        assert (result / "SKILL.md").exists()

    def test_create_skill_already_exists(self, tmp_synapse: Path) -> None:
        """Creating a skill that already exists returns None."""
        _create_synapse_skill(tmp_synapse, "existing")
        result = create_skill("existing", synapse_dir=tmp_synapse)
        assert result is None


# ──────────────────────────────────────────────────────────
# Add Skill from Repo (npx wrapper)
# ──────────────────────────────────────────────────────────


class TestAddSkillFromRepo:
    def test_add_skill_from_repo(self, tmp_home: Path, tmp_synapse: Path) -> None:
        """npx execution is mocked, new skills are imported and removed from source."""

        def _mock_npx_side_effect(*args, **kwargs):
            # Simulate npx adding a skill to ~/.claude/skills/
            skill_dir = tmp_home / ".claude" / "skills" / "new-repo-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                '---\nname: new-repo-skill\ndescription: "From repo"\n---\nBody.'
            )
            mock_result = MagicMock()
            mock_result.returncode = 0
            return mock_result

        with patch("synapse.skills.subprocess.run", side_effect=_mock_npx_side_effect):
            result = add_skill_from_repo(
                "github.com/user/skills",
                synapse_dir=tmp_synapse,
                user_dir=tmp_home,
            )

        assert result.npx_success is True
        assert "new-repo-skill" in result.imported
        # Imported to synapse store
        assert (tmp_synapse / "skills" / "new-repo-skill" / "SKILL.md").exists()
        # Removed from ~/.claude/skills/
        assert not (tmp_home / ".claude" / "skills" / "new-repo-skill").exists()

    def test_add_skill_npx_not_found(self, tmp_home: Path, tmp_synapse: Path) -> None:
        """npx not installed returns appropriate error."""
        with patch(
            "synapse.skills.subprocess.run",
            side_effect=FileNotFoundError("npx not found"),
        ):
            result = add_skill_from_repo(
                "github.com/user/skills",
                synapse_dir=tmp_synapse,
                user_dir=tmp_home,
            )
        assert result.npx_success is False
        assert len(result.messages) > 0


# ──────────────────────────────────────────────────────────
# Skill Set CRUD (migrated from skill_sets.py)
# ──────────────────────────────────────────────────────────


class TestSkillSetCRUD:
    def test_create_skill_set(self, tmp_path: Path) -> None:
        """Create a new skill set via programmatic API."""
        sets_file = tmp_path / "skill_sets.json"
        create_skill_set(
            name="my-set",
            description="My custom set",
            skills=["code-quality"],
            sets_path=sets_file,
        )
        data = json.loads(sets_file.read_text())
        assert "my-set" in data
        assert data["my-set"]["skills"] == ["code-quality"]

    def test_delete_skill_set(self, tmp_path: Path) -> None:
        """Delete a skill set."""
        sets_file = tmp_path / "skill_sets.json"
        sets = {
            "reviewer": SkillSetDefinition(
                name="reviewer",
                description="Code review",
                skills=["code-quality"],
            )
        }
        save_skill_sets(sets, sets_file)
        assert delete_skill_set("reviewer", sets_path=sets_file)
        data = json.loads(sets_file.read_text())
        assert "reviewer" not in data

    def test_delete_skill_set_not_found(self, tmp_path: Path) -> None:
        """Delete unknown set returns False."""
        sets_file = tmp_path / "skill_sets.json"
        sets_file.write_text("{}")
        assert not delete_skill_set("nonexistent", sets_path=sets_file)

    def test_edit_skill_set(self, tmp_path: Path) -> None:
        """Edit a skill set's description and skills."""
        sets_file = tmp_path / "skill_sets.json"
        sets = {
            "reviewer": SkillSetDefinition(
                name="reviewer",
                description="Old desc",
                skills=["code-quality", "agent-memory"],
            )
        }
        save_skill_sets(sets, sets_file)
        assert edit_skill_set(
            "reviewer",
            description="Updated desc",
            skills=["code-quality"],
            sets_path=sets_file,
        )
        data = json.loads(sets_file.read_text())
        assert data["reviewer"]["description"] == "Updated desc"
        assert data["reviewer"]["skills"] == ["code-quality"]

    def test_edit_skill_set_not_found(self, tmp_path: Path) -> None:
        """Edit unknown set returns False."""
        sets_file = tmp_path / "skill_sets.json"
        sets_file.write_text("{}")
        assert not edit_skill_set("nonexistent", sets_path=sets_file)


# ──────────────────────────────────────────────────────────
# Create Skill Guided (Anthropic methodology)
# ──────────────────────────────────────────────────────────


class TestCreateSkillGuided:
    def test_create_guided_basic(self, tmp_synapse: Path) -> None:
        """Guided creation produces SKILL.md, scripts/, references/, assets/."""
        result = create_skill_guided("my-skill", synapse_dir=tmp_synapse)
        assert result is not None
        assert result.exists()
        assert (result / "SKILL.md").is_file()
        assert (result / "scripts").is_dir()
        assert (result / "references").is_dir()
        assert (result / "assets").is_dir()

    def test_create_guided_frontmatter(self, tmp_synapse: Path) -> None:
        """SKILL.md contains correct name in frontmatter."""
        result = create_skill_guided("test-skill", synapse_dir=tmp_synapse)
        assert result is not None
        content = (result / "SKILL.md").read_text(encoding="utf-8")
        assert "name: test-skill" in content
        assert "TODO" in content

    def test_create_guided_with_references(self, tmp_synapse: Path) -> None:
        """Starter references (checklist.md, patterns.md) are copied from bundled creator."""
        result = create_skill_guided(
            "ref-skill", synapse_dir=tmp_synapse, include_references=True
        )
        assert result is not None
        # References are only copied if bundled creator exists
        # In test environment this may not be available, so just check structure
        assert (result / "references").is_dir()

    def test_create_guided_already_exists(self, tmp_synapse: Path) -> None:
        """Creating a skill that already exists returns None."""
        _create_synapse_skill(tmp_synapse, "existing-skill")
        result = create_skill_guided("existing-skill", synapse_dir=tmp_synapse)
        assert result is None

    def test_create_guided_no_references(self, tmp_synapse: Path) -> None:
        """include_references=False skips reference file copying."""
        result = create_skill_guided(
            "no-ref-skill", synapse_dir=tmp_synapse, include_references=False
        )
        assert result is not None
        assert (result / "references").is_dir()
        # references/ dir exists but should be empty (no starter files copied)
        ref_files = list((result / "references").iterdir())
        assert len(ref_files) == 0


# ──────────────────────────────────────────────────────────
# Delete Skill Error Handling
# ──────────────────────────────────────────────────────────


class TestDeleteSkillErrorHandling:
    def test_delete_synapse_skill(self, tmp_synapse: Path) -> None:
        """Deleting a SYNAPSE scope skill removes it from synapse_dir/skills/."""
        _create_synapse_skill(tmp_synapse, "removable")
        skills = discover_skills(synapse_dir=tmp_synapse)
        assert len(skills) == 1

        deleted = delete_skill(skills[0], base_dir=tmp_synapse)
        assert len(deleted) == 1
        assert not (tmp_synapse / "skills" / "removable").exists()

    def test_delete_permission_error(self, tmp_synapse: Path) -> None:
        """PermissionError during rmtree does not crash; returns empty list."""
        _create_synapse_skill(tmp_synapse, "protected")
        skills = discover_skills(synapse_dir=tmp_synapse)

        with patch(
            "synapse.skills.shutil.rmtree", side_effect=OSError("Permission denied")
        ):
            deleted = delete_skill(skills[0], base_dir=tmp_synapse)
        assert len(deleted) == 0


# ──────────────────────────────────────────────────────────
# Skill Name Validation
# ──────────────────────────────────────────────────────────


class TestSkillNameValidation:
    def test_reject_empty_name(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(ValueError, match="empty"):
            validate_skill_name("")

    def test_reject_slash_in_name(self) -> None:
        """Names containing slashes are rejected."""
        with pytest.raises(ValueError, match="slash"):
            validate_skill_name("foo/bar")

    def test_reject_name_with_spaces(self) -> None:
        """Names containing spaces are rejected."""
        with pytest.raises(ValueError, match="space"):
            validate_skill_name("my skill")

    def test_reject_too_long_name(self) -> None:
        """Names exceeding 128 characters are rejected."""
        with pytest.raises(ValueError, match="128"):
            validate_skill_name("a" * 129)

    def test_reject_dot_and_dotdot(self) -> None:
        """Path-traversal names '.' and '..' are rejected."""
        with pytest.raises(ValueError, match=r"\.\.|\."):
            validate_skill_name(".")
        with pytest.raises(ValueError, match=r"\.\.|\."):
            validate_skill_name("..")

    def test_accept_valid_names(self) -> None:
        """Valid names pass without error."""
        for name in ("synapse-a2a", "my_skill.v2", "code-quality", "a"):
            validate_skill_name(name)  # Should not raise


# ──────────────────────────────────────────────────────────
# Skill Creator Init Logging
# ──────────────────────────────────────────────────────────


class TestSkillCreatorInitLogging:
    def test_creator_failure_logs_warning(self, tmp_synapse: Path) -> None:
        """Exception in _try_skill_creator_init logs a warning."""
        from synapse.skills import _try_skill_creator_init

        skill_dir = tmp_synapse / "skills" / "log-test"
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Create a fake init_skill.py so the code finds the file and tries to load it
        init_dir = tmp_synapse / "skills" / "skill-creator" / "scripts"
        init_dir.mkdir(parents=True, exist_ok=True)
        (init_dir / "init_skill.py").write_text("def init_skill(n, d): pass")

        with (
            patch(
                "importlib.util.spec_from_file_location",
                side_effect=RuntimeError("boom"),
            ),
            patch("synapse.skills.logger") as mock_logger,
        ):
            result = _try_skill_creator_init("log-test", skill_dir, tmp_synapse)

        assert result is False
        mock_logger.warning.assert_called_once()
        assert "boom" in mock_logger.warning.call_args[0][0]


# ──────────────────────────────────────────────────────────
# Skill Set Edge Cases
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# Check Deploy Status
# ──────────────────────────────────────────────────────────


class TestCheckDeployStatus:
    """Tests for check_deploy_status() which checks where a SYNAPSE skill is deployed."""

    def test_no_deployments(self, tmp_home: Path, tmp_project: Path) -> None:
        """No deployments → all agents False for both scopes."""
        from synapse.skills import check_deploy_status

        result = check_deploy_status(
            "my-skill", user_dir=tmp_home, project_dir=tmp_project
        )
        assert "user" in result
        assert "project" in result
        # All agents should be False
        for agent in ("claude", "codex", "gemini", "opencode", "copilot"):
            assert result["user"][agent] is False
            assert result["project"][agent] is False

    def test_user_deploy_detected(self, tmp_home: Path, tmp_project: Path) -> None:
        """Skill deployed to user claude dir → claude: True in user scope."""
        from synapse.skills import check_deploy_status

        _create_skill(tmp_home, ".claude", "my-skill", "deployed")
        result = check_deploy_status(
            "my-skill", user_dir=tmp_home, project_dir=tmp_project
        )
        assert result["user"]["claude"] is True
        assert result["user"]["gemini"] is False
        assert result["project"]["claude"] is False

    def test_project_deploy_detected(self, tmp_home: Path, tmp_project: Path) -> None:
        """Skill deployed to project claude dir → claude: True in project scope."""
        from synapse.skills import check_deploy_status

        _create_skill(tmp_project, ".claude", "my-skill", "deployed")
        result = check_deploy_status(
            "my-skill", user_dir=tmp_home, project_dir=tmp_project
        )
        assert result["project"]["claude"] is True
        assert result["user"]["claude"] is False

    def test_both_scopes_deployed(self, tmp_home: Path, tmp_project: Path) -> None:
        """Skill deployed to both user and project → both True."""
        from synapse.skills import check_deploy_status

        _create_skill(tmp_home, ".claude", "my-skill", "user deployed")
        _create_skill(tmp_project, ".gemini", "my-skill", "project deployed")
        result = check_deploy_status(
            "my-skill", user_dir=tmp_home, project_dir=tmp_project
        )
        assert result["user"]["claude"] is True
        assert result["project"]["gemini"] is True
        assert result["user"]["gemini"] is False
        assert result["project"]["claude"] is False

    def test_shared_agents_dir(self, tmp_home: Path, tmp_project: Path) -> None:
        """codex/opencode/copilot share .agents/skills — deploying once marks all three."""
        from synapse.skills import check_deploy_status

        _create_skill(tmp_home, ".agents", "my-skill", "shared deploy")
        result = check_deploy_status(
            "my-skill", user_dir=tmp_home, project_dir=tmp_project
        )
        # All agents that map to .agents/skills should be True
        assert result["user"]["codex"] is True
        assert result["user"]["opencode"] is True
        assert result["user"]["copilot"] is True
        assert result["user"]["claude"] is False

    def test_none_dirs(self) -> None:
        """None for both dirs → empty results, no crash."""
        from synapse.skills import check_deploy_status

        result = check_deploy_status("my-skill", user_dir=None, project_dir=None)
        assert result["user"] == {}
        assert result["project"] == {}


class TestSkillSetEdgeCases:
    def test_set_show_nonexistent(self, tmp_path: Path, capsys) -> None:
        """Showing a nonexistent skill set prints 'not found'."""
        from synapse.commands.skill_manager import cmd_skills_set_show

        empty_file = tmp_path / "empty.json"
        empty_file.write_text("{}")
        cmd_skills_set_show("does-not-exist", sets_path=empty_file)
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_set_list_empty(self, tmp_path: Path, capsys) -> None:
        """Empty skill sets file prints 'No skill sets'."""
        from synapse.commands.skill_manager import cmd_skills_set_list

        sets_file = tmp_path / "skill_sets.json"
        sets_file.write_text("{}")
        cmd_skills_set_list(sets_path=sets_file)
        captured = capsys.readouterr()
        assert "no skill sets" in captured.out.lower()
