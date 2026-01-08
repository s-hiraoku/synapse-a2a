"""Coverage tests for synapse/server.py."""

from unittest.mock import MagicMock, patch

import pytest

from synapse.server import (
    _get_standalone_task_store,
    _send_legacy_message,
    load_profile,
)


class TestServerCoverage:
    """Tests for missing coverage in server.py."""

    def test_load_profile_dict_error(self, tmp_path):
        """Test error when profile is not a dictionary (Lines 34-35)."""
        profile_file = tmp_path / "invalid.yaml"
        profile_file.write_text("- not a dict")

        with (
            patch("synapse.server.os.path.join", return_value=str(profile_file)),
            patch("synapse.server.os.path.exists", return_value=True),
            pytest.raises(ValueError, match="must be a dictionary"),
        ):
            load_profile("invalid")

    def test_send_legacy_message_no_ctrl(self):
        """Test error when controller is missing (Lines 194-196)."""
        task_store = MagicMock()
        msg = MagicMock()
        with pytest.raises(pytest.importorskip("fastapi").HTTPException) as exc:
            _send_legacy_message(None, task_store, msg, "\n")
        assert exc.value.status_code == 503

    def test_standalone_task_store_singleton(self):
        """Test singleton task store (Line 237)."""
        with patch("synapse.server.standalone_task_store", None):
            store1 = _get_standalone_task_store()
            store2 = _get_standalone_task_store()
            assert store1 is store2
            assert store1 is not None

    def test_send_legacy_message_write_failure(self):
        """Test write failure in legacy message (Lines 218-220)."""
        ctrl = MagicMock()
        ctrl.write.side_effect = Exception("write error")
        task_store = MagicMock()
        task = MagicMock()
        task.id = "t1"
        task_store.create.return_value = task

        msg = MagicMock()
        msg.content = "hello"
        msg.priority = 1

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _send_legacy_message(ctrl, task_store, msg, "\n")
        assert exc.value.status_code == 500
        task_store.update_status.assert_called_with("t1", "failed")
