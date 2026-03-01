# AI Coding Agent CLI Cheatsheet

> 4 major CLI tools: **Claude Code** / **Gemini CLI** / **Codex CLI** / **Copilot CLI**
>
> Last updated: 2026-02-26

## Startup

```bash
# Claude Code
claude                    # Interactive mode
claude "question"         # One-shot mode
claude -p "question"      # --print: output to stdout and exit
claude --output-format json "question" # JSON output
claude --worktree         # Isolated git worktree (-w)
claude remote-control     # Remote Control: operate from mobile (/rc)

# Gemini CLI
gemini                    # Interactive mode
gemini "question"         # One-shot mode
gemini -p "question"      # --prompt
gemini -p "question" --output-format json  # JSON output

# Codex CLI
codex                     # Full-screen TUI
codex "question"          # Start with initial prompt
codex exec "question"     # Non-interactive mode (alias: codex e)
codex app                 # Desktop app (macOS)

# Copilot CLI
copilot                   # Interactive mode
copilot -p "question"     # --prompt: non-interactive
copilot --model gpt-5     # Start with specific model
copilot --experimental    # Enable experimental features
```

## Session Management

```bash
# Claude Code
claude --continue         # Resume latest session (-c)
claude --resume           # Select session to resume (-r)
claude --resume <id>      # Resume specific session
claude --from-pr <PR#>    # Resume session linked to PR

# Gemini CLI
gemini --resume           # Resume latest session
gemini --resume <index>   # Resume specific session
/resume                   # Select session from within
/chat save <tag>          # Save checkpoint with tag
/chat resume <tag>        # Restore from checkpoint

# Codex CLI
codex resume              # Select session to resume
codex resume --last       # Resume latest session
codex resume <SESSION_ID> # Resume specific session
/resume                   # Resume from within session
/new                      # Start new session in same CLI

# Copilot CLI
copilot --resume          # Select session to resume
/resume                   # Select session from within
/session                  # Show current session info
```

## Permission Modes

| Level | Claude Code | Gemini CLI | Codex CLI | Copilot CLI |
|-------|------------|------------|-----------|-------------|
| **Read-only** | -- | `--sandbox` | `/permissions` -> Read-only | Default (confirm each) |
| **Confirm** | Default | Default | `/permissions` -> Auto (default) | `--allow-tool=<tool>` |
| **Full auto** | `--dangerously-skip-permissions` | `-y` (yolo) / `Shift+Y` | `--full-auto` (sandboxed) / `--dangerously-bypass-approvals-and-sandbox` (unrestricted) | `--allow-all-tools` / `/yolo` |

**Notes:**
- Codex CLI: `/permissions` command to switch modes mid-session. Auto is default (read/write/execute in working directory).
- Copilot CLI: `Shift+Tab` to cycle modes: **Interactive** (default) -> **Plan** -> **Autopilot**.
- Gemini CLI: `Shift+Y` or `Shift+Tab` for mode switch. Policy Engine for org-level permission control.

## Slash Commands

### Claude Code

| Command | Description |
|---------|-------------|
| `/help` | Show help and command list |
| `/init` | Generate project CLAUDE.md |
| `/clear` | Clear conversation context |
| `/compact` | Summarize and compress conversation |
| `/context` | Show token usage breakdown |
| `/cost` | Show session cost and token count |
| `/usage` | Show plan usage limits |
| `/model` | Switch model (Opus 4.6 / Sonnet 4.6 / Haiku 4.5) |
| `/rewind` | Rewind conversation and undo code changes |
| `/debug` | Troubleshoot current session |
| `/rename` | Rename session (updates terminal tab title) |
| `/permissions` | View/change permission settings |
| `/config` | View/edit configuration files |
| `/mcp` | Check MCP server connection status |
| `/vim` | Toggle vim mode |
| `/terminal-setup` | Configure Shift+Enter support |
| `/login` | Log in to Anthropic account |
| `/doctor` | Run environment diagnostic tool |
| `/fast` | Toggle Fast Mode (Opus 4.6 fast output) |
| `/bug` | Submit bug report |
| `!<command>` | Execute shell command directly (saves tokens) |

