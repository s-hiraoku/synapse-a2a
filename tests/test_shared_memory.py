"""Tests for Shared Memory — Cross-Agent Knowledge Sharing.

Test-first development: these tests define the expected behavior
for the SharedMemory class before implementation.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

# ============================================================
# TestSharedMemoryInit - Database initialization
# ============================================================


class TestSharedMemoryInit:
    """Tests for SharedMemory database initialization."""

    @pytest.fixture
    def memory(self, tmp_path):
        """Create a SharedMemory instance."""
        from synapse.shared_memory import SharedMemory

        db_path = str(tmp_path / "memory.db")
        return SharedMemory(db_path=db_path)

    def test_init_creates_db(self, memory):
        """Database file should be created on init."""
        assert os.path.exists(memory.db_path)

    def test_memories_table_exists(self, memory):
        """memories table should exist."""
        conn = sqlite3.connect(memory.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_indexes_exist(self, memory):
        """Key and author indexes should exist."""
        conn = sqlite3.connect(memory.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        index_names = {row[0] for row in cursor.fetchall()}
        assert "idx_memory_key" in index_names
        assert "idx_memory_author" in index_names
        conn.close()

    def test_wal_mode(self, memory):
        """Database should use WAL journal mode."""
        conn = sqlite3.connect(memory.db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        conn.close()

    def test_init_migrates_legacy_db_scope_and_working_dir_columns(self, tmp_path):
        """Legacy DBs should gain scope and working_dir columns on init."""
        db_path = tmp_path / "legacy_memory.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE memories (
                id         TEXT PRIMARY KEY,
                key        TEXT NOT NULL UNIQUE,
                content    TEXT NOT NULL,
                author     TEXT NOT NULL,
                tags       TEXT DEFAULT '[]',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO memories (id, key, content, author, tags)
            VALUES ('legacy-id', 'legacy-key', 'Legacy content', 'legacy-author', '[]')
            """
        )
        conn.commit()
        conn.close()

        from synapse.shared_memory import SharedMemory

        memory = SharedMemory(db_path=str(db_path))

        conn = sqlite3.connect(memory.db_path)
        columns = {
            row[1]: row
            for row in conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        conn.close()

        assert "scope" in columns
        assert "working_dir" in columns

        result = memory.get("legacy-key")
        assert result is not None
        assert result["scope"] == "global"
        assert result["working_dir"] is None

    def test_from_env(self, tmp_path, monkeypatch):
        """from_env should read SYNAPSE_SHARED_MEMORY_* env vars."""
        from synapse.shared_memory import SharedMemory

        db_path = str(tmp_path / "env_memory.db")
        monkeypatch.setenv("SYNAPSE_SHARED_MEMORY_DB_PATH", db_path)
        monkeypatch.setenv("SYNAPSE_SHARED_MEMORY_ENABLED", "true")

        mem = SharedMemory.from_env()
        assert mem.enabled is True
        assert mem.db_path == db_path

    def test_from_env_disabled(self, monkeypatch):
        """from_env should create disabled instance when ENABLED=false."""
        from synapse.shared_memory import SharedMemory

        monkeypatch.setenv("SYNAPSE_SHARED_MEMORY_ENABLED", "false")

        mem = SharedMemory.from_env()
        assert mem.enabled is False

    def test_disabled_noop(self, tmp_path):
        """Disabled SharedMemory should return safe defaults."""
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "disabled.db"), enabled=False)
        # All operations should return safe defaults
        result = mem.save("key", "content", "author")
        assert result is None
        assert mem.get("key") is None
        assert mem.list_memories() == []
        assert mem.search("query") == []
        assert mem.delete("key") is False
        stats = mem.stats()
        assert stats["total"] == 0


# ============================================================
# TestSharedMemorySave - Save (UPSERT) operations
# ============================================================


