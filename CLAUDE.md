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

## Closing shipped issues — keep the backlog honest

PRs that fully resolve an issue MUST use one of GitHub's auto-close
keywords on its own line in the PR body: `Closes #<num>`, `Fixes #<num>`,
or `Resolves #<num>`. Free-form prose (`Closes the focus part of #N`) and
commit-style references (`(#N)`) do **not** trigger auto-close — they leave
the issue orphaned in the backlog even after the work ships.

Conventions:

- For partial fixes or related references that should NOT close the issue:
  `Refs #<num>`.
- For meta/parent issues split across multiple sub-PRs: only the LAST
  sub-PR uses `Closes #<parent>`. Earlier sub-PRs use `Refs #<parent>`.
- The `.github/PULL_REQUEST_TEMPLATE.md` includes the canonical `Linked
  Issues` block; keep it filled in.

When triaging the backlog, an issue that "looks already done" usually is
— search merged PRs (`gh pr list --state merged --search "<num>"`) and if
any of them implemented it without the keyword, close the issue with a
comment pointing at those PRs and the implementation file/line. We
discovered six such orphans during the 0.31.0 cycle (#311, #356, #604,
#644, #647, #655); the cost was real session time spent re-verifying
"is this issue actually open?". Closing on sight prevents this.

## Commands

```bash
uv sync                                  # Install
pytest                                    # All tests
pytest tests/test_foo.py -v               # Specific file
pytest -k "test_bar" -v                   # Pattern match
```
