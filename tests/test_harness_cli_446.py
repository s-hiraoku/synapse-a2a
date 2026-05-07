"""CLI wiring and behavior tests for `synapse harness` (#446/#489)."""

import subprocess
import sys
from argparse import Namespace
from pathlib import Path


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "synapse.cli", *args],
        capture_output=True,
        text=True,
    )


def test_harness_help_lists_package_manager_subcommands() -> None:
    result = _run_cli("harness", "--help")

    assert result.returncode == 0
    assert "Manage harness packages" in result.stdout
    for command in ("install", "list", "use", "enable", "disable", "remove"):
        assert command in result.stdout


def test_harness_disable_enable_and_remove_update_lockfile(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    from synapse.commands.harness_cmd import (
        cmd_harness_disable,
        cmd_harness_enable,
        cmd_harness_remove,
    )
    from synapse.harness import HarnessLock

    managed_file = tmp_path / "managed.txt"
    managed_file.write_text("managed", encoding="utf-8")
    lock = HarnessLock()
    lock.add_harness(
        "demo",
        "local:demo",
        "0.1.0",
        "abc",
        [str(managed_file)],
        1,
        True,
    )

    cmd_harness_disable(Namespace(name="demo"))
    assert lock.get_harness("demo")["enabled"] is False

    cmd_harness_enable(Namespace(name="demo"))
    assert lock.get_harness("demo")["enabled"] is True

    cmd_harness_remove(Namespace(name="demo", keep_files=False))
    assert lock.get_harness("demo") is None
    assert not managed_file.exists()
    assert "Removed demo" in capsys.readouterr().out
