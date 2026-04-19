"""Tests for the `synapse cleanup` command (issue #332)."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

# A PID virtually guaranteed not to map to a live process. INT32_MAX is
# above the kernel's max PID on every supported platform, so we can use it
# to simulate a dead parent without risking a hit on a real process.
_DEAD_PID = 2**31 - 1


def _install_kill_recorder(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Replace os.kill with a recorder that ignores signal-0 liveness probes.

    `is_process_running` uses `os.kill(pid, 0)` to test whether a PID is
    alive; we must not interfere with those probes (otherwise our DEAD
    parent PID would appear to be killable). Only record real signals.
    """
    real_kill = os.kill
    kills: list[int] = []

    def recorder(pid: int, sig: int) -> None:
        if sig == 0:
            # Pass through probes to the real OS so liveness checks work.
            real_kill(pid, sig)
            return
        kills.append(pid)

    monkeypatch.setattr(os, "kill", recorder)
    return kills


def _registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Build an isolated AgentRegistry in tmp_path."""
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path / "registry"))
    from synapse.registry import AgentRegistry

    return AgentRegistry()


def _write_agent(
    registry_dir: Path,
    agent_id: str,
    *,
    pid: int,
    spawned_by: str | None = None,
    status: str = "READY",
    status_changed_at: float | None = None,
) -> None:
    """Write a registry JSON entry directly (bypassing register())."""
    registry_dir.mkdir(parents=True, exist_ok=True)
    entry: dict[str, Any] = {
        "agent_id": agent_id,
        "agent_type": "claude",
        "port": 8100 + (hash(agent_id) % 50),
        "pid": pid,
        "status": status,
    }
    if spawned_by:
        entry["spawned_by"] = spawned_by
    if status_changed_at is not None:
        entry["status_changed_at"] = status_changed_at
    (registry_dir / f"{agent_id}.json").write_text(json.dumps(entry))


def _args(**overrides: Any) -> argparse.Namespace:
    data: dict[str, Any] = {
        "target": None,
        "dry_run": False,
        "force": True,  # tests run non-interactively; skip prompt
    }
    data.update(overrides)
    return argparse.Namespace(**data)


# ---------------------------------------------------------------------------
# Required tests from the spec
# ---------------------------------------------------------------------------


def test_cleanup_dry_run_lists_orphans_without_killing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`synapse cleanup --dry-run` reports orphans but never calls os.kill."""
    registry = _registry(monkeypatch, tmp_path)
    registry_dir = registry.registry_dir
    # Parent registered with a dead PID, so its child is an orphan.
    _write_agent(registry_dir, "synapse-codex-8100", pid=_DEAD_PID, status="READY")
    _write_agent(
        registry_dir,
        "synapse-claude-8200",
        pid=os.getpid(),  # child PID is alive
        spawned_by="synapse-codex-8100",
    )

    kills = _install_kill_recorder(monkeypatch)

    from synapse.commands import cleanup

    cleanup.cmd_cleanup(_args(dry_run=True))

    output = capsys.readouterr().out
    assert "synapse-claude-8200" in output
    assert "dry-run" in output.lower() or "would" in output.lower()
    assert kills == []  # nothing was actually killed
    # Registry entry must still exist after dry-run.
    assert (registry_dir / "synapse-claude-8200.json").exists()


def test_cleanup_kills_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`synapse cleanup` kills every orphan and unregisters them."""
    registry = _registry(monkeypatch, tmp_path)
    registry_dir = registry.registry_dir
    _write_agent(registry_dir, "synapse-codex-8100", pid=_DEAD_PID)
    _write_agent(
        registry_dir,
        "synapse-claude-8200",
        pid=12345,
        spawned_by="synapse-codex-8100",
    )
    _write_agent(
        registry_dir,
        "synapse-claude-8201",
        pid=12346,
        spawned_by="synapse-codex-8100",
    )

    kills = _install_kill_recorder(monkeypatch)

    from synapse.commands import cleanup

    cleanup.cmd_cleanup(_args())

    assert sorted(kills) == [12345, 12346]
    # Registry entries for orphans should be cleaned up.
    assert not (registry_dir / "synapse-claude-8200.json").exists()
    assert not (registry_dir / "synapse-claude-8201.json").exists()
    # Output should mention each agent.
    output = capsys.readouterr().out
    assert "synapse-claude-8200" in output
    assert "synapse-claude-8201" in output


def test_cleanup_specific_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`synapse cleanup <agent>` only kills the targeted orphan."""
    registry = _registry(monkeypatch, tmp_path)
    registry_dir = registry.registry_dir
    _write_agent(registry_dir, "synapse-codex-8100", pid=_DEAD_PID)
    _write_agent(
        registry_dir,
        "synapse-claude-8200",
        pid=12345,
        spawned_by="synapse-codex-8100",
    )
    _write_agent(
        registry_dir,
        "synapse-claude-8201",
        pid=12346,
        spawned_by="synapse-codex-8100",
    )

    kills = _install_kill_recorder(monkeypatch)

    from synapse.commands import cleanup

    cleanup.cmd_cleanup(_args(target="synapse-claude-8200"))

    assert kills == [12345]
    assert not (registry_dir / "synapse-claude-8200.json").exists()
    # Untargeted orphan must remain untouched.
    assert (registry_dir / "synapse-claude-8201.json").exists()