> **`claude agents`**: Run as subcommand to view all configured agents.

### Gemini CLI

| Command | Description |
|---------|-------------|
| `/help` | Show help and command list |
| `/plan` | Launch Plan Mode (design then execute) |
| `/chat save <tag>` | Save current session with tag |
| `/chat resume <tag>` | Restore saved session |
| `/chat list` | List saved sessions |
| `/resume` | Show session selection UI |
| `/tools` | Show available tools |
| `/mcp` | Check MCP server status |
| `/memory` | Show memory (context) state |
| `/stats` | Show usage statistics |
| `/compress` | Compress conversation (save tokens) |
| `/rewind` | Rewind conversation history |
| `/skills install` | Install Agent Skills |
| `/skills uninstall` | Uninstall Agent Skills |
| `/skills reload` | Reload Skills definitions |
| `/agents refresh` | Refresh agent settings |
| `/prompt-suggest` | Generate prompt suggestions |
| `/introspect` | Debug introspection command |
| `/logout` | Clear auth credentials |
| `/theme` | Switch theme (auto-detect supported) |
| `/quit` | End session |

### Codex CLI

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/model` | Switch model (GPT-5.3-Codex etc.) |
| `/permissions` | Change approval mode (Auto / Read-only / Full Access) |
| `/review` | Request AI code review |
| `/plan` | Switch to Plan Mode |
| `/diff` | Show git diff (staged/unstaged/untracked) |
| `/mention <path>` | Add file to context |
| `/new` | Start new conversation in same CLI |
| `/resume` | Restore saved session |
| `/compact` | Summarize and compress conversation |
| `/personality` | Change agent response style |
| `/agent` | Agent settings |
| `/status` | Show debug/policy diagnostics |
| `/statusline` | Customize footer statusline items |
| `/experimental` | Toggle experimental features (Multi-agents etc.) |
| `/quit` / `/exit` | End session |

### Copilot CLI

| Command | Description |
|---------|-------------|
| `/help` | Show help and command list (`?` also works) |
| `/model` | Switch model (Claude Sonnet 4.5 / Claude Opus 4.6 / GPT-5.3-Codex / Gemini 3 Pro etc.) |
| `/clear` | Clear conversation context |
| `/compact` | Compress conversation to save tokens |
| `/context` | Show token usage details |
| `/usage` | Show session statistics (premium request count etc.) |
| `/session` | Show current session info |
| `/resume` | Restore previous session |
| `/cwd <path>` | Change working directory |
| `/add-dir <path>` | Grant access to specific directory |
| `/add-file <file>` | Add specific file to context |
| `/review` | Run code change review |
| `/delegate` | Push task to GitHub Copilot coding agent (creates PR) |
| `/plugin install <owner/repo>` | Install plugin from GitHub repo |
| `/share` | Export session as Markdown file |
| `/mcp` | Manage MCP servers (add/remove/reload) |
| `/allow-all` | Allow all tool usage |
| `/yolo` | Skip all approvals (full auto mode) |
| `/login` | Log in to GitHub account |
| `/feedback` | Send feedback to GitHub |
| `/terminal-setup` | Configure multi-line input |
| `/experimental` | Enable experimental features |
| `/lsp` | Check LSP server settings |
| `/skills` | Show available skills |
| `/exit` / `/quit` | End session |

> **Cross-session memory**: Copilot CLI automatically remembers coding conventions and project structure during work, utilizing them in subsequent sessions.

> **Copilot CLI GA: February 25, 2026.** Supports Claude Opus 4.6 / Sonnet 4.6, GPT-5.3-Codex, Gemini 3 Pro / 3.1 Pro and more. Plugin system included.

## Sub-Agents

```bash
# Claude Code (via prompt or --agents flag)
"use subagent to ..."     # Launch subagent to delegate task
# Up to 10 parallel. Each agent has independent context window

