# Repository Guidelines

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
- `python3 synapse/tools/a2a.py list` lists running agents.
- `python3 synapse/tools/a2a.py send --target <agent> "<message>"` sends a task.

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
- Commit messages follow Conventional Commits (examples in history):
  `feat:`, `fix:`, `refactor:`, `docs:`, `test:` + concise subject.
- PRs should include: a short summary, rationale, and tests run (e.g., `pytest -v`).
- Link related issues or docs when changes affect protocol behavior.

## Configuration & Docs
- Agent profiles and defaults are documented in `guides/profiles.md` and `guides/references.md`.
- For architecture or protocol details, start with `guides/architecture.md`.
- Agent-specific instructions for tooling live in `CLAUDE.md`.
