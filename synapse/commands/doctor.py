"""Health checks for Synapse project setup."""

from __future__ import annotations

import json
import shutil
import socket
import sqlite3
from pathlib import Path
from typing import Any


def _result(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def check_settings_file(root: Path) -> dict[str, str]:
    """Validate the project settings file."""
    settings_path = root / ".synapse" / "settings.json"
    if not settings_path.exists():
        return _result("Settings file", "error", "Missing .synapse/settings.json")
    try:
        json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _result("Settings file", "error", "Invalid JSON in settings file")
    return _result("Settings file", "pass", "Settings file (.synapse/settings.json)")


def _collect_skill_files(base: Path) -> dict[str, str]:
    if not base.exists():
        return {}
    files: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(base))] = path.read_text(encoding="utf-8")
    return files


def check_skill_sync(root: Path) -> dict[str, str]:
    """Compare plugin skills against .claude and .agents copies."""
    plugin_files = _collect_skill_files(root / "plugins" / "synapse-a2a" / "skills")
    claude_files = _collect_skill_files(root / ".claude" / "skills")
    agents_files = _collect_skill_files(root / ".agents" / "skills")
    if plugin_files == claude_files == agents_files:
        return _result("Skill sync", "pass", "Skill sync (plugins → .claude → .agents)")
    return _result(
        "Skill sync",
        "warn",
        "Skill copies are out of sync across plugins/.claude/.agents",
    )


def check_ports(start: int = 8100, end: int = 8149) -> dict[str, str]:
    """Scan the Synapse agent port range for active listeners."""
    in_use: list[int] = []
    for port in range(start, end + 1):
        try:
            connection = socket.create_connection(("127.0.0.1", port), timeout=0.05)
        except OSError as exc:
            if "in use" in str(exc).lower():
                in_use.append(port)
            continue
        else:
            in_use.append(port)
            close = getattr(connection, "close", None)
            if callable(close):
                close()
    if not in_use:
        return _result("Port scan", "pass", f"Ports {start}-{end} available")
    ports = ", ".join(str(port) for port in in_use[:5])
    suffix = " ..." if len(in_use) > 5 else ""
    return _result("Port scan", "warn", f"Port {ports}{suffix}: in use")


def check_dependencies() -> dict[str, str]:
    """Check core runtime dependencies."""
    missing = [name for name in ("python", "uv") if shutil.which(name) is None]
    if missing:
        return _result(
            "Dependencies",
            "error",
            f"Missing dependencies: {', '.join(missing)}",
        )
    return _result("Dependencies", "pass", "Dependencies (python, uv)")


def check_cli_tools() -> dict[str, str]:
    """Report optional CLI tool availability."""
    tool_statuses = []
    for name in ("claude", "codex", "gemini", "opencode", "copilot"):
        tool_statuses.append(f"{name} {'✔' if shutil.which(name) else '✗'}")
    return _result("CLI tools", "info", f"CLI tools: {', '.join(tool_statuses)}")


def check_databases(root: Path) -> dict[str, str]:
    """Run a lightweight integrity check on known SQLite databases."""
    synapse_dir = root / ".synapse"
    db_names = ("memory.db", "observations.db", "instincts.db")
    for name in db_names:
        db_path = synapse_dir / name
        if not db_path.exists():
            continue
        conn = sqlite3.connect(db_path)
        try:
            status = conn.execute("PRAGMA quick_check").fetchone()
        finally:
            conn.close()
        if not status or status[0] != "ok":
            return _result(
                "Database integrity", "error", f"Database check failed: {name}"
            )
    return _result("Database integrity", "pass", "Database integrity")


def _format_symbol(status: str) -> str:
    return {
        "pass": "✔",
        "warn": "⚠",
        "error": "✖",
        "info": "ℹ",
    }[status]


def _run_checks(root: Path) -> list[dict[str, str]]:
    return [
        check_settings_file(root),
        check_skill_sync(root),
        check_ports(),
        check_dependencies(),
        check_cli_tools(),
        check_databases(root),
    ]


def cmd_doctor(args: Any) -> None:
    """Run health checks and report results."""
    root = Path(getattr(args, "root", Path.cwd()))
    results = _run_checks(root)

    print("Synapse Doctor")
    print("══════════════════════════════════════════")
    print()
    for item in results:
        print(f"  {_format_symbol(item['status'])} {item['message']}")

    passed = sum(1 for item in results if item["status"] == "pass")
    warnings = sum(1 for item in results if item["status"] == "warn")
    errors = sum(1 for item in results if item["status"] == "error")
    print()
    print(
        f"  Result: {len(results)} checks, {passed} passed, "
        f"{warnings} warning, {errors} errors"
    )

    if errors:
        raise SystemExit(1)