def test_cleanup_skips_non_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`synapse cleanup` refuses to kill agents whose parent is alive or absent (root)."""
    registry = _registry(monkeypatch, tmp_path)
    registry_dir = registry.registry_dir
    # Root agent has no spawned_by → never orphan.
    _write_agent(registry_dir, "synapse-claude-8100", pid=os.getpid())
    # Live parent + child → child is not orphan.
    _write_agent(registry_dir, "synapse-codex-8101", pid=os.getpid())
    _write_agent(
        registry_dir,
        "synapse-claude-8201",
        pid=12345,
        spawned_by="synapse-codex-8101",
    )

    kills = _install_kill_recorder(monkeypatch)

    from synapse.commands import cleanup

    cleanup.cmd_cleanup(_args())

    assert kills == []
    # Both entries remain.
    assert (registry_dir / "synapse-claude-8100.json").exists()
    assert (registry_dir / "synapse-claude-8201.json").exists()
    output = capsys.readouterr().out
    assert "no orphan" in output.lower() or "0 orphan" in output.lower()


def test_cleanup_specific_target_must_be_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`synapse cleanup <agent>` refuses non-orphan targets (preserve `synapse kill` semantics)."""
    registry = _registry(monkeypatch, tmp_path)
    registry_dir = registry.registry_dir
    _write_agent(registry_dir, "synapse-codex-8100", pid=os.getpid())  # alive parent
    _write_agent(
        registry_dir,
        "synapse-claude-8200",
        pid=12345,
        spawned_by="synapse-codex-8100",
    )

    kills = _install_kill_recorder(monkeypatch)

    from synapse.commands import cleanup

    with pytest.raises(SystemExit):
        cleanup.cmd_cleanup(_args(target="synapse-claude-8200"))

    assert kills == []
    output = capsys.readouterr().out
    assert "not an orphan" in output.lower() or "not orphan" in output.lower()


def test_idle_timeout_kills_long_ready_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SYNAPSE_ORPHAN_IDLE_TIMEOUT triggers opportunistic cleanup of long-READY orphans."""
    registry = _registry(monkeypatch, tmp_path)
    registry_dir = registry.registry_dir
    monkeypatch.setenv("SYNAPSE_ORPHAN_IDLE_TIMEOUT", "60")
    _write_agent(registry_dir, "synapse-codex-8100", pid=_DEAD_PID)
    # READY for ~5 minutes (well past the 60s timeout).
    _write_agent(
        registry_dir,
        "synapse-claude-8200",
        pid=12345,
        spawned_by="synapse-codex-8100",
        status="READY",
        status_changed_at=time.time() - 300,
    )
    # Fresh orphan: just transitioned to READY.
    _write_agent(
        registry_dir,
        "synapse-claude-8201",
        pid=12346,
        spawned_by="synapse-codex-8100",
        status="READY",
        status_changed_at=time.time(),
    )

    kills = _install_kill_recorder(monkeypatch)

    from synapse.commands import cleanup

    cleanup.opportunistic_cleanup_idle_orphans()

    # Stale orphan was killed; fresh orphan was not.
    assert kills == [12345]
    assert not (registry_dir / "synapse-claude-8200.json").exists()
    assert (registry_dir / "synapse-claude-8201.json").exists()


def test_idle_timeout_disabled_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without SYNAPSE_ORPHAN_IDLE_TIMEOUT set, opportunistic cleanup never kills."""
    registry = _registry(monkeypatch, tmp_path)
    registry_dir = registry.registry_dir
    monkeypatch.delenv("SYNAPSE_ORPHAN_IDLE_TIMEOUT", raising=False)
    _write_agent(registry_dir, "synapse-codex-8100", pid=_DEAD_PID)
    _write_agent(
        registry_dir,
        "synapse-claude-8200",
        pid=12345,
        spawned_by="synapse-codex-8100",
        status="READY",
        status_changed_at=time.time() - 999_999,
    )

    kills = _install_kill_recorder(monkeypatch)

    from synapse.commands import cleanup

    cleanup.opportunistic_cleanup_idle_orphans()
    assert kills == []
    assert (registry_dir / "synapse-claude-8200.json").exists()
