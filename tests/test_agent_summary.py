"""Tests for agent summary feature (issue #472).

Agents can set a persistent summary describing what they're working on.
Unlike current_task_preview (30 chars, ephemeral), summary is longer (120 chars)
and persists until explicitly changed or cleared.
"""

from pathlib import Path

from synapse.registry import AgentRegistry


class TestSummaryRegistry:
    """Tests for summary in registry."""

    def test_update_summary_stores_value(self, tmp_path: Path) -> None:
        """Registry should store agent summary."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-claude-8100"
        registry.register(agent_id=agent_id, agent_type="claude", port=8100)

        summary = "Working on auth refactor for issue #123"
        result = registry.update_summary(agent_id, summary)

        assert result is True
        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("summary") == summary
        assert agent_data.get("summary_updated_at") is not None

    def test_update_summary_clears_on_none(self, tmp_path: Path) -> None:
        """Setting None should clear the summary."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-claude-8100"
        registry.register(agent_id=agent_id, agent_type="claude", port=8100)

        registry.update_summary(agent_id, "Some summary")
        registry.update_summary(agent_id, None)

        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("summary") is None
        assert agent_data.get("summary_updated_at") is None

    def test_update_summary_truncates_long_text(self, tmp_path: Path) -> None:
        """Summaries exceeding 120 chars should be truncated."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-claude-8100"
        registry.register(agent_id=agent_id, agent_type="claude", port=8100)

        long_summary = "A" * 200
        registry.update_summary(agent_id, long_summary)

        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        summary = agent_data.get("summary", "")
        # Should be truncated to 117 chars + "..."
        assert len(summary) <= 120
        assert summary.endswith("...")

    def test_update_summary_nonexistent_agent(self, tmp_path: Path) -> None:
        """Should return False for non-existent agent."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        result = registry.update_summary("nonexistent-agent", "Some summary")
        assert result is False

    def test_summary_preserved_across_status_update(self, tmp_path: Path) -> None:
        """Summary should be preserved when status is updated."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-claude-8100"
        registry.register(agent_id=agent_id, agent_type="claude", port=8100)

        registry.update_summary(agent_id, "Important work")
        registry.update_status(agent_id, "READY")

        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("summary") == "Important work"

    def test_summary_independent_of_current_task(self, tmp_path: Path) -> None:
        """Summary and current_task_preview should be independent fields."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-claude-8100"
        registry.register(agent_id=agent_id, agent_type="claude", port=8100)

        registry.update_summary(agent_id, "Auth refactor")
        registry.update_current_task(agent_id, "Reading file X")

        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("summary") == "Auth refactor"
        assert agent_data.get("current_task_preview") == "Reading file X"

        # Clearing task preview should not affect summary
        registry.update_current_task(agent_id, None)
        agent_data = registry.get_agent(agent_id)
        assert agent_data.get("summary") == "Auth refactor"

    def test_summary_update_overwrites_previous(self, tmp_path: Path) -> None:
        """Updating summary should overwrite the previous value."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-claude-8100"
        registry.register(agent_id=agent_id, agent_type="claude", port=8100)

        registry.update_summary(agent_id, "First summary")
        registry.update_summary(agent_id, "Second summary")

        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("summary") == "Second summary"


class TestSummaryListDisplay:
    """Tests for summary in list display."""

    def test_rich_renderer_summary_column_defined(self) -> None:
        """SUMMARY should be a valid column in the renderer."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        assert "SUMMARY" in RichRenderer.COLUMN_DEFS

    def test_rich_renderer_summary_column_renders(self) -> None:
        """SUMMARY column should render correctly in a table."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": "alice",
                "role": None,
                "port": 8100,
                "status": "PROCESSING",
                "transport": "-",
                "working_dir": "project",
                "current_task_preview": None,
                "summary": "Working on auth refactor",
            }
        ]

        table = renderer.build_table(
            agents, show_file_safety=False, columns=["ID", "SUMMARY"]
        )

        column_names = [col.header for col in table.columns]
        assert "SUMMARY" in column_names

    def test_rich_renderer_summary_not_in_defaults(self) -> None:
        """SUMMARY should NOT be in DEFAULT_COLUMNS (opt-in only)."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        assert "SUMMARY" not in RichRenderer.DEFAULT_COLUMNS
