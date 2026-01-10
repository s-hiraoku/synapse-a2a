FILE SAFETY RULES - MANDATORY FOR MULTI-AGENT COORDINATION
================================================================================

You are operating in a multi-agent environment where other agents may edit
files simultaneously. To prevent conflicts, you MUST follow these rules:

## Before Editing Any File

1. **Check current locks** to see if the file is being edited:
   ```
   synapse file-safety locks
   ```

2. **Acquire a lock** BEFORE making changes:
   ```
   synapse file-safety lock <file_path> {{agent_id}} --intent "description"
   ```

3. **If lock fails** (file is locked by another agent):
   - DO NOT proceed with editing
   - Wait or notify the user

## After Editing

4. **Record the modification** for tracking:
   ```
   synapse file-safety record <file_path> {{agent_id}} <task_id> --type MODIFY --intent "what you changed"
   ```

   Change types: `CREATE`, `MODIFY`, `DELETE`

5. **Release the lock** immediately:
   ```
   synapse file-safety unlock <file_path> {{agent_id}}
   ```

## Complete Workflow Example

```bash
# Step 1: Check locks
synapse file-safety locks

# Step 2: Acquire lock
synapse file-safety lock /path/to/file.py {{agent_id}} --intent "Adding auth"

# Step 3: Edit the file
# ... make your changes ...

# Step 4: Record modification
synapse file-safety record /path/to/file.py {{agent_id}} task-123 --type MODIFY --intent "Added auth middleware"

# Step 5: Release lock
synapse file-safety unlock /path/to/file.py {{agent_id}}
```

## Checking History

```bash
# View modification history for a file
synapse file-safety history <file_path>

# View recent modifications across all files
synapse file-safety recent
```

## Important Notes

- Lock duration is 5 minutes (auto-expires)
- Always release locks immediately after editing
- Always record modifications for audit trail
- If locked by another agent, wait or notify user
