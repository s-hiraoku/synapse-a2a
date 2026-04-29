"""Pure unit tests for _resolve_polling_endpoint (#686, follow-up to PR #676 / #515).

The helper at synapse/a2a_client.py:36 was extracted by PR #676 as a
pure function deciding which (endpoint, uds_path, task_id) triple
``send_to_local`` should poll for ``wait_for_completion``. It is
already covered indirectly by ``tests/test_send_to_local_wait_strategy_515.py``
through full ``send_to_local()`` invocations with mocked HTTP, but no
test exercises the helper directly. These tests close that gap so a
future regression in the input→output mapping fails fast without
requiring the integration mocks.
"""

from synapse.a2a_client import _resolve_polling_endpoint


def test_returns_sender_when_task_id_and_endpoint_present():
    sender_info = {
        "sender_endpoint": "http://localhost:8100",
        "sender_uds_path": "/tmp/sender.sock",
    }
    endpoint, uds, task_id = _resolve_polling_endpoint(
        sender_task_id="sender-task",
        sender_info=sender_info,
        target_endpoint="http://localhost:8124",
        target_uds_path="/tmp/target.sock",
        target_task_id="target-task",
    )
    assert endpoint == "http://localhost:8100"
    assert uds == "/tmp/sender.sock"
    assert task_id == "sender-task"


def test_returns_target_when_sender_endpoint_missing():
    """sender_task_id present but sender_info has no sender_endpoint
    falls back to target polling — the silent-skip case PR #676 closed."""
    sender_info = {"sender_endpoint": None, "sender_uds_path": "/tmp/sender.sock"}
    endpoint, uds, task_id = _resolve_polling_endpoint(
        sender_task_id="sender-task",
        sender_info=sender_info,
        target_endpoint="http://localhost:8124",
        target_uds_path="/tmp/target.sock",
        target_task_id="target-task",
    )
    assert endpoint == "http://localhost:8124"
    assert uds == "/tmp/target.sock"
    assert task_id == "target-task"


def test_returns_target_when_no_sender_task_id():
    """sender_task_id absent (workflow subprocess case from PR #513) falls
    back to target polling regardless of what sender_info contains."""
    sender_info = {
        "sender_endpoint": "http://localhost:8100",
        "sender_uds_path": "/tmp/sender.sock",
    }
    endpoint, uds, task_id = _resolve_polling_endpoint(
        sender_task_id=None,
        sender_info=sender_info,
        target_endpoint="http://localhost:8124",
        target_uds_path="/tmp/target.sock",
        target_task_id="target-task",
    )
    assert endpoint == "http://localhost:8124"
    assert uds == "/tmp/target.sock"
    assert task_id == "target-task"


def test_returns_target_when_sender_info_none():
    endpoint, uds, task_id = _resolve_polling_endpoint(
        sender_task_id="sender-task",
        sender_info=None,
        target_endpoint="http://localhost:8124",
        target_uds_path="/tmp/target.sock",
        target_task_id="target-task",
    )
    assert endpoint == "http://localhost:8124"
    assert uds == "/tmp/target.sock"
    assert task_id == "target-task"


def test_sender_uds_path_passthrough():
    """When the sender path is selected, the sender's uds_path (not the
    target's) is returned alongside the sender endpoint."""
    sender_info = {
        "sender_endpoint": "http://localhost:8100",
        "sender_uds_path": "/tmp/SENDER.sock",
    }
    _, uds, _ = _resolve_polling_endpoint(
        sender_task_id="sender-task",
        sender_info=sender_info,
        target_endpoint="http://localhost:8124",
        target_uds_path="/tmp/TARGET.sock",
        target_task_id="target-task",
    )
    assert uds == "/tmp/SENDER.sock"
