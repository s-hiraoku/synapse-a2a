from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from synapse.canvas import server as server_module
from synapse.canvas.export import MAX_EXPORT_SIZE, export_card
from synapse.canvas.protocol import FORMAT_REGISTRY, CanvasMessage, validate_message

cards_router = APIRouter()


async def _enrich_link_previews(msg: CanvasMessage) -> None:
    """Enrich link-preview content blocks with OGP metadata."""
    from synapse.canvas.ogp import fetch_ogp

    blocks = msg.content if isinstance(msg.content, list) else [msg.content]
    targets: list[tuple[Any, dict[str, Any], str]] = []
    for block in blocks:
        if block.format != "link-preview":
            continue
        body = block.body
        if not isinstance(body, dict):
            continue
        url = body.get("url")
        if not url or not isinstance(url, str):
            continue
        if body.get("fetched"):
            continue
        targets.append((block, body, url))

    if not targets:
        return

    results = await asyncio.gather(
        *(fetch_ogp(url) for _, _, url in targets),
        return_exceptions=True,
    )
    for (block, body, _), result in zip(targets, results, strict=True):
        if isinstance(result, BaseException) or not isinstance(result, dict):
            continue
        body.update(result)
        block.body = body


@cards_router.post("/api/tips/consume")
async def consume_tip(request: Request) -> dict[str, Any]:
    """Delete a tip card after it has been displayed."""
    body = await request.json()
    card_id = body.get("card_id", "")
    if not card_id:
        raise HTTPException(status_code=400, detail="card_id is required")
    deleted = request.app.state.store.consume_tip(card_id)
    return {"consumed": deleted, "card_id": card_id}


@cards_router.post("/api/cards", status_code=201, response_model=None)
async def create_card(request: Request) -> Any:
    body = await request.json()
    msg = CanvasMessage.from_dict(body)

    errors = validate_message(msg)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    await _enrich_link_previews(msg)

    if isinstance(msg.content, list):
        content_json = json.dumps(
            [block.to_dict() for block in msg.content],
            ensure_ascii=False,
        )
    else:
        content_json = json.dumps(msg.content.to_dict(), ensure_ascii=False)

    store = request.app.state.store
    if msg.card_id:
        existing = store.get_card(msg.card_id)
        result = store.upsert_card(
            card_id=msg.card_id,
            agent_id=msg.agent_id,
            content=content_json,
            title=msg.title,
            agent_name=msg.agent_name or None,
            pinned=msg.pinned,
            tags=msg.tags or None,
            template=msg.template,
            template_data=msg.template_data or None,
        )
        if result is None:
            raise HTTPException(
                status_code=403,
                detail=f"Card '{msg.card_id}' is owned by a different agent",
            )
        if existing is not None:
            server_module._broadcast_event("card_updated", result)
            return JSONResponse(content=result, status_code=200)

        server_module._broadcast_event("card_created", result)
        return result

    result = store.add_card(
        agent_id=msg.agent_id,
        content=content_json,
        title=msg.title,
        agent_name=msg.agent_name or None,
        pinned=msg.pinned,
        tags=msg.tags or None,
        template=msg.template,
        template_data=msg.template_data or None,
    )
    server_module._broadcast_event("card_created", result)
    return result


@cards_router.get("/api/cards")
async def list_cards(
    request: Request,
    agent_id: str | None = None,
    search: str | None = None,
    type: str | None = None,
) -> list[dict[str, Any]]:
    cards = request.app.state.store.list_cards(
        agent_id=agent_id, search=search, content_type=type
    )
    return cast(list[dict[str, Any]], cards)


@cards_router.get("/api/cards/{card_id}")
async def get_card(card_id: str, request: Request) -> dict[str, Any]:
    card = request.app.state.store.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return cast(dict[str, Any], card)


@cards_router.get("/api/cards/{card_id}/download")
async def download_card(
    card_id: str,
    request: Request,
    format: str | None = None,
) -> Response:
    card = request.app.state.store.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    content_bytes, filename, content_type = export_card(card, target_format=format)
    if len(content_bytes) > MAX_EXPORT_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Export too large ({len(content_bytes)} bytes). "
                f"Maximum is {MAX_EXPORT_SIZE} bytes."
            ),
        )
    return Response(
        content=content_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@cards_router.delete("/api/cards/{card_id}")
async def delete_card(card_id: str, request: Request) -> dict[str, str]:
    agent_id = request.headers.get("X-Agent-Id", "")
    store = request.app.state.store
    card = store.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if card["agent_id"] != agent_id:
        raise HTTPException(
            status_code=403, detail="Cannot delete another agent's card"
        )
    store.delete_card(card_id, agent_id=agent_id)
    server_module._broadcast_event("card_deleted", {"card_id": card_id})
    return {"deleted": card_id}


@cards_router.delete("/api/cards")
async def clear_cards(
    request: Request,
    agent_id: str | None = None,
) -> dict[str, int]:
    caller_id = request.headers.get("X-Agent-Id", "")
    effective_agent_id = agent_id or caller_id or None
    count = request.app.state.store.clear_all(agent_id=effective_agent_id)
    return {"cleared": count}


@cards_router.get("/api/formats")
async def list_formats() -> dict[str, dict[str, Any]]:
    return {
        name: {"body_type": spec.body_type, "sandboxed": spec.sandboxed}
        for name, spec in FORMAT_REGISTRY.items()
    }
