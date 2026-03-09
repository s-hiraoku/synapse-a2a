"""Tests for canvas stop command — health-based PID detection."""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest


class TestCanvasStopViaHealth:
    """cmd_canvas_stop should find running server via health endpoint."""

    def test_stop_via_health_endpoint(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Server running (health returns pid) but no PID file → should still stop."""
        from synapse.cli import cmd_canvas_stop

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "pid": 12345, "cards": 3}

        with (
            patch("httpx.get", return_value=mock_resp),
            patch("synapse.commands.canvas.is_pid_alive", return_value=True),
            patch("os.kill") as mock_kill,
        ):
            args = argparse.Namespace(port=None)
            cmd_canvas_stop(args)

        mock_kill.assert_called_once()
        out = capsys.readouterr().out
        assert "12345" in out
        assert "Stopped" in out

    def test_stop_no_server_running(self, capsys: pytest.CaptureFixture[str]) -> None:
        """No server running → should print not running message."""
        from synapse.cli import cmd_canvas_stop

        with (
            patch("httpx.get", side_effect=httpx.ConnectError("refused")),
            patch("synapse.commands.canvas.read_pid_file", return_value=(None, None)),
        ):
            args = argparse.Namespace(port=None)
            cmd_canvas_stop(args)

        out = capsys.readouterr().out
        assert "not running" in out

    def test_stop_falls_back_to_pid_file(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Health reachable but no pid in response → fall back to PID file."""
        from synapse.cli import cmd_canvas_stop

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "cards": 0}

        pid_file = tmp_path / "canvas.pid"  # type: ignore[operator]
        pid_file.write_text(json.dumps({"pid": 99999, "port": 3000}))

        with (
            patch("httpx.get", return_value=mock_resp),
            patch("synapse.commands.canvas.PID_FILE", str(pid_file)),
            patch("synapse.commands.canvas.is_pid_alive", return_value=True),
            patch("os.kill") as mock_kill,
        ):
            args = argparse.Namespace(port=None)
            cmd_canvas_stop(args)

        mock_kill.assert_called_once()
        out = capsys.readouterr().out
        assert "99999" in out


class TestHealthEndpointIncludesPid:
    """The /api/health endpoint should include the server PID."""

    def test_health_returns_pid(self) -> None:
        from starlette.testclient import TestClient

        from synapse.canvas.server import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "pid" in data
        assert isinstance(data["pid"], int)
