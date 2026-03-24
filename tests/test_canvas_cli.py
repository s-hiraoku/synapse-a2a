"""Tests for Canvas CLI commands.

Test-first development: these tests define the expected behavior
for the synapse canvas CLI subcommands.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def _isolate_from_live_server(request, monkeypatch):
    """Prevent tests from writing to a live Canvas server's DB.

    post_shortcut / post_card check is_canvas_server_running() and, when True,
    bypass the db_path argument and write via HTTP to the production DB.
    Force the fallback (direct DB write with tmp_path) in all tests.

    Tests that need the real function can use @pytest.mark.no_server_mock.
    """
    if "no_server_mock" in request.keywords:
        return
    monkeypatch.setattr(
        "synapse.commands.canvas.is_canvas_server_running", lambda port=3000: False
    )


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

    def test_post_card_autofills_agent_name_from_registry_for_http_posts(
        self, monkeypatch
    ):
        """HTTP post path should receive registry-derived agent_name in payload."""
        from synapse.commands.canvas import post_card

        captured: dict = {}

        class _Registry:
            def get_agent(self, agent_id):
                assert agent_id == "synapse-codex-8120"
                return {"name": "Cody"}

        monkeypatch.setattr(
            "synapse.commands.canvas.AgentRegistry", lambda: _Registry()
        )
        monkeypatch.setattr(
            "synapse.commands.canvas.is_canvas_server_running", lambda port: True
        )

        def _capture(payload, port):
            captured["payload"] = payload
            captured["port"] = port
            return {"agent_name": payload["agent_name"], "card_id": "test"}

        monkeypatch.setattr("synapse.commands.canvas._post_via_api", _capture)

        msg_json = json.dumps(
            {
                "type": "render",
                "content": {"format": "markdown", "body": "hello"},
                "agent_id": "synapse-codex-8120",
                "title": "Raw Auto Name",
            }
        )

        result = post_card(msg_json)

        assert result is not None
        assert result["agent_name"] == "Cody"
        assert captured["payload"]["agent_name"] == "Cody"
        assert captured["payload"]["agent_id"] == "synapse-codex-8120"

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

    def test_post_shortcut_does_not_swallow_unexpected_registry_errors(
        self, tmp_path, monkeypatch
    ):
        """Unexpected registry failures should surface instead of becoming empty names."""
        from synapse.commands.canvas import post_shortcut

        class _Registry:
            def get_agent(self, agent_id):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            "synapse.commands.canvas.AgentRegistry", lambda: _Registry()
        )

        with pytest.raises(RuntimeError, match="boom"):
            post_shortcut(
                format_name="markdown",
                body="hello",
                title="Error Name",
                agent_id="synapse-codex-8120",
                db_path=str(tmp_path / "canvas.db"),
            )


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

    @pytest.mark.no_server_mock
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


class TestCanvasServe:
    """Tests for the canvas serve CLI command."""

    def test_serve_help_includes_port_and_no_open(self):
        """serve parser should advertise --port and --no-open."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "canvas", "serve", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--port" in result.stdout
        assert "--no-open" in result.stdout

    def test_cmd_canvas_serve_respects_port_and_no_open(self, monkeypatch):
        """cmd_canvas_serve should pass the requested port and skip opening the browser."""
        import argparse
        import types

        from synapse import cli

        calls: dict[str, object] = {}

        def fake_create_app():
            calls["app_created"] = True
            return "app"

        def fake_run(app, host, port, log_level):
            calls["run"] = {
                "app": app,
                "host": host,
                "port": port,
                "log_level": log_level,
            }

        def fake_open(url):
            calls["opened_url"] = url
            return True

        monkeypatch.setattr("synapse.canvas.server.create_app", fake_create_app)
        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
        monkeypatch.setattr("webbrowser.open", fake_open)

        args = argparse.Namespace(port=4310, no_open=True)
        cli.cmd_canvas_serve(args)

        assert calls["app_created"] is True
        assert calls["run"] == {
            "app": "app",
            "host": "0.0.0.0",
            "port": 4310,
            "log_level": "warning",
        }
        assert "opened_url" not in calls

    def test_cmd_canvas_serve_opens_browser_when_no_open_false(self, monkeypatch):
        """cmd_canvas_serve should schedule browser open when no_open is False."""
        import argparse
        import types

        from synapse import cli

        calls: dict[str, object] = {}
        thread_calls: list[dict] = []

        def fake_create_app():
            calls["app_created"] = True
            return "app"

        def fake_run(app, host, port, log_level):
            calls["run"] = {
                "app": app,
                "host": host,
                "port": port,
                "log_level": log_level,
            }

        class FakeThread:
            def __init__(self, *, target, args, daemon):
                thread_calls.append({"target": target, "args": args, "daemon": daemon})

            def start(self):
                pass

        monkeypatch.setattr("synapse.canvas.server.create_app", fake_create_app)
        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
        monkeypatch.setattr("threading.Thread", FakeThread)

        args = argparse.Namespace(port=4310, no_open=False)
        cli.cmd_canvas_serve(args)

        assert len(thread_calls) == 1
        assert thread_calls[0]["target"] is cli._wait_and_open_browser
        assert thread_calls[0]["args"] == ("http://localhost:4310",)
        assert thread_calls[0]["daemon"] is True
        assert calls["run"]["port"] == 4310


# ============================================================
# TestCanvasBriefing — synapse canvas briefing
# ============================================================


