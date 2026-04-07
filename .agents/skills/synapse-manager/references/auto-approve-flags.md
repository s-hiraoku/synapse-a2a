# Tool-Specific Automation Args

Each CLI agent uses different forwarded automation args. Pass them after `--`
when spawning.

**Default behavior:** Since v0.X.X, `synapse spawn` and `synapse team start`
automatically inject the appropriate auto-approve flag for each agent profile.
Use `--no-auto-approve` to disable this behavior.

## Quick Reference

| Agent | Args | Example |
|-------|------|---------|
| **Claude Code** | `--dangerously-skip-permissions` | `synapse spawn claude -- --dangerously-skip-permissions` |
| **Gemini CLI** | `--yolo` (or `-y`) | `synapse spawn gemini -- --yolo` |
| **Codex CLI** | `--full-auto` | `synapse spawn codex -- --full-auto` |
| **GitHub Copilot CLI** | `--yolo` (or `--allow-all`) | `synapse spawn copilot -- --yolo` |
| **OpenCode** | env: `OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true` | Config: `opencode.json` に `"permission": "allow"` |

## Detailed Permission Modes

### Claude Code

6-level permission modes (toggle with `Shift+Tab` during session):

| Mode | Description |
|------|-------------|
| `default` | Ask before every tool use |
| `acceptEdits` | Auto-approve file edits only; bash commands still require confirmation |
| `auto` | AI classifier (Sonnet 4.6) evaluates each action before execution; blocks dangerous ops. Requires `--enable-auto-mode` |
| `bypassPermissions` | Skip all permission prompts. **`--dangerously-skip-permissions`**. Sandbox-only |

v2.0+ recommends **Hooks** (PreToolUse events) as a safer alternative to `--dangerously-skip-permissions`.

### Codex CLI

Two-axis control: `approval_policy` × `sandbox_mode`.

| Flag | Behavior |
|------|----------|
| `--full-auto` | `-a on-request -s workspace-write` — sandboxed auto-approve (read/write in workspace) |
| `-a never` | Never ask for approval (sandbox restrictions still apply) |
| `--dangerously-bypass-approvals-and-sandbox` (`--yolo`) | Bypass both approval and sandbox — isolated runners only |

Config: `~/.codex/config.toml` profiles with `approval_policy = "never"`.

### Gemini CLI

| Flag | Behavior |
|------|----------|
| `--yolo` (`-y`) | Auto-approve all tool calls. Docker sandbox enabled by default |
| `--approval-mode=auto_edit` | Auto-approve file read/write only |
| `--allowed-tools "ShellTool(git status)"` | Bypass specific tools only |

Toggle in session: `Ctrl+Y`. Config: `~/.gemini/settings.json`.

### OpenCode

| Method | Behavior |
|--------|----------|
| `opencode.json` → `"permission": "allow"` | Auto-approve all tools |
| env `OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true` | Same effect via env var |

No `--dangerously-skip-permissions` CLI flag yet (Feature Request open).

### GitHub Copilot CLI

| Flag | Behavior |
|------|----------|
| `--yolo` (`--allow-all`) | Approve all tool/path/URL access |
| `--no-ask-user` | Suppress clarification questions |
| Autopilot mode + `--allow-all` | Fully autonomous execution |

In-session: `/yolo` or `/allow-all` slash commands.

## Synapse Auto-Approve

Synapse automatically injects the appropriate flag when spawning agents:

```bash
# Default: auto-approve enabled
synapse spawn claude          # → --dangerously-skip-permissions injected
synapse team start claude gemini  # → each agent gets its own flag

# Opt out
synapse spawn claude --no-auto-approve
synapse team start claude gemini --no-auto-approve
```

Runtime WAITING detection: if an agent hits a permission prompt despite the
CLI flag, Synapse's controller detects the WAITING status and automatically
sends the approval response (profile-specific: `y\r`, `\r`, `1\r`, `a\r`).

Safety controls:
- Unlimited consecutive auto-approvals by default (`max_consecutive=0`; set to a positive integer to cap)
- No cooldown between approvals by default (`cooldown=0.0`)
- `SYNAPSE_AUTO_APPROVE=false` env var disables globally
