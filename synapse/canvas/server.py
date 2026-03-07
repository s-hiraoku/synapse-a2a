"""Canvas Server — FastAPI application with SSE and HTML serving.

A dedicated server (default port 3000) that renders agent-posted cards
in the browser with real-time updates via Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from synapse.canvas.protocol import (
    FORMAT_REGISTRY,
    CanvasMessage,
    validate_message,
)
from synapse.canvas.store import CanvasStore

logger = logging.getLogger(__name__)

# SSE event queue for broadcasting to connected clients
_sse_queues: list[asyncio.Queue[str]] = []


def _broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an SSE event to all connected clients."""
    payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    for q in _sse_queues:
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(payload)


CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


def create_app(db_path: str | None = None) -> FastAPI:
    """Create and configure the Canvas FastAPI app."""
    store = CanvasStore(db_path=db_path)

    async def _cleanup_loop() -> None:
        """Periodically remove expired cards."""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            removed = store.cleanup_expired()
            if removed:
                logger.info("Auto-cleanup removed %d expired card(s)", removed)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        task = asyncio.create_task(_cleanup_loop())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Synapse Canvas", lifespan=lifespan)

    # Store reference for access in endpoints
    app.state.store = store

    # Static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ----------------------------------------------------------------
    # GET / — Main HTML page
    # ----------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        template_path = Path(__file__).parent / "templates" / "index.html"
        if template_path.exists():
            return HTMLResponse(template_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Synapse Canvas</h1><p>Template not found.</p>")

    # ----------------------------------------------------------------
    # GET /api/health
    # ----------------------------------------------------------------
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "cards": store.count()}

    # ----------------------------------------------------------------
    # POST /api/cards — Create or update card
    # ----------------------------------------------------------------
    @app.post("/api/cards", status_code=201, response_model=None)
    async def create_card(request: Request) -> Any:
        body = await request.json()
        msg = CanvasMessage.from_dict(body)

        errors = validate_message(msg)
        if errors:
            raise HTTPException(status_code=422, detail=errors)

        # Serialize content to JSON string for storage
        if isinstance(msg.content, list):
            content_json = json.dumps(
                [
                    {
                        "format": b.format,
                        "body": b.body,
                        **({"lang": b.lang} if b.lang else {}),
                    }
                    for b in msg.content
                ],
                ensure_ascii=False,
            )
        else:
            d: dict[str, Any] = {"format": msg.content.format, "body": msg.content.body}
            if msg.content.lang:
                d["lang"] = msg.content.lang
            content_json = json.dumps(d, ensure_ascii=False)

        if msg.card_id:
            # Check if card already exists (for status code decision)
            existing = store.get_card(msg.card_id)

            result = store.upsert_card(
                card_id=msg.card_id,
                agent_id=msg.agent_id,
                content=content_json,
                title=msg.title,
                agent_name=msg.agent_name or None,
                pinned=msg.pinned,
                tags=msg.tags or None,
            )
            if result is None:
                raise HTTPException(
                    status_code=403,
                    detail=f"Card '{msg.card_id}' is owned by a different agent",
                )
            if existing is not None:
                _broadcast_event("card_updated", result)
                return JSONResponse(content=result, status_code=200)
            else:
                _broadcast_event("card_created", result)
                return result
        else:
            # Create new
            result = store.add_card(
                agent_id=msg.agent_id,
                content=content_json,
                title=msg.title,
                agent_name=msg.agent_name or None,
                pinned=msg.pinned,
                tags=msg.tags or None,
            )
            _broadcast_event("card_created", result)
            return result

    # ----------------------------------------------------------------
    # GET /api/cards — List cards
    # ----------------------------------------------------------------
    @app.get("/api/cards")
    async def list_cards(
        agent_id: str | None = None,
        search: str | None = None,
        type: str | None = None,
    ) -> list[dict[str, Any]]:
        return store.list_cards(
            agent_id=agent_id,
            search=search,
            content_type=type,
        )

    # ----------------------------------------------------------------
    # GET /api/cards/{card_id} — Get single card
    # ----------------------------------------------------------------
    @app.get("/api/cards/{card_id}")
    async def get_card(card_id: str) -> dict[str, Any]:
        card = store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        return card

    # ----------------------------------------------------------------
    # DELETE /api/cards/{card_id} — Delete card
    # ----------------------------------------------------------------
    @app.delete("/api/cards/{card_id}")
    async def delete_card(card_id: str, request: Request) -> dict[str, str]:
        agent_id = request.headers.get("X-Agent-Id", "")
        card = store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        if card["agent_id"] != agent_id:
            raise HTTPException(
                status_code=403, detail="Cannot delete another agent's card"
            )
        store.delete_card(card_id, agent_id=agent_id)
        _broadcast_event("card_deleted", {"card_id": card_id})
        return {"deleted": card_id}

    # ----------------------------------------------------------------
    # DELETE /api/cards — Clear cards
    # ----------------------------------------------------------------
    @app.delete("/api/cards")
    async def clear_cards(agent_id: str | None = None) -> dict[str, int]:
        count = store.clear_all(agent_id=agent_id)
        return {"cleared": count}

    # ----------------------------------------------------------------
    # GET /api/formats — List supported formats
    # ----------------------------------------------------------------
    @app.get("/api/formats")
    async def list_formats() -> dict[str, dict[str, Any]]:
        return {
            name: {"body_type": spec.body_type, "sandboxed": spec.sandboxed}
            for name, spec in FORMAT_REGISTRY.items()
        }

    # ----------------------------------------------------------------
    # GET /api/stream — SSE endpoint
    # ----------------------------------------------------------------
    @app.get("/api/stream")
    async def stream() -> StreamingResponse:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        _sse_queues.append(queue)

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                # Send initial keepalive
                yield ": keepalive\n\n"
                while True:
                    payload = await queue.get()
                    yield payload
            except asyncio.CancelledError:
                pass
            finally:
                _sse_queues.remove(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
