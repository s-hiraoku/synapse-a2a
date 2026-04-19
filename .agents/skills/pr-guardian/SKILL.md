---
name: pr-guardian
license: MIT
description: >-
  Continuously monitor a GitHub PR for merge conflicts, CI failures, and
  CodeRabbit review comments, then automatically fix any issues found.
  Polls every 5 minutes and loops until every check is green. Use this
  skill whenever a PR has just been created or code has been pushed to a
  PR branch — it should be the default follow-up action after any PR
  creation or push. Also trigger on: "watch this PR", "guard this PR",
  "monitor CI", "keep fixing until green", "PRを監視して", "CIが通るまで
  直して", /pr-guardian. When a PostToolUse hook reports that a push or
  PR creation just happened, proactively invoke this skill to start
  monitoring without waiting for the user to ask.
---

# PR Guardian

Watch a PR, detect problems, fix them, repeat — until everything is green.

## Why this exists

After pushing a PR you typically wait for CI, check for merge conflicts,
and respond to CodeRabbit review comments. Each issue requires a separate
manual step. PR Guardian automates the entire feedback loop: it uses
`gh run watch` to efficiently wait for CI completion (consuming zero
session cycles while waiting), then polls the PR status, dispatches the
appropriate fix skill when a problem is found, and exits only when all
checks pass (or the iteration limit is reached).

## Quick start

```
/pr-guardian                     # Default: 5 min interval, 20 max iterations
/pr-guardian --interval 3        # Poll every 3 minutes
/pr-guardian --max-iterations 10 # Give up after 10 cycles
```

## Workflow

### Step 0: Validate preconditions

Before starting the loop, verify:

1. `gh` CLI is installed and authenticated
2. Current branch has an open PR (`gh pr view`)
3. Display the PR number and URL

If any check fails, report the error and stop.

### Step 1: Wait for CI with `gh run watch`

Before polling, wait for all GitHub Actions workflow runs to complete
using `gh run watch`. This blocks at the shell level until CI finishes,
consuming zero Claude Code session cycles while waiting.

```bash
# Get the latest workflow run for the current branch
RUN_ID=$(gh run list --branch "$(git rev-parse --abbrev-ref HEAD)" \
  --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || echo "")

if [[ -n "$RUN_ID" ]]; then
  # Block until this run completes (exit code reflects pass/fail)
  gh run watch "$RUN_ID" --exit-status 2>/dev/null || true
fi
```

**Fallback**: If `gh run watch` is unavailable or fails (e.g., no
workflow runs found yet on the first cycle after push), skip straight
to Step 2 and let the polling script detect `checks_running > 0`.

### Step 2: Poll PR status

Run the bundled status script:

```bash
bash <skill-path>/scripts/poll_pr_status.sh
```

This returns a JSON object with these fields:

| Field               | Type    | Meaning                                       |
|---------------------|---------|-----------------------------------------------|
| `branch`            | string  | Current branch name                           |
| `pr_number`         | int     | PR number                                     |
| `checks_total`      | int     | Total CI checks (excludes CodeRabbit)         |
| `checks_passed`     | int     | CI checks that passed                         |
| `checks_failed`     | int     | CI checks that failed                         |
| `checks_running`    | int     | CI checks still in progress                   |
| `has_conflict`      | bool    | Merge conflicts detected                      |
| `coderabbit_check`  | string  | CodeRabbit check status: `none`/`pending`/`pass`/`fail` |
| `coderabbit_comments` | int   | Number of CodeRabbit inline comments          |
| `all_green`         | bool    | True when everything passes (including CodeRabbit) |

**Important**: `all_green` is only true when ALL of these hold:
- No merge conflicts
- No CI failures
- No CI checks still running
- CodeRabbit check is NOT `pending` AND NOT `none` (review must have completed at least once)
- No unresolved CodeRabbit inline comments (comments marked `✅ Addressed` are excluded)
- At least one CI check exists

### Step 3: Evaluate and report

Print a concise status line each cycle:

```
[PR Guardian] Cycle 3/20 — PR #42
  CI: 4 passed, 1 failed, 0 running
  Conflicts: none
  CodeRabbit: review completed, 2 inline comments
  → Action: fixing CodeRabbit comments
```

### Step 4: Dispatch fixes (priority order)

When issues are found, fix them one category at a time in this order.
Only fix one category per cycle — after fixing, go back to Step 1 to
re-poll, because a fix may have changed the state (e.g., a push
triggers new CI runs and `gh run watch` will wait for them).

**Priority 1 — Merge conflicts**

