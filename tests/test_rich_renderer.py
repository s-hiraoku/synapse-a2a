"""Tests for Rich TUI renderer for synapse list."""

from io import StringIO

from rich.console import Console

from synapse.commands.renderers.rich_renderer import RichRenderer


class TestRichRendererStatusColors:
    """Tests for status color mapping."""

    def test_ready_status_is_green(self):
        """READY status should be displayed in green."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)

        # Render to string
        console.print(table)
        output = console.file.getvalue()

        # Check that READY is present and styled (bold green in ANSI)
        assert "READY" in output
        # Bold green color code should be present (\x1b[1;32m = bold green)
        assert "\x1b[1;32m" in output

    def test_processing_status_is_yellow(self):
        """PROCESSING status should be displayed in yellow."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "PROCESSING",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)

        console.print(table)
        output = console.file.getvalue()

        assert "PROCESSING" in output
        # Bold yellow color code should be present (\x1b[1;33m = bold yellow)
        assert "\x1b[1;33m" in output

    def test_unknown_status_default_style(self):
        """Unknown status should use default styling."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "UNKNOWN",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)
        console.print(table)
        output = console.file.getvalue()

        # Should still render the status
        assert "UNKNOWN" in output


class TestRichRendererTableStructure:
    """Tests for table structure and borders."""

    def test_table_has_rounded_box_style(self):
        """Table should use ROUNDED box style."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)

        # Check table box style
        from rich import box

        assert table.box == box.ROUNDED

    def test_table_has_required_columns(self):
        """Table should have TYPE, PORT, STATUS, TRANSPORT, PID, WORKING_DIR, ENDPOINT columns."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)

        column_headers = [col.header for col in table.columns]
        assert "TYPE" in column_headers
        assert "PORT" in column_headers
        assert "STATUS" in column_headers
        assert "TRANSPORT" in column_headers
        assert "PID" in column_headers
        assert "WORKING_DIR" in column_headers
        assert "ENDPOINT" in column_headers

    def test_transport_column_always_present(self):
        """TRANSPORT column should always be present."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "UDS→",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)

        column_headers = [col.header for col in table.columns]
        assert "TRANSPORT" in column_headers


class TestRichRendererPanel:
    """Tests for panel structure."""

    def test_build_panel_contains_table(self):
        """Panel should contain the table."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)
        panel = renderer.build_panel(
            table,
            title="Synapse A2A v0.2.26",
            subtitle="Last updated: 2026-01-18 12:00:00",
        )

        console.print(panel)
        output = console.file.getvalue()

        # Panel should contain title info
        assert "Synapse A2A" in output
        assert "2026-01-18 12:00:00" in output

    def test_panel_has_title_and_subtitle(self):
        """Panel should display title and subtitle."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = []
        table = renderer.build_table(agents)
        panel = renderer.build_panel(
            table,
            title="Test Title",
            subtitle="Test Subtitle",
        )

        console.print(panel)
        output = console.file.getvalue()

        assert "Test Title" in output
        assert "Test Subtitle" in output


class TestRichRendererEmptyState:
    """Tests for empty agent list handling."""

    def test_empty_agents_shows_message(self):
        """Empty agent list should show 'No agents running' message."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = []
        table = renderer.build_table(agents)

        console.print(table)
        output = console.file.getvalue()

        assert "No agents running" in output

    def test_empty_agents_shows_port_ranges(self):
        """Empty agent list should show port ranges."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = []
        table = renderer.build_table(agents)

        console.print(table)
        output = console.file.getvalue()

        # Should show port ranges for known agents
        assert "claude" in output.lower() or "8100" in output


class TestRichRendererMultipleAgents:
    """Tests for multiple agent display."""

    def test_multiple_agents_rendered(self):
        """Multiple agents should all be rendered in the table."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            },
            {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "port": 8110,
                "status": "PROCESSING",
                "transport": "-",
                "pid": 12346,
                "working_dir": "/home",
                "endpoint": "http://localhost:8110",
            },
            {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "status": "READY",
                "transport": "-",
                "pid": 12347,
                "working_dir": "/var",
                "endpoint": "http://localhost:8120",
            },
        ]

        table = renderer.build_table(agents)

        console.print(table)
        output = console.file.getvalue()

        assert "claude" in output
        assert "gemini" in output
        assert "codex" in output
        assert "8100" in output
        assert "8110" in output
        assert "8120" in output

    def test_multiple_agents_with_different_transport_states(self):
        """Multiple agents with different transport states."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "PROCESSING",
                "transport": "UDS→",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            },
            {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "port": 8110,
                "status": "PROCESSING",
                "transport": "→UDS",
                "pid": 12346,
                "working_dir": "/home",
                "endpoint": "http://localhost:8110",
            },
            {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "status": "READY",
                "transport": "-",
                "pid": 12347,
                "working_dir": "/var",
                "endpoint": "http://localhost:8120",
            },
        ]

        table = renderer.build_table(agents)

        console.print(table)
        output = console.file.getvalue()

        assert "UDS→" in output
        assert "→UDS" in output


