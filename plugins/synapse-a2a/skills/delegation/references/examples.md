# Delegation Examples

## Setup Example

```
> /delegate orchestrator

Please describe your delegation rules:
> Coding goes to Codex, research goes to Gemini

✓ Configuration saved

Current settings:
- Mode: orchestrator
- Rules: Coding goes to Codex, research goes to Gemini

Activate delegation with these settings? [Y/n]
> Y

✓ Delegation enabled

---

> Implement user authentication

[Pre-check]
- Codex: READY ✓
- File Safety: src/auth.py - not locked ✓

Delegating coding task to Codex...
@codex Please implement user authentication. Target file: src/auth.py
Acquire file lock before editing.

[Codex processing... monitor with synapse list --watch]

Response from Codex:
- Created src/auth.py
- Created tests/test_auth.py
- Lock released

Integrated result:
✓ User authentication implemented
  - New files: src/auth.py, tests/test_auth.py
  - Tests: 5 passed
```

## Status Display Example

When `/delegate status` is invoked:

```
=== Delegation Configuration ===
Mode: orchestrator
Rules:
  Coding goes to Codex, research goes to Gemini
Status: active

=== Available Agents ===
NAME     STATUS      PORT   WORKING_DIR
claude   READY       8100   /path/to/project
codex    READY       8120   /path/to/project
gemini   PROCESSING  8110   /path/to/project

=== File Safety ===
Active Locks: 1
  /path/to/api.py - gemini (expires: 12:30:00)
================================
```

## Error Handling Examples

### Agent Not Responding

If agent doesn't respond within reasonable time:

1. Check agent status:
   ```bash
   synapse list
   ```

2. If PROCESSING for too long, send priority 4-5 follow-up:
   ```bash
   python3 synapse/tools/a2a.py send --target <agent> --priority 4 "Status update?"
   ```

3. If agent appears stuck, inform user and suggest alternatives

### Agent Not Available

If target agent is not running:

```
Target agent (<agent>) not found.
Solutions:
1. Start in another terminal: synapse <agent>
2. Delegate to different agent
3. Process manually
```

### Task Failed

If delegated task fails:

1. Review error message from agent
2. Provide context and retry with adjusted instructions
3. If repeated failures, process directly or suggest user intervention

## Monitoring Examples

### Real-time Status

```bash
# Watch agent status changes
synapse list --watch

# Check specific agent
synapse list | grep <agent>
```

### Task History

If history is enabled:

```bash
# Recent tasks by agent
synapse history list --agent <agent> --limit 10

# Task details
synapse history show <task_id>

# Statistics
synapse history stats --agent <agent>
```

### Git Activity

Monitor file changes from delegated tasks:

```bash
git status
git log --oneline -5
git diff
```
