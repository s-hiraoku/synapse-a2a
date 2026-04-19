# Test Layer Conventions

The test suite is split into three layers: `core`, `adapters`, and `e2e`. This pilot only creates the structure and moves one representative file per layer; do not move existing tests in bulk until a follow-up migration plan is approved.

## Core

Core tests cover pure project logic. They must not spawn subprocesses, allocate PTYs, use network access, or touch the filesystem outside `tmp_path`. They must be runnable with only the Python standard library, `pytest`, `pytest-asyncio`, and this project's own modules.

## Adapters

Adapter tests cover wrappers around external CLI or protocol boundaries, including Claude CLI, Codex CLI, Gemini CLI, A2A transport, and the canvas frontend bridge. They may spawn subprocesses, use PTYs, or hit local sockets when that boundary is the behavior under test.

## E2E

End-to-end tests cover multiple agents, full round-trips, or long-lived servers. They are slow or flaky-prone by nature and may be marker-skipped in quick local or CI runs.

## Decision Heuristic

If this test would still pass after the CLI binary is renamed, it is core. If it depends on the CLI binary existing, it is adapter. If it needs two agents to actually talk to each other, it is e2e.

## Pilot Rules

Add new tests under the correct subdirectory from day one. During this pilot, move exactly one existing test file into each layer and do not move the rest of the existing flat test suite yet.

Layer pilot runs are path-based:

```bash
uv run pytest tests/core/
uv run pytest tests/adapters/
uv run pytest tests/e2e/
```

The existing `e2e` pytest marker is reserved for the pre-existing opt-in E2E marker contract. Do not use it as the layer selector for this pilot.
