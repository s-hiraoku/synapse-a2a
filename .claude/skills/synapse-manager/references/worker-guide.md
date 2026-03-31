# Worker Agent Guide

How to operate as a worker agent in a multi-agent team.

## On Task Receipt

1. **Start immediately** — `[REPLY EXPECTED]` messages require a response; others are fire-and-forget
2. **Check shared knowledge first** — other agents may have already solved similar problems:
   ```bash
   synapse memory search "<task topic>"
   ```
3. **Lock files before editing** — without locks, concurrent edits silently overwrite each other:
   ```bash
   synapse file-safety lock <file> $SYNAPSE_AGENT_ID --intent "description"
   ```

## During Work

Progress reporting prevents managers from sending unnecessary interrupts:
- Report progress on long tasks (>5 min): `synapse send <manager> "Progress: <update>" --silent`
- Report blockers immediately: `synapse send <manager> "<specific question>" --wait`
- Save discoveries for the team: `synapse memory save <key> "<finding>" --tags <topic>`

### Sub-Delegation

Workers can spawn helpers for independent subtasks:
```bash
# Single helper
synapse spawn gemini --worktree --name Helper --role "test writer"
synapse send Helper "Write tests for auth.py and report the result" --notify
synapse kill Helper -f

# Multiple helpers — use team start for proper tile layout
synapse team start gemini:Tester codex:Linter --worktree
synapse send Tester "Write tests for auth.py" --notify
synapse send Linter "Run linting on src/" --notify
# Clean up after completion:
synapse kill Tester -f && synapse kill Linter -f
```
Auto-approve flags are injected automatically. Prefer different model types to distribute load.

## On Completion

1. Report results to manager:
   ```bash
   synapse send <manager> "Done: <change summary>" --silent
   ```
2. Include test results if tests were run

## On Failure

Transparency prevents wasted effort — the manager needs to reassign or adjust the plan:
1. `synapse send <manager> "Failed: <error details>" --silent`
2. Do NOT silently move on

## Default vs Proactive Mode

In **default mode**, the checkpoints described above apply as written.

In **proactive mode** (`SYNAPSE_PROACTIVE_MODE_ENABLED=true`), those same checkpoints apply
**plus** mandatory use of shared memory, file safety, canvas, and broadcast — even for
1-line fixes. Follow the injected checklist strictly. See `synapse-a2a/references/features.md`
for the full checklist.

## When No Manager Exists

If there is no manager/coordinator agent in the team:
- Assess the situation: `synapse list`
- Coordinate directly with available teammates
- Proactively delegate and spawn when it improves efficiency
- Share decisions via `synapse memory` so the team stays aligned
