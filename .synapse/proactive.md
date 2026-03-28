PROACTIVE MODE (Synapse Feature Usage Guide):

Use Synapse coordination features based on task size and context.
Not every task needs every feature — use judgment.

--- BEFORE starting work ---
1. synapse memory search "<relevant keywords>"           - Check if someone already solved this
2. synapse list                                          - Check available agents (for delegation)

  Skip if: trivial task (< 5 min), single file change, or no other agents running.

--- DURING work ---
3. synapse file-safety lock <file>                       - Lock files before editing
4. synapse memory save <key> "<finding>" --tags <tags>   - Save discoveries worth sharing
5. synapse canvas post markdown "<content>" --title "…"  - Post complex artifacts
6. For subtasks: synapse spawn/send to delegate          - Delegate when beneficial

--- AFTER completing work ---
7. synapse file-safety unlock <file>                     - Release all file locks
8. synapse broadcast "Completed: <summary>"              - Notify team of significant completions

WHEN TO USE EACH FEATURE:

  File Safety (lock/unlock):
  - USE when multiple agents are running AND you're editing shared files
  - SKIP for single-agent tasks, new file creation, or read-only operations

  Shared Memory:
  - USE for discoveries, patterns, or decisions that benefit OTHER agents
  - SKIP for task-specific notes or information only relevant to you
  - Prefer --scope global for cross-project knowledge, project for project-specific

  Canvas:
  - USE for complex artifacts: diagrams, comparison tables, design docs,
    multi-step plans, or results that need visual structure
  - SKIP for simple completion reports, single-file changes, or quick fixes
  - Prefer A2A reply or broadcast for simple notifications

  Delegation:
  - USE when another agent has better expertise, or subtasks can run in parallel
  - SKIP when the overhead of delegation exceeds the task itself
  - Consider agent availability before spawning

  Broadcast:
  - USE for significant milestones that affect other agents' work
  - SKIP for trivial completions or work that only concerns you

TASK SIZE GUIDE:

  Small (< 5 min, 1-2 files):
    → memory search optional, file-safety if multi-agent, skip canvas/broadcast

  Medium (5-30 min, 3-5 files):
    → memory search recommended, file-safety in multi-agent, canvas for complex output

  Large (30+ min, 5+ files, multiple phases):
    → memory search, file-safety, canvas for plans/results, delegate subtasks, broadcast milestones
