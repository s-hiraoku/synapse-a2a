"""Regression tests for issue #715 — parallel spawn port allocation race.

These tests reproduce the race window where two parallel spawns can both
receive the same free port from PortManager.get_available_port() and then
both attempt to AgentRegistry.register() against the same port file, with
the second write silently overwriting the first.

The fix is an atomic API (PortManager.allocate_and_register) that takes
AgentRegistry.registry_write_lock() (cross-process flock) for both the
free-port discovery and the placeholder registration.

multiprocessing.Process is required: threading would run a single fcntl
flock holder in-process so the cross-process serialization being tested
would be a no-op.
"""

from __future__ import annotations

import multiprocessing as mp
import os

import pytest

from synapse.port_manager import PORT_RANGES, PortManager
from synapse.registry import AgentRegistry, NameConflictError

# macOS defaults to "spawn" since Python 3.8; force it explicitly so the test
# behaves identically on Linux too. "spawn" re-imports modules in the child,
# so worker functions must live at module level (below) and configuration
# must travel via env vars or pickled args.
_MP_CTX = mp.get_context("spawn")


@pytest.fixture
def registry_dir(tmp_path, monkeypatch):
    """Per-test registry dir, propagated to children via SYNAPSE_REGISTRY_DIR.

    The env var is what AgentRegistry consults via get_registry_dir(); using
    monkeypatch ensures cleanup even if the test fails. Children inherit the
    parent's environment under the "spawn" start method.
    """
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(reg_dir))
    return reg_dir


# --- Module-level worker functions (required for "spawn" start method) ---


def _worker_allocate(
    agent_type: str,
    name: str | None,
    parent_pid: int,
    barrier: mp.Barrier,
    queue: mp.Queue,
) -> None:
    """Child: wait at the barrier so all children call the API simultaneously,
    then attempt allocate_and_register and report (port, agent_id, error).

    The placeholder entry is registered with ``parent_pid`` (the test process's
    pid) instead of the child's, so the registry view models a real spawn:
    the spawn parent process owns the agent_id and keeps it alive, the
    short-lived child only performs the atomic reservation. Without this the
    child's ``atexit`` would delete the placeholder when the child exits.
    """
    try:
        # The child registers an atexit handler in _register_locked that
        # unregisters the entry on interpreter shutdown — for a real spawn
        # the parent process holds the agent for its lifetime, so the
        # entries persist. Suppress atexit in this short-lived test child
        # so the placeholder survives child exit for the parent to verify.
        import atexit

        atexit.register = lambda *a, **kw: None  # type: ignore[assignment]
        barrier.wait(timeout=10)
        registry = AgentRegistry()
        port_manager = PortManager(registry)
        port, agent_id = port_manager.allocate_and_register(
            agent_type, name=name, pid=parent_pid
        )
        queue.put(("ok", port, agent_id, None))
    except Exception as e:  # noqa: BLE001 — propagating any failure to parent
        queue.put(("err", None, None, f"{type(e).__name__}: {e}"))


def _worker_register_same_name(
    agent_id: str,
    agent_type: str,
    port: int,
    name: str,
    barrier: mp.Barrier,
    queue: mp.Queue,
) -> None:
    """Child: race two registrations with the same custom name; exactly one
    must succeed (NameConflictError for the other)."""
    try:
        barrier.wait(timeout=10)
        registry = AgentRegistry()
        registry.register(agent_id, agent_type, port, name=name)
        queue.put(("ok", None))
    except NameConflictError as e:
        queue.put(("name_conflict", str(e)))
    except Exception as e:  # noqa: BLE001
        queue.put(("err", f"{type(e).__name__}: {e}"))


# --- Helpers ---


def _run_parallel(targets: list[tuple], barrier_parties: int) -> list:
    """Run a set of (fn, args) child processes synchronized at a barrier and
    return their queue-reported results in completion order.

    Each tuple is (fn, args_without_barrier_or_queue). The barrier and the
    queue are appended automatically.
    """
    barrier = _MP_CTX.Barrier(barrier_parties)
    queue = _MP_CTX.Queue()
    procs = [
        _MP_CTX.Process(target=fn, args=(*args, barrier, queue)) for fn, args in targets
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=20)
        assert not p.is_alive(), f"child {p.pid} did not exit cleanly"
    results = []
    while not queue.empty():
        results.append(queue.get_nowait())
    return results


# --- Tests ---


