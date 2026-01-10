# File Safety Reference

File Safety prevents conflicts when multiple agents edit the same files.

## Enable File Safety

```bash
# Via environment variable
export SYNAPSE_FILE_SAFETY_ENABLED=true
synapse claude

# Via settings.json
synapse init
# Edit .synapse/settings.json
```

## Commands

### Check Status

```bash
# Overall statistics
synapse file-safety status

# List active locks
synapse file-safety locks
synapse file-safety locks --agent claude
```

### Lock/Unlock Files

```bash
# Acquire lock
synapse file-safety lock /path/to/file.py claude --intent "Refactoring" --duration 300

# Release lock
synapse file-safety unlock /path/to/file.py claude
```

### View File History

```bash
# File modification history
synapse file-safety history /path/to/file.py
synapse file-safety history /path/to/file.py --limit 10

# Recent modifications (all files)
synapse file-safety recent
synapse file-safety recent --agent claude --limit 20
```

### Record Modifications

```bash
synapse file-safety record /path/to/file.py claude task-123 \
  --type MODIFY \
  --intent "Bug fix"
```

### Cleanup and Debug

```bash
# Clean old records
synapse file-safety cleanup --days 30 --force

# Debug info
synapse file-safety debug
```

## Workflow

### Before Editing

1. Check if file is locked:
   ```bash
   synapse file-safety locks
   ```

2. Acquire lock:
   ```bash
   synapse file-safety lock /path/to/file.py <agent_name> --intent "Description"
   ```

### After Editing

1. Record modification:
   ```bash
   synapse file-safety record /path/to/file.py <agent_name> <task_id> --type MODIFY
   ```

2. Release lock:
   ```bash
   synapse file-safety unlock /path/to/file.py <agent_name>
   ```

## Error Handling

### File Locked by Another Agent

```
Error: File is locked by gemini (expires: 2026-01-09T12:00:00)
```

**Solutions:**
1. Wait for lock to expire
2. Work on different files first
3. Coordinate with lock holder: `@gemini What's your progress?`

## Storage

- Default DB: `~/.synapse/file_safety.db` (SQLite)
- Project-level: `.synapse/file_safety.db`
- Configure via `SYNAPSE_FILE_SAFETY_DB_PATH`
