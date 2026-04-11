"""Tests for token statistics in history (#5 Token/Cost Tracking)."""

import pytest


class TestGetTokenStatistics:
    """Tests for HistoryManager.get_token_statistics()."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a HistoryManager instance with a temporary database."""
        from synapse.history import HistoryManager

        db_path = str(tmp_path / "test_history.db")
        return HistoryManager(db_path=db_path, enabled=True)

    def test_get_token_statistics_empty(self, manager):
        """No observations → zero-value token stats."""
        stats = manager.get_token_statistics()
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0
        assert stats["total_cost_usd"] == 0.0
        assert stats["by_agent"] == {}

    def test_get_token_statistics_no_token_data(self, manager):
        """Observations without token metadata → zero-value stats."""
        manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="sess-1",
            input_text="hello",
            output_text="world",
            status="completed",
            metadata={"some_key": "value"},
        )
        stats = manager.get_token_statistics()
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0

    def test_get_token_statistics_with_data(self, manager):
        """Observations with token metadata should be aggregated."""
        manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="sess-1",
            input_text="hello",
            output_text="world",
            status="completed",
            metadata={
                "tokens": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cost_usd": 0.01,
                    "model": "claude-sonnet-4-20250514",
                }
            },
        )
        manager.save_observation(
            task_id="task-2",
            agent_name="claude",
            session_id="sess-1",
            input_text="foo",
            output_text="bar",
            status="completed",
            metadata={
                "tokens": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "cost_usd": 0.02,
                    "model": "claude-sonnet-4-20250514",
                }
            },
        )
        stats = manager.get_token_statistics()
        assert stats["total_input_tokens"] == 300
        assert stats["total_output_tokens"] == 150
        assert abs(stats["total_cost_usd"] - 0.03) < 1e-9

    def test_get_token_statistics_by_agent(self, manager):
        """Filtering by agent should only include that agent's tokens."""
        manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="sess-1",
            input_text="hello",
            output_text="world",
            status="completed",
            metadata={
                "tokens": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cost_usd": 0.01,
                    "model": None,
                }
            },
        )
        manager.save_observation(
            task_id="task-2",
            agent_name="gemini",
            session_id="sess-1",
            input_text="foo",
            output_text="bar",
            status="completed",
            metadata={
                "tokens": {
                    "input_tokens": 500,
                    "output_tokens": 300,
                    "cost_usd": 0.05,
                    "model": None,
                }
            },
        )
        stats = manager.get_token_statistics(agent_name="claude")
        assert stats["total_input_tokens"] == 100
        assert stats["total_output_tokens"] == 50
        assert abs(stats["total_cost_usd"] - 0.01) < 1e-9

    def test_get_token_statistics_by_agent_breakdown(self, manager):
        """Without agent filter, by_agent should contain per-agent breakdown."""
        manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="sess-1",
            input_text="hello",
            output_text="world",
            status="completed",
            metadata={
                "tokens": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cost_usd": 0.01,
                    "model": None,
                }
            },
        )
        manager.save_observation(
            task_id="task-2",
            agent_name="gemini",
            session_id="sess-1",
            input_text="foo",
            output_text="bar",
            status="completed",
            metadata={
                "tokens": {
                    "input_tokens": 500,
                    "output_tokens": 300,
                    "cost_usd": 0.05,
                    "model": None,
                }
            },
        )
        stats = manager.get_token_statistics()
        assert "claude" in stats["by_agent"]
        assert "gemini" in stats["by_agent"]
        assert stats["by_agent"]["claude"]["input_tokens"] == 100
        assert stats["by_agent"]["gemini"]["input_tokens"] == 500

    def test_get_token_statistics_disabled(self, tmp_path):
        """Disabled manager should return empty dict."""
        from synapse.history import HistoryManager

        manager = HistoryManager(db_path=str(tmp_path / "disabled.db"), enabled=False)
        stats = manager.get_token_statistics()
        assert stats == {}


class TestHistoryStatsDisplayTokens:
    """Test that cmd_history_stats shows token info when available."""

    def test_history_stats_display_tokens(self, capsys, tmp_path):
        """cmd_history_stats should display TOKEN USAGE section when data exists."""
        from unittest.mock import patch

        from synapse.history import HistoryManager

        manager = HistoryManager(db_path=str(tmp_path / "stats.db"), enabled=True)
        manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="sess-1",
            input_text="hello",
            output_text="world",
            status="completed",
            metadata={
                "tokens": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cost_usd": 0.05,
                    "model": None,
                }
            },
        )

        import argparse

        args = argparse.Namespace(agent=None)

        with patch(
            "synapse.commands.history._get_history_manager", return_value=manager
        ):
            from synapse.cli import cmd_history_stats

            cmd_history_stats(args)

        output = capsys.readouterr().out
        assert "TOKEN USAGE" in output
        assert "1,000" in output  # input tokens (formatted with comma)
        assert "500" in output  # output tokens

    def test_history_stats_no_tokens_no_section(self, capsys, tmp_path):
        """cmd_history_stats should NOT show TOKEN USAGE when no token data."""
        from unittest.mock import patch

        from synapse.history import HistoryManager

        manager = HistoryManager(db_path=str(tmp_path / "stats.db"), enabled=True)
        manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="sess-1",
            input_text="hello",
            output_text="world",
            status="completed",
        )

        import argparse

        args = argparse.Namespace(agent=None)

        with patch(
            "synapse.commands.history._get_history_manager", return_value=manager
        ):
            from synapse.cli import cmd_history_stats

            cmd_history_stats(args)

        output = capsys.readouterr().out
        assert "TOKEN USAGE" not in output
