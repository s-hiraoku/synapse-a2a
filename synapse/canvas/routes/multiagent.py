"""Canvas routes for multi agent patterns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from synapse.canvas import server as server_module

multiagent_router = APIRouter()


@multiagent_router.get("/api/multiagent")
async def multiagent_list() -> dict[str, Any]:
    """List all defined multi agent patterns."""
    patterns: list[dict[str, Any]] = []
    try:
        from synapse.patterns.store import PatternStore

        store = PatternStore()
        for pattern in store.list_patterns():
            patterns.append(pattern)
    except Exception:
        server_module.logger.debug("Failed to list patterns", exc_info=True)
    return {"patterns": patterns, "project_dir": str(Path.cwd())}


@multiagent_router.get("/api/multiagent/runs")
async def multiagent_runs() -> dict[str, Any]:
    """List active and recent pattern runs."""
    from synapse.patterns.runner import get_runner

    runner = get_runner()
    runs = runner.get_runs()
    return {"runs": [run.to_dict() for run in runs]}


@multiagent_router.get("/api/multiagent/runs/{run_id}")
async def multiagent_run_status(run_id: str) -> dict[str, Any]:
    """Get status of a specific pattern run."""
    from synapse.patterns.runner import get_runner

    runner = get_runner()
    run = runner.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"run": run.to_dict()}


@multiagent_router.get("/api/multiagent/{name}")
async def multiagent_show(name: str) -> dict[str, Any]:
    """Get a single pattern definition by name."""
    from synapse.patterns.store import PatternStore

    store = PatternStore()
    try:
        config = store.load(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if config is None:
        raise HTTPException(status_code=404, detail=f"Pattern '{name}' not found")
    return {"pattern": config}
