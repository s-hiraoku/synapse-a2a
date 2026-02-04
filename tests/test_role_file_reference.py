"""Tests for role file reference feature.

Role can be specified as:
- String: --role "Code reviewer"
- File reference: --role @./roles/reviewer.md

When file reference is used:
- File is copied to ~/.a2a/registry/roles/{agent_id}-role.md
- Registry stores "@{copied_path}" as role value
- Reading role detects @ prefix and loads file content
"""

import shutil
from pathlib import Path

import pytest

from synapse.registry import AgentRegistry


@pytest.fixture
def registry():
    """Setup: Use a temp directory for registry."""
    reg = AgentRegistry()
    reg.registry_dir = Path("/tmp/a2a_test_role_file_registry")
    reg.registry_dir.mkdir(parents=True, exist_ok=True)
    yield reg
    # Teardown: Cleanup temp directory
    shutil.rmtree(reg.registry_dir, ignore_errors=True)


@pytest.fixture
def role_file(tmp_path):
    """Create a temporary role file for testing."""
    role_content = """# Code Reviewer Role

You are a code reviewer specializing in:
- Security vulnerabilities
- Performance optimization
- Code style consistency

Always provide constructive feedback.
"""
    role_path = tmp_path / "reviewer-role.md"
    role_path.write_text(role_content, encoding="utf-8")
    return role_path, role_content


# ============================================================================
# Role file reference detection
# ============================================================================


def test_is_role_file_reference():
    """Should detect @ prefix as file reference."""
    from synapse.utils import is_role_file_reference

    assert is_role_file_reference("@./roles/reviewer.md") is True
    assert is_role_file_reference("@/home/user/role.md") is True
    assert is_role_file_reference("@~/roles/role.md") is True
    assert is_role_file_reference("Code reviewer") is False
    assert is_role_file_reference("") is False
    assert is_role_file_reference(None) is False


def test_is_role_file_reference_edge_cases():
    """Should handle edge cases correctly."""
    from synapse.utils import is_role_file_reference

    # @ in the middle is not a file reference
    assert is_role_file_reference("email@example.com") is False
    # Just @ is not valid
    assert is_role_file_reference("@") is False
    # Whitespace after @ is not valid
    assert is_role_file_reference("@ ./file.md") is False


# ============================================================================
# Role file path extraction
# ============================================================================


def test_extract_role_file_path():
    """Should extract file path from @ reference."""
    from synapse.utils import extract_role_file_path

    assert extract_role_file_path("@./roles/reviewer.md") == "./roles/reviewer.md"
    assert extract_role_file_path("@/home/user/role.md") == "/home/user/role.md"
    assert extract_role_file_path("@~/roles/role.md") == "~/roles/role.md"


def test_extract_role_file_path_non_reference():
    """Should return None for non-file-reference strings."""
    from synapse.utils import extract_role_file_path

    assert extract_role_file_path("Code reviewer") is None
    assert extract_role_file_path("") is None
    assert extract_role_file_path(None) is None


# ============================================================================
# Role file resolution and copying
# ============================================================================


def test_resolve_role_with_file_reference(registry, role_file):
    """Should copy file to registry and return @ path."""
    from synapse.utils import resolve_role_value

    role_path, role_content = role_file
    agent_id = "synapse-claude-8100"

    resolved = resolve_role_value(f"@{role_path}", agent_id, registry.registry_dir)

    # Should return @ path pointing to copied file
    assert resolved.startswith("@")
    copied_path = Path(resolved[1:])  # Remove @ prefix

    # File should be copied to registry/roles/
    assert copied_path.parent.name == "roles"
    assert copied_path.name == f"{agent_id}-role.md"
    assert copied_path.exists()

    # Content should match
    assert copied_path.read_text(encoding="utf-8") == role_content


def test_resolve_role_with_string():
    """Should return string as-is when not a file reference."""
    from synapse.utils import resolve_role_value

    resolved = resolve_role_value("Code reviewer", "synapse-claude-8100", Path("/tmp"))
    assert resolved == "Code reviewer"


def test_resolve_role_with_none():
    """Should return None when role is None."""
    from synapse.utils import resolve_role_value

    resolved = resolve_role_value(None, "synapse-claude-8100", Path("/tmp"))
    assert resolved is None