Merge conflicts block everything else. When `has_conflict` is true:

1. Invoke `/fix-conflict`
2. After resolution, the push triggers new CI runs — go back to Step 1

**Priority 2 — CI failures**

When `checks_failed > 0` and `checks_running == 0` (Step 1's
`gh run watch` already waited, so running should normally be 0):

1. Invoke `/fix-ci`
2. After the fix commit is pushed, go back to Step 1

**Priority 3 — CodeRabbit review comments**

When `coderabbit_check == "pass"` and `coderabbit_comments > 0` and CI
is passing:

1. Invoke `/fix-review`
2. `/fix-review` will verify each finding against current code before fixing
3. After the fix commit is pushed, go back to Step 1

**IMPORTANT**: Only dispatch `/fix-review` when `coderabbit_check` is
`"pass"` (review completed). If it is `"pending"`, wait — the review is
still in progress and comments may not be final yet.

### Step 5: Handle pending states

The correct action is to **wait** (not fix) when:

- `checks_running > 0`: CI is still running — this should be rare
  since Step 1 already waited via `gh run watch`, but can happen if
  new runs were triggered between watch and poll
- `coderabbit_check == "pending"`: CodeRabbit review is in progress —
  wait with a short sleep (60-120 seconds) and re-run Step 2 only.
  Do NOT go back to Step 1 (`gh run watch`) — CodeRabbit is not a
  GitHub Actions run. Retry up to 5 times before moving to the next
  full cycle
- `coderabbit_check == "none"`: CodeRabbit hasn't started yet (common
  right after a push) — same short-sleep retry as `pending`
- `checks_total == 0` and it's the first cycle: checks haven't started
  yet — go back to Step 1 where `gh run watch` will block until they appear

Do not invoke any fix skill while checks are still running or reviews
are pending — you would be fixing based on incomplete information.

### Step 6: Check exit conditions

After each cycle, check:

1. **All green** (`all_green == true`): Print success message and exit
2. **Max iterations reached**: Print summary of remaining issues and exit
3. **Same failure repeated 3 times**: The automatic fix is not working.
   Print what failed and suggest manual intervention, then exit

If none of these conditions are met, go back to Step 1. There is no
fixed sleep between cycles — `gh run watch` in Step 1 provides the
natural wait for CI to complete after a fix push.

## Configuration

| Flag               | Default | Description                                  |
|--------------------|---------|----------------------------------------------|
| `--interval`       | 2       | Minutes between CodeRabbit pending retries   |
| `--max-iterations` | 20      | Max cycles before giving up                  |

## Exit messages

**Success:**
```
[PR Guardian] All checks green! PR #42 is ready.
  CI: 6/6 passed | Conflicts: none | CodeRabbit: pass, 0 comments
  Completed in 3 cycles over 15 minutes.
```

**Max iterations:**
```
[PR Guardian] Reached 20 cycles without all-green.
  Remaining issues:
    - CI: tests failing (pytest assertion error in test_auth.py)
    - CodeRabbit: 2 unresolved inline comments
  Manual intervention needed.
```

**Repeated failure:**
```
[PR Guardian] Same CI failure persisted after 3 fix attempts.
  Failing check: tests
  Last error: AssertionError in test_auth.py:42
  Automatic repair is not resolving this — please fix manually.
```

## Important notes

- This skill composes `/fix-conflict`, `/fix-ci`, and `/fix-review`.
  It does not reimplement their logic — it orchestrates them.
- Only one fix category is attempted per cycle to avoid cascading
  changes that confuse the state.
- `gh run watch` replaces the old fixed-interval sleep loop for CI
  waiting. This eliminates wasted polling cycles and reduces session
  consumption from 5-10 cycles to 1-3 for a typical PR.
- The skill respects both CI timing AND CodeRabbit timing: `gh run
  watch` handles CI, and a short-sleep retry loop (60-120s, max 5
  retries) handles CodeRabbit pending states.
- **Synapse-independent**: This skill depends only on `gh` CLI and
  standard git commands. It works outside Synapse environments.
- If `gh run watch` is unavailable (no runs found, older gh version),
  the skill falls back to the polling script detecting
  `checks_running > 0` and retrying on the next cycle.
- CodeRabbit check status (`pending`/`pass`/`fail`) is tracked
  separately from inline comment count. A `pending` check means
  the review is still running — do NOT dispatch `/fix-review` yet.
- Each fix skill handles its own commit and push. PR Guardian only
  handles the loop and dispatch.
- `/fix-review` verifies each CodeRabbit finding against the current
  code before applying fixes — it does not blindly apply suggestions.