class TestRichRendererFileSafety:
    """Tests for File Safety column display."""

    def test_editing_file_column_when_enabled(self):
        """Should show EDITING FILE column when show_file_safety=True."""
        console = Console(file=StringIO(), force_terminal=True, width=200)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "PROCESSING",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
                "editing_file": "test.py",
            }
        ]

        table = renderer.build_table(agents, show_file_safety=True)

        column_headers = [col.header for col in table.columns]
        assert "EDITING FILE" in column_headers

        console.print(table)
        output = console.file.getvalue()
        assert "test.py" in output

    def test_no_editing_file_column_when_disabled(self):
        """Should not show EDITING FILE column when show_file_safety=False."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents, show_file_safety=False)

        column_headers = [col.header for col in table.columns]
        assert "EDITING FILE" not in column_headers


class TestRichRendererFooter:
    """Tests for footer display."""

    def test_build_footer_contains_exit_hint(self):
        """Footer should contain q exit hint."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        footer = renderer.build_footer()

        console.print(footer)
        output = console.file.getvalue()

        assert "q" in output
        assert "exit" in output.lower()


class TestRichRendererStaleLocksWarning:
    """Tests for stale locks warning display."""

    def test_stale_locks_warning_displayed(self):
        """Stale locks warning should be displayed when present."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        stale_locks = [
            {"file_path": "/tmp/test.py", "pid": 99999, "agent_id": "dead-agent"}
        ]

        warning = renderer.build_stale_locks_warning(stale_locks)

        console.print(warning)
        output = console.file.getvalue()

        assert "stale" in output.lower()
        assert "1" in output  # count

    def test_no_warning_when_no_stale_locks(self):
        """No warning should be shown when there are no stale locks."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        warning = renderer.build_stale_locks_warning([])

        assert warning is None


class TestRichRendererInteractiveMode:
    """Tests for interactive mode with row selection."""

    def test_row_numbers_shown_when_interactive(self):
        """Row numbers should be shown when show_row_numbers=True."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents, show_row_numbers=True)

        column_headers = [col.header for col in table.columns]
        assert "#" in column_headers

    def test_row_numbers_hidden_when_not_interactive(self):
        """Row numbers should be hidden when show_row_numbers=False."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents, show_row_numbers=False)

        column_headers = [col.header for col in table.columns]
        assert "#" not in column_headers

    def test_selected_row_highlighted(self):
        """Selected row should have different styling."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            },
            {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "port": 8110,
                "status": "PROCESSING",
                "transport": "-",
                "pid": 12346,
                "working_dir": "/home",
                "endpoint": "http://localhost:8110",
            },
        ]

        table = renderer.build_table(agents, show_row_numbers=True, selected_row=1)

        console.print(table)
        output = console.file.getvalue()

        # Output should contain both agents
        assert "claude" in output
        assert "gemini" in output


class TestRichRendererDetailPanel:
    """Tests for detail panel display."""

    def test_detail_panel_shows_full_path(self):
        """Detail panel should show full working directory path."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agent = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "status": "READY",
            "pid": 12345,
            "working_dir": "/Volumes/SSD/ghq/github.com/s-hiraoku/very-long-path",
            "endpoint": "http://localhost:8100",
        }

        panel = renderer.build_detail_panel(agent)

        console.print(panel)
        output = console.file.getvalue()

        # Full path should be visible (not truncated)
        assert "very-long-path" in output
        assert "Agent Details" in output

    def test_detail_panel_includes_all_fields(self):
        """Detail panel should include all agent fields."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        agent = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "status": "READY",
            "pid": 12345,
            "working_dir": "/tmp",
            "endpoint": "http://localhost:8100",
            "transport": "UDS→",
        }

        panel = renderer.build_detail_panel(agent)

        console.print(panel)
        output = console.file.getvalue()

        assert "synapse-claude-8100" in output
        assert "claude" in output
        assert "8100" in output
        assert "READY" in output
        assert "12345" in output
        assert "UDS" in output


class TestRichRendererInteractiveFooter:
    """Tests for interactive footer."""

    def test_footer_shows_key_hints_when_interactive(self):
        """Footer should show number key hints in interactive mode."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        footer = renderer.build_footer(
            interactive=True, agent_count=3, has_selection=True
        )

        console.print(footer)
        output = console.file.getvalue()

        assert "1-3" in output
        assert "ESC" in output  # clear filter/selection
        assert "q" in output

    def test_footer_minimal_when_not_interactive(self):
        """Footer should be minimal in non-interactive mode."""
        console = Console(file=StringIO(), force_terminal=True)
        renderer = RichRenderer(console=console)

        footer = renderer.build_footer(interactive=False, agent_count=3)

        console.print(footer)
        output = console.file.getvalue()

        assert "q" in output
        assert "1-3" not in output


class TestRichRendererDisplayInteractive:
    """Tests for interactive display."""

    def test_display_with_selection(self):
        """Display should show detail panel when row selected."""
        console = Console(file=StringIO(), force_terminal=True, width=150)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/Volumes/SSD/ghq/github.com/full/path/here",
                "endpoint": "http://localhost:8100",
            }
        ]

        display = renderer.render_display(
            agents=agents,
            version="0.2.26",
            timestamp="2026-01-18 12:00:00",
            interactive=True,
            selected_row=1,
        )

        console.print(display)
        output = console.file.getvalue()

        # Should have both main table and detail panel
        assert "Synapse A2A" in output
        assert "Agent Details" in output
        assert "full/path/here" in output

    def test_display_without_selection(self):
        """Display should not show detail panel when no selection."""
        console = Console(file=StringIO(), force_terminal=True, width=150)
        renderer = RichRenderer(console=console)

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        ]

        display = renderer.render_display(
            agents=agents,
            version="0.2.26",
            timestamp="2026-01-18 12:00:00",
            interactive=True,
            selected_row=None,
        )

        console.print(display)
        output = console.file.getvalue()

        assert "Synapse A2A" in output
        assert "Agent Details" not in output
