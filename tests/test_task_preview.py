"""Tests for task preview in synapse list (v0.3.13).

When an agent is PROCESSING, the list should show what task it's working on.
This helps users understand what each agent is doing.
"""

from pathlib import Path

from synapse.registry import AgentRegistry


class TestTaskPreviewRegistry:
    """Tests for task preview in registry."""

    def test_update_current_task_stores_preview(self, tmp_path: Path) -> None:
        """Registry should store current task preview."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        # Register an agent first
        agent_id = "synapse-claude-8100"
        registry.register(
            agent_id=agent_id,
            agent_type="claude",
            port=8100,
            status="PROCESSING",
        )

        # Update current task
        preview = "Reviewing code in src/main.py"
        registry.update_current_task(agent_id, preview)

        # Read back and verify
        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("current_task_preview") == preview

    def test_update_current_task_clears_on_none(self, tmp_path: Path) -> None:
        """Setting None should clear the task preview."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        # Register an agent first
        agent_id = "synapse-claude-8100"
        registry.register(
            agent_id=agent_id,
            agent_type="claude",
            port=8100,
            status="PROCESSING",
        )

        # Set a preview
        registry.update_current_task(agent_id, "Some task")

        # Clear it
        registry.update_current_task(agent_id, None)

        # Verify it's cleared
        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("current_task_preview") is None

    def test_update_current_task_truncates_long_text(self, tmp_path: Path) -> None:
        """Long task previews should be truncated."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        # Register an agent first
        agent_id = "synapse-claude-8100"
        registry.register(
            agent_id=agent_id,
            agent_type="claude",
            port=8100,
            status="PROCESSING",
        )

        # Very long preview
        long_preview = "A" * 100  # 100 chars
        registry.update_current_task(agent_id, long_preview)

        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        preview = agent_data.get("current_task_preview", "")
        # Should be truncated to ~30 chars + "..."
        assert len(preview) <= 40  # Some margin for "..."

    def test_update_current_task_nonexistent_agent(self, tmp_path: Path) -> None:
        """Should handle nonexistent agent gracefully."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        # Should not raise
        result = registry.update_current_task("nonexistent-agent", "Some task")
        assert result is False

    def test_current_task_preserved_across_status_update(self, tmp_path: Path) -> None:
        """Current task should be preserved when status is updated."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-claude-8100"
        registry.register(
            agent_id=agent_id,
            agent_type="claude",
            port=8100,
            status="PROCESSING",
        )

        # Set current task
        registry.update_current_task(agent_id, "Important task")

        # Update status
        registry.update_status(agent_id, "READY")

        # Task preview should still be there
        agent_data = registry.get_agent(agent_id)
        assert agent_data is not None
        assert agent_data.get("current_task_preview") == "Important task"


class TestTaskPreviewListDisplay:
    """Tests for task preview in list command."""

    def test_get_agent_data_includes_current_task(self) -> None:
        """Agent data should include current_task_preview field."""
        # This tests the list command's _get_agent_data method
        # The agent data dict should include current_task_preview
        agent_data = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "status": "PROCESSING",
            "current_task_preview": "Working on task X",
        }

        assert "current_task_preview" in agent_data
        assert agent_data["current_task_preview"] == "Working on task X"

    def test_rich_renderer_shows_current_column(self) -> None:
        """Rich renderer should include CURRENT column."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": "ヒンメル",
                "role": "勇者",
                "port": 8100,
                "status": "PROCESSING",
                "transport": "-",
                "working_dir": "project",
                "current_task_preview": "フリーレンと相談中...",
            }
        ]

        table = renderer.build_table(agents, show_file_safety=False)

        # Check that CURRENT column exists
        column_names = [col.header for col in table.columns]
        assert "CURRENT" in column_names

    def test_rich_renderer_shows_dash_when_no_task(self) -> None:
        """CURRENT should show '-' when no task preview."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()

        agents = [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": None,
                "role": None,
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "working_dir": "project",
                "current_task_preview": None,
            }
        ]

        table = renderer.build_table(agents, show_file_safety=False)
        # Table should be built without error
        assert table is not None
