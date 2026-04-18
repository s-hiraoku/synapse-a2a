"""Health checks for Synapse project setup."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse.port_manager import PORT_RANGES
from synapse.registry import AgentRegistry, is_process_running


@dataclass(frozen=True)
class ListenerProcess:
    """Process that owns a listening TCP port."""

    pid: int
    command: str


@dataclass(frozen=True)
class OrphanListener:
    """Listening managed port that has no matching live registry entry."""

    agent_type: str
    port: int
    process: ListenerProcess | None


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


def _truncate_command(command: str, max_len: int = 120) -> str:
    command = " ".join(command.split())
    if len(command) <= max_len:
        return command
    return f"{command[: max_len - 3]}..."


def _command_for_pid(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read().replace(b"\0", b" ").strip()
        if raw:
            return _truncate_command(raw.decode(errors="replace"))
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "?"

    command = result.stdout.strip()
    return _truncate_command(command) if command else "?"


def _get_listener_process_psutil(port: int) -> ListenerProcess | None:
    try:
        import psutil
    except ImportError:
        return None

    try:
        connections = psutil.net_connections(kind="inet")
    except (OSError, psutil.Error):
        return None

    listen_status = getattr(psutil, "CONN_LISTEN", "LISTEN")
    for conn in connections:
        laddr = getattr(conn, "laddr", None)
        if not laddr or getattr(laddr, "port", None) != port:
            continue
        host = getattr(laddr, "ip", "")
        if host not in ("127.0.0.1", "0.0.0.0", "::1", "::", ""):
            continue
        if getattr(conn, "status", None) != listen_status or conn.pid is None:
            continue

        try:
            proc = psutil.Process(conn.pid)
            command = " ".join(proc.cmdline()) or proc.name()
        except (OSError, psutil.Error):
            command = _command_for_pid(conn.pid)
        return ListenerProcess(conn.pid, _truncate_command(command))

    return None


def _get_listener_process_lsof(port: int) -> ListenerProcess | None:
    if shutil.which("lsof") is None:
        return None
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-F", "pc"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    pid: int | None = None
    command = "?"
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            with contextlib.suppress(ValueError):
                pid = int(line[1:])
        elif line.startswith("c") and line[1:]:
            command = line[1:]

    if pid is None:
        return None
    if command == "?":
        command = _command_for_pid(pid)
    return ListenerProcess(pid, _truncate_command(command))


def _get_listener_process(port: int) -> ListenerProcess | None:
    return _get_listener_process_psutil(port) or _get_listener_process_lsof(port)


def _is_tcp_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.05):
            return True
    except OSError:
        return False


def _live_registry_pids(agents: dict[str, dict]) -> set[int]:
    pids = set()
    for info in agents.values():
        pid = info.get("pid")
        if isinstance(pid, int) and is_process_running(pid):
            pids.add(pid)
    return pids


def _find_orphan_listeners(registry: AgentRegistry) -> list[OrphanListener]:
    agents = registry.list_agents()
    live_registry_pids = _live_registry_pids(agents)
    by_port: dict[int, list[tuple[str, dict]]] = {}
    for agent_id, info in agents.items():
        port = info.get("port")
        if isinstance(port, int):
            by_port.setdefault(port, []).append((agent_id, info))

    orphans: list[OrphanListener] = []
    for agent_type, (start, end) in PORT_RANGES.items():
        for port in range(start, end + 1):
            if not _is_tcp_listening(port):
                continue

            process = _get_listener_process(port)
            listener_pid = process.pid if process else None
            registered = by_port.get(port, [])
            has_matching_live_registry = False
            for _, info in registered:
                pid = info.get("pid")
                if (
                    isinstance(pid, int)
                    and is_process_running(pid)
                    and (listener_pid is None or pid == listener_pid)
                ):
                    has_matching_live_registry = True
                    break

            if has_matching_live_registry:
                continue
            if listener_pid is not None and listener_pid in live_registry_pids:
                continue
            orphans.append(OrphanListener(agent_type, port, process))

    return orphans


def _uds_dir() -> Path:
    return Path(os.environ.get("SYNAPSE_UDS_DIR", "/tmp/synapse-a2a"))


def _find_stale_sockets(registry: AgentRegistry) -> list[Path]:
    uds_dir = _uds_dir()
    if not uds_dir.exists():
        return []
    registry_files = {path.stem for path in registry.registry_dir.glob("*.json")}
    return sorted(
        path
        for path in uds_dir.glob("*.sock")
        if path.is_socket() or path.is_file()
        if path.stem not in registry_files
    )


def _terminate_process(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.time() + 5
    while time.time() < deadline:
        if not is_process_running(pid):
            return
        time.sleep(0.1)

    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


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
    strict = bool(getattr(args, "strict", False))
    clean = bool(getattr(args, "clean", False))
    yes = bool(getattr(args, "yes", False))
    registry = AgentRegistry()
    results = _run_checks(root)
    orphan_listeners = _find_orphan_listeners(registry)
    stale_sockets = _find_stale_sockets(registry)

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

    if orphan_listeners:
        print()
        print("Orphan listeners:")
        for orphan in orphan_listeners:
            process = orphan.process
            pid = process.pid if process else "?"
            command = process.command if process else "?"
            print(
                f"  {orphan.agent_type} port={orphan.port} pid={pid} command={command}"
            )

    if stale_sockets:
        print()
        print("Stale sockets:")
        for path in stale_sockets:
            print(f"  {path}")

    cleaned_processes = 0
    cleaned_sockets = 0
    if clean:
        print()
        for orphan in orphan_listeners:
            process = orphan.process
            if process is None:
                print(
                    f"Skipping port {orphan.port}: listener PID could not be resolved"
                )
                continue
            print(
                f"Orphan listener {orphan.agent_type} port={orphan.port} "
                f"pid={process.pid} command={process.command}"
            )
            if not yes:
                answer = input("Terminate this orphan process? [y/N] ")
                if answer.strip().lower() not in ("y", "yes"):
                    continue
            _terminate_process(process.pid)
            cleaned_processes += 1

        for path in stale_sockets:
            with contextlib.suppress(OSError):
                path.unlink()
                cleaned_sockets += 1

        print(
            f"Cleaned {cleaned_processes} orphan processes, {cleaned_sockets} stale sockets."
        )

    if errors:
        raise SystemExit(1)
    if strict and (orphan_listeners or stale_sockets):
        raise SystemExit(1)
