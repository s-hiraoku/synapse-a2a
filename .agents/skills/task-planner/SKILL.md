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
# Returns: 3f2a1b4c (displayed prefix of a UUID such as 3f2a1b4c-1111-2222-3333-444444444444)

synapse tasks create "Implement auth module" \
  -d "Add OAuth2 with JWT in synapse/auth.py" \
  --priority 4 \
  --blocked-by 3f2a1b4c
# Returns: 7a9d2e10 (displayed prefix of a UUID such as 7a9d2e10-5555-6666-7777-888888888888)

synapse tasks create "Integration test" \
  -d "End-to-end auth flow verification" \
  --priority 3 \
  --blocked-by 7a9d2e10
# Returns: c84ef901 (displayed prefix of a UUID such as c84ef901-9999-aaaa-bbbb-cccccccccccc)

# Capture the created IDs, then assign ownership using the UUID prefix
TESTS_ID=$(synapse tasks create "Write auth tests" \
  -d "Cover valid login, invalid credentials, token expiry" \
  --priority 5 | awk '{print $3}')
IMPL_ID=$(synapse tasks create "Implement auth module" \
  -d "Add OAuth2 with JWT in synapse/auth.py" \
  --priority 4 \
  --blocked-by "$TESTS_ID" | awk '{print $3}')
INT_ID=$(synapse tasks create "Integration test" \
  -d "End-to-end auth flow verification" \
  --priority 3 \
  --blocked-by "$IMPL_ID" | awk '{print $3}')

synapse tasks assign "$TESTS_ID" Tester
synapse tasks assign "$IMPL_ID" Impl
synapse tasks assign "$INT_ID" Tester
```

Use `--blocked-by` to express dependency chains. Blocked tasks cannot start
until their blockers are completed, making execution order explicit.
`synapse tasks create` generates full UUIDs, while the CLI prints the first
8 characters. `synapse tasks assign`, `synapse tasks complete`, and
`--blocked-by` accept either the full UUID or a unique prefix.

### Plan Card Output (Canvas)

For visual plans with Mermaid DAG visualization and step-level status tracking,
post a plan card to Canvas and optionally accept it into the task board:

```bash
# Post plan card with Mermaid DAG and step list
synapse canvas plan '{"plan_id":"plan-auth","status":"proposed","mermaid":"graph TD; A[Tests]-->B[Impl]-->C[Review]","steps":[{"id":"s1","subject":"Write auth tests","agent":"Tester","status":"pending"},{"id":"s2","subject":"Implement auth","agent":"Impl","status":"pending","blocked_by":["s1"]},{"id":"s3","subject":"Review","agent":"Tester","status":"pending","blocked_by":["s2"]}]}' --title "Auth Plan"

# Accept plan and register steps as task board tasks (one command)
synapse tasks accept-plan plan-auth

# Sync task board progress back to the plan card
synapse tasks sync-plan plan-auth
```

Plan cards are useful when the decomposition should be visible to the team in the
Canvas dashboard, not just the task board. Use plan cards for plans with 3+ steps
or complex dependency chains that benefit from DAG visualization.

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

- **Done:** `"Task 3f2a1b4c (Write auth tests) complete — 4 tests passing"` + `synapse tasks complete "$TESTS_ID"`
- **Next:** `"Starting task 7a9d2e10 (Implement auth module); previously blocked by 3f2a1b4c"`
- **Blocked:** `"Task c84ef901 (Integration test) waiting — blocked by 7a9d2e10 (dependency will auto-unblock on completion)"`
