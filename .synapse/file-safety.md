================================================================================
STOP! READ THIS BEFORE EVERY FILE EDIT
================================================================================

You are {{agent_id}} in a multi-agent environment.
Other agents may be editing files at the same time.

================================================================================
BEFORE YOU USE: Edit, Write, sed, awk, or ANY file modification
================================================================================

ASK YOURSELF: "Did I run synapse file-safety lock?"

If NO --> Run this FIRST:
```bash
synapse file-safety lock <file_path> {{agent_id}} --intent "what you plan to do"
```

If lock fails (another agent has it):
  - DO NOT edit the file
  - Work on something else
  - Try again later

================================================================================
AFTER YOUR EDIT IS COMPLETE
================================================================================

Run BOTH commands:
```bash
synapse file-safety record <file_path> {{agent_id}} <task_id> --type MODIFY --intent "what you changed"
synapse file-safety unlock <file_path> {{agent_id}}
```

================================================================================
QUICK REFERENCE
================================================================================

BEFORE EDIT:
  synapse file-safety lock src/foo.py {{agent_id}} --intent "Fix bug"

AFTER EDIT:
  synapse file-safety record src/foo.py {{agent_id}} task-123 --type MODIFY --intent "Fixed null check"
  synapse file-safety unlock src/foo.py {{agent_id}}

CHECK WHO HAS LOCKS:
  synapse file-safety locks

================================================================================
CRITICAL WRITE PROTOCOL (Read-After-Write Verification)
================================================================================

After any WRITE operation, you MUST verify your change exists:

1. WRITE the file (using Edit, Write, or other modification tool)
2. READ the file back immediately to verify your change exists
3. If missing or incorrect, RETRY immediately:
   - Re-acquire lock if expired
   - Write again
   - Verify again

NEVER assume write success without reading it back.

Example workflow:
```bash
# 1. Lock
synapse file-safety lock src/foo.py {{agent_id}} --intent "Fix bug"

# 2. Edit the file
# (use Edit tool)

# 3. VERIFY - Read the file back and confirm your changes exist
# (use Read tool)

# 4. If verified, record and unlock
synapse file-safety record src/foo.py {{agent_id}} task-123 --type MODIFY --intent "Fixed null check"
synapse file-safety unlock src/foo.py {{agent_id}}

# 5. If NOT verified, retry from step 2 (or step 1 if lock expired)
```

================================================================================
WHY THIS MATTERS
================================================================================

- Without locks, two agents editing the same file = DATA LOSS
- Your changes may be overwritten without warning
- Other agents' work may be destroyed
- Without Read-After-Write verification, you may not notice failed writes

EVERY EDIT NEEDS A LOCK. NO EXCEPTIONS.
EVERY WRITE NEEDS VERIFICATION. NO EXCEPTIONS.
