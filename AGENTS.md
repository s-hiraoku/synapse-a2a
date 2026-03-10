# AGENTS.md

Instructions for non-Claude agents (Codex, Gemini, OpenCode, Copilot).
For full details, see `CLAUDE.md`.

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
synapse <profile>                          # Start agent (claude, gemini, codex, opencode, copilot)
synapse list                               # List running agents
synapse send <target> "message" --wait     # Send message (synchronous)
synapse send <target> "message" --silent   # Send message (fire-and-forget)
```

## Coding Style

- Python 3.10+, PEP 8, 4-space indentation
- `snake_case` for functions/variables, `PascalCase` for classes
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`

## Branch Rules

- Do NOT commit directly to `main`
- Always create a branch and submit a PR
- Stay on the current branch until the task is complete

## Skill Update Rules

`plugins/synapse-a2a/skills/` is the source of truth. Edit there, then sync with `sync-plugin-skills`. Do not edit `.claude/skills/` or `.agents/skills/` directly.

## Testing

```bash
pytest                                     # All tests
pytest tests/test_<area>.py -v             # Specific file
pytest -k "test_<pattern>" -v              # Pattern match
```

## Reference

See `CLAUDE.md` for comprehensive documentation including:
- Full command reference
- Architecture details
- Profile configuration
- Port ranges
- Storage paths
