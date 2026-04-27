# CLAUDE.md

## Development Flow

1. Write tests first → confirm spec → implement → pass all tests
2. **Default base branch is `main`** for all PRs
3. Do NOT change branches during active work without user confirmation (worktree agents are exempt)

## Dogfooding policy — file an issue when synapse misbehaves

This repo IS the synapse-a2a tool itself. We use it daily to develop it, so
every odd / clunky / surprising behavior observed during real use is signal,
not noise. **File a GitHub issue immediately** when you observe any of:

- A `synapse` command exits non-zero despite the underlying operation
  succeeding (e.g. delivery succeeded, cleanup failed)
- An agent appears stuck (PROCESSING / WAITING / SENDING_REPLY) for longer
  than its operation should take, with no clear cause from `synapse status`
- Output is misleading or hard to interpret (status string, table column,
  log line, error message)
- A workflow / skill / slash command produces unexpected results, retries
  needlessly, or leaves orphan state behind
- Documentation describes behavior that no longer matches the code
- Defaults that surprised you (timeout values, retry counts, fallback paths)

When in doubt, **err on filing**. A duplicate or "wontfix" issue is cheap;
a forgotten observation that would have improved the tool is expensive.
The goal is a continuous improvement loop driven by lived usage.

Use `gh issue create --label <bug|enhancement>` with a body that includes:
the exact reproduction (commands run, expected vs. actual), what you were
trying to do, and any session context that made the issue visible (e.g.
"observed during PR #X work, codex agent on port Y").

## Commands

```bash
uv sync                                  # Install
pytest                                    # All tests
pytest tests/test_foo.py -v               # Specific file
pytest -k "test_bar" -v                   # Pattern match
```
