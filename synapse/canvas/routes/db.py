from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

db_router = APIRouter()


def _get_synapse_dir() -> str:
    return os.environ.get("SYNAPSE_DIR", os.path.join(os.getcwd(), ".synapse"))


def _get_global_synapse_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".synapse")


def _scan_db_files(base_dir: str) -> list[tuple[str, str]]:
    """Recursively find .db files under base_dir. Returns (relative_name, abs_path)."""
    results: list[tuple[str, str]] = []
    hidden_dbs = {"task_board.db"}
    skip_dirs = {"worktrees"}
    if not os.path.isdir(base_dir):
        return results
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in sorted(files):
            if not f.endswith(".db") or f in hidden_dbs:
                continue
            abs_path = os.path.join(root, f)
            rel = os.path.relpath(abs_path, base_dir)
            results.append((rel, abs_path))
    return results


def _list_databases() -> list[dict[str, Any]]:
    databases: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for scope, base_dir in [
        ("global", _get_global_synapse_dir()),
        ("project", _get_synapse_dir()),
    ]:
        for rel_name, abs_path in _scan_db_files(base_dir):
            real = os.path.realpath(abs_path)
            if real in seen_paths:
                continue
            seen_paths.add(real)
            try:
                with sqlite3.connect(f"file:{abs_path}?mode=ro", uri=True) as conn:
                    tables = [
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                        )
                    ]
                databases.append(
                    {
                        "name": rel_name,
                        "path": abs_path,
                        "tables": tables,
                        "size": os.path.getsize(abs_path),
                        "scope": scope,
                    }
                )
            except Exception:
                continue
    return databases


@db_router.get("/api/db/list")
async def db_list() -> list[dict[str, Any]]:
    """List all SQLite databases in .synapse/."""
    return _list_databases()


@db_router.get("/api/db/{db_name:path}/{table_name}")
async def db_query(
    db_name: str,
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    scope: str = "project",
) -> dict[str, Any]:
    """Query rows from a table in a Synapse database (read-only)."""
    if not db_name.endswith(".db"):
        raise HTTPException(status_code=400, detail="Invalid database name")
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        raise HTTPException(status_code=400, detail="Invalid table name")
    if scope not in ("project", "global"):
        raise HTTPException(status_code=400, detail="Invalid scope")

    base_dir = _get_global_synapse_dir() if scope == "global" else _get_synapse_dir()
    db_path = os.path.normpath(os.path.join(base_dir, db_name))
    # Prevent path traversal
    if not db_path.startswith(os.path.normpath(base_dir) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid database path")
    if not os.path.isfile(db_path):
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            columns = [
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table_name})")  # noqa: S608
            ]
            if not columns:
                raise HTTPException(
                    status_code=404, detail=f"Table '{table_name}' not found"
                )

            total = conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608
            ).fetchone()[0]
            rows = [
                dict(row)
                for row in conn.execute(
                    f"SELECT * FROM {table_name} LIMIT ? OFFSET ?",  # noqa: S608
                    (min(limit, 500), offset),
                )
            ]
    except sqlite3.OperationalError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "db": db_name,
        "table": table_name,
        "columns": columns,
        "rows": rows,
        "total": total,
        "limit": min(limit, 500),
        "offset": offset,
    }
