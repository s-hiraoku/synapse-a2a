"""Tests for CanvasStore — SQLite-backed card storage.

Test-first development: these tests define the expected behavior
for the CanvasStore class before implementation.
"""

from __future__ import annotations

import os
import sqlite3
import time

import pytest

# ============================================================
# TestCanvasStoreInit — Database initialization
# ============================================================


class TestCanvasStoreInit:
    """Tests for CanvasStore database initialization."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        db_path = str(tmp_path / "canvas.db")
        return CanvasStore(db_path=db_path)

    def test_init_creates_db(self, store):
        """Database file should be created on init."""
        assert os.path.exists(store.db_path)

    def test_cards_table_exists(self, store):
        """cards table should exist."""
        conn = sqlite3.connect(store.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cards'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_indexes_exist(self, store):
        """card_id, agent, and expires indexes should exist."""
        conn = sqlite3.connect(store.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        index_names = {row[0] for row in cursor.fetchall()}
        assert "idx_cards_card_id" in index_names
        assert "idx_cards_agent" in index_names
        assert "idx_cards_expires" in index_names
        conn.close()

    def test_wal_mode(self, store):
        """Database should use WAL journal mode."""
        conn = sqlite3.connect(store.db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        conn.close()


# ============================================================
# TestAddCard — Card creation
# ============================================================


class TestAddCard:
    """Tests for adding cards to the store."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        return CanvasStore(db_path=str(tmp_path / "canvas.db"))

    def test_add_card_returns_card(self, store):
        """add_card should return a Card with generated id."""
        card = store.add_card(
            agent_id="synapse-claude-8103",
            agent_name="Gojo",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Auth Flow",
        )
        assert card["id"] is not None
        assert len(card["id"]) == 8  # uuid4()[:8]
        assert card["agent_id"] == "synapse-claude-8103"
        assert card["agent_name"] == "Gojo"
        assert card["title"] == "Auth Flow"

    def test_add_card_with_card_id(self, store):
        """Should accept user-specified card_id."""
        card = store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow",
            card_id="auth-flow",
        )
        assert card["card_id"] == "auth-flow"

    def test_add_card_auto_generates_id(self, store):
        """card_id should be auto-generated (8-char UUID) if not provided."""
        card = store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow",
        )
        assert card["card_id"] is not None
        assert len(card["card_id"]) == 8

    def test_add_card_sets_expires_at(self, store):
        """Non-pinned card should have expires_at set."""
        card = store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow",
        )
        assert card["expires_at"] is not None

    def test_add_pinned_card_no_expiry(self, store):
        """Pinned card should have no expires_at."""
        card = store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow",
            pinned=True,
        )
        assert card["expires_at"] is None

    def test_add_card_with_tags(self, store):
        """Should store tags as JSON array."""
        card = store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow",
            tags=["design", "auth"],
        )
        assert card["tags"] == ["design", "auth"]


# ============================================================
# TestUpsert — Card update via card_id
# ============================================================


class TestUpsert:
    """Tests for upserting cards by card_id."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        return CanvasStore(db_path=str(tmp_path / "canvas.db"))

    def test_upsert_creates_new(self, store):
        """Upsert with new card_id should create a card."""
        card = store.upsert_card(
            card_id="auth-flow",
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow v1",
        )
        assert card["card_id"] == "auth-flow"
        assert card["title"] == "Flow v1"

    def test_upsert_updates_existing(self, store):
        """Upsert with existing card_id should update content and title."""
        store.upsert_card(
            card_id="auth-flow",
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow v1",
        )
        updated = store.upsert_card(
            card_id="auth-flow",
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B; B-->C"}',
            title="Flow v2",
        )
        assert updated["title"] == "Flow v2"
        assert "B-->C" in updated["content"]

        # Should still be only one card
        cards = store.list_cards()
        assert len(cards) == 1

    def test_upsert_rejects_different_agent(self, store):
        """Upsert should fail if card_id belongs to different agent."""
        store.upsert_card(
            card_id="auth-flow",
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"v1"}',
            title="Flow",
        )
        result = store.upsert_card(
            card_id="auth-flow",
            agent_id="synapse-gemini-8110",  # Different agent
            content='{"format":"mermaid","body":"v2"}',
            title="Flow",
        )
        assert result is None  # Rejected

    def test_upsert_refreshes_expires_at(self, store):
        """Upsert should refresh expires_at on update."""
        card1 = store.upsert_card(
            card_id="auth-flow",
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"v1"}',
            title="Flow",
        )
        time.sleep(0.1)
        card2 = store.upsert_card(
            card_id="auth-flow",
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"v2"}',
            title="Flow v2",
        )
        assert card2["updated_at"] >= card1["updated_at"]


# ============================================================
# TestListCards — Card listing and filtering
# ============================================================


class TestListCards:
    """Tests for listing and filtering cards."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        s = CanvasStore(db_path=str(tmp_path / "canvas.db"))
        # Add test data
        s.add_card(
            agent_id="synapse-claude-8103",
            agent_name="Gojo",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Auth Flow",
            card_id="auth-flow",
            tags=["design"],
        )
        s.add_card(
            agent_id="synapse-gemini-8110",
            agent_name="Gemini",
            content='{"format":"table","body":{"headers":["a"],"rows":[["1"]]}}',
            title="Test Results",
            card_id="test-results",
            tags=["testing"],
        )
        s.add_card(
            agent_id="synapse-claude-8103",
            agent_name="Gojo",
            content='{"format":"markdown","body":"## Design"}',
            title="Design Doc",
            card_id="design-doc",
            tags=["design"],
        )
        return s

    def test_list_all(self, store):
        """list_cards without filters returns all cards."""
        cards = store.list_cards()
        assert len(cards) == 3

    def test_list_by_agent_id(self, store):
        """Should filter by agent_id."""
        cards = store.list_cards(agent_id="synapse-claude-8103")
        assert len(cards) == 2
        assert all(c["agent_id"] == "synapse-claude-8103" for c in cards)

    def test_list_by_search(self, store):
        """Should search by title."""
        cards = store.list_cards(search="Auth")
        assert len(cards) == 1
        assert cards[0]["title"] == "Auth Flow"

    def test_list_by_content_type(self, store):
        """Should filter by content format type."""
        cards = store.list_cards(content_type="mermaid")
        assert len(cards) == 1
        assert cards[0]["card_id"] == "auth-flow"

    def test_list_ordered_by_updated(self, store):
        """Cards should be ordered newest first."""
        cards = store.list_cards()
        for i in range(len(cards) - 1):
            assert cards[i]["updated_at"] >= cards[i + 1]["updated_at"]


