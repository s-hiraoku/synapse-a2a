"""Tests for Canvas CLI commands.

Test-first development: these tests define the expected behavior
for the synapse canvas CLI subcommands.
"""

from __future__ import annotations

import json

import pytest

# ============================================================
# TestCanvasPost — synapse canvas post
# ============================================================


class TestCanvasPost:
    """Tests for the canvas post CLI command."""

    def test_post_raw_json(self, tmp_path):
        """synapse canvas post should accept raw JSON."""
        from synapse.commands.canvas import post_card

        db_path = str(tmp_path / "canvas.db")
        msg_json = json.dumps(
            {
                "type": "render",
                "content": {"format": "mermaid", "body": "graph TD; A-->B"},
                "agent_id": "synapse-claude-8103",
                "title": "Test",
            }
        )
        result = post_card(msg_json, db_path=db_path)
        assert result is not None
        assert result["title"] == "Test"

    def test_post_invalid_json(self, tmp_path):
        """Should return error for invalid JSON."""
        from synapse.commands.canvas import post_card

        db_path = str(tmp_path / "canvas.db")
        result = post_card("not valid json", db_path=db_path)
        assert result is None

    def test_post_from_file(self, tmp_path):
        """post_shortcut should read the body from a file when file_path is given."""
        from synapse.commands.canvas import post_shortcut

        db_path = str(tmp_path / "canvas.db")
        body_file = tmp_path / "diagram.mmd"
        body_file.write_text("graph TD; File-->Canvas", encoding="utf-8")

        result = post_shortcut(
            format_name="mermaid",
            body="ignored when file_path is set",
            file_path=str(body_file),
            title="Flow From File",
            agent_id="synapse-claude-8103",
            db_path=db_path,
        )
        assert result is not None
        content = json.loads(result["content"])
        assert content["format"] == "mermaid"
        assert content["body"] == "graph TD; File-->Canvas"

    def test_post_shortcut_autofills_agent_name_from_registry(
        self, tmp_path, monkeypatch
    ):
        """Should resolve agent_name from registry when only agent_id is given."""
        from synapse.commands.canvas import post_shortcut

        class _Registry:
            def get_agent(self, agent_id):
                assert agent_id == "synapse-codex-8120"
                return {"name": "Cody"}

        monkeypatch.setattr(
            "synapse.commands.canvas.AgentRegistry", lambda: _Registry()
        )

        result = post_shortcut(
            format_name="markdown",
            body="hello",
            title="Auto Name",
            agent_id="synapse-codex-8120",
            db_path=str(tmp_path / "canvas.db"),
        )

        assert result is not None
        assert result["agent_name"] == "Cody"

    def test_post_shortcut_prefers_explicit_agent_name_over_registry(
        self, tmp_path, monkeypatch
    ):
        """Explicit agent_name should win over registry-derived name."""
        from synapse.commands.canvas import post_shortcut

        class _Registry:
            def get_agent(self, agent_id):
                assert agent_id == "synapse-codex-8120"
                return {"name": "RegistryName"}

        monkeypatch.setattr(
            "synapse.commands.canvas.AgentRegistry", lambda: _Registry()
        )

        result = post_shortcut(
            format_name="markdown",
            body="hello",
            title="Explicit Name",
            agent_id="synapse-codex-8120",
            agent_name="Cody",
            db_path=str(tmp_path / "canvas.db"),
        )

        assert result is not None
        assert result["agent_name"] == "Cody"


# ============================================================
# TestCanvasMermaid — synapse canvas mermaid shortcut
# ============================================================


class TestCanvasMermaid:
    """Tests for the canvas mermaid shortcut."""

    def test_mermaid_shortcut(self, tmp_path):
        """synapse canvas mermaid should create a mermaid card."""
        from synapse.commands.canvas import post_shortcut

        db_path = str(tmp_path / "canvas.db")
        result = post_shortcut(
            format_name="mermaid",
            body="graph TD; A-->B",
            title="Flow",
            agent_id="synapse-claude-8103",
            db_path=db_path,
        )
        assert result is not None
        content = json.loads(result["content"])
        assert content["format"] == "mermaid"
        assert content["body"] == "graph TD; A-->B"

    def test_mermaid_with_id(self, tmp_path):
        """Should accept --id for upsert."""
        from synapse.commands.canvas import post_shortcut

        db_path = str(tmp_path / "canvas.db")
        result = post_shortcut(
            format_name="mermaid",
            body="graph TD; A-->B",
            title="Flow",
            agent_id="synapse-claude-8103",
            card_id="auth-flow",
            db_path=db_path,
        )
        assert result["card_id"] == "auth-flow"

    def test_mermaid_with_pin(self, tmp_path):
        """Should accept --pin flag."""
        from synapse.commands.canvas import post_shortcut

        db_path = str(tmp_path / "canvas.db")
        result = post_shortcut(
            format_name="mermaid",
            body="graph TD; A-->B",
            title="Flow",
            agent_id="synapse-claude-8103",
            pinned=True,
            db_path=db_path,
        )
        assert result["pinned"] == 1