class TestCanvasBriefing:
    """Tests for the canvas briefing CLI command."""

    # Use a port that's not running to force direct DB write
    _TEST_PORT = 39998

    def test_post_briefing_json(self, tmp_path):
        """post_briefing should accept JSON with content and sections."""
        from synapse.commands.canvas import post_briefing

        db_path = str(tmp_path / "canvas.db")
        json_data = json.dumps(
            {
                "title": "Sprint 42",
                "summary": "All green",
                "sections": [
                    {"title": "Tests", "blocks": [0]},
                    {"title": "Architecture", "blocks": [1]},
                ],
                "content": [
                    {"format": "markdown", "body": "## Test Results"},
                    {"format": "mermaid", "body": "graph TD; A-->B"},
                ],
            }
        )
        result = post_briefing(
            json_data=json_data,
            agent_id="synapse-claude-8103",
            db_path=db_path,
            port=self._TEST_PORT,
        )
        assert result is not None
        assert result["template"] == "briefing"
        assert result["title"] == "Sprint 42"

    def test_post_briefing_file(self, tmp_path):
        """post_briefing should read from file."""
        from synapse.commands.canvas import post_briefing

        db_path = str(tmp_path / "canvas.db")
        briefing_file = tmp_path / "report.json"
        briefing_file.write_text(
            json.dumps(
                {
                    "title": "CI Report",
                    "sections": [{"title": "Results", "blocks": [0]}],
                    "content": [{"format": "markdown", "body": "All pass"}],
                }
            ),
            encoding="utf-8",
        )
        result = post_briefing(
            json_data=None,
            file_path=str(briefing_file),
            agent_id="synapse-claude-8103",
            db_path=db_path,
            port=self._TEST_PORT,
        )
        assert result is not None
        assert result["template"] == "briefing"
        assert result["title"] == "CI Report"

    def test_post_briefing_with_summary(self, tmp_path):
        """summary argument should be reflected in template_data."""
        from synapse.commands.canvas import post_briefing

        db_path = str(tmp_path / "canvas.db")
        json_data = json.dumps(
            {
                "sections": [{"title": "A", "blocks": [0]}],
                "content": [{"format": "markdown", "body": "hello"}],
            }
        )
        result = post_briefing(
            json_data=json_data,
            agent_id="synapse-claude-8103",
            title="With Summary",
            summary="Executive summary",
            db_path=db_path,
            port=self._TEST_PORT,
        )
        assert result is not None
        # template_data should contain the summary
        td = result["template_data"]
        assert td["summary"] == "Executive summary"

    def _post_and_retrieve(self, tmp_path, briefing_dict, **kwargs):
        """Post a briefing and return the card from the store."""
        from synapse.canvas.store import CanvasStore
        from synapse.commands.canvas import post_briefing

        db_path = str(tmp_path / "canvas.db")
        post_briefing(
            json_data=json.dumps(briefing_dict),
            agent_id=kwargs.pop("agent_id", "synapse-claude-8103"),
            db_path=db_path,
            port=self._TEST_PORT,
            **kwargs,
        )
        store = CanvasStore(db_path=db_path)
        cards = store.list_cards()
        assert len(cards) == 1
        return cards[0]

    def test_post_briefing_round_trip_store(self, tmp_path):
        """post_briefing result should survive store round-trip with types intact."""
        card = self._post_and_retrieve(
            tmp_path,
            {
                "title": "Round Trip",
                "summary": "Exec summary",
                "sections": [
                    {"title": "Sec A", "blocks": [0], "summary": "sec summary"},
                    {"title": "Sec B", "blocks": [1]},
                    {"title": "Divider"},
                ],
                "content": [
                    {"format": "markdown", "body": "Block 0"},
                    {"format": "table", "body": {"headers": ["h"], "rows": [["r"]]}},
                ],
            },
        )
        assert card["template"] == "briefing"
        assert card["title"] == "Round Trip"

        td = card["template_data"]
        assert isinstance(td, dict)
        assert td["summary"] == "Exec summary"
        assert isinstance(td["sections"], list)
        assert len(td["sections"]) == 3
        assert td["sections"][0]["title"] == "Sec A"
        assert td["sections"][0]["blocks"] == [0]
        assert td["sections"][0]["summary"] == "sec summary"
        assert td["sections"][2]["title"] == "Divider"
        assert "blocks" not in td["sections"][2]

        # Verify block index types are preserved as int
        assert all(isinstance(idx, int) for idx in td["sections"][0]["blocks"])

        # Content should be parseable JSON list
        content = json.loads(card["content"])
        assert isinstance(content, list)
        assert len(content) == 2

    def test_post_briefing_export_markdown(self, tmp_path):
        """Briefing card export should produce correct markdown with sections."""
        from synapse.canvas.export import export_card

        card = self._post_and_retrieve(
            tmp_path,
            {
                "title": "Export Test",
                "summary": "Top summary",
                "sections": [
                    {"title": "Overview", "blocks": [0]},
                    {"title": "Data", "blocks": [1]},
                ],
                "content": [
                    {"format": "markdown", "body": "Overview content here"},
                    {"format": "markdown", "body": "Data content here"},
                ],
            },
        )
        result = export_card(card)
        assert result is not None

        data, filename, content_type = result
        md = data.decode("utf-8")

        assert filename.endswith(".md")
        assert "markdown" in content_type
        assert "# Export Test" in md
        assert "Top summary" in md
        assert "## Overview" in md
        assert "## Data" in md
        assert "Overview content here" in md
        assert "Data content here" in md
        # Sections should appear in order
        assert md.index("## Overview") < md.index("## Data")
