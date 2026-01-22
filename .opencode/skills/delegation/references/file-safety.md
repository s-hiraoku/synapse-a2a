# File Safety Integration

When delegating file modification tasks, use File Safety to prevent conflicts.

## Before Delegation

```bash
# Check existing locks
synapse file-safety locks

# Acquire lock for the target file
synapse file-safety lock /path/to/file.py <agent_name> --intent "Task description"
```

## In Delegation Message

Include file context:

```
@codex Please refactor src/auth.py.
Note: File is locked by claude for this task. Lock will be released after you complete.
Recent changes: claude fixed authentication logic (2026-01-09)
```

## After Delegation Completes

```bash
# Verify changes were recorded
synapse file-safety history /path/to/file.py

# Release lock if held
synapse file-safety unlock /path/to/file.py <agent_name>
```

## Handling Lock Conflicts

If target file is locked by another agent:

```
File /path/to/file.py is locked by <agent>.
Options:
1. Wait for completion
2. Work on different files first
3. Check with lock holder: @<agent> What's your progress?
```

## Pre-Delegation File Safety Check

When delegating file edits:

1. **Check lock status**:
   ```bash
   synapse file-safety locks
   ```

2. **If locked by another agent**: Inform user and wait or work on other files

3. **If unlocked**: Include lock instruction in delegation message

4. **After completion**: Verify lock was released

## Error Handling

### Lock Already Held

```
Error: File is locked by gemini (expires: 12:30:00)
```

**Solutions:**
- Wait for lock to expire
- Work on different files
- Coordinate with lock holder

### Failed to Acquire Lock

```
Error: Could not acquire lock for /path/to/file.py
```

**Solutions:**
- Check if file exists
- Check permissions
- Retry after brief delay