# ============================================================
# TestGetCard — Single card retrieval
# ============================================================


class TestGetCard:
    """Tests for retrieving a single card."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        s = CanvasStore(db_path=str(tmp_path / "canvas.db"))
        s.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow",
            card_id="auth-flow",
        )
        return s

    def test_get_by_card_id(self, store):
        """Should retrieve card by card_id."""
        card = store.get_card("auth-flow")
        assert card is not None
        assert card["title"] == "Flow"

    def test_get_nonexistent(self, store):
        """Should return None for nonexistent card_id."""
        card = store.get_card("nonexistent")
        assert card is None


# ============================================================
# TestDeleteCard — Card deletion with ownership
# ============================================================


class TestDeleteCard:
    """Tests for deleting cards with ownership check."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        s = CanvasStore(db_path=str(tmp_path / "canvas.db"))
        s.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Flow",
            card_id="auth-flow",
        )
        return s

    def test_delete_own_card(self, store):
        """Should delete own card."""
        result = store.delete_card("auth-flow", agent_id="synapse-claude-8103")
        assert result is True
        assert store.get_card("auth-flow") is None

    def test_delete_other_agent_card_rejected(self, store):
        """Should not delete another agent's card."""
        result = store.delete_card("auth-flow", agent_id="synapse-gemini-8110")
        assert result is False
        assert store.get_card("auth-flow") is not None

    def test_delete_nonexistent_card(self, store):
        """Should return False for nonexistent card."""
        result = store.delete_card("nonexistent", agent_id="synapse-claude-8103")
        assert result is False


# ============================================================
# TestClearCards — Bulk deletion
# ============================================================


class TestClearCards:
    """Tests for clearing cards."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        s = CanvasStore(db_path=str(tmp_path / "canvas.db"))
        s.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"v1"}',
            title="Card 1",
        )
        s.add_card(
            agent_id="synapse-gemini-8110",
            content='{"format":"mermaid","body":"v2"}',
            title="Card 2",
        )
        return s

    def test_clear_all(self, store):
        """clear_all without filter should remove all cards."""
        count = store.clear_all()
        assert count == 2
        assert store.list_cards() == []

    def test_clear_by_agent(self, store):
        """clear_all with agent_id should only remove that agent's cards."""
        count = store.clear_all(agent_id="synapse-claude-8103")
        assert count == 1
        remaining = store.list_cards()
        assert len(remaining) == 1
        assert remaining[0]["agent_id"] == "synapse-gemini-8110"


# ============================================================
# TestTTLExpiry — Card expiration
# ============================================================


class TestTTLExpiry:
    """Tests for card TTL expiration."""

    @pytest.fixture
    def store(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        return CanvasStore(
            db_path=str(tmp_path / "canvas.db"), card_ttl=1
        )  # 1 second TTL

    def test_expired_cards_excluded_from_list(self, store):
        """Expired cards should not appear in list_cards."""
        store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Expiring Card",
        )
        assert len(store.list_cards()) == 1

        time.sleep(1.5)  # Wait for TTL

        assert len(store.list_cards()) == 0

    def test_pinned_cards_exempt_from_ttl(self, store):
        """Pinned cards should not expire."""
        store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Pinned Card",
            pinned=True,
        )
        time.sleep(1.5)  # Wait for TTL

        cards = store.list_cards()
        assert len(cards) == 1
        assert cards[0]["title"] == "Pinned Card"

    def test_cleanup_expired_cards(self, store):
        """cleanup_expired should physically remove expired cards from DB."""
        store.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Old Card",
        )
        time.sleep(1.5)

        removed = store.cleanup_expired()
        assert removed >= 1

        # Directly check DB - should be gone
        conn = sqlite3.connect(store.db_path)
        count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        conn.close()
        assert count == 0
