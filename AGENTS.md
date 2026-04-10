# AGENTS.md

## Development Flow (Mandatory)

1. Write tests first
2. Present the tests to confirm the specification
3. Proceed to implementation only after confirmation
4. Adjust implementation until all tests pass

## Commands

```bash
uv sync                                    # Install dependencies
pytest                                     # Run all tests
pytest tests/test_<area>.py -v             # Run specific tests
pytest -k "test_<pattern>" -v              # Pattern match
```

## Coding Style

- Python 3.10+, PEP 8, 4-space indentation
- `snake_case` for functions/variables, `PascalCase` for classes
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`

## Branch Rules

- Do NOT commit directly to `main`
- Always create a branch and submit a PR
- Stay on the current branch until the task is complete
