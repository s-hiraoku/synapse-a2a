# Multi-Agent Workflow Examples

## Basic Setup

### Start Multiple Agents

```bash
# Terminal 1: Start Claude with File Safety (History is enabled by default since v0.3.13)
SYNAPSE_FILE_SAFETY_ENABLED=true synapse claude

# Terminal 2: Start Codex
SYNAPSE_FILE_SAFETY_ENABLED=true synapse codex

# Terminal 3: Start OpenCode
SYNAPSE_FILE_SAFETY_ENABLED=true synapse opencode

# Terminal 4: Monitor
synapse list
```

## Communication Examples

### Simple Message (Fire-and-forget)

```bash
# Delegate a task (no reply needed)
synapse send codex "Please refactor the authentication module" --no-response --from synapse-claude-8100
```

### Request with Reply

```bash
# Ask a question and wait for response
synapse send gemini "What is the best approach for caching?" --response --from synapse-claude-8100
```

### With Priority

```bash
# Urgent follow-up
synapse send gemini "Status update?" --priority 4 --response --from synapse-claude-8100

# Emergency interrupt
synapse send codex "STOP" --priority 5 --from synapse-claude-8100
```

### Broadcast to All Agents

```bash
# Ask all agents in the same directory for a status check
synapse broadcast "Status check - what are you working on?" --response --from synapse-claude-8100

# Notify all agents of a completed build
synapse broadcast "FYI: Build passed, main branch updated" --no-response --from synapse-claude-8100

# Urgent broadcast to stop all work
synapse broadcast "STOP: Critical bug found in shared module" --priority 4 --from synapse-claude-8100
```

## File Coordination Example

### Delegating File Edit with Lock

```bash
# 1. Check Codex is ready
synapse list

# 2. Check file is not locked
synapse file-safety locks

# 3. Send task
synapse send codex "Please refactor src/auth.py. Acquire file lock before editing." --no-response --from synapse-claude-8100

# 4. Monitor progress
synapse file-safety locks
synapse history list --agent codex --limit 5
```

### Handling Lock Conflict

If a file is locked:

```text
File src/auth.py is locked by gemini (expires: 12:30:00)

Options:
1. Wait for lock to expire
2. Work on different files first
3. Check with lock holder:
   synapse send gemini "What's your progress on src/auth.py?" --response --from synapse-claude-8100
```

## Collaborative Development

### Code Review Workflow

```bash
# Terminal 1 (Claude): Implement feature
# Make changes to src/feature.py

# Send for review (wait for feedback)
synapse send codex "Please review the changes in src/feature.py" --response --from synapse-claude-8100

# Terminal 2 (Codex): Reply after reviewing
synapse reply "LGTM. Two suggestions: ..."
```

### Parallel Research

```bash
# Ask multiple agents simultaneously (no reply needed - they'll work independently)
synapse send gemini "Research best practices for authentication" --no-response --from synapse-claude-8100
synapse send codex "Check how other projects implement this pattern" --no-response --from synapse-claude-8100
```

## Monitoring Tasks

### Watch Agent Status

```bash
synapse list
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

## Agent Teams Workflow

### Task Board Coordination

```bash
# Coordinator creates tasks
synapse tasks create "Implement auth module" -d "OAuth2 with JWT"
synapse tasks create "Write auth tests" --blocked-by <auth_task_id>

# Assign to agents
synapse tasks assign <auth_task_id> gemini
synapse tasks assign <test_task_id> codex

# Monitor progress
synapse tasks list --status in_progress

# Complete task (auto-unblocks dependent test task)
synapse tasks complete <auth_task_id>
```

### Delegate Mode Setup

```bash
# Terminal 1: Start coordinator (cannot edit files)
synapse claude --delegate-mode --name coordinator

# Terminal 2-3: Start worker agents
synapse gemini --name worker-1
synapse codex --name worker-2

# Coordinator delegates tasks
synapse send worker-1 "Implement auth in src/auth.py" --from synapse-claude-8100
synapse send worker-2 "Write tests in tests/test_auth.py" --from synapse-claude-8100
```

### Quick Team Start (tmux)

```bash
# Start 3 agents in split panes
synapse team start claude gemini codex --layout split
```

### Sub-Agent Delegation Patterns

Spawn creates child agents for sub-task delegation — preserving context, parallelizing work for speed, and assigning specialist roles for precision. The parent always owns the lifecycle: **spawn → send → evaluate → kill**.

#### Waiting for Readiness

`synapse list` is a point-in-time snapshot. After spawning, poll until the agent shows `STATUS=READY`:

```bash
# Poll until agent is ready (re-run manually or script it)
while ! synapse list 2>/dev/null | grep -q "Tester.*READY"; do
  sleep 1
