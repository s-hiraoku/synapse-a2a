"""
Tests for configurable list columns via settings.json.
"""

import json
from pathlib import Path

import pytest

from synapse.commands.renderers.rich_renderer import RichRenderer
from synapse.settings import DEFAULT_SETTINGS, SynapseSettings


class TestListColumnsSettings:
    """Tests for list column configuration in settings."""

    def test_default_columns_in_settings(self) -> None:
        """DEFAULT_SETTINGS should include list.columns."""
        assert "list" in DEFAULT_SETTINGS
        assert "columns" in DEFAULT_SETTINGS["list"]
        columns = DEFAULT_SETTINGS["list"]["columns"]
        assert isinstance(columns, list)
        assert len(columns) > 0

    def test_default_columns_order(self) -> None:
        """Default columns should be in expected order."""
        columns = DEFAULT_SETTINGS["list"]["columns"]
        expected = ["ID", "NAME", "STATUS", "CURRENT", "TRANSPORT", "WORKING_DIR"]
        assert columns == expected

    def test_synapse_settings_has_list_columns(self) -> None:
        """SynapseSettings should expose list columns."""
        settings = SynapseSettings.from_defaults()
        columns = settings.get_list_columns()
        assert columns == [
            "ID",
            "NAME",
            "STATUS",
            "CURRENT",
            "TRANSPORT",
            "WORKING_DIR",
        ]

    def test_custom_columns_from_settings_file(self, tmp_path: Path) -> None:
        """Custom columns from settings.json should override defaults."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"list": {"columns": ["ID", "STATUS", "NAME"]}})
        )

        settings = SynapseSettings.load(
            user_path=settings_file,
            project_path=tmp_path / "nonexistent.json",
        )
        columns = settings.get_list_columns()
        assert columns == ["ID", "STATUS", "NAME"]


class TestRichRendererColumns:
    """Tests for RichRenderer with configurable columns."""

    @pytest.fixture
    def renderer(self) -> RichRenderer:
        return RichRenderer()

    @pytest.fixture
    def sample_agents(self) -> list[dict]:
        return [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": "my-claude",
                "role": "code reviewer",
                "status": "READY",
                "current_task_preview": "Working on tests",
                "transport": "-",
                "working_dir": "synapse-a2a",
                "editing_file": "test.py",
            }
        ]

    def test_build_table_with_default_columns(
        self, renderer: RichRenderer, sample_agents: list[dict]
    ) -> None:
        """Table should use default columns when none specified."""
        table = renderer.build_table(sample_agents)
        column_names = [col.header for col in table.columns]
        assert "ID" in column_names
        assert "NAME" in column_names
        assert "STATUS" in column_names

    def test_build_table_with_custom_columns(
        self, renderer: RichRenderer, sample_agents: list[dict]
    ) -> None:
        """Table should use custom columns when specified."""
        custom_columns = ["ID", "STATUS"]
        table = renderer.build_table(sample_agents, columns=custom_columns)
        column_names = [col.header for col in table.columns]
        assert column_names == ["ID", "STATUS"]

    def test_build_table_with_all_available_columns(
        self, renderer: RichRenderer, sample_agents: list[dict]
    ) -> None:
        """All available columns should be renderable."""
        all_columns = [
            "ID",
            "NAME",
            "TYPE",
            "ROLE",
            "STATUS",
            "CURRENT",
            "TRANSPORT",
            "WORKING_DIR",
            "EDITING_FILE",
        ]
        table = renderer.build_table(
            sample_agents,
            columns=all_columns,
            show_file_safety=True,
        )
        column_names = [col.header for col in table.columns]
        assert "EDITING_FILE" in column_names

    def test_build_table_ignores_unknown_columns(
        self, renderer: RichRenderer, sample_agents: list[dict]
    ) -> None:
        """Unknown column names should be ignored gracefully."""
        columns = ["ID", "UNKNOWN_COLUMN", "STATUS"]
        table = renderer.build_table(sample_agents, columns=columns)
        column_names = [col.header for col in table.columns]
        assert "ID" in column_names
        assert "STATUS" in column_names
        assert "UNKNOWN_COLUMN" not in column_names

    def test_build_table_empty_columns_uses_default(
        self, renderer: RichRenderer, sample_agents: list[dict]
    ) -> None:
        """Empty columns list should fall back to defaults."""
        table = renderer.build_table(sample_agents, columns=[])
        column_names = [col.header for col in table.columns]
        assert len(column_names) > 0  # Should have default columns

    def test_editing_file_only_shown_when_file_safety_enabled(
        self, renderer: RichRenderer, sample_agents: list[dict]
    ) -> None:
        """EDITING_FILE column only shown when show_file_safety=True."""
        columns = ["ID", "EDITING_FILE"]

        # Without file safety enabled
        table = renderer.build_table(
            sample_agents, columns=columns, show_file_safety=False
        )
        column_names = [col.header for col in table.columns]
        assert "ID" in column_names
        assert "EDITING_FILE" not in column_names

        # With file safety enabled
        table = renderer.build_table(
            sample_agents, columns=columns, show_file_safety=True
        )
        column_names = [col.header for col in table.columns]
        assert "ID" in column_names
        assert "EDITING_FILE" in column_names
