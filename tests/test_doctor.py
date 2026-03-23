from __future__ import annotations

import json
import socket
import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest


def test_settings_file_check_passes_with_valid_json(
    tmp_path: Path, monkeypatch
) -> None:
    from synapse.commands.doctor import check_settings_file

    monkeypatch.chdir(tmp_path)
    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir()
    (synapse_dir / "settings.json").write_text(json.dumps({"env": {}}))

    result = check_settings_file(tmp_path)

    assert result["status"] == "pass"


def test_settings_file_check_errors_when_missing(tmp_path: Path) -> None:
    from synapse.commands.doctor import check_settings_file

    result = check_settings_file(tmp_path)

    assert result["status"] == "error"
    assert "missing" in result["message"].lower()


def test_settings_file_check_errors_on_invalid_json(tmp_path: Path) -> None:
    from synapse.commands.doctor import check_settings_file

    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir()
    (synapse_dir / "settings.json").write_text("{invalid")

    result = check_settings_file(tmp_path)

    assert result["status"] == "error"
    assert "invalid" in result["message"].lower()


def test_skill_sync_check_passes_when_directories_match(tmp_path: Path) -> None:
    from synapse.commands.doctor import check_skill_sync

    for relative in (
        "plugins/synapse-a2a/skills/demo/SKILL.md",
        ".claude/skills/demo/SKILL.md",
        ".agents/skills/demo/SKILL.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("same")

    result = check_skill_sync(tmp_path)

    assert result["status"] == "pass"


def test_skill_sync_check_warns_when_directories_differ(tmp_path: Path) -> None:
    from synapse.commands.doctor import check_skill_sync

    plugin_file = tmp_path / "plugins/synapse-a2a/skills/demo/SKILL.md"
    claude_file = tmp_path / ".claude/skills/demo/SKILL.md"
    agents_file = tmp_path / ".agents/skills/demo/SKILL.md"
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    claude_file.parent.mkdir(parents=True, exist_ok=True)
    agents_file.parent.mkdir(parents=True, exist_ok=True)
    plugin_file.write_text("plugin")
    claude_file.write_text("plugin")
    agents_file.write_text("different")

    result = check_skill_sync(tmp_path)

    assert result["status"] == "warn"
    assert "out of sync" in result["message"].lower()


def test_port_check_reports_in_use_port(monkeypatch) -> None:
    from synapse.commands.doctor import check_ports

    def fake_create_connection(
        address: tuple[str, int], timeout: float = 0.1
    ) -> socket.socket:
        if address[1] == 8100:
            raise OSError("in use")
        return object()  # type: ignore[return-value]

    monkeypatch.setattr("socket.create_connection", fake_create_connection)

    result = check_ports(8100, 8102)

    assert result["status"] == "warn"
    assert "8100" in result["message"]


def test_dependency_check_errors_when_uv_missing(monkeypatch) -> None:
    from synapse.commands.doctor import check_dependencies

    def fake_which(name: str) -> str | None:
        return None if name == "uv" else f"/usr/bin/{name}"

    monkeypatch.setattr("shutil.which", fake_which)

    result = check_dependencies()

    assert result["status"] == "error"
    assert "uv" in result["message"]


def test_database_integrity_passes_for_sqlite_files(tmp_path: Path) -> None:
    from synapse.commands.doctor import check_databases

    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir()
    for name in ("memory.db", "observations.db", "instincts.db"):
        conn = sqlite3.connect(synapse_dir / name)
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

    result = check_databases(tmp_path)

    assert result["status"] == "pass"


def test_cmd_doctor_exits_nonzero_on_error(tmp_path: Path, capsys) -> None:
    from synapse.commands.doctor import cmd_doctor

    with pytest.raises(SystemExit) as exc_info:
        cmd_doctor(Namespace(root=tmp_path))

    output = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "synapse doctor" in output.lower()
