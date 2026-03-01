# Troubleshooting

## PTY / TUI Issues

### Screen Corruption

**Symptom**: Agent's TUI display is garbled or overlapping.

**Solutions**:

- Press ++ctrl+l++ to redraw the screen
- Restart the agent: `synapse kill <agent> && synapse <type>`
- Check terminal encoding: `locale` should show UTF-8

### Agent Display Not Updating

**Symptom**: `synapse list` shows stale status.

**Solutions**:

- File watcher may have failed — press any key to force refresh
- Check if the agent process is still running: `ps aux | grep synapse`
- Restart `synapse list`

### Font Rendering Issues

**Symptom**: Icons or special characters display as boxes.

**Solution**: Install a [Nerd Font](https://www.nerdfonts.com/) and configure your terminal to use it.

## Agent Detection Problems

### @Agent Not Found

**Symptom**: `@gemini` pattern doesn't route messages.

**Solutions**:

- Verify the target agent is running: `synapse list`
- Check working directory matches (agents in different directories can't see each other by default)
- Use explicit `synapse send` instead of `@agent` pattern

### Agent Missing from List

**Symptom**: Agent is running but doesn't appear in `synapse list`.

**Solutions**:

- Check registry directory: `ls ~/.a2a/registry/`
- Agent may have crashed — check logs: `synapse logs <type>`
- Stale registry entry — restart the agent

### Stale Registry Entries

**Symptom**: Dead agents still appear in `synapse list`.

**Solution**: Dead processes are auto-cleaned on next registry read. If persistent:

```bash
# Check PID
cat ~/.a2a/registry/synapse-<type>-<port>.json | python -m json.tool

# Remove manually if PID is dead
rm ~/.a2a/registry/synapse-<type>-<port>.json
```

## Network / Port Issues

### Port Conflict

**Symptom**: "Address already in use" error.

**Solutions**:

```bash
# Find what's using the port
lsof -i :<port>

# Use a different port
synapse claude --port 8105

# Kill stale processes
synapse kill <agent> -f
```

### Codex Sandbox Networking

**Symptom**: Codex can't communicate with other agents.

**Solution**: Codex runs in a sandboxed environment that may block network access. Use `--force` to bypass working directory checks, or check Codex's network permissions.

### Connection Timeout

**Symptom**: `synapse send` hangs or times out.

**Solutions**:

- Verify target agent is READY: `synapse list`
- Check if the agent is initializing (HTTP 503 = not ready yet)
- Try with higher priority: `--priority 4`
- Check logs: `synapse logs <target-type>`

## State Detection Problems

### Agent Stuck in PROCESSING

**Symptom**: Agent never reaches READY state.

**Solutions**:

- The agent may be actively working — check its terminal
- Idle detection timeout may be too short — increase in profile YAML
- Send an interrupt: `synapse interrupt <agent> "Status?"`
- Force kill and restart: `synapse kill <agent> -f`

### Response Timeout

**Symptom**: `--wait` flag waits indefinitely.

**Solutions**:

- Check if the target received the `[REPLY EXPECTED]` marker
- Verify the target knows to use `synapse reply`
- Send a follow-up with higher priority: `synapse send <agent> "Reply?" -p 4 --wait`

## Input Issues

### IME Problems

**Symptom**: Japanese/Chinese input doesn't work correctly.

**Solution**: PTY may not handle IME well. Type the message in an editor and use `synapse send --message-file`.

### Large Message Fails

**Symptom**: Long messages are truncated or not submitted.

**Solution**: Use file-based messaging:

```bash
synapse send claude --message-file /tmp/message.txt --silent
```

## Spawn Issues

### Pane Not Created

**Symptom**: `synapse spawn` or `synapse team start` doesn't create new panes.

**Solutions**:

- Verify terminal support: tmux, iTerm2, Terminal.app, Ghostty, or Zellij
- Check if tmux is running: `tmux list-sessions`
- Try explicit terminal: `synapse spawn claude --terminal tmux`

### Agent Not Ready After Spawn

**Symptom**: Spawned agent is in PROCESSING state for a long time.

**Solution**: Wait for initialization to complete. Check with `synapse list`. The agent needs time to start the CLI tool and detect the first idle state.

## Terminal-Specific Issues

### Ghostty: Agent Spawned in Wrong Tab

**Symptom**: `synapse spawn` or `synapse team start` creates new panes in a different Ghostty tab than intended.

**Cause**: Ghostty uses AppleScript to target the **currently focused window/tab**. If you switch tabs while the command is running, the agent will be spawned in whichever tab is focused at that moment.

**Solution**: Wait for the `spawn` or `team start` command to complete before switching tabs in Ghostty.

## File Safety Issues

### Lock Not Releasing

**Symptom**: File remains locked after agent finishes.

**Solution**:

```bash
synapse file-safety cleanup-locks --force
```

### Database Not Found

**Symptom**: "File safety database not found" error.

**Solution**: Enable file safety and initialize:

```bash
export SYNAPSE_FILE_SAFETY_ENABLED=true
synapse init --scope project
```

## Logging

### Check Agent Logs

```bash
synapse logs claude              # Latest logs
synapse logs claude -f           # Follow (live)
synapse logs claude -n 200       # Last 200 lines
```

### Log Location

```
~/.synapse/logs/<agent-type>-<port>.log
```

## Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/test_controller.py -v

# Pattern match
pytest -k "test_identity" -v
```

## Getting Help

- **GitHub Issues**: [github.com/s-hiraoku/synapse-a2a/issues](https://github.com/s-hiraoku/synapse-a2a/issues)
- **Check logs**: `synapse logs <agent>` and `~/.synapse/logs/`
- **Debug info**: `synapse file-safety debug` for File Safety diagnostics
