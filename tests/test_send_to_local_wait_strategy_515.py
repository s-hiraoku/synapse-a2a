"""Regression tests for send_to_local wait polling selection (#515)."""

from unittest.mock import patch

from synapse.a2a_client import A2AClient, A2ATask


class DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def _task_payload(task_id: str, status: str = "working") -> dict:
    return {"task": {"id": task_id, "status": status, "artifacts": []}}


def _completed_task(task_id: str = "completed-task") -> A2ATask:
    return A2ATask(id=task_id, status="completed", artifacts=[])


def test_polls_sender_when_sender_task_and_endpoint_present():
    client = A2AClient()
    sender_info = {
        "sender_endpoint": "http://localhost:8100",
        "sender_uds_path": "/tmp/sender.sock",
    }

    with (
        patch("synapse.a2a_client.Path.exists", return_value=False),
        patch("synapse.a2a_client.requests.post") as mock_post,
        patch.object(
            client,
            "_wait_for_local_completion",
            return_value=_completed_task("sender-task"),
        ) as mock_wait,
    ):
        mock_post.side_effect = [
            DummyResponse(_task_payload("sender-task")),
            DummyResponse(_task_payload("target-task")),
        ]

        task = client.send_to_local(
            endpoint="http://localhost:8124",
            message="hello",
            wait_for_completion=True,
            response_mode="wait",
            sender_info=sender_info,
        )

    assert task is not None
    assert task.id == "sender-task"
    mock_wait.assert_called_once_with(
        "http://localhost:8100",
        "sender-task",
        60,
        uds_path="/tmp/sender.sock",
    )


def test_polls_target_when_sender_endpoint_missing():
    client = A2AClient()
    sender_info = {
        "sender_endpoint": "http://localhost:8100",
        "sender_uds_path": "/tmp/sender.sock",
    }

    def post_side_effect(url, json=None, timeout=None):
        if url == "http://localhost:8100/tasks/create":
            sender_info["sender_endpoint"] = None
            return DummyResponse(_task_payload("sender-task"))
        return DummyResponse(_task_payload("target-task"))

    with (
        patch("synapse.a2a_client.Path.exists", return_value=False),
        patch("synapse.a2a_client.requests.post", side_effect=post_side_effect),
        patch.object(
            client,
            "_wait_for_local_completion",
            return_value=_completed_task("target-task"),
        ) as mock_wait,
    ):
        task = client.send_to_local(
            endpoint="http://localhost:8124",
            message="hello",
            wait_for_completion=True,
            response_mode="wait",
            sender_info=sender_info,
            uds_path="/tmp/target.sock",
        )

    assert task is not None
    assert task.id == "target-task"
    mock_wait.assert_called_once_with(
        "http://localhost:8124",
        "target-task",
        60,
        uds_path="/tmp/target.sock",
    )


def test_polls_target_when_no_sender_task_id():
    client = A2AClient()

    with (
        patch("synapse.a2a_client.requests.post") as mock_post,
        patch.object(
            client,
            "_wait_for_local_completion",
            return_value=_completed_task("target-task"),
        ) as mock_wait,
    ):
        mock_post.return_value = DummyResponse(_task_payload("target-task"))

        task = client.send_to_local(
            endpoint="http://localhost:8124",
            message="hello",
            wait_for_completion=True,
            response_mode="wait",
            sender_info=None,
        )

    assert task is not None
    assert task.id == "target-task"
    mock_wait.assert_called_once_with(
        "http://localhost:8124",
        "target-task",
        60,
        uds_path=None,
    )


def test_skip_polling_when_wait_disabled():
    client = A2AClient()

    with (
        patch("synapse.a2a_client.requests.post") as mock_post,
        patch.object(client, "_wait_for_local_completion") as mock_wait,
    ):
        mock_post.return_value = DummyResponse(_task_payload("target-task"))

        task = client.send_to_local(
            endpoint="http://localhost:8124",
            message="hello",
            wait_for_completion=False,
            response_mode="wait",
        )

    assert task is not None
    assert task.id == "target-task"
    mock_wait.assert_not_called()


def test_warning_logged_on_polling_timeout():
    client = A2AClient()

    with (
        patch("synapse.a2a_client.requests.post") as mock_post,
        patch.object(client, "_wait_for_local_completion", return_value=None),
        patch("synapse.a2a_client.logger.warning") as mock_warning,
    ):
        mock_post.return_value = DummyResponse(_task_payload("target-task"))

        task = client.send_to_local(
            endpoint="http://localhost:8124",
            message="hello",
            wait_for_completion=True,
            response_mode="wait",
            timeout=3,
        )

    assert task is not None
    assert task.id == "target-task"
    mock_warning.assert_called_once_with(
        "wait_for_completion=True but polling timed out at %s/tasks/%s; "
        "returning unfinished task",
        "http://localhost:8124",
        "target-task",
    )
