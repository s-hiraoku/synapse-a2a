"""Tests for the doctor command."""

from __future__ import annotations

import argparse
import json
import socket
import sqlite3
from pathlib import Path

import pytest

from synapse.commands import doctor


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    data = {
        "root": tmp_path,
        "strict": False,
        "clean": False,
        "yes": False,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


@pytest.fixture
def passing_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor,
        "_run_checks",
        lambda root: [
            {
                "name": "Settings file",
                "status": "pass",
                "message": "Settings file (.synapse/settings.json)",
            }
        ],
    )


def test_doctor_reports_orphan_listeners(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passing_checks: None,
) -> None:
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(doctor, "PORT_RANGES", {"claude": (8100, 8100)})
    monkeypatch.setattr(doctor, "_is_tcp_listening", lambda port: True)
    monkeypatch.setattr(
        doctor,
        "_get_listener_process",
        lambda port: doctor.ListenerProcess(12345, "synapse claude --port 8100"),
    )

    doctor.cmd_doctor(_args(tmp_path))

    output = capsys.readouterr().out
    assert "Orphan listeners" in output
    assert "claude port=8100 pid=12345 command=synapse claude --port 8100" in output


def test_doctor_reports_stale_sockets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passing_checks: None,
) -> None:
    registry_dir = tmp_path / "registry"
    uds_dir = tmp_path / "uds"
    uds_dir.mkdir()
    (uds_dir / "synapse-claude-8100.sock").touch()
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("SYNAPSE_UDS_DIR", str(uds_dir))
    monkeypatch.setattr(doctor, "PORT_RANGES", {})

    doctor.cmd_doctor(_args(tmp_path))

    output = capsys.readouterr().out
    assert "Stale sockets" in output
    assert "synapse-claude-8100.sock" in output


def test_doctor_clean_removes_stale_sockets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passing_checks: None,
) -> None:
    uds_dir = tmp_path / "uds"
    uds_dir.mkdir()
    stale_socket = uds_dir / "synapse-claude-8100.sock"
    stale_socket.touch()
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("SYNAPSE_UDS_DIR", str(uds_dir))
    monkeypatch.setattr(doctor, "PORT_RANGES", {})

    doctor.cmd_doctor(_args(tmp_path, clean=True))

    output = capsys.readouterr().out
    assert not stale_socket.exists()
    assert "Cleaned 0 orphan processes, 1 stale sockets." in output


def test_doctor_clean_yes_skips_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passing_checks: None,
) -> None:
    terminated: list[int] = []
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("SYNAPSE_UDS_DIR", str(tmp_path / "uds"))
    monkeypatch.setattr(doctor, "PORT_RANGES", {"claude": (8100, 8100)})
    monkeypatch.setattr(doctor, "_is_tcp_listening", lambda port: True)
    monkeypatch.setattr(
        doctor,
        "_get_listener_process",
        lambda port: doctor.ListenerProcess(12345, "synapse claude --port 8100"),
    )
    monkeypatch.setattr(
        doctor, "_terminate_process", lambda pid: terminated.append(pid)
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: pytest.fail("prompt should be skipped by --yes"),
    )

    doctor.cmd_doctor(_args(tmp_path, clean=True, yes=True))

    output = capsys.readouterr().out
    assert terminated == [12345]
    assert "Cleaned 1 orphan processes, 0 stale sockets." in output


def test_doctor_strict_exits_1_on_orphans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, passing_checks: None
) -> None:
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(doctor, "PORT_RANGES", {"claude": (8100, 8100)})
    monkeypatch.setattr(doctor, "_is_tcp_listening", lambda port: True)
    monkeypatch.setattr(
        doctor,
        "_get_listener_process",
        lambda port: doctor.ListenerProcess(12345, "synapse claude --port 8100"),
    )

    with pytest.raises(SystemExit) as exc:
        doctor.cmd_doctor(_args(tmp_path, strict=True))

    assert exc.value.code == 1


def test_doctor_ignores_sockets_with_registry_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passing_checks: None,
) -> None:
    registry_dir = tmp_path / "registry"
    uds_dir = tmp_path / "uds"
    registry_dir.mkdir()
    uds_dir.mkdir()
    agent_id = "synapse-claude-8100"
    (uds_dir / f"{agent_id}.sock").touch()
    (registry_dir / f"{agent_id}.json").write_text(
        json.dumps({"agent_id": agent_id}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("SYNAPSE_UDS_DIR", str(uds_dir))
    monkeypatch.setattr(doctor, "PORT_RANGES", {})

    doctor.cmd_doctor(_args(tmp_path))

    output = capsys.readouterr().out
    assert "Stale sockets" not in output


def test_settings_file_check_passes_with_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir()
    (synapse_dir / "settings.json").write_text(json.dumps({"env": {}}))

    result = doctor.check_settings_file(tmp_path)

    assert result["status"] == "pass"


def test_settings_file_check_errors_when_missing(tmp_path: Path) -> None:
    result = doctor.check_settings_file(tmp_path)

    assert result["status"] == "error"
    assert "missing" in result["message"].lower()


def test_settings_file_check_errors_on_invalid_json(tmp_path: Path) -> None:
    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir()
    (synapse_dir / "settings.json").write_text("{invalid")

    result = doctor.check_settings_file(tmp_path)

    assert result["status"] == "error"
    assert "invalid" in result["message"].lower()


def test_skill_sync_check_passes_when_directories_match(tmp_path: Path) -> None:
    for relative in (
        "plugins/synapse-a2a/skills/demo/SKILL.md",
        ".claude/skills/demo/SKILL.md",
        ".agents/skills/demo/SKILL.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("same")

    result = doctor.check_skill_sync(tmp_path)

    assert result["status"] == "pass"


def test_skill_sync_check_warns_when_directories_differ(tmp_path: Path) -> None:
    plugin_file = tmp_path / "plugins/synapse-a2a/skills/demo/SKILL.md"
    claude_file = tmp_path / ".claude/skills/demo/SKILL.md"
    agents_file = tmp_path / ".agents/skills/demo/SKILL.md"
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    claude_file.parent.mkdir(parents=True, exist_ok=True)
    agents_file.parent.mkdir(parents=True, exist_ok=True)
    plugin_file.write_text("plugin")
    claude_file.write_text("plugin")
    agents_file.write_text("different")

    result = doctor.check_skill_sync(tmp_path)

    assert result["status"] == "warn"
    assert "out of sync" in result["message"].lower()


def test_port_check_reports_in_use_port(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_create_connection(
        address: tuple[str, int], timeout: float = 0.1
    ) -> socket.socket:
        if address[1] == 8100:
            raise OSError("in use")
        return object()  # type: ignore[return-value]

    monkeypatch.setattr("socket.create_connection", fake_create_connection)

    result = doctor.check_ports(8100, 8102)

    assert result["status"] == "warn"
    assert "8100" in result["message"]


def test_dependency_check_errors_when_uv_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        return None if name == "uv" else f"/usr/bin/{name}"

    monkeypatch.setattr("shutil.which", fake_which)

    result = doctor.check_dependencies()

    assert result["status"] == "error"
    assert "uv" in result["message"]


def test_database_integrity_passes_for_sqlite_files(tmp_path: Path) -> None:
    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir()
    for name in ("memory.db", "observations.db", "instincts.db"):
        conn = sqlite3.connect(synapse_dir / name)
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

    result = doctor.check_databases(tmp_path)

    assert result["status"] == "pass"


def test_cmd_doctor_exits_nonzero_on_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        doctor.cmd_doctor(_args(tmp_path))

    output = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "synapse doctor" in output.lower()