# Pre-define agents with --agents flag
claude --agents '{
  "code-reviewer": {
    "description": "Expert code reviewer",
    "prompt": "You are a senior code reviewer.",
    "tools": ["Read", "Grep", "Glob", "Bash"],
    "model": "sonnet"
  }
}'

# Worktree isolation (per agent definition)
# "isolation": "worktree" runs agent in isolated git worktree

# Agent Teams (Research Preview: multi-agent coordination)
# CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 to enable

# Gemini CLI (v0.29+ subagent support)
# /agents refresh to update agent settings

# Codex CLI (experimental Multi-agents)
/experimental             # Enable Multi-agents
# Multiple agents work in parallel on same repo (isolated worktrees)
```

> Copilot CLI sub-agents are on the roadmap.

## Tool-Specific Features

### Claude Code: Remote Control (Mobile)

```bash
claude remote-control         # Shows QR code
# Or from within session
/rc                           # Connect existing session to Remote Control
# Scan QR with mobile -> Operate from Claude app
```

> Remote Control is Research Preview for Max plan. Local machine runs Claude Code; mobile acts as remote control.

### Copilot CLI: GitHub Integration & Task Delegation

```bash
copilot "Fix Issue #42"
/review                                    # Review changes
/delegate Add tests and create PR          # Delegate to remote agent
& Complete API integration tests           # & prefix also delegates
copilot "Fix the bug in @src/auth/middleware.ts"  # @ file reference

# Mode switch (Shift+Tab): Interactive -> Plan -> Autopilot
```

### Codex CLI: Desktop App & Codex Cloud

```bash
codex app                        # Launch app
codex app ~/projects/my-app      # Open specific workspace
codex cloud-tasks                # List/run cloud tasks
codex cloud-tasks --json         # JSON output
codex apply                      # Apply cloud task diff locally
/review                          # Launch review mode
```

## Custom Instruction Files

| Tool | Filename | Location |
|------|----------|----------|
| **Claude Code** | `CLAUDE.md` | Project root / `~/.claude/` |
| **Gemini CLI** | `GEMINI.md` | Project root / `~/.gemini/` |
| **Codex CLI** | `AGENTS.md` | Project root / `~/.codex/` |
| **Copilot CLI** | `.github/copilot-instructions.md` | Project root |
| | `*.instructions.md` | `~/.copilot/instructions/` (user-level) |

```bash
# Auto-generate instruction files
claude /init              # Claude Code
gemini --init             # Gemini CLI
```

## Custom Slash Commands / Skills

| Tool | Project scope | User scope |
|------|--------------|------------|
| **Claude Code** | `.claude/commands/` / `.claude/skills/` | `~/.claude/commands/` |
| **Gemini CLI** | `.gemini/commands/` | `~/.gemini/commands/` |
| **Codex CLI** | `.codex/commands/` | `~/.codex/commands/` |
| **Copilot CLI** | `.github/copilot/commands/` | `~/.copilot/commands/` |

All 4 tools define commands as **Markdown files** and accept `$ARGUMENTS` for command arguments.

All 4 tools support the **Agent Skills** open standard ([agentskills.io](https://agentskills.io)).

## MCP (Model Context Protocol) Server Integration

All 4 tools support MCP server connections.

| Tool | Config file |
|------|------------|
| Claude Code | `.claude/mcp.json` |
| Gemini CLI | `~/.gemini/settings.json` |
| Codex CLI | `~/.codex/config.toml` |
| Copilot CLI | `~/.copilot/mcp-config.json` (or `/mcp add`) |

**Built-in integrations:**
- Copilot CLI: **GitHub MCP server built-in**
- Gemini CLI: **Google Search grounding** built-in
- Claude Code: **claude.ai MCP connector** integration

## Pipe Integration

```bash
# Claude Code
cat error.log | claude "Analyze this error"
git diff | claude -p "Review this change"

# Gemini CLI
cat error.log | gemini "Analyze this error"
git diff | gemini -p "Review"

