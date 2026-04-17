"""Tests for the ``GET /debug/pty`` A2A router endpoint.

This endpoint exposes the child agent's rendered virtual terminal so a
parent (or a human debugging waiting_detection misses) can see exactly
what text the waiting_detection regex is being evaluated against. This
is the Step A deliverable for issue #572.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import create_a2a_router
from synapse.pty_renderer import PtyRenderer


@pytest.fixture
def renderer_with_working_overlay() -> PtyRenderer:
    """Reproduce the Step D diagnostic capture: ratatui-style cursor
    motion with repeated "Working" overwrites plus a real prompt line.
    """
    r = PtyRenderer(columns=120, rows=24)
    r.feed(
        b"\x1b[H"
        + b"Working"
        + b"\x1b[H"
        + b"Working"
        + b"\x1b[3;1H"
        + b"\xe2\x96\xa0 You've hit your usage limit. Upgrade to Pro"
    )
    return r


@pytest.fixture
def controller(renderer_with_working_overlay: PtyRenderer) -> MagicMock:
    c = MagicMock()
    c.status = "PROCESSING"
    c.pty_snapshot = renderer_with_working_overlay.snapshot
    return c


@pytest.fixture
def client(controller: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(create_a2a_router(controller, "codex", 8126, "\n"))
    return TestClient(app)


class TestDebugPtyEndpoint:
    def test_returns_200_and_json(self, client: TestClient) -> None:
        response = client.get("/debug/pty")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    def test_returns_rendered_display(self, client: TestClient) -> None:
        """The rendered display must contain the clean final state,
        not the raw cursor-motion byte stream."""
        response = client.get("/debug/pty")
        body = response.json()
        assert "display" in body
        assert isinstance(body["display"], list)
        joined = "\n".join(body["display"])
        # The repeated "Working" overwrites must have collapsed:
        assert "Working•Working" not in joined
        # The real banner must be visible:
        assert "You've hit your usage limit" in joined

    def test_returns_cursor_position(self, client: TestClient) -> None:
        response = client.get("/debug/pty")
        body = response.json()
        assert "cursor" in body
        assert "x" in body["cursor"]
        assert "y" in body["cursor"]

    def test_returns_alt_screen_flag(self, client: TestClient) -> None:
        response = client.get("/debug/pty")
        body = response.json()
        assert body["alt_screen"] is False

    def test_returns_screen_dimensions(self, client: TestClient) -> None:
        response = client.get("/debug/pty")
        body = response.json()
        assert body["columns"] == 120
        assert body["rows"] == 24

    def test_handles_missing_controller(self) -> None:
        """When the router is created without a controller the endpoint
        should return 503 rather than crashing."""
        app = FastAPI()
        app.include_router(create_a2a_router(None, "codex", 8126, "\n"))
        client = TestClient(app)
        response = client.get("/debug/pty")
        assert response.status_code == 503

    def test_handles_controller_without_pty_snapshot(self) -> None:
        """Legacy controllers without a ``pty_snapshot`` method should
        degrade to 503 rather than 500."""
        legacy = MagicMock(spec=["status", "on_status_change"])
        legacy.status = "PROCESSING"
        app = FastAPI()
        app.include_router(create_a2a_router(legacy, "codex", 8126, "\n"))
        client = TestClient(app)
        response = client.get("/debug/pty")
        assert response.status_code == 503