class TestSharedMemorySave:
    """Tests for saving memories (UPSERT)."""

    @pytest.fixture
    def memory(self, tmp_path):
        from synapse.shared_memory import SharedMemory

        return SharedMemory(db_path=str(tmp_path / "memory.db"))

    def test_save_new(self, memory):
        """save() should create a new memory and return dict."""
        result = memory.save(
            key="auth-pattern",
            content="Use OAuth2 with PKCE flow",
            author="synapse-claude-8100",
        )
        assert result is not None
        assert result["key"] == "auth-pattern"
        assert result["content"] == "Use OAuth2 with PKCE flow"
        assert result["author"] == "synapse-claude-8100"
        assert result["id"]  # UUID should be set
        assert result["tags"] == []
        assert result["created_at"]
        assert result["updated_at"]
        assert result["scope"] == "global"
        assert result["working_dir"] is None

    def test_save_with_tags(self, memory):
        """save() should store tags as JSON array."""
        result = memory.save(
            key="db-choice",
            content="Use PostgreSQL for production",
            author="synapse-gemini-8110",
            tags=["architecture", "database"],
        )
        assert result["tags"] == ["architecture", "database"]
        assert result["scope"] == "global"

    def test_save_upsert_existing_key(self, memory):
        """save() with existing key should update content and updated_at."""
        first = memory.save(
            key="api-style",
            content="REST with JSON",
            author="synapse-claude-8100",
        )
        second = memory.save(
            key="api-style",
            content="GraphQL preferred",
            author="synapse-gemini-8110",
        )

        assert first["id"] == second["id"]  # Same row
        assert second["content"] == "GraphQL preferred"
        assert second["author"] == "synapse-gemini-8110"  # Author updated

    def test_save_upsert_preserves_created_at(self, memory):
        """UPSERT should preserve the original created_at timestamp."""
        first = memory.save(key="test-key", content="v1", author="claude")
        second = memory.save(key="test-key", content="v2", author="gemini")
        assert first["created_at"] == second["created_at"]

    def test_save_with_project_scope_stores_working_dir(self, memory, monkeypatch):
        """Project-scoped memories should record the current working directory."""
        monkeypatch.setattr(os, "getcwd", lambda: "/tmp/project-a")

        result = memory.save(
            key="project-key",
            content="Project memory",
            author="synapse-claude-8100",
            scope="project",
        )

        assert result["scope"] == "project"
        assert result["working_dir"] == "/tmp/project-a"

    def test_save_with_private_scope(self, memory):
        """Private memories should be saved with private scope."""
        result = memory.save(
            key="private-key",
            content="Private memory",
            author="synapse-claude-8100",
            scope="private",
        )

        assert result["scope"] == "private"
        assert result["working_dir"] is None


# ============================================================
# TestSharedMemoryGet - Get operations
# ============================================================


class TestSharedMemoryGet:
    """Tests for retrieving memories."""

    @pytest.fixture
    def memory(self, tmp_path):
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        mem.save(
            key="test-key",
            content="Test content",
            author="synapse-claude-8100",
            tags=["test"],
        )
        return mem

    def test_get_by_id(self, memory):
        """get() should find memory by UUID."""
        items = memory.list_memories()
        item_id = items[0]["id"]
        result = memory.get(item_id)
        assert result is not None
        assert result["key"] == "test-key"

    def test_get_by_key(self, memory):
        """get() should find memory by key string."""
        result = memory.get("test-key")
        assert result is not None
        assert result["content"] == "Test content"
        assert result["tags"] == ["test"]
        assert result["scope"] == "global"

    def test_get_nonexistent_returns_none(self, memory):
        """get() should return None for nonexistent id/key."""
        assert memory.get("nonexistent") is None
        assert memory.get("00000000-0000-0000-0000-000000000000") is None


# ============================================================
# TestSharedMemoryList - List operations
# ============================================================


