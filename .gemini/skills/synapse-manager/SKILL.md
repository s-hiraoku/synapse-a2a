---
name: synapse-manager
description: >-
  Multi-agent management workflow — task delegation, progress monitoring,
  quality verification with regression testing, feedback delivery, and
  cross-review orchestration. Use this skill when coordinating multiple agents
  on a shared task, monitoring delegated work, or ensuring quality across
  agent outputs.
---

# Synapse Manager

Orchestrate multi-agent work with structured delegation, monitoring, and quality gates.

## When to Use

- Coordinating 2+ agents on related subtasks
- Monitoring progress of delegated work
- Verifying agent outputs (tests, file changes, integration)
- Sending targeted feedback with error details and fix guidance
- Orchestrating cross-review between agents

## Workflow (5 Steps)

### Step 1: Delegate

Analyze the task, decompose into subtasks, and assign to agents.

**Actions:**
1. Break the task into independent, parallelizable subtasks
2. Spawn or identify agents for each subtask
3. Send each agent a specific, actionable task message

**Spawn agents:**
```bash
synapse spawn claude --name Impl --role "feature implementation"
synapse spawn gemini --name Tester --role "test writer"
```

**Wait for readiness:**
```bash
elapsed=0
while ! synapse list | grep -q "Impl.*READY"; do
  sleep 1; elapsed=$((elapsed + 1))
  [ "$elapsed" -ge 30 ] && echo "ERROR: Impl not READY after ${elapsed}s" >&2 && break
done
```

**Send tasks with specifics:**
```bash
synapse send Impl "Implement X in synapse/foo.py:
- Add function bar() that does Y
- Update __init__.py exports
- Follow existing patterns in synapse/baz.py" --silent

synapse send Tester "Write tests for X in tests/test_foo.py:
- Test bar() with valid input
- Test bar() with edge cases (empty, None, overflow)
- Follow pytest patterns in tests/test_baz.py" --silent
```

**Key rules:**
- Include specific file names, function names, and acceptance criteria
- Reference existing code patterns the agent should follow
- Use `--notify` (default) for standard task delegation
- Use `--wait` if you need immediate results and want to block
- Use `--silent` for purely informational feedback or background tasks

### Step 2: Monitor

Periodically check agent status and work artifacts.

**Status check:**
```bash
synapse list
```

**Verify expected output:**
```bash
# Check for new/modified files
git diff --name-only

# Check specific files exist
ls tests/test_foo.py synapse/foo.py

# Read implementation to verify correctness
# (use Read tool or cat to inspect key files)
```

**Monitoring cadence:**
- Check `synapse list` every 1-2 minutes during active work
- Once an agent shows READY after being PROCESSING, inspect its output
- If an agent stays PROCESSING for >5 minutes, send a status check:
  ```bash
  synapse interrupt <name> "Status update — what is your current progress?"
  ```

### Step 3: Verify

Run tests to validate quality. This is the critical quality gate.

**Run new tests first (fast feedback):**
```bash
pytest tests/test_foo.py -v
```

**Then run full regression tests (every time new tests pass):**
```bash
# Full suite with short output — catches side-effects early
pytest --tb=short -q
```

**Regression triage — distinguish new breakage from pre-existing:**
```bash
# Stash agent changes and re-run failing tests against clean state
git stash
pytest tests/test_failing_module.py -v
git stash pop
```
- If the test **also fails on clean state** → pre-existing issue, not caused by the agent. Note it and continue.
- If the test **passes on clean state** → the agent's changes introduced the regression. Proceed to Step 4 with the diff that caused it.

**Why every time, not just at the end:** Regressions caught early are cheaper to fix. The agent still has context about what it just changed. Deferring regression checks to the final step risks compounding failures that are harder to untangle.

**On test failure:**
1. Identify failing test name and error message
2. Determine if it is a new-test failure or regression
3. Proceed to Step 4 (Feedback) with specifics

### Step 4: Feedback

When issues are found, send concrete, actionable feedback.

**Feedback message structure:**
```bash
synapse send <name> "Issues found — please fix:

1. FAILING TEST: test_bar_with_none (tests/test_foo.py)
   ERROR: TypeError: cannot unpack non-iterable NoneType object
   FIX: Add None guard at the top of bar()

2. MISSING INTEGRATION: foo.py is not imported in __init__.py
   FIX: Add 'from .foo import bar' to synapse/__init__.py

3. REGRESSION: test_existing_feature broke
   ERROR: AssertionError: expected 3, got 4
   CAUSE: bar() side-effect on shared state
   FIX: Use a local copy instead of mutating the input" --silent
```

**Key rules:**
- Always include the failing test name and exact error
- Always suggest a fix direction (not just "it's broken")
- Distinguish between new-test failures and regressions
- After sending feedback, return to Step 2 (Monitor) and wait

### Step 5: Review

After all tests pass, orchestrate cross-review and final confirmation.

**Cross-review:**
```bash
synapse send Tester "Review implementation changes:
$(git diff --name-only | grep -v test)
Focus on: correctness, edge cases, naming consistency" --wait

synapse send Impl "Review test coverage:
$(git diff --name-only | grep test)
Focus on: missing edge cases, test isolation, assertion quality" --wait
```

**Final verification:**
```bash
# Full test suite one last time
pytest --tb=short -q

# Verify no unintended changes
git diff --stat
```

**Cleanup:**
```bash
synapse kill Impl -f
synapse kill Tester -f
```

**Report completion:**
- Summarize what was done
- List files changed
- Confirm all tests pass
- Note any remaining concerns from cross-review

## Decision Table

| Situation | Action |
|-----------|--------|
| Agent stuck PROCESSING >5min | `synapse interrupt` with status request |
| New test fails | Feedback with error + suggested fix |
| Regression test fails | Feedback with cause analysis + fix direction |
| Agent READY but no output | Check `git diff`, re-send task if needed |
| Cross-review finds issue | Send fix request, re-verify |
| All tests pass, reviews clean | Kill agents, report done |

## Commands Reference

| Command | Purpose |
|---------|---------|
| `synapse list` | Check agent status |
| `synapse spawn <type> --name <n> --role "<r>"` | Start agent |
| `synapse send <name> "<msg>" --notify` | Delegate task (async notification - default) |
| `synapse send <name> "<msg>" --wait` | Request reply (immediate/blocking) |
| `synapse send <name> "<msg>" --silent` | Send feedback / FYI (no notification) |
| `synapse interrupt <name> "<msg>"` | Urgent status check (priority 4) |
| `synapse kill <name> -f` | Terminate agent |
| `pytest <file> -v` | Run specific tests |
| `pytest --tb=short -q` | Run full regression |
| `git diff --name-only` | Check changed files |
