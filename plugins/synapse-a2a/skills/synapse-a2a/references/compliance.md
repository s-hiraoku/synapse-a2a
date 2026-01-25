# Compliance / Permissions Reference

Compliance modes control automatic input/submit operations per provider for security control.

## Modes

| Mode | Description |
|------|-------------|
| `auto` | Full automation - all operations allowed (default, backward compatible) |
| `prefill` | Input injection only - Enter/submit suppressed, user presses Enter manually |
| `manual` | No automation - content displayed/copied to clipboard, user pastes manually |

## Capability Mapping

| Mode | inject | submit | confirm | route |
|------|--------|--------|---------|-------|
| `auto` | ✓ | ✓ | ✓ | ✓ |
| `prefill` | ✓ | ✗ | ✗ | ✗ |
| `manual` | ✗ | ✗ | ✗ | ✗ |

**Capabilities:**
- **inject**: Write to provider's stdin/PTY
- **submit**: Send Enter/newline to execute
- **confirm**: Auto-respond to y/n prompts
- **route**: Route messages between agents

## Configuration

### Settings File

Configure in `.synapse/settings.json`:

```json
{
  "defaultMode": "auto",
  "providers": {
    "claude": { "mode": "prefill" },
    "codex": { "mode": "manual" },
    "gemini": { "mode": "auto" }
  },
  "ui": {
    "warningBanner": "always"
  }
}
```

### Resolution Order

Effective mode is resolved:
```
providers.<provider>.mode > defaultMode > "auto"
```

### Known Providers

- `claude`
- `codex`
- `gemini`
- `opencode`
- `copilot`

## UI Settings

### Warning Banner

| Setting | Behavior |
|---------|----------|
| `always` | Always show compliance mode banner at startup |
| `autoOnly` | Show only if any provider uses auto mode |
| `off` | Never show banner |

## API Response Behavior

| Mode | Action | HTTP Response |
|------|--------|---------------|
| `auto` | Normal send | 200 OK |
| `prefill` | Input injected, submit suppressed | 202 Accepted + `status: input_required` |
| `manual` | Blocked (display/clipboard only) | 403 Forbidden |

## Use Cases

### Security-Sensitive Projects

```json
{
  "defaultMode": "prefill",
  "providers": {
    "codex": { "mode": "manual" }
  }
}
```

Human review of all commands before execution.

### Production Environment Audit

```json
{
  "defaultMode": "manual",
  "ui": { "warningBanner": "always" }
}
```

All operations require explicit user action.

### Development with Specific Restrictions

```json
{
  "defaultMode": "auto",
  "providers": {
    "codex": { "mode": "prefill" }
  }
}
```

Full automation for most agents, but review Codex commands.

## Interaction with Other Features

### A2A Messaging

When compliance blocks routing:
- `auto` mode: Messages routed normally
- `prefill` mode: Messages blocked from routing (inject allowed but route denied)
- `manual` mode: All routing blocked

### File Safety

Compliance modes are independent of File Safety. Both can be enabled simultaneously:
- File Safety: Prevents multi-agent file conflicts
- Compliance: Controls automation level

## Troubleshooting

### Message Not Sending

If A2A messages aren't being sent:
1. Check compliance mode: `synapse config show`
2. If `prefill` or `manual`, routing is blocked
3. Switch to `auto` or send manually

### Prefill Mode: Input Appears But Doesn't Execute

Expected behavior in `prefill` mode:
1. Input is injected into PTY
2. User must press Enter to execute
3. This provides human-in-the-loop review