class TestSequentialAllocation:
    """Sanity test: sequential allocate_and_register should give distinct ports."""

    def test_sequential_allocation_distinct_ports(self, registry_dir):
        registry = AgentRegistry()
        port_manager = PortManager(registry)

        port_a, id_a = port_manager.allocate_and_register("claude", pid=os.getpid())
        port_b, id_b = port_manager.allocate_and_register("claude", pid=os.getpid())

        assert port_a != port_b
        start, end = PORT_RANGES["claude"]
        assert start <= port_a <= end
        assert start <= port_b <= end
        agents = registry.list_agents()
        assert id_a in agents
        assert id_b in agents
        assert agents[id_a]["port"] == port_a
        assert agents[id_b]["port"] == port_b


class TestParallelSpawnRace:
    """The core regression: two parallel spawns must NOT collide on the same port."""

    def test_parallel_spawn_two_processes_get_distinct_ports(self, registry_dir):
        ppid = os.getpid()
        results = _run_parallel(
            targets=[
                (_worker_allocate, ("claude", None, ppid)),
                (_worker_allocate, ("claude", None, ppid)),
            ],
            barrier_parties=2,
        )
        assert len(results) == 2
        for tag, _, _, err in results:
            assert tag == "ok", f"unexpected child failure: {err}"

        ports = sorted(r[1] for r in results)
        ids = {r[2] for r in results}

        assert ports[0] != ports[1], (
            f"port-allocation race regressed: both children got the same "
            f"port {ports[0]}"
        )
        start, end = PORT_RANGES["claude"]
        assert all(start <= p <= end for p in ports)

        # Both placeholder entries must persist in the shared registry.
        registry = AgentRegistry()
        agents = registry.list_agents()
        assert ids.issubset(agents.keys()), (
            f"registry lost a placeholder entry — saw {set(agents.keys())} "
            f"expected {ids}"
        )
        assert len({agents[i]["port"] for i in ids}) == 2

    def test_parallel_spawn_exhaustion_one_succeeds_one_fails(self, registry_dir):
        """With 9 of 10 dummy ports pre-occupied, exactly 1 of 2 parallel
        children must succeed; the other must fail with PortExhaustionError."""
        from synapse.port_manager import PortExhaustionError  # noqa: F401

        registry = AgentRegistry()
        start, end = PORT_RANGES["dummy"]
        # Pre-register 9 of the 10 dummy ports with this process's pid
        # (PortManager treats them as "live" and skips them).
        for port in range(start, end):  # 8190..8198 (9 ports)
            registry.register(
                f"synapse-dummy-{port}", "dummy", port, status="PROCESSING"
            )

        ppid = os.getpid()
        results = _run_parallel(
            targets=[
                (_worker_allocate, ("dummy", None, ppid)),
                (_worker_allocate, ("dummy", None, ppid)),
            ],
            barrier_parties=2,
        )

        oks = [r for r in results if r[0] == "ok"]
        errs = [r for r in results if r[0] == "err"]
        assert len(oks) == 1, f"expected exactly 1 success, got {results}"
        assert len(errs) == 1, f"expected exactly 1 failure, got {results}"
        assert "PortExhaustion" in errs[0][3], (
            f"expected PortExhaustionError, got: {errs[0][3]}"
        )
        # The successful port is the one remaining free port.
        assert oks[0][1] == end  # 8199


class TestRegisterLockSerialization:
    """Existing behavior regression: same-name parallel register → exactly one wins."""

    def test_register_lock_serializes_writes(self, registry_dir):
        results = _run_parallel(
            targets=[
                (
                    _worker_register_same_name,
                    ("synapse-claude-8100", "claude", 8100, "duplicate-name"),
                ),
                (
                    _worker_register_same_name,
                    ("synapse-claude-8101", "claude", 8101, "duplicate-name"),
                ),
            ],
            barrier_parties=2,
        )
        oks = [r for r in results if r[0] == "ok"]
        conflicts = [r for r in results if r[0] == "name_conflict"]
        assert len(oks) == 1, f"expected 1 success, got {results}"
        assert len(conflicts) == 1, f"expected 1 NameConflictError, got {results}"


class TestLegacyCompatibility:
    """The public register() signature must remain byte-compatible — direct
    callers (other modules, tests) pass agent_id/agent_type/port positionally
    and rely on the function taking the lock internally."""

    def test_legacy_register_signature_unchanged(self, registry_dir):
        registry = AgentRegistry()

        # Positional + keyword combination used throughout the codebase.
        path = registry.register(
            "synapse-claude-8108",
            "claude",
            8108,
            status="PROCESSING",
            name="legacy-caller",
            role="tester",
        )
        assert path.exists()
        agents = registry.list_agents()
        assert "synapse-claude-8108" in agents
        assert agents["synapse-claude-8108"]["name"] == "legacy-caller"
        assert agents["synapse-claude-8108"]["role"] == "tester"
