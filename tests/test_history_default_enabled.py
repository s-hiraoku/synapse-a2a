"""Tests for history enabled by default (v0.3.13).

History should be enabled by default. Users can disable it explicitly
by setting SYNAPSE_HISTORY_ENABLED=false.
"""

import pytest

from synapse.history import HistoryManager


class TestHistoryDefaultEnabled:
    """Tests for history default enabled behavior."""

    def test_history_enabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """History should be enabled when env var is not set."""
        monkeypatch.delenv("SYNAPSE_HISTORY_ENABLED", raising=False)

        manager = HistoryManager.from_env(db_path="/tmp/test.db")
        assert manager.enabled is True

    def test_history_enabled_with_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """History should be enabled with SYNAPSE_HISTORY_ENABLED=true."""
        monkeypatch.setenv("SYNAPSE_HISTORY_ENABLED", "true")

        manager = HistoryManager.from_env(db_path="/tmp/test.db")
        assert manager.enabled is True

    def test_history_enabled_with_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """History should be enabled with SYNAPSE_HISTORY_ENABLED=1."""
        monkeypatch.setenv("SYNAPSE_HISTORY_ENABLED", "1")

        manager = HistoryManager.from_env(db_path="/tmp/test.db")
        assert manager.enabled is True

    def test_history_disabled_with_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """History should be disabled with SYNAPSE_HISTORY_ENABLED=false."""
        monkeypatch.setenv("SYNAPSE_HISTORY_ENABLED", "false")

        manager = HistoryManager.from_env(db_path="/tmp/test.db")
        assert manager.enabled is False

    def test_history_disabled_with_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """History should be disabled with SYNAPSE_HISTORY_ENABLED=0."""
        monkeypatch.setenv("SYNAPSE_HISTORY_ENABLED", "0")

        manager = HistoryManager.from_env(db_path="/tmp/test.db")
        assert manager.enabled is False

    def test_history_enabled_with_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """History should be enabled with empty string (not explicitly disabled)."""
        monkeypatch.setenv("SYNAPSE_HISTORY_ENABLED", "")

        manager = HistoryManager.from_env(db_path="/tmp/test.db")
        # Empty string is not "false" or "0", so it should be enabled
        assert manager.enabled is True

    def test_history_enabled_with_random_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """History should be enabled with any value except false/0."""
        monkeypatch.setenv("SYNAPSE_HISTORY_ENABLED", "yes")

        manager = HistoryManager.from_env(db_path="/tmp/test.db")
        assert manager.enabled is True

    def test_history_disabled_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FALSE and False should also disable history."""
        for value in ["FALSE", "False", "FaLsE"]:
            monkeypatch.setenv("SYNAPSE_HISTORY_ENABLED", value)

            manager = HistoryManager.from_env(db_path="/tmp/test.db")
            assert manager.enabled is False, f"Failed for value: {value}"