def test_resolve_role_file_not_found(registry):
    """Should raise error when referenced file does not exist."""
    from synapse.utils import RoleFileNotFoundError, resolve_role_value

    with pytest.raises(RoleFileNotFoundError) as exc_info:
        resolve_role_value(
            "@/nonexistent/file.md", "synapse-claude-8100", registry.registry_dir
        )

    assert "not found" in str(exc_info.value).lower()


def test_resolve_role_expands_home_directory(registry, tmp_path):
    """Should expand ~ in file path."""
    from synapse.utils import resolve_role_value

    # Create file in a known location
    role_content = "# Test Role"
    role_path = tmp_path / "test-role.md"
    role_path.write_text(role_content, encoding="utf-8")

    # Use absolute path (simulating expanded ~)
    resolved = resolve_role_value(
        f"@{role_path}", "synapse-claude-8100", registry.registry_dir
    )

    assert resolved.startswith("@")
    copied_path = Path(resolved[1:])
    assert copied_path.exists()


# ============================================================================
# Registry integration
# ============================================================================


def test_register_with_role_file_reference(registry, role_file):
    """Should register agent with role file reference."""
    role_path, role_content = role_file
    agent_id = "synapse-claude-8100"

    # Register with file reference
    registry.register(
        agent_id,
        "claude",
        8100,
        role=f"@{role_path}",
    )

    info = registry.get_agent(agent_id)
    assert info is not None
    # Role should be stored as @ reference
    assert info["role"].startswith("@")

    # Verify file was copied
    copied_path = Path(info["role"][1:])
    assert copied_path.exists()
    assert copied_path.read_text(encoding="utf-8") == role_content


def test_register_with_string_role(registry):
    """Should register agent with string role (backward compatibility)."""
    agent_id = "synapse-claude-8100"

    registry.register(
        agent_id,
        "claude",
        8100,
        role="Code reviewer",
    )

    info = registry.get_agent(agent_id)
    assert info["role"] == "Code reviewer"


# ============================================================================
# Role content reading
# ============================================================================


def test_get_role_content_from_file(registry, role_file):
    """Should read content from role file reference."""
    from synapse.utils import get_role_content

    role_path, role_content = role_file
    agent_id = "synapse-claude-8100"

    # Register with file reference
    registry.register(agent_id, "claude", 8100, role=f"@{role_path}")

    info = registry.get_agent(agent_id)
    content = get_role_content(info["role"])

    assert content == role_content


def test_get_role_content_from_string():
    """Should return string as-is when not a file reference."""
    from synapse.utils import get_role_content

    content = get_role_content("Code reviewer")
    assert content == "Code reviewer"


def test_get_role_content_from_none():
    """Should return None when role is None."""
    from synapse.utils import get_role_content

    content = get_role_content(None)
    assert content is None


def test_get_role_content_missing_file():
    """Should raise error when role file is missing."""
    from synapse.utils import RoleFileNotFoundError, get_role_content

    with pytest.raises(RoleFileNotFoundError):
        get_role_content("@/nonexistent/file.md")


# ============================================================================
# Update role with file reference
# ============================================================================


def test_update_role_with_file_reference(registry, role_file):
    """Should update role with file reference via update_name."""
    role_path, role_content = role_file
    agent_id = "synapse-claude-8100"

    # Register without role
    registry.register(agent_id, "claude", 8100)

    # Update with file reference
    result = registry.update_name(agent_id, None, role=f"@{role_path}")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["role"].startswith("@")

    # Verify file was copied
    copied_path = Path(info["role"][1:])
    assert copied_path.exists()


def test_update_role_from_file_to_string(registry, role_file):
    """Should allow changing from file reference to string."""
    role_path, _ = role_file
    agent_id = "synapse-claude-8100"

    # Register with file reference
    registry.register(agent_id, "claude", 8100, role=f"@{role_path}")

    # Update to string
    result = registry.update_name(agent_id, None, role="New string role")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["role"] == "New string role"


