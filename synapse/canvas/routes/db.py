from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

db_router = APIRouter()


def _get_synapse_dir() -> str:
    return os.environ.get("SYNAPSE_DIR", os.path.join(os.getcwd(), ".synapse"))


def _list_databases() -> list[dict[str, Any]]:
    synapse_dir = _get_synapse_dir()
    databases: list[dict[str, Any]] = []
    if not os.path.isdir(synapse_dir):
        return databases

    hidden_dbs = {"task_board.db"}
    for file_name in sorted(os.listdir(synapse_dir)):
        if not file_name.endswith(".db") or file_name in hidden_dbs:
            continue
        path = os.path.join(synapse_dir, file_name)
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
                tables = [
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                ]
            databases.append(
                {
                    "name": file_name,
                    "path": path,
                    "tables": tables,
                    "size": os.path.getsize(path),
                }
            )
        except Exception:
            continue
    return databases


@db_router.get("/api/db/list")
async def db_list() -> list[dict[str, Any]]:
    """List all SQLite databases in .synapse/."""
    return _list_databases()


@db_router.get("/api/db/{db_name}/{table_name}")
async def db_query(
    db_name: str,
    table_name: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Query rows from a table in a Synapse database (read-only)."""
    if not db_name.endswith(".db"):
        raise HTTPException(status_code=400, detail="Invalid database name")
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        raise HTTPException(status_code=400, detail="Invalid table name")

    db_path = os.path.join(_get_synapse_dir(), db_name)
    if not os.path.isfile(db_path):
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        with conn:
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
