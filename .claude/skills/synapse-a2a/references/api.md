# A2A Protocol Reference

This document provides technical details for developers and advanced users.
**For normal agent communication, use `synapse send` and `synapse reply` commands.**

## Message Format

### Receiving Messages

Messages arrive with a simple `A2A:` prefix:

```text
A2A: <message content>
```

### Replying to Messages

Use `synapse reply` to respond:

```bash
synapse reply "<your response>" --from <your_agent_type>
```

The framework automatically handles routing - you don't need to know where the message came from.

## API Endpoints

### A2A Compliant

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/agent.json` | GET | Agent Card |
| `/tasks/send` | POST | Send message |
| `/tasks/send-priority` | POST | Send with priority |
| `/tasks/create` | POST | Create task (no PTY send, for `--response`) |
| `/tasks/{id}` | GET | Get task status |
| `/tasks` | GET | List tasks |
| `/tasks/{id}/cancel` | POST | Cancel task |
| `/status` | GET | READY/PROCESSING status |

### Synapse Extensions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/reply-stack/get` | GET | Get sender info without removing (peek before send) |
| `/reply-stack/pop` | GET | Pop sender info from reply map (for `synapse reply`) |

## Priority Levels

| Priority | Use Case |
|----------|----------|
| 1-2 | Low priority, background tasks |
| 3 | Normal tasks (default) |
| 4 | Urgent follow-ups |
| 5 | Emergency interrupt (sends SIGINT first) |

## Error Handling

### Agent Not Found

```text
Error: No agent found matching 'xyz'
```
**Solution:** Use `synapse list` to see available agents.

### Multiple Agents Found

```text
Error: Ambiguous target 'codex'. Multiple agents found.
```
**Solution:** Use custom name (e.g., `my-codex`) or specific identifier (e.g., `codex-8120`).

### Agent Not Responding

```text
Error: Agent 'synapse-claude-8100' server on port 8100 is not responding.
```
**Solution:** Restart the agent with `synapse claude`.
