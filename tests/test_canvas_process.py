"""Tests for Canvas server process management.

Covers: stale process detection, PID file management, health endpoint
verification, and asset version tracking.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

# ============================================================
# PID file — absolute path
# ============================================================


class TestPidFilePath:
    """PID_FILE should use a fixed absolute path so all CWDs share one PID."""

    def test_pid_file_is_absolute(self):
        from synapse.commands.canvas import PID_FILE

        assert os.path.isabs(PID_FILE), f"PID_FILE must be absolute, got: {PID_FILE}"

    def test_pid_file_under_user_synapse(self):
        from synapse.commands.canvas import PID_FILE

        assert "/.synapse/" in PID_FILE


# ============================================================
# Health endpoint — version and PID
# ============================================================


class TestHealthEndpoint:
    """GET /api/health should return pid and version."""

    def test_health_returns_pid(self):
        from starlette.testclient import TestClient

        from synapse.canvas.server import create_app

        app = create_app(db_path=":memory:")
        client = TestClient(app)
        resp = client.get("/api/health")
        data = resp.json()
        assert "pid" in data
        assert data["pid"] == os.getpid()

    def test_health_returns_version(self):
        from starlette.testclient import TestClient

        from synapse.canvas.server import create_app

        app = create_app(db_path=":memory:")
        client = TestClient(app)
        resp = client.get("/api/health")
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        # Version should look like a semver
        parts = data["version"].split(".")
        assert len(parts) >= 2


# ============================================================
# Status — PID mismatch detection
# ============================================================


class TestStatusMismatch:
    """canvas status should detect PID mismatch between health and PID file."""

    def test_detect_pid_mismatch(self, tmp_path, capsys):
        """When health PID != PID file PID, status should report mismatch."""
        from synapse.commands.canvas import write_pid_file

        pid_path = str(tmp_path / "canvas.pid")
        write_pid_file(pid_path, pid=11111, port=3000)

        # Mock health returning a different PID
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {
            "status": "ok",
            "pid": 22222,
            "version": "0.11.4",
            "cards": 0,
        }

        with (
            patch("synapse.commands.canvas.PID_FILE", pid_path),
            patch("httpx.get", return_value=health_resp),
            patch(
                "synapse.commands.canvas.is_canvas_server_running",
                return_value=True,
            ),
            patch("synapse.commands.canvas.is_pid_alive", return_value=True),
        ):
            from synapse.commands.canvas import canvas_status

            canvas_status(port=3000)

        out = capsys.readouterr().out
        assert "mismatch" in out.lower() or "MISMATCH" in out


# ============================================================
# Stop — port release verification
# ============================================================


class TestStopVerification:
    """canvas stop should verify the port is actually released."""

    def _mock_stop(self, tmp_path, pid=12345):
        """Helper: set up mocks for canvas_stop tests."""
        from synapse.commands.canvas import write_pid_file

        pid_path = str(tmp_path / "canvas.pid")
        write_pid_file(pid_path, pid=pid, port=3000)

        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"pid": pid}

        # is_pid_alive: True on first call (pre-kill check), False for all subsequent
        call_count = {"n": 0}

        def alive_side_effect(_pid):
            call_count["n"] += 1
            return call_count["n"] == 1  # True only on first call

        return pid_path, health_resp, alive_side_effect

    def test_stop_removes_pid_file(self, tmp_path):
        pid_path, health_resp, alive_calls = self._mock_stop(tmp_path)
        assert Path(pid_path).exists()

        with (
            patch("synapse.commands.canvas.PID_FILE", pid_path),
            patch("os.kill"),
            patch(
                "synapse.commands.canvas.is_pid_alive",
                side_effect=alive_calls,
            ),
            patch(
                "synapse.commands.canvas.is_canvas_server_running",
                return_value=False,
            ),
            patch(
                "synapse.commands.canvas._is_synapse_canvas_process",
                return_value=True,
            ),
            patch("synapse.commands.canvas.time.sleep"),
            patch("httpx.get", return_value=health_resp),
        ):
            from synapse.commands.canvas import canvas_stop

            canvas_stop(port=3000)

        assert not Path(pid_path).exists()

    def test_stop_verifies_port_released(self, tmp_path, capsys):
        """Stop should check health returns False after kill."""
        pid_path, health_resp, alive_calls = self._mock_stop(tmp_path, pid=99999)

        with (
            patch("synapse.commands.canvas.PID_FILE", pid_path),
            patch("os.kill"),
            patch(
                "synapse.commands.canvas.is_pid_alive",
                side_effect=alive_calls,
            ),
            patch(
                "synapse.commands.canvas.is_canvas_server_running",
                return_value=False,
            ),
            patch(
                "synapse.commands.canvas._is_synapse_canvas_process",
                return_value=True,
            ),
            patch("synapse.commands.canvas.time.sleep"),
            patch("httpx.get", return_value=health_resp),
        ):
            from synapse.commands.canvas import canvas_stop

            canvas_stop(port=3000)

        out = capsys.readouterr().out
        assert "Stopped" in out


# ============================================================
# Serve — stale process detection before startup
# ============================================================


class TestServeStaleDetection:
    """serve should detect and handle stale processes occupying the port."""

    def test_detect_stale_on_port(self):
        """_detect_stale_canvas should identify a stale synapse canvas process."""
        from synapse.commands.canvas import _detect_stale_canvas

        # Mock: health responds with a PID that doesn't match our PID file
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {
            "status": "ok",
            "pid": 55555,
            "version": "0.11.4",
        }

        with (
            patch("httpx.get", return_value=health_resp),
            patch(
                "synapse.commands.canvas._is_synapse_canvas_process",
                return_value=True,
            ),
            patch("synapse.commands.canvas.is_pid_alive", return_value=True),
        ):
            result = _detect_stale_canvas(port=3000)

        assert result is not None
        assert result["pid"] == 55555

    def test_no_stale_when_port_free(self):
        """No stale process when port is not in use."""
        import httpx

        from synapse.commands.canvas import _detect_stale_canvas

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            result = _detect_stale_canvas(port=3000)

        assert result is None


# ============================================================
# Process identity verification
# ============================================================


class TestProcessIdentity:
    """_is_synapse_canvas_process should verify process command line."""

    def test_identifies_canvas_process(self):
        """Should return True for synapse canvas serve command lines."""
        from synapse.commands.canvas import _is_synapse_canvas_process

        # Mock ps output to simulate a canvas process
        mock_result = MagicMock()
        mock_result.stdout = "python -m synapse.canvas --port 3000"
        with patch("subprocess.run", return_value=mock_result):
            assert _is_synapse_canvas_process(12345) is True

        # Mock ps output for a non-canvas process
        mock_result.stdout = "/usr/bin/python3 some_other_script.py"
        with patch("subprocess.run", return_value=mock_result):
            assert _is_synapse_canvas_process(12345) is False

    def test_handles_missing_pid(self):
        """Should return False when subprocess.run raises OSError."""
        from synapse.commands.canvas import _is_synapse_canvas_process

        with patch("subprocess.run", side_effect=OSError("No such process")):
            assert _is_synapse_canvas_process(12345) is False


# ============================================================
# ensure_server_running — returns port for callers
# ============================================================


class TestEnsureServerRunning:
    """is_canvas_server_running should query health endpoint."""

    def test_returns_true_when_healthy(self):
        from synapse.commands.canvas import is_canvas_server_running

        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"status": "ok"}

        with patch("httpx.get", return_value=health_resp):
            assert is_canvas_server_running(port=3000) is True

    def test_returns_false_when_unreachable(self):
        import httpx

        from synapse.commands.canvas import is_canvas_server_running

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert is_canvas_server_running(port=3000) is False

    def test_replaces_running_server_when_health_pid_mismatches_pid_file(self):
        from synapse.commands.canvas import ensure_server_running

        proc = MagicMock()
        proc.pid = 33333

        # After killing PID 22222, is_pid_alive should return False for it
        killed = set()

        def kill_side_effect(pid, sig_num):
            killed.add(pid)

        def alive_side_effect(pid):
            return pid not in killed

        with (
            patch(
                "synapse.commands.canvas._get_health",
                side_effect=[
                    {"service": "synapse-canvas", "pid": 22222},
                    None,
                ],
            ),
            patch(
                "synapse.commands.canvas.read_pid_file",
                side_effect=[(11111, 3000), (None, None)],
            ),
            patch(
                "synapse.commands.canvas.is_pid_alive",
                side_effect=alive_side_effect,
            ),
            patch(
                "synapse.commands.canvas._is_synapse_canvas_process",
                return_value=True,
            ),
            patch("synapse.commands.canvas._poll", return_value=True),
            patch("os.kill", side_effect=kill_side_effect) as mock_kill,
            patch("subprocess.Popen", return_value=proc) as mock_popen,
            patch("synapse.commands.canvas.write_pid_file") as mock_write_pid,
        ):
            assert ensure_server_running(port=3000) is True

        mock_kill.assert_called_once_with(22222, signal.SIGTERM)
        mock_popen.assert_called_once()
        mock_write_pid.assert_called_once_with(
            mock_write_pid.call_args.args[0],
            pid=33333,
            port=3000,
        )

    def test_starts_new_server_when_pid_file_points_to_live_non_canvas_process(self):
        from synapse.commands.canvas import ensure_server_running

        proc = MagicMock()
        proc.pid = 44444

        with (
            patch("synapse.commands.canvas._get_health", return_value=None),
            patch(
                "synapse.commands.canvas.read_pid_file",
                return_value=(99999, 3000),
            ),
            patch("synapse.commands.canvas.is_pid_alive", return_value=True),
            patch(
                "synapse.commands.canvas._is_synapse_canvas_process",
                return_value=False,
            ),
            patch("synapse.commands.canvas._detect_stale_canvas", return_value=None),
            patch("synapse.commands.canvas._poll", return_value=True),
            patch("subprocess.Popen", return_value=proc) as mock_popen,
            patch("synapse.commands.canvas.write_pid_file") as mock_write_pid,
        ):
            assert ensure_server_running(port=3000) is True

        mock_popen.assert_called_once()
        mock_write_pid.assert_called_once_with(
            mock_write_pid.call_args.args[0],
            pid=44444,
            port=3000,
        )
