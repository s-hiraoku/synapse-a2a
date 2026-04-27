---
name: synapse-manager
license: MIT
description: >-
  Multi-agent management workflow — task delegation, progress monitoring,
  quality verification with regression testing, feedback delivery, and
  cross-review orchestration. Use this skill when coordinating multiple agents
  on a shared task, monitoring delegated work, ensuring quality across
  agent outputs, or implementing a multi-phase plan (3+ phases or 10+ file changes).
---

# Synapse Manager

Orchestrate multi-agent work with structured delegation, monitoring, and quality gates.

## When to Use

- Coordinating 2+ agents on related subtasks
- Monitoring progress of delegated work
- Verifying agent outputs (tests, file changes, integration)
- Sending targeted feedback with error details and fix guidance
- Orchestrating cross-review between agents
- Implementing a multi-phase plan (3+ phases or 10+ file changes)
- Planning agent assignment for multi-file changes

## Workflow (7 Steps)

### Step 1: Plan, Spec, and Setup

Prefer test-first when the scope is clear: create tests -> present/confirm spec -> then implement. For exploratory work, prototypes, or trivial fixes, writing tests after implementation is acceptable.

Edit `plugins/synapse-a2a/skills/` first, then sync generated copies with `sync-plugin-skills`.

**Check existing agents before spawning** — reuse is faster (avoids startup overhead,
instruction injection, and readiness wait):
```bash
synapse list --json
```

