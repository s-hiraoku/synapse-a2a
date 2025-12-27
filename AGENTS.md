# Repository Guidelines

## Project Structure & Module Organization

- `synapse/`: core implementation (PTY controller, input routing, registry, CLI, server).
- `synapse/profiles/`: agent profile definitions (`claude.yaml`, `codex.yaml`, etc.).
- `guides/`: user-facing documentation (setup, usage, architecture, troubleshooting, references).
- `tasks/`: project notes and known issues.
- `docs/`: draft specs and design notes.
- `dummy_agent.py`: local test agent for basic interaction.

## Build, Test, and Development Commands

- Install dependencies:
  - `pip install -r requirements.txt`
- Install CLI locally:
  - `pip install -e .`
- Run an agent in interactive mode:
  - `synapse claude --port 8100`
- Run in background server mode:
  - `synapse start claude --port 8100`
- Send a message to a running agent:
  - `synapse send --target claude --priority 1 "Hello"`
- Check status:
  - `curl http://localhost:8100/status`

## Coding Style & Naming Conventions

- Language: Python 3.10+.
- Indentation: 4 spaces; keep functions short and focused.
- Naming: `snake_case` for variables/functions, `PascalCase` for classes, file names lowercase.
- Avoid heavy output in core runtime; prefer concise logs in `~/.synapse/logs`.

## Testing Guidelines

- No formal test suite is defined yet.
- If you add tests, place them under `tests/` and use `pytest` naming (`test_*.py`).
- Document new test commands in `README.md` and `guides/usage.md`.

## Commit & Pull Request Guidelines

- No strict commit message convention is documented in this repo.
- Keep commits focused and descriptive, e.g. `Fix PTY resize sync`.
- For PRs (if used), include:
  - What changed and why
  - How to run or verify the change
  - Relevant logs or screenshots for UI/TUI behavior

## Configuration Tips

- Profiles live in `synapse/profiles/*.yaml`.
- Key fields: `command`, `idle_regex`, `submit_sequence`, and `env`.
- `submit_sequence` may need `\r` for some TUI apps.
