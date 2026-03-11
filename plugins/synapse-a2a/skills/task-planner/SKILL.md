---
name: task-planner
description: >-
  Guide for decomposing large tasks into a task board plan with dependency
  chains, managing priorities, and distributing work across agents. Outputs
  task board entries as the team contract; TodoList for personal micro-steps.
---

# Task Planner

This skill helps you turn ambiguous or large requests into a clear, sequenced plan with ownership and verification.

## Outputs To Produce

- A short problem statement
- Assumptions and open questions
- A step-by-step plan with measurable outcomes
- Risks and rollback/containment options
- Test and verification steps

## Decomposition Technique

Split work into thin vertical slices:

- One slice should be mergeable on its own
- Each slice should include tests or validation
- Prefer smallest unit that reduces uncertainty

Common slice types:

- Spec tests (lock requirements, CLI flags, edge cases)
- Implementation changes (small, isolated)
- Documentation updates
- Observability and traceability improvements

## Dependency And Priority Rules

- Identify blockers first (missing API, failing tests, permissions).
- Order by "unblocks others" and "reduces uncertainty".
- For multi-agent work, keep interfaces stable and define contracts (inputs/outputs) per slice.

## Multi-Agent Assignment

When delegating:

- Specify the exact deliverable (files, tests, output format)
- Specify constraints (no commits, branch constraints, time limits)
- Specify the acceptance test (what must pass)

Example delegation message:

```
Please write tests for <feature>.
Constraints:
- Do not change implementation yet
- Use pytest
Acceptance:
- Tests fail before implementation
- Tests cover edge cases: <...>
```

## Task Board Output

Decomposition results go to the **task board** — the team-visible contract:

```bash
# Create tasks with dependency chains
synapse tasks create "Write auth tests" \
  -d "Cover valid login, invalid credentials, token expiry" \
  --priority 5
# Returns: task-tests-001

synapse tasks create "Implement auth module" \
  -d "Add OAuth2 with JWT in synapse/auth.py" \
  --priority 4 \
  --blocked-by task-tests-001
# Returns: task-impl-002

synapse tasks create "Integration test" \
  -d "End-to-end auth flow verification" \
  --priority 3 \
  --blocked-by task-impl-002
# Returns: task-int-003

# Assign ownership
synapse tasks assign task-tests-001 Tester
synapse tasks assign task-impl-002 Impl
synapse tasks assign task-int-003 Tester
```

Use `--blocked-by` to express dependency chains. Blocked tasks cannot start
until their blockers are completed, making execution order explicit.

### TodoList for Personal Micro-Steps

Use a TodoList for your **own** micro-step tracking within a single task.
Task board entries are coarse-grained (one per delegation); TodoList items
are fine-grained (one per coding step):

- Add failing tests for <behavior>
- Implement <behavior> behind tests
- Run targeted tests
- Update docs
- Run full test suite

## Progress Reporting

Reference task board IDs in all status updates:

- **Done:** `"Task task-tests-001 complete — 4 tests passing"` + `synapse tasks complete task-tests-001`
- **Next:** `"Starting task task-impl-002 (was blocked by task-tests-001)"`
- **Blocked:** `"Task task-int-003 waiting — blocked by task-impl-002 (dependency will auto-unblock on completion)"`
