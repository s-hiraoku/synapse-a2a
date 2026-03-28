---
name: task-planner
description: >-
  Guide for decomposing large tasks into a structured plan with dependency
  chains, managing priorities, and distributing work across agents. Outputs
  plan cards or delegation messages as the team contract; TodoList for personal micro-steps.
metadata:
  internal: true
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

## Plan Output

### Plan Card Output (Canvas)

For visual plans with Mermaid DAG visualization and step-level status tracking,
post a plan card to Canvas:

```bash
# Post plan card with Mermaid DAG and step list
synapse canvas plan '{"plan_id":"plan-auth","status":"proposed","mermaid":"graph TD; A[Tests]-->B[Impl]-->C[Review]","steps":[{"id":"s1","subject":"Write auth tests","agent":"Tester","status":"pending"},{"id":"s2","subject":"Implement auth","agent":"Impl","status":"pending","blocked_by":["s1"]},{"id":"s3","subject":"Review","agent":"Tester","status":"pending","blocked_by":["s2"]}]}' --title "Auth Plan"
```

Plan cards are useful when the decomposition should be visible to the team in the
Canvas dashboard. Use plan cards for plans with 3+ steps
or complex dependency chains that benefit from DAG visualization.

### TodoList for Personal Micro-Steps

Use a TodoList for your **own** micro-step tracking within a single task.
TodoList items are fine-grained (one per coding step):

- Add failing tests for <behavior>
- Implement <behavior> behind tests
- Run targeted tests
- Update docs
- Run full test suite

## Progress Reporting

Include clear status updates in all communications:

- **Done:** `"Write auth tests complete — 4 tests passing"`
- **Next:** `"Starting Implement auth module; tests are confirmed"`
- **Blocked:** `"Integration test waiting — implementation not yet complete"`
