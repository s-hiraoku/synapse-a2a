# Delegation Examples

## Setup Example

### Step 1: Initialize Settings (if not done)

```bash
synapse init
# Select: Project scope (./.synapse/)
```

### Step 2: Enable Delegation

Edit `.synapse/settings.json`:
```json
{
  "delegation": {
    "enabled": true
  }
}
```

Or use interactive TUI:
```bash
synapse config
# Select: Delegation
# Set: enabled = true
```

### Step 3: Define Rules

Edit `.synapse/delegate.md`:
```markdown
# Delegation Rules

Coding goes to Codex, research goes to Gemini.
Code reviews stay with Claude.
```

### Step 4: Start Agents and Delegate

```text
> Implement user authentication

[Pre-check]
- Codex: READY ✓
- File Safety: src/auth.py - not locked ✓

Delegating coding task to Codex...
synapse send codex "Please implement user authentication. Target file: src/auth.py" --response --from claude

[Codex processing... monitor with synapse list --watch]

Response from Codex:
- Created src/auth.py
- Created tests/test_auth.py

Integrated result:
✓ User authentication implemented
  - New files: src/auth.py, tests/test_auth.py
  - Tests: 5 passed
```

## Status Display Example

Check current delegation status:

```bash
# View settings
synapse config show

# View running agents
synapse list

# With watch mode (shows TRANSPORT during communication)
synapse list --watch
```

Example output:
```text
TYPE       PORT     STATUS       TRANSPORT   PID      WORKING_DIR              ENDPOINT
claude     8100     READY        -           12345    /path/to/project         http://localhost:8100
codex      8120     READY        -           12346    /path/to/project         http://localhost:8120
gemini     8110     PROCESSING   -           12347    /path/to/project         http://localhost:8110
```

Check file safety status:
```bash
synapse file-safety locks
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
   synapse send <agent> "Status update?" --priority 4 --from <your-agent>
   ```

3. If agent appears stuck, inform user and suggest alternatives

### Agent Not Available

If target agent is not running:

```text
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
