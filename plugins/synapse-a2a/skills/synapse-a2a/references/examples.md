# Multi-Agent Workflow Examples

## Basic Setup

### Start Multiple Agents

```bash
# Terminal 1: Start Claude with all features
SYNAPSE_HISTORY_ENABLED=true SYNAPSE_FILE_SAFETY_ENABLED=true synapse claude

# Terminal 2: Start Codex
SYNAPSE_HISTORY_ENABLED=true SYNAPSE_FILE_SAFETY_ENABLED=true synapse codex

# Terminal 3: Monitor
synapse list --watch
```

## Communication Examples

### Simple Message

```
@codex Please refactor the authentication module
```

### With Priority

```bash
# Urgent follow-up
python3 synapse/tools/a2a.py send --target gemini --priority 4 "Status update?"

# Emergency interrupt
python3 synapse/tools/a2a.py send --target codex --priority 5 "STOP"
```

### Fire-and-forget (No Response Expected)

```
@gemini --non-response Log this completion event
```

## File Coordination Example

### Delegating File Edit with Lock

```bash
# 1. Check Codex is ready
synapse list

# 2. Check file is not locked
synapse file-safety locks

# 3. Send task
@codex Please refactor src/auth.py. Acquire file lock before editing.

# 4. Monitor progress
synapse file-safety locks
synapse history list --agent codex --limit 5
```

### Handling Lock Conflict

If a file is locked:

```
File src/auth.py is locked by gemini (expires: 12:30:00)

Options:
1. Wait for lock to expire
2. Work on different files first
3. Check with lock holder: @gemini What's your progress on src/auth.py?
```

## Collaborative Development

### Code Review Workflow

```bash
# Terminal 1 (Claude): Implement feature
# Make changes to src/feature.py

# Send for review
@codex Please review the changes in src/feature.py

# Wait for feedback and iterate
```

### Parallel Research

```bash
# Ask multiple agents simultaneously
@gemini Research best practices for authentication
@codex Check how other projects implement this pattern
```

## Monitoring Tasks

### Watch Agent Status

```bash
synapse list --watch
```

### View Task History

```bash
# Recent tasks
synapse history list --limit 10

# By agent
synapse history list --agent codex

# Search
synapse history search "auth" --agent codex
```

### Check Git Changes

```bash
git status
git log --oneline -5
git diff
```

## Troubleshooting

### Agent Not Responding

1. Check status:
   ```bash
   synapse list
   ```

2. If PROCESSING for too long:
   ```bash
   python3 synapse/tools/a2a.py send --target <agent> --priority 4 "Status?"
   ```

3. Emergency stop:
   ```bash
   python3 synapse/tools/a2a.py send --target <agent> --priority 5 "STOP"
   ```

### Agent Not Found

```bash
# List available agents
synapse list

# Start missing agent
synapse codex  # in new terminal
```