# ============================================================
# TestCanvasList — synapse canvas list
# ============================================================


class TestCanvasList:
    """Tests for the canvas list command."""

    @pytest.fixture
    def store_with_cards(self, tmp_path):
        from synapse.canvas.store import CanvasStore

        s = CanvasStore(db_path=str(tmp_path / "canvas.db"))
        s.add_card(
            agent_id="synapse-claude-8103",
            agent_name="Gojo",
            content='{"format":"mermaid","body":"graph TD; A-->B"}',
            title="Auth Flow",
            card_id="auth-flow",
        )
        s.add_card(
            agent_id="synapse-gemini-8110",
            content='{"format":"table","body":{}}',
            title="Results",
            card_id="results",
        )
        return s

    def test_list_returns_all(self, store_with_cards):
        """list should return all cards."""
        cards = store_with_cards.list_cards()
        assert len(cards) == 2

    def test_list_mine_filters_by_agent(self, store_with_cards):
        """--mine should filter by agent_id."""
        cards = store_with_cards.list_cards(agent_id="synapse-claude-8103")
        assert len(cards) == 1
        assert cards[0]["agent_name"] == "Gojo"

    def test_list_search(self, store_with_cards):
        """--search should filter by title."""
        cards = store_with_cards.list_cards(search="Auth")
        assert len(cards) == 1
        assert cards[0]["card_id"] == "auth-flow"


# ============================================================
# TestCanvasDelete — synapse canvas delete
# ============================================================


class TestCanvasDelete:
    """Tests for the canvas delete command."""

    def test_delete_own_card(self, tmp_path):
        """Should delete own card by card_id."""
        from synapse.canvas.store import CanvasStore

        s = CanvasStore(db_path=str(tmp_path / "canvas.db"))
        s.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"v1"}',
            title="Flow",
            card_id="auth-flow",
        )
        result = s.delete_card("auth-flow", agent_id="synapse-claude-8103")
        assert result is True

    def test_delete_other_rejected(self, tmp_path):
        """Should reject deletion of another agent's card."""
        from synapse.canvas.store import CanvasStore

        s = CanvasStore(db_path=str(tmp_path / "canvas.db"))
        s.add_card(
            agent_id="synapse-claude-8103",
            content='{"format":"mermaid","body":"v1"}',
            title="Flow",
            card_id="auth-flow",
        )
        result = s.delete_card("auth-flow", agent_id="synapse-gemini-8110")
        assert result is False


# ============================================================
# TestAutoStart — Server auto-start logic
# ============================================================


class TestAutoStart:
    """Tests for Canvas server auto-start on first post."""

    def test_is_server_running_false_when_not_started(self):
        """Should return False when no server is running."""
        from synapse.commands.canvas import is_canvas_server_running

        # Use a port that's unlikely to be in use
        assert is_canvas_server_running(port=39999) is False

    def test_pid_file_written_on_serve(self, tmp_path):
        """serve should write PID file."""
        from synapse.commands.canvas import read_pid_file, write_pid_file

        pid_path = str(tmp_path / "canvas.pid")
        write_pid_file(pid_path, pid=12345, port=3000)

        pid, port = read_pid_file(pid_path)
        assert pid == 12345
        assert port == 3000

    def test_pid_file_stale_detection(self, tmp_path):
        """Should detect stale PID file (process not running)."""
        from synapse.commands.canvas import is_pid_alive, write_pid_file

        pid_path = str(tmp_path / "canvas.pid")
        write_pid_file(pid_path, pid=999999, port=3000)  # Non-existent PID

        assert is_pid_alive(999999) is False
