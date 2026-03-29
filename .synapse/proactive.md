PROACTIVE MODE — Synapse Feature Usage Guide

Use features based on task size and context. Not every task needs every feature.
When in doubt, skip — unnecessary coordination wastes more time than it saves.

────────────────────────────────────────────────
TASK SIZE → FEATURE MATRIX
────────────────────────────────────────────────

  Small (< 5 min, 1-2 files):
    memory search   : optional (skip if topic is obvious)
    file-safety     : only if multi-agent + shared files
    canvas          : skip — use broadcast/reply instead
    delegation      : skip — overhead exceeds benefit
    broadcast       : skip — unless blocking others

  Medium (5-30 min, 3-5 files):
    memory search   : recommended before starting
    file-safety     : if multi-agent + shared files
    canvas          : only for complex output (see format/template guide in base instructions)
    delegation      : if subtasks can run in parallel
    broadcast       : on completion if others are waiting

  Large (30+ min, 5+ files, multiple phases):
    memory search   : required — check what's already known
    file-safety     : required in multi-agent setups
    canvas          : for plans (plan/steps template), results (briefing template)
    delegation      : actively delegate subtasks to available agents
    broadcast       : on milestones that affect others' work

────────────────────────────────────────────────
PER-FEATURE SKIP CONDITIONS
────────────────────────────────────────────────

  File Safety (lock/unlock):
    SKIP: single-agent, new file creation, read-only operations, tests

  Shared Memory:
    SKIP: task-specific notes, information only relevant to you
    USE:  discoveries or decisions that benefit other agents
    Scope: global for cross-project, project for project-specific, private for personal

  Canvas:
    SKIP: simple completion reports, single-file changes, quick fixes, brief confirmations
    USE:  when visual structure adds value (see base instructions for format/template guide)
    DO NOT post mechanically — only when it genuinely helps understanding

  Delegation:
    SKIP: overhead exceeds the task, no suitable agent available
    USE:  another agent has better expertise, or subtasks can parallelize
    Check: run `synapse list` to confirm target is READY before sending

  Broadcast:
    SKIP: trivial completions, work that only concerns you
    USE:  significant milestones, blockers, or status changes affecting others
