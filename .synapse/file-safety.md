FILE SAFETY RULES - STRICTLY MANDATORY
================================================================================

You are operating in a shared multi-agent environment.
**IT IS A PROTOCOL VIOLATION TO EDIT ANY FILE WITHOUT LOCKING IT FIRST.**

## ⚠️ CRITICAL: NO LOCK = NO EDIT ⚠️

1. **NEVER** modify a file without acquiring a lock first.
2. **NEVER** ignore a lock failure. If locked by another agent, YOU MUST WAIT.
3. **ALWAYS** release the lock immediately after editing.

## Mandatory Workflow (Do NOT deviate)

### 1. ACQUIRE LOCK (Required)
Before ANY `write_file`, `replace`, or shell command that modifies files:

```bash
synapse file-safety lock <file_path> {{agent_id}} --intent "Short description"
```

> **IF LOCK FAILS:**
> - 🛑 **STOP**. Do NOT edit the file.
> - Move to other tasks or wait.
> - Retry lock later.

### 2. EDIT FILE
Perform your edits only after seeing "Lock acquired".

### 3. RECORD & UNLOCK (Required)
Immediately after the edit is complete:

```bash
# 1. Record the change
synapse file-safety record <file_path> {{agent_id}} <task_id> --type MODIFY --intent "What changed"

# 2. Release the lock
synapse file-safety unlock <file_path> {{agent_id}}
```

## Example

```bash
# CORRECT WAY
synapse file-safety lock src/main.py {{agent_id}} --intent "Fix bug"
# ... (wait for success) ...
# ... (edit file) ...
synapse file-safety record src/main.py {{agent_id}} task-123 --type MODIFY --intent "Fixed NPE"
synapse file-safety unlock src/main.py {{agent_id}}
```

## Checking Status

- `synapse file-safety locks` : See who is holding locks
- `synapse file-safety history <file>` : See past changes

**VIOLATING THESE RULES WILL CAUSE DATA CORRUPTION AND AGENT CONFLICTS.**
