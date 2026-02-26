# File Safety

## Overview

File Safety prevents multi-agent file conflicts with exclusive locking, change tracking, and modification history. When multiple agents work on the same project, File Safety ensures they don't overwrite each other's changes.

## Enabling File Safety

```bash
# Via environment variable
export SYNAPSE_FILE_SAFETY_ENABLED=true
synapse claude

# Or in .synapse/settings.json
{
  "env": {
    "SYNAPSE_FILE_SAFETY_ENABLED": "true"
  }
}
```

Storage: `.synapse/file_safety.db` (project-local SQLite, WAL mode)

## File Locking

### Check Current Locks

```bash
synapse file-safety locks
synapse file-safety locks --file src/auth.py
synapse file-safety locks --agent claude
```

### Acquire a Lock

```bash
synapse file-safety lock src/auth.py claude \
  --intent "Refactoring authentication" \
  --duration 300    # 5 minutes (default: auto-expiry)
```

!!! danger "Always Lock Before Editing"
    Two agents editing the same file simultaneously causes **data loss**. Changes are overwritten without warning. Every edit needs a lock — no exceptions.

### Release a Lock

```bash
synapse file-safety unlock src/auth.py claude
```

### Force Unlock

```bash
synapse file-safety unlock src/auth.py claude --force
```

## Change Tracking

### Record a Modification

```bash
synapse file-safety record src/auth.py claude task-123 \
  --type MODIFY \
  --intent "Added OAuth2 support"
```

Change types: `CREATE`, `MODIFY`, `DELETE`

### View File History

```bash
synapse file-safety history src/auth.py
synapse file-safety history src/auth.py --limit 10
```

### Recent Changes

```bash
synapse file-safety recent
synapse file-safety recent --agent claude --limit 20
```

## Complete Workflow

### Before Editing

```bash
# 1. Check if file is locked
synapse file-safety locks

# 2. Acquire lock
synapse file-safety lock src/auth.py claude --intent "Bug fix"

# 3. Verify lock
synapse file-safety locks
```

### After Editing

```bash
# 4. Record the modification
synapse file-safety record src/auth.py claude task-123 --type MODIFY

# 5. Release lock
synapse file-safety unlock src/auth.py claude
```

## Cleanup

### Stale Locks

Locks from dead processes (crashed agents):

```bash
synapse file-safety cleanup-locks              # Interactive
synapse file-safety cleanup-locks --force      # No confirmation
```

### Old Records

```bash
synapse file-safety cleanup --days 30          # Remove records older than 30 days
synapse file-safety cleanup --days 30 --force  # No confirmation
```

## Status and Debug

```bash
synapse file-safety status    # Overview statistics
synapse file-safety debug     # Database paths, schema version, details
```

## Python API

```python
from synapse.file_safety import FileSafetyManager, ChangeType, LockStatus

manager = FileSafetyManager.from_env()

# Acquire lock
result = manager.acquire_lock("src/auth.py", "claude", intent="Refactoring")
if result["status"] == LockStatus.ACQUIRED:
    # Edit file...
    manager.record_modification(
        "src/auth.py", "claude", "task-123",
        change_type=ChangeType.MODIFY,
        intent="Added OAuth2"
    )
    manager.release_lock("src/auth.py", "claude")

# Query
context = manager.get_file_context("src/auth.py", limit=5)
history = manager.get_file_history("src/auth.py", limit=20)
stats = manager.get_statistics()
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| File locked by another agent | Wait, work on different files, or `synapse send` to coordinate |
| Stale locks (dead process) | `synapse file-safety cleanup-locks` |
| Database not found | Enable with `SYNAPSE_FILE_SAFETY_ENABLED=true` |
| Frequent conflicts | Separate tasks by file, shorten lock duration |