class TestSharedMemoryList:
    """Tests for listing memories."""

    @pytest.fixture
    def memory(self, tmp_path):
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        mem.save("key-a", "Content A", "synapse-claude-8100", tags=["arch"])
        mem.save("key-b", "Content B", "synapse-gemini-8110", tags=["test"])
        mem.save("key-c", "Content C", "synapse-claude-8100", tags=["arch", "test"])
        return mem

    def test_list_all(self, memory):
        """list() without filters should return all memories."""
        items = memory.list_memories()
        assert len(items) == 3

    def test_list_filter_author(self, memory):
        """list() with author filter should return matching memories."""
        items = memory.list_memories(author="synapse-claude-8100")
        assert len(items) == 2
        assert all(i["author"] == "synapse-claude-8100" for i in items)

    def test_list_filter_tags(self, memory):
        """list() with tags filter should return memories containing that tag."""
        items = memory.list_memories(tags=["arch"])
        assert len(items) == 2
        assert all("arch" in i["tags"] for i in items)

    def test_list_filter_tags_exact_match(self, memory):
        """list() tag filter should use exact matching via json_each (#293).

        Tags containing SQL wildcard characters (% or _) must not cause
        false positives due to LIKE pattern interpretation.
        """
        memory.save(
            "key-d",
            "Content D",
            "synapse-claude-8100",
            tags=["100%"],
        )
        memory.save(
            "key-e",
            "Content E",
            "synapse-claude-8100",
            tags=["100"],
        )
        # Searching for tag "100%" must match only key-d, not key-e
        items = memory.list_memories(tags=["100%"])
        assert len(items) == 1
        assert items[0]["key"] == "key-d"

        # SQL underscore wildcard: "v_1" must not match "vX1"
        memory.save("key-f", "Content F", "synapse-claude-8100", tags=["v_1"])
        memory.save("key-g", "Content G", "synapse-claude-8100", tags=["vX1"])
        items = memory.list_memories(tags=["v_1"])
        assert len(items) == 1
        assert items[0]["key"] == "key-f"

    def test_list_limit(self, memory):
        """list() with limit should cap results."""
        items = memory.list_memories(limit=2)
        assert len(items) == 2

    def test_list_filter_scope_global(self, memory):
        """list() with global scope should return only global memories."""
        memory.save(
            "key-project",
            "Project Content",
            "synapse-claude-8100",
            scope="project",
        )
        memory.save(
            "key-private",
            "Private Content",
            "synapse-claude-8100",
            scope="private",
        )

        items = memory.list_memories(scope="global")

        assert len(items) == 3
        assert all(item["scope"] == "global" for item in items)

    def test_list_filter_scope_project(self, tmp_path, monkeypatch):
        """Project scope should only return items for the matching working dir."""
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        monkeypatch.setattr(os, "getcwd", lambda: "/tmp/project-a")
        mem.save("project-a", "Content A", "claude", scope="project")
        monkeypatch.setattr(os, "getcwd", lambda: "/tmp/project-b")
        mem.save("project-b", "Content B", "claude", scope="project")

        items = mem.list_memories(scope="project", working_dir="/tmp/project-a")

        assert [item["key"] for item in items] == ["project-a"]
        assert items[0]["working_dir"] == "/tmp/project-a"

    def test_list_filter_scope_private(self, tmp_path):
        """Private scope should only return items authored by the caller."""
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        mem.save("private-a", "Content A", "claude", scope="private")
        mem.save("private-b", "Content B", "gemini", scope="private")

        items = mem.list_memories(scope="private", author="claude")

        assert [item["key"] for item in items] == ["private-a"]
        assert items[0]["scope"] == "private"


# ============================================================
# TestSharedMemorySearch - Search operations
# ============================================================


