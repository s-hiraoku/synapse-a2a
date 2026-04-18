FILE SAFETY (Multi-Agent File Locking):

You are {{agent_id}}. When multiple agents are running, lock files before
editing to prevent conflicts.

Worktree note: if `SYNAPSE_WORKTREE_PATH` is set, this agent is running in an
isolated git worktree and may skip locks for edits inside that worktree.

WHEN TO LOCK:
- Multiple agents are active AND you're modifying an existing shared file
- Another agent might be editing the same file concurrently

WHEN LOCKING IS NOT NEEDED:
- You're the only running agent (check: synapse list --json)
- Creating a new file (no conflict possible)
- Read-only operations
- `SYNAPSE_WORKTREE_PATH` is set AND you're editing inside that worktree tree

Still lock shared paths outside the worktree, such as $HOME config, parent repo
registries, or cross-worktree databases like ~/.synapse/file_safety.db.

WORKFLOW:

  Before editing:
  ```bash
  synapse file-safety lock <file_path> {{agent_id}} --intent "what you plan to do"
  ```

  After editing:
  ```bash
  synapse file-safety record <file_path> {{agent_id}} --type MODIFY --intent "what you changed"
  synapse file-safety unlock <file_path> {{agent_id}}
  ```

IF LOCK FAILS (another agent has it):
- Do NOT edit the file
- Check who has the lock: synapse file-safety locks
- Work on something else or coordinate with the lock holder

QUICK REFERENCE:

| Action        | Command                                                    |
|---------------|------------------------------------------------------------|
| Lock file     | synapse file-safety lock FILE {{agent_id}}                 |
| Unlock file   | synapse file-safety unlock FILE {{agent_id}}               |
| Check locks   | synapse file-safety locks                                  |
| Record change | synapse file-safety record FILE {{agent_id}} --type MODIFY |