# Codex CLI
cat error.log | codex exec "Analyze error"
git diff | codex exec "Review"

# Copilot CLI
cat error.log | copilot -p "Analyze this error"
git diff | copilot -p "Review this change"
```

## Common One-Liners

### Code Review

```bash
git diff --staged | claude -p "Code review. Show issues and improvements"
git diff --staged | gemini -p "Code review"
# Codex: /review (in-session)
# Copilot: /review (in-session)
```

### Test Generation

```bash
claude "Write unit tests for src/utils/parser.ts"
gemini "Write unit tests for src/utils/parser.ts"
codex "Write unit tests for src/utils/parser.ts"
copilot "Fix @src/utils/parser.ts and add unit tests"
```

### Commit Message Generation

```bash
git diff --staged | claude -p "Generate commit message in Conventional Commits format"
git diff --staged | gemini -p "Generate commit message"
git diff --staged | codex exec "Generate commit message"
copilot "Generate commit message for staged changes"
```

## Feature Comparison

| Feature | Claude Code | Gemini CLI | Codex CLI | Copilot CLI |
|---------|:-----------:|:----------:|:---------:|:-----------:|
| Interactive mode | Yes | Yes | Yes (TUI) | Yes |
| One-shot mode | `-p` | `-p` | `exec` | `-p` |
| Session restore | `-c` / `-r` | `--resume` | `resume` | `--resume` |
| Plan Mode | Yes | `/plan` | `/plan` | `Shift+Tab` |
| Permission control | Yes | Policy Engine | 3-level + execpolicy | 3-mode + per-tool |
| Thinking mode | 3-level | No | No | No |
| Sub-agents | Up to 10 + `--agents` | Yes (v0.29+) | Experimental | Roadmap |
| Custom commands | Yes | Yes | Yes | Yes |
| Agent Skills | Progressive Disclosure | install/uninstall | Yes | Yes |
| MCP integration | Yes | Yes + Google Search | Yes | Yes + GitHub MCP |
| Code review | No | No | `/review` | `/review` |
| Remote delegation | No | No | Codex Cloud | `/delegate` |
| GitHub integration | `--from-pr` | No | @codex mention | Issue/PR/repo |
| Rewind / Undo | `/rewind` | `/rewind` | No | No |
| Desktop app | No | No | macOS | No |
| IDE extensions | VS Code / JetBrains | VS Code | VS Code etc. | Roadmap |
| Multi-model | No (Anthropic) | No (Gemini) | No (OpenAI) | Claude / GPT / Gemini |
| Plugin | Marketplace | Extensions | No | `/plugin install` |
| Remote Control | `remote-control` | No | No | No |
| Deep research | No | No | No | `/research` |
| LSP support | No | No | No | Yes |
| Auto compaction | Yes | No | Yes | Yes (95%) |
| JSON output | Yes | Yes | JSONL | Yes |
| Worktree isolation | `--worktree` | No | No | No |
| Session memory | Auto memory | No | No | Experimental |
| **Default model** | **Opus 4.6 / Sonnet 4.6** | **Gemini 3** | **GPT-5.3-Codex** | **Claude Sonnet 4.5** |

## Permission Skip Flags (Quick Reference)

For use with `synapse spawn` and `synapse team start`:

| CLI | Flag | Synapse spawn example |
|-----|------|-----------------------|
| **Claude Code** | `--dangerously-skip-permissions` | `synapse spawn claude -- --dangerously-skip-permissions` |
| **Gemini CLI** | `-y` | `synapse spawn gemini -- -y` |
| **Codex CLI** | `--full-auto` | `synapse spawn codex -- --full-auto` |
| **Copilot CLI** | `--allow-all-tools` | `synapse spawn copilot -- --allow-all-tools` |

## Official Documentation

- [Claude Code Docs](https://code.claude.com/docs)
- [Gemini CLI Docs](https://geminicli.com/docs)
- [Codex CLI Docs](https://developers.openai.com/codex/cli/)
- [Copilot CLI Docs](https://docs.github.com/copilot/copilot-cli)
