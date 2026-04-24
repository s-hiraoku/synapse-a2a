# Tool-Specific Automation Args

Each CLI agent uses different forwarded automation args. Pass them after `--`
when spawning.

**Default behavior:** Since v0.X.X, `synapse spawn` and `synapse team start`
automatically inject the appropriate auto-approve flag for each agent profile.
Use `--no-auto-approve` to disable this behavior.

## Quick Reference

| Agent | Default Args | Example |
|-------|------|---------|
| **Claude Code** | `--permission-mode=auto` (was `--dangerously-skip-permissions`) | `synapse spawn claude -- --permission-mode=auto` |
| **Gemini CLI** | `--approval-mode=yolo` (was `--yolo` / `-y`) | `synapse spawn gemini -- --approval-mode=yolo` |
| **Codex CLI** | `--full-auto` | `synapse spawn codex -- --full-auto` |
| **GitHub Copilot CLI** | `--allow-all` (alias `--yolo`) | `synapse spawn copilot -- --allow-all` |
| **OpenCode** | env: `OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true` | Config: `opencode.json` に `"permission": "allow"` |

> **Migration note (2026-04):** Anthropic deprecated `--dangerously-skip-permissions`
> in favor of `--permission-mode=auto`, which keeps a safety classifier active
> instead of disabling all checks. Gemini CLI similarly recommends the unified
> `--approval-mode=<mode>` form over the legacy short flags. The legacy flags
> still work and remain in each profile's `alternative_flags` so users who pass
> them manually do not get a duplicated flag injected.

## Detailed Permission Modes

### Claude Code

6 permission modes (launch with `--permission-mode <mode>`; settings key `permissions.defaultMode`; Shift+Tab cycles default → acceptEdits → plan during a session):

| Mode | Description |
|------|-------------|
| `default` | Launch default; prompts before edits and commands, while reads are allowed. |
| `acceptEdits` | Auto-approves file edits and fs commands (mkdir/mv/cp/touch/rm/rmdir/sed); bash still prompts. |
| `plan` | Read-only planning mode; proposes changes without applying them. |
| `auto` | Background classifier safety checks (Research Preview; Sonnet/Opus 4.6+, eligible plans only). |
| `dontAsk` | Denies all tools except `permissions.allow` rules and read-only Bash. |
| `bypassPermissions` | Skips all checks except protected paths; **`--dangerously-skip-permissions`** is the alias for `--permission-mode bypassPermissions`. Isolated containers only. |

**Synapse default:** `--permission-mode=auto` (was `--dangerously-skip-permissions`).
v2.0+ also recommends **Hooks** (PreToolUse events) as a more granular alternative
to bypass-style flags.

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
| `--approval-mode=yolo` | Auto-approve all tool calls. Docker sandbox enabled by default. Synapse default |
| `--yolo` (`-y`) | Legacy short form of `--approval-mode=yolo`; still accepted |
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
synapse spawn claude          # → --permission-mode=auto injected (was --dangerously-skip-permissions)
synapse team start claude gemini  # → each agent gets its own flag (Gemini gets --approval-mode=yolo)

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