class TestSharedMemorySearch:
    """Tests for searching memories."""

    @pytest.fixture
    def memory(self, tmp_path):
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        mem.save("auth-pattern", "Use OAuth2 with PKCE", "claude", tags=["security"])
        mem.save(
            "db-schema",
            "PostgreSQL with UUID primary keys",
            "gemini",
            tags=["database"],
        )
        mem.save("api-design", "REST endpoints with OpenAPI", "claude", tags=["api"])
        return mem

    def test_search_by_key(self, memory):
        """search() should match on key field."""
        results = memory.search("auth")
        assert len(results) >= 1
        assert any(r["key"] == "auth-pattern" for r in results)

    def test_search_by_content(self, memory):
        """search() should match on content field."""
        results = memory.search("PostgreSQL")
        assert len(results) >= 1
        assert any(r["key"] == "db-schema" for r in results)

    def test_search_by_tag(self, memory):
        """search() should match on tags field."""
        results = memory.search("security")
        assert len(results) >= 1
        assert any(r["key"] == "auth-pattern" for r in results)

    def test_search_no_results(self, memory):
        """search() should return empty list for no matches."""
        results = memory.search("nonexistent-xyz")
        assert results == []

    def test_search_limit(self, memory):
        """search() should respect limit parameter (#292)."""
        # All 3 memories match partial key/content containing common patterns
        # Add more items so we can test limiting
        memory.save("api-v2", "REST API v2 design", "claude", tags=["api"])
        memory.save("api-v3", "REST API v3 design", "claude", tags=["api"])
        results_all = memory.search("api")
        assert len(results_all) >= 3  # api-design, api-v2, api-v3
        results_limited = memory.search("api", limit=2)
        assert len(results_limited) == 2

    def test_search_default_limit(self, memory):
        """search() should have a default limit of 100 (#292)."""
        import inspect

        from synapse.shared_memory import SharedMemory

        sig = inspect.signature(SharedMemory.search)
        assert sig.parameters["limit"].default == 100

    def test_search_rejects_zero_limit(self, memory):
        """search() should reject zero limit with ValueError."""
        with pytest.raises(ValueError, match="limit must be greater than 0"):
            memory.search("api", limit=0)

    def test_search_rejects_negative_limit(self, memory):
        """search() should reject negative limit with ValueError."""
        with pytest.raises(ValueError, match="limit must be greater than 0"):
            memory.search("api", limit=-1)

    def test_search_filter_scope_global(self, memory):
        """Global scope search should not return project/private memories."""
        memory.save("project-auth", "Use project auth", "claude", scope="project")
        memory.save("private-auth", "Use private auth", "claude", scope="private")

        results = memory.search("auth", scope="global")

        assert [item["key"] for item in results] == ["auth-pattern"]

    def test_search_filter_scope_project(self, tmp_path, monkeypatch):
        """Project scope search should require a matching working dir."""
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        monkeypatch.setattr(os, "getcwd", lambda: "/tmp/project-a")
        mem.save("project-auth-a", "Auth for project a", "claude", scope="project")
        monkeypatch.setattr(os, "getcwd", lambda: "/tmp/project-b")
        mem.save("project-auth-b", "Auth for project b", "claude", scope="project")

        results = mem.search(
            "Auth",
            scope="project",
            working_dir="/tmp/project-a",
        )

        assert [item["key"] for item in results] == ["project-auth-a"]

    def test_search_filter_scope_private(self, tmp_path):
        """Private scope search should require the matching author."""
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        mem.save("private-auth-a", "Auth for claude", "claude", scope="private")
        mem.save("private-auth-b", "Auth for gemini", "gemini", scope="private")

        results = mem.search("Auth", scope="private", author="claude")

        assert [item["key"] for item in results] == ["private-auth-a"]


# ============================================================
# TestSharedMemoryDelete - Delete operations
# ============================================================


class TestSharedMemoryDelete:
    """Tests for deleting memories."""

    @pytest.fixture
    def memory(self, tmp_path):
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        mem.save("to-delete", "Will be deleted", "claude")
        return mem

    def test_delete_by_id(self, memory):
        """delete() should remove memory by UUID."""
        items = memory.list_memories()
        item_id = items[0]["id"]
        assert memory.delete(item_id) is True
        assert memory.get(item_id) is None

    def test_delete_by_key(self, memory):
        """delete() should remove memory by key."""
        assert memory.delete("to-delete") is True
        assert memory.get("to-delete") is None

    def test_delete_nonexistent_returns_false(self, memory):
        """delete() should return False for nonexistent id/key."""
        assert memory.delete("nonexistent") is False


# ============================================================
# TestSharedMemoryStats - Statistics
# ============================================================


class TestSharedMemoryStats:
    """Tests for memory statistics."""

    @pytest.fixture
    def memory(self, tmp_path):
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory(db_path=str(tmp_path / "memory.db"))
        mem.save("key-a", "Content A", "synapse-claude-8100", tags=["arch"])
        mem.save("key-b", "Content B", "synapse-gemini-8110", tags=["test"])
        mem.save("key-c", "Content C", "synapse-claude-8100", tags=["arch", "test"])
        return mem

    def test_stats(self, memory):
        """stats() should return total count."""
        stats = memory.stats()
        assert stats["total"] == 3

    def test_stats_by_author(self, memory):
        """stats() should include per-author breakdown."""
        stats = memory.stats()
        assert "by_author" in stats
        assert stats["by_author"]["synapse-claude-8100"] == 2
        assert stats["by_author"]["synapse-gemini-8110"] == 1

    def test_stats_by_tag(self, memory):
        """stats() should include per-tag breakdown."""
        stats = memory.stats()
        assert "by_tag" in stats
        assert stats["by_tag"]["arch"] == 2
        assert stats["by_tag"]["test"] == 2
