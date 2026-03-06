---
name: synapse-manager
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

### Step 1: Plan & Setup

**Check existing agents before spawning** — reuse is faster (avoids startup overhead,
instruction injection, and readiness wait):
```bash
synapse list
```

Review WORKING_DIR, ROLE, STATUS, TYPE. Only READY agents can accept work immediately.

**Spawn only when no existing agent can handle the task:**
```bash
synapse spawn claude --worktree --name Impl --role "feature implementation"
synapse spawn gemini -w --name Tester --role "test writer"
```

Cross-model spawning (Claude spawns Gemini, etc.) provides diverse strengths and
distributes token usage across providers, avoiding rate limits.

**Wait for readiness** using the helper script:
```bash
scripts/wait_ready.sh Impl 30
scripts/wait_ready.sh Tester 30
```

See `references/auto-approve-flags.md` for per-CLI permission skip flags.

### Step 2: Delegate via Task Board

Task board makes work visible to the entire team, preventing duplication:
```bash
synapse tasks create "Implement auth module" \
  -d "Add OAuth2 with JWT in synapse/auth.py. Follow patterns in synapse/server.py." \
  --priority 4

synapse tasks create "Write auth tests" \
  -d "Cover: valid login, invalid credentials, token expiry, refresh flow" \
  --blocked-by 1
```

**Assign and send instructions:**
```bash
synapse tasks assign 1 Impl
synapse send Impl "Implement auth module — see task #1 on the board.
- Add OAuth2 flow in synapse/auth.py
- Follow existing patterns" --attach synapse/server.py --silent
```

Use `--attach` to send reference files the agent should study.
Use `--silent` for delegated tasks, `--wait` when you need immediate results.

### Step 3: Monitor

```bash
synapse list                              # Live status (auto-updates)
synapse tasks list --status in_progress   # Task board progress
synapse history list --agent Impl         # Completed work
```

Or use the aggregation script:
```bash
scripts/check_team_status.sh
```

If an agent stays PROCESSING >5 min, send an interrupt:
```bash
synapse interrupt Impl "Status update — what is your current progress?"
```

### Step 4: Approve Plans

```bash
synapse approve <task_id>
synapse reject <task_id> --reason "Use refresh tokens instead of long-lived JWTs."
```

### Step 5: Verify

Testing is the critical quality gate — an agent's changes may break unrelated
modules through import chains or shared state:

```bash
# New tests first (fast feedback)
pytest tests/test_auth.py -v

# Full regression (catches cross-module breakage)
pytest --tb=short -q
```

**Regression triage** — distinguish new breakage from pre-existing issues:
```bash
scripts/regression_triage.sh tests/test_failing_module.py -v
```
- Exit 0 = REGRESSION (your changes broke it) → proceed to Step 6
- Exit 1 = PRE-EXISTING (already broken) → note it and continue

**Update task board:**
```bash
synapse tasks complete <task_id>
synapse tasks fail <task_id> --reason "test_refresh_token fails — TypeError on line 42"
```

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
   FIX: Exclude health-check endpoints from auth" --silent
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
synapse send Tester "Review implementation. Focus on: correctness, edge cases" \
  --attach synapse/auth.py --wait
synapse send Impl "Review test coverage. Focus on: missing cases, assertion quality" \
  --attach tests/test_auth.py --wait
```

**Final verification and cleanup:**
```bash
pytest --tb=short -q                      # All tests pass
synapse tasks complete 1 && synapse tasks complete 2
synapse kill Impl -f && synapse kill Tester -f
synapse list                              # Verify cleanup
```

Killing spawned agents frees ports, memory, and PTY sessions. Orphaned agents
may accidentally accept future tasks intended for other agents.

## Decision Table

| Situation | Action |
|-----------|--------|
| Agent stuck PROCESSING >5min | `synapse interrupt <name> "Status?"` |
| Check all agents at once | `synapse broadcast "Status check" -p 4` |
| New test fails | Feedback with error + suggested fix (Step 6) |
| Regression test fails | `scripts/regression_triage.sh` to classify |
| Agent READY but no output | Check `git diff`, re-send if needed |
| Agent submits a plan | `synapse approve` or `synapse reject --reason "..."` |
| Discovered a reusable pattern | `synapse memory save <key> "<pattern>" --notify` |
| Cross-review finds issue | Send fix request with `--attach`, re-verify |
| All tests pass, reviews clean | Complete tasks, kill agents, report done |

## References

| Reference | Contents |
|-----------|----------|
| `references/auto-approve-flags.md` | Per-CLI permission skip flags |
| `references/worker-guide.md` | Worker agent responsibilities and communication patterns |
| `references/features-table.md` | A2A features with commands |
| `references/commands-quick-ref.md` | All manager-relevant commands |
| `scripts/wait_ready.sh` | Poll until agent reaches READY status |
| `scripts/check_team_status.sh` | Aggregate team status (agents + task board) |
| `scripts/regression_triage.sh` | Classify test failure as regression or pre-existing |