Review WORKING_DIR, ROLE, STATUS, TYPE. Only READY agents can accept work immediately.
Other relevant statuses: `SENDING_REPLY` (brief outbound A2A send/reply POST;
wait for the previous status to return), `PROCESSING` (busy), `WAITING`
(permission prompt — use `synapse approve`/`synapse reject`), `WAITING_FOR_INPUT`
(#538 — task paused asking for input, reply via `synapse reply <task_id>`),
`RATE_LIMITED` (#561 — LLM provider rate limit hit; wait for the window to reset
before re-sending), `DONE` (demotes to READY ~10s later), `SHUTTING_DOWN` (do not
send).

**Spawn only when no existing agent can handle the task:**
```bash
synapse spawn claude --worktree --name Impl --role "feature implementation"
synapse spawn gemini -w --name Tester --role "test writer"
```

Cross-model spawning (Claude spawns Gemini, etc.) provides diverse strengths and
distributes token usage across providers, avoiding rate limits.

**Wait for readiness** using the helper script. Resolve it from the skill root so the
command works from any working directory, whether you are in the plugin source or a
synced copy:
```bash
cd plugins/synapse-a2a/skills/synapse-manager
scripts/wait_ready.sh Impl 30
scripts/wait_ready.sh Tester 30

# Synced copy example
cd .agents/skills/synapse-manager
scripts/wait_ready.sh Impl 30
```

See `references/auto-approve-flags.md` for per-CLI permission skip flags.

### Step 2: Create Tests and Confirm the Spec

**Assign the test/spec task and confirm scope before implementation starts:**
```bash
synapse send Tester "Write the tests first and confirm the spec for auth module.
- Cover valid login, invalid credentials, token expiry, refresh flow
- Report any scope gaps before implementation starts" --attach synapse/server.py --force --wait
```

Use `--attach` to send reference files the agent should study.
Use `--wait` while confirming tests/spec, then `--silent` or `--notify` once execution is unblocked.

### Step 3: Delegate Implementation and Monitor

After tests/spec are confirmed, delegate the implementation task:
```bash
synapse send Impl "Implement auth module — tests/spec are confirmed.
- Add OAuth2 flow in synapse/auth.py
- Follow existing patterns" --attach synapse/server.py --force --silent
```

```bash
synapse list --json                       # AI-safe snapshot
synapse history list --agent Impl         # Completed work
```

Or use the aggregation script:
```bash
cd plugins/synapse-a2a/skills/synapse-manager && scripts/check_team_status.sh
```

If an agent stays PROCESSING >5 min, send an interrupt:
```bash
synapse interrupt Impl "Status update — what is your current progress?" --force
```

### Step 4: Approve Plans

```bash
synapse approve <task_id>
synapse reject <task_id> --reason "Use refresh tokens instead of long-lived JWTs."
```

### Step 5: Verify

Run the tests created in Step 2 first for fast feedback, then consider broader regression
coverage if the changes touch shared modules or public interfaces:

```bash
# New tests first (fast feedback)
pytest tests/test_auth.py -v

# Full regression (catches cross-module breakage)
pytest --tb=short -q
```

**Regression triage** — distinguish new breakage from pre-existing issues:
```bash
cd plugins/synapse-a2a/skills/synapse-manager && scripts/regression_triage.sh tests/test_failing_module.py -v
```
- Exit 0 = REGRESSION (your changes broke it) → proceed to Step 6
- Exit 1 = PRE-EXISTING (already broken) → note it and continue

### Step 6: Feedback

Concrete, actionable feedback saves iteration cycles:
```bash
synapse send Impl "Issues found — please fix:

1. FAILING TEST: test_token_expiry (tests/test_auth.py)
   ERROR: TypeError: cannot unpack non-iterable NoneType object
   FIX: Add None guard at the top of validate_token()

2. REGRESSION: test_existing_endpoint broke
   ERROR: expected 200, got 401
   CAUSE: auth middleware intercepts all routes
   FIX: Exclude health-check endpoints from auth" --force --silent
```

**Save patterns for the team:**
```bash
synapse memory save auth-middleware-pattern \
  "Auth middleware must exclude /status and /.well-known/* endpoints" \
  --tags auth,middleware --notify
```

After sending feedback, return to Step 3 (Monitor).

### Step 7: Review & Wrap-up

**Cross-review catches blind spots** — each agent reviews the other's work:
```bash
synapse send Tester "Review implementation. Focus on: correctness, edge cases" --force \
  --attach synapse/auth.py --wait
synapse send Impl "Review test coverage. Focus on: missing cases, assertion quality" --force \
  --attach tests/test_auth.py --wait
```

**Final verification and cleanup:**
```bash
pytest --tb=short -q                      # All tests pass
synapse kill Impl -f && synapse kill Tester -f
synapse list --json                       # Verify cleanup
```

Killing spawned agents frees ports, memory, and PTY sessions. Orphaned agents
may accidentally accept future tasks intended for other agents.

## Decision Table

| Situation | Action |
|-----------|--------|
| Agent stuck PROCESSING >5min | `synapse interrupt <name> "Status?"` |
| Agent in `WAITING_FOR_INPUT` | `synapse reply <task_id> "<answer>"` |
| Agent in `RATE_LIMITED` | Wait for LLM provider window to reset, then re-send |
| Check all agents at once | `synapse broadcast "Status check" -p 4` |
| New test fails | Feedback with error + suggested fix (Step 6) |
| Regression test fails | `scripts/regression_triage.sh` to classify |
| Agent READY but no output | Check `git diff`, re-send if needed |
| Agent submits a plan | `synapse approve` or `synapse reject --reason "..."` |
| Discovered a reusable pattern | `synapse memory save <key> "<pattern>" --notify` |
| Cross-review finds issue | Send fix request with `--attach`, re-verify |
| All tests pass, reviews clean | Kill agents, report done |

## References

| Reference | Contents |
|-----------|----------|
| `references/auto-approve-flags.md` | Per-CLI permission skip flags |
| `references/worker-guide.md` | Worker agent responsibilities and communication patterns |
| `references/features-table.md` | A2A features with commands |
| `references/commands-quick-ref.md` | All manager-relevant commands |
| `scripts/wait_ready.sh` | Poll until agent reaches READY status |
| `scripts/check_team_status.sh` | Aggregate team status |
| `scripts/regression_triage.sh` | Classify test failure as regression or pre-existing |