def test_update_role_from_string_to_file(registry, role_file):
    """Should allow changing from string to file reference."""
    role_path, role_content = role_file
    agent_id = "synapse-claude-8100"

    # Register with string role
    registry.register(agent_id, "claude", 8100, role="Original role")

    # Update to file reference
    result = registry.update_name(agent_id, None, role=f"@{role_path}")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["role"].startswith("@")


# ============================================================================
# Edge cases and error handling
# ============================================================================


def test_role_file_with_unicode_content(registry, tmp_path):
    """Should handle role files with unicode content."""
    from synapse.utils import get_role_content

    role_content = """# コードレビュー担当

日本語でのコードレビューを行います。
セキュリティ、パフォーマンス、可読性を重視します。
"""
    role_path = tmp_path / "japanese-role.md"
    role_path.write_text(role_content, encoding="utf-8")

    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, role=f"@{role_path}")

    info = registry.get_agent(agent_id)
    content = get_role_content(info["role"])

    assert content == role_content


def test_role_file_overwrite_on_update(registry, tmp_path):
    """Should overwrite existing role file on update."""
    from synapse.utils import get_role_content

    # Create first role file
    role1_content = "# First Role"
    role1_path = tmp_path / "role1.md"
    role1_path.write_text(role1_content, encoding="utf-8")

    # Create second role file
    role2_content = "# Second Role"
    role2_path = tmp_path / "role2.md"
    role2_path.write_text(role2_content, encoding="utf-8")

    agent_id = "synapse-claude-8100"

    # Register with first file
    registry.register(agent_id, "claude", 8100, role=f"@{role1_path}")
    info = registry.get_agent(agent_id)
    assert get_role_content(info["role"]) == role1_content

    # Update with second file
    registry.update_name(agent_id, None, role=f"@{role2_path}")
    info = registry.get_agent(agent_id)
    assert get_role_content(info["role"]) == role2_content


def test_roles_directory_created_automatically(registry, role_file):
    """Should create roles directory if it doesn't exist."""
    role_path, _ = role_file
    agent_id = "synapse-claude-8100"

    # Ensure roles dir doesn't exist
    roles_dir = registry.registry_dir / "roles"
    if roles_dir.exists():
        shutil.rmtree(roles_dir)

    # Register should create the directory
    registry.register(agent_id, "claude", 8100, role=f"@{role_path}")

    assert roles_dir.exists()
    assert roles_dir.is_dir()


def test_multiple_agents_separate_role_files(registry, tmp_path):
    """Each agent should have its own role file copy."""
    from synapse.utils import get_role_content

    # Create shared role file
    role_content = "# Shared Role"
    role_path = tmp_path / "shared-role.md"
    role_path.write_text(role_content, encoding="utf-8")

    # Register two agents with same role file
    registry.register("synapse-claude-8100", "claude", 8100, role=f"@{role_path}")
    registry.register("synapse-gemini-8110", "gemini", 8110, role=f"@{role_path}")

    info1 = registry.get_agent("synapse-claude-8100")
    info2 = registry.get_agent("synapse-gemini-8110")

    # Each should have its own copy
    path1 = Path(info1["role"][1:])
    path2 = Path(info2["role"][1:])

    assert path1 != path2
    assert path1.name == "synapse-claude-8100-role.md"
    assert path2.name == "synapse-gemini-8110-role.md"

    # Both should have same content
    assert get_role_content(info1["role"]) == role_content
    assert get_role_content(info2["role"]) == role_content


# ============================================================================
# Display helper tests
# ============================================================================


def test_get_role_display_string():
    """Should return string as-is."""
    from synapse.utils import get_role_display

    assert get_role_display("Code reviewer") == "Code reviewer"


def test_get_role_display_file_reference():
    """Should return filename only for file references."""
    from synapse.utils import get_role_display

    assert (
        get_role_display("@/home/user/.a2a/registry/roles/agent-role.md")
        == "@agent-role.md"
    )
    assert get_role_display("@./roles/reviewer.md") == "@reviewer.md"
    assert get_role_display("@~/docs/AGENTS.md") == "@AGENTS.md"


def test_get_role_display_none():
    """Should return None for None input."""
    from synapse.utils import get_role_display

    assert get_role_display(None) is None
