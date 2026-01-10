FILE SAFETY RULES - MANDATORY FOR MULTI-AGENT COORDINATION
================================================================================

You are operating in a multi-agent environment where other agents may edit
files simultaneously. To prevent conflicts, you MUST follow these rules:

## Before Editing Any File

1. Acquire a lock BEFORE making changes:
   ```
   synapse file-safety lock <file_path> {{agent_id}} --intent "description of changes"
   ```

2. If the lock fails (file is locked by another agent):
   - DO NOT proceed with editing
   - Wait for the lock to be released, or
   - Notify the user that the file is currently being edited by another agent

## After Editing

3. Release the lock immediately after completing your changes:
   ```
   synapse file-safety unlock <file_path> {{agent_id}}
   ```

## Checking Lock Status

4. To see which files are currently locked:
   ```
   synapse file-safety locks
   ```

## Example Workflow

```
# Step 1: Acquire lock before editing
synapse file-safety lock /path/to/file.py {{agent_id}} --intent "Adding authentication"

# Step 2: Make your changes to the file
# ... edit file.py ...

# Step 3: Release lock after done
synapse file-safety unlock /path/to/file.py {{agent_id}}
```

## Important Notes

- Lock duration is 5 minutes by default (auto-expires)
- Always release locks as soon as you finish editing
- If you see "File is already locked by <agent>", respect the lock and wait
- Multiple files can be locked simultaneously if needed