done
```

#### Pattern 1: Single-Task Delegation (Happy Path)

Spawn one agent, send one task, verify, kill.

```bash
# Spawn specialist
synapse spawn gemini --name Tester --role "test writer"

# Confirm readiness (re-run until STATUS=READY; this is a point-in-time snapshot)
synapse list   # Verify Tester shows STATUS=READY

# Delegate and wait for result
synapse send Tester "Write unit tests for src/auth.py" --response --from $SYNAPSE_AGENT_ID

# Evaluate: read reply, then verify artifacts
# (e.g., check git diff or run pytest to confirm tests exist and pass)

# Done — MUST kill
synapse kill Tester -f
# Or graceful kill (sends shutdown request, waits up to 30s): synapse kill Tester
```

#### Pattern 2: Re-Send When Result Is Insufficient

If the result doesn't meet requirements, re-send with refined instructions — don't kill and re-spawn.

```bash
# Spawn
synapse spawn codex --name Reviewer --role "code reviewer"

# Confirm readiness (re-run until STATUS=READY; this is a point-in-time snapshot)
synapse list   # Verify Reviewer shows STATUS=READY

# First attempt
synapse send Reviewer "Review src/server.py for security issues" --response --from $SYNAPSE_AGENT_ID

# Evaluate: reply is too vague → re-send with specifics
synapse send Reviewer "Also check for SQL injection in the query builder on lines 45-80" --response --from $SYNAPSE_AGENT_ID

# Evaluate: now the review is thorough — MUST kill
synapse kill Reviewer -f
```

#### Pattern 3: Multiple Specialists for Parallel Subtasks

Spawn N agents for independent subtasks, collect results, verify, kill all.

```bash
# Spawn specialists
synapse spawn gemini --name Tester --role "test writer"
synapse spawn codex --name Fixer --role "bug fixer"

# Confirm readiness of all agents (re-run until both show STATUS=READY)
synapse list   # Verify both Tester and Fixer show STATUS=READY

# Delegate parallel subtasks
synapse send Tester "Write tests for src/auth.py" --no-response --from $SYNAPSE_AGENT_ID
synapse send Fixer "Fix the timeout bug in src/server.py" --no-response --from $SYNAPSE_AGENT_ID

# Monitor progress, then collect results
synapse send Tester "Report your progress" --response --from $SYNAPSE_AGENT_ID
synapse send Fixer "Report your progress" --response --from $SYNAPSE_AGENT_ID

# Evaluate: verify artifacts (e.g., git diff, pytest)

# All done — MUST kill all
synapse kill Tester -f
synapse kill Fixer -f
```

#### How Many Agents to Spawn

1. **User-specified count** → follow it exactly (top priority)
2. **No user specification** → parent decides based on task structure:
   - Single focused subtask → 1 agent
   - Independent parallel subtasks → N agents (one per subtask)

#### Communication Notes

- Use `synapse send ... --from $SYNAPSE_AGENT_ID` (not `synapse reply`) for all communication with spawned agents ([#237](https://github.com/s-hiraoku/synapse-a2a/issues/237)). `$SYNAPSE_AGENT_ID` is automatically set by Synapse on agent start (e.g., `synapse-claude-8100`).
- **Pane auto-close:** All supported terminals automatically close spawned panes when the agent terminates.
- **Stdout capture:** `synapse spawn` prints `<agent_id> <port>` to stdout; warnings go to stderr, so command substitution captures only the clean output:
  ```bash
  result=$(synapse spawn gemini --name Helper --role "helper")
  agent_id=$(echo "$result" | awk '{print $1}')  # e.g., synapse-gemini-8110
  port=$(echo "$result" | awk '{print $2}')       # e.g., 8110
  ```
  This works in all terminals but is most useful with `tmux` where the spawning shell remains interactive.

## Troubleshooting

### Agent Not Responding

1. Check status:
   ```bash
   synapse list
   ```

2. If PROCESSING for too long:
   ```bash
   synapse send <agent> "Status?" --priority 4 --response --from <your_agent_id>
   ```

3. Emergency stop:
   ```bash
   synapse send <agent> "STOP" --priority 5 --from <your_agent_id>
   ```

### Agent Not Found

```bash
# List available agents
synapse list

# Start missing agent
synapse codex  # in new terminal
```
