# Repository Guidelines

## Development Flow (Mandatory)

1. When receiving a feature request or modification, write tests first
2. Present the tests to confirm the specification
3. Proceed to implementation only after confirmation
4. Adjust implementation until all tests pass

## Project Structure & Module Organization

- `synapse/` holds the core Python package (A2A server, routing, registry, CLI).
- `synapse/tools/` contains helper scripts (e.g., `a2a.py`).
- `synapse/profiles/` stores runnable agent profiles.
- `tests/` holds pytest suites (e.g., `tests/test_a2a_compat.py`).
- `guides/` and `docs/` contain architecture, usage, and troubleshooting docs.

## Build, Test, and Development Commands

- `uv sync` installs dependencies (preferred).
- `pip install -e .` installs the package in editable mode.
- `synapse <profile>` runs an agent in the foreground (e.g., `synapse claude`).
- `synapse start <profile>` / `synapse stop <profile>` manage background agents.
- `synapse list` lists running agents.
- `synapse send <agent> "<message>" --from <sender>` sends a message to an agent.

## Coding Style & Naming Conventions

- Python 3.10+ codebase; follow PEP 8 with 4-space indentation.
- Use `snake_case` for functions/variables and `PascalCase` for classes.
- Keep module names aligned with existing patterns (e.g., `a2a_client.py`, `port_manager.py`).
- No formatter is enforced in config; match local style in touched files.

## Testing Guidelines

- Test runner: `pytest` (see `pyproject.toml`).
- Run all tests: `pytest`.
- Targeted tests: `pytest tests/test_a2a_compat.py -v`.
- Name new tests as `tests/test_<area>.py` and prefer `test_<behavior>` functions.

## Commit & Pull Request Guidelines

- **Branch Management (Mandatory):**
  - **Do NOT commit directly to the `main` branch.**
  - **Always create a separate branch for your changes.**
  - **Submit a Pull Request (PR) for all modifications.**
- Commit messages follow Conventional Commits (examples in history):
  `feat:`, `fix:`, `refactor:`, `docs:`, `test:` + concise subject.
- PRs should include: a short summary, rationale, and tests run (e.g., `pytest -v`).
- Link related issues or docs when changes affect protocol behavior.

## Configuration & Docs

- Agent profiles and defaults are documented in `guides/profiles.md` and `guides/references.md`.
- For architecture or protocol details, start with `guides/architecture.md`.
- Agent-specific instructions for tooling live in `CLAUDE.md`.

## Registry & Status Updates Testing

### Manual Verification of `synapse list --watch`

To verify agent status tracking and updates work correctly:

```bash
# Terminal 1: Start a Claude agent
synapse claude

# Terminal 2: Watch agent status changes in real-time
synapse list --watch                      # 2s refresh (default)
synapse list -w -i 0.5                    # 0.5s refresh (faster for testing)

# Expected behavior:
# 1. Agent starts in PROCESSING status (initialization phase)
# 2. After initialization, status changes to READY (idle and waiting for input)
# 3. Status updates appear within the refresh interval
# 4. No flickering or temporary disappearances
# 5. No stale status values (always shows current state)
```

### Verifying Recent Bug Fixes (Registry Race Conditions)

The following bugs were fixed in the registry status update system:

**Bug #1 (Non-Atomic Writes - Race Conditions)**:
- Start multiple agents simultaneously: `synapse claude & synapse gemini & synapse codex`
- Watch status updates: `synapse list --watch`
- Verify: All updates are consistent (no lost updates), status values are correct

**Bug #2 (Silent Failures)**:
- Monitor logs during watch: `tail -f ~/.synapse/logs/synapse.log`
- Any status update failures will be logged with `"Failed to update status for ..."`
- File permission or disk issues are now visible

**Bug #3 (Partial JSON Reads)**:
- Watch for agent flickering: `synapse list -w -i 0.5`
- With atomic writes, agents should never disappear temporarily
- Temp files (`.*.json.tmp`) should never appear in `~/.a2a/registry/`

### Running Test Suite

```bash
# All tests
pytest

# Registry and status update tests
pytest tests/test_cmd_list_watch.py -v
pytest tests/test_registry.py -v
pytest tests/test_controller_registry_sync.py -v

# Tests for the specific bug fixes
pytest tests/test_cmd_list_watch.py::TestSilentFailures -v
pytest tests/test_cmd_list_watch.py::TestRegistryRaceConditions -v
pytest tests/test_cmd_list_watch.py::TestPartialJSONRead -v
```

See `CLAUDE.md` for additional testing details and troubleshooting.
