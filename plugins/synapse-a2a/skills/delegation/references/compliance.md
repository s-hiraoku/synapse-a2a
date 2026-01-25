# Compliance Mode Integration with Delegation

Compliance modes affect how delegation works between agents.

## Impact on Routing

| Mode | Routing Allowed | Behavior |
|------|-----------------|----------|
| `auto` | Yes | Messages routed normally between agents |
| `prefill` | No | Routing blocked - `route` capability disabled |
| `manual` | No | All automation blocked |

## Check Compliance Before Delegating

```bash
# View effective settings
synapse config show

# Check specific provider's mode
synapse config show --scope project
```

## Configuration for Delegation

For delegation to work, the source agent (coordinator) must have `auto` mode:

```json
{
  "defaultMode": "auto",
  "providers": {
    "claude": { "mode": "auto" }
  }
}
```

If Claude (coordinator) is in `prefill` or `manual` mode, it cannot route messages to other agents.

## Scenarios

### Full Automation (Default)

```json
{
  "defaultMode": "auto"
}
```

All agents can route messages freely. Delegation works normally.

### Restricted Coordinator

```json
{
  "defaultMode": "auto",
  "providers": {
    "claude": { "mode": "prefill" }
  }
}
```

Claude cannot route messages. Must switch to manual @agent patterns or use `synapse send` directly.

### Restricted Worker

```json
{
  "defaultMode": "auto",
  "providers": {
    "codex": { "mode": "prefill" }
  }
}
```

Claude can route TO Codex, but:
- Input is injected into Codex's PTY
- User must press Enter to execute
- Useful for reviewing commands before execution

## Troubleshooting

### Delegation Not Working

1. **Check source agent's mode:**
   ```bash
   synapse config show
   ```

2. **If `prefill` or `manual`:**
   - Routing is blocked
   - Use `synapse send` command directly from your terminal
   - Or change mode to `auto`

### API Returns 403 Forbidden

Target provider is in `manual` mode:
- Cannot receive automated messages
- User must manually interact with that agent

### API Returns 202 with input_required

Target provider is in `prefill` mode:
- Input was injected
- User must press Enter in target agent's terminal
- Use terminal jump: `synapse list` → select agent → Enter/j
