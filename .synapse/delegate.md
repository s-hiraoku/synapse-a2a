# Delegation Rules

## Critical Rules (MUST FOLLOW)

### Self-Execution Rule
- **Do NOT delegate tasks to yourself** - If you ARE the target agent, execute the task directly
- Example: If you are Codex and the task matches "delegate to @codex", DO NOT delegate - just do it
- Example: If you are Gemini and the task is "write tests", DO NOT delegate - just write the tests

### Branch Management
- **Do NOT change branches during active work** - All agents must stay on the current branch
- **If branch change is needed**, ask the user for confirmation first
- Before switching, ensure all changes are committed or stashed
- When receiving delegated tasks, work on the same branch as the delegating agent

### Task Execution
- When you receive a task via A2A, **execute it immediately** - do not wait or announce
- Start working on the task right away, then report results
- Do not output "waiting for results" or similar - just do the work

---

## When to delegate to @gemini
- Writing tests (unit tests, integration tests, test cases)
- Test-first development (TDD)
- Creating test fixtures and mocks
- Adding test coverage

## When to delegate to @codex
- Difficult/complex problems that require deep analysis
- Debugging and fixing bugs
- Code refactoring and optimization
- Performance improvements

## Examples

### Delegate to Gemini
- "Write tests for the new feature"
- "Create unit tests for UserService"
- "Add test coverage for the API endpoints"

### Delegate to Codex
- "This function has a race condition, please fix it"
- "Refactor this module to use dependency injection"
- "Debug why the authentication is failing"
- "Optimize this database query"

---

## Task Management with History

### Monitoring Agent Progress
Use `synapse history` commands to track delegated tasks:

```bash
# List recent tasks
synapse history list

# Filter by agent
synapse history list --agent gemini
synapse history list --agent codex

# View task details
synapse history show <task_id>

# Get statistics
synapse history stats
```

### Progress Check Protocol
When managing multiple agents:

1. **Before delegating**: Check agent status with `synapse list`
2. **After delegating**: Monitor with `synapse history list --agent <name>`
3. **On completion**: Review with `synapse history show <task_id>`

### Task Status Tracking
- Use `python3 synapse/tools/a2a.py list` for real-time agent status
- Check git commits for completed work: `git log --oneline -5`
- Use priority levels (1-5) for urgent follow-ups

### Follow-up Commands
```bash
# Check if agent finished
python3 synapse/tools/a2a.py list

# Send follow-up with priority
python3 synapse/tools/a2a.py send --target <agent> --priority 4 "Status update?"

# View task history for specific agent
synapse history list --agent <agent> --limit 10
```

---

## Orchestration Best Practices

1. **Clear task descriptions**: Include context and expected outcomes
2. **Track task IDs**: Note task IDs from delegation responses
3. **Periodic checks**: Monitor `synapse list --watch` for status changes
4. **Commit verification**: Use `git status` and `git log` to verify work
5. **Escalate with priority**: Use `--priority 4-5` for urgent follow-ups
