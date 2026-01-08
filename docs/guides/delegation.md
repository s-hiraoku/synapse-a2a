# Delegation Guide

This guide explains how to use the delegation feature to automatically route tasks between agents (Claude, Codex, Gemini).

## Overview

Delegation allows Claude to automatically forward tasks to other agents based on natural language rules you define. For example:
- Forward all coding tasks to Codex
- Forward research tasks to Gemini
- Keep code reviews with Claude

## Configuration

Delegation uses two configuration sources:

| Setting | Location | Purpose |
|---------|----------|---------|
| Mode | `.synapse/settings.json` | "orchestrator", "passthrough", or "off" |
| Rules | `.synapse/delegate.md` | Natural language delegation instructions |

## Quick Start

### Step 1: Set delegation mode

```bash
synapse delegate set orchestrator
```

Or manually edit `.synapse/settings.json`:
```json
{
  "delegation": {
    "mode": "orchestrator"
  }
}
```

### Step 2: Create delegation rules

Create `.synapse/delegate.md`:

```markdown
# Delegation Rules

コーディング作業（ファイルの編集、新規作成、リファクタリング）はCodexに任せる。
調査やドキュメント検索はGeminiに依頼する。
コードレビューは自分（Claude）で行う。
```

### Step 3: Start agents

```bash
# Terminal 1: Start Codex
synapse codex

# Terminal 2: Start Claude
synapse claude
```

Claude will automatically apply delegation rules and route tasks accordingly.

## Delegation Modes

### Orchestrator Mode (Recommended)

Claude analyzes each task, delegates to appropriate agent, waits for response, integrates results, and reports to user.

```
User → Claude (analyze) → @codex (execute) → Claude (integrate) → User
```

**Best for:**
- Complex tasks that need coordination
- When you want Claude to review/integrate results
- Multi-step workflows

### Passthrough Mode

Claude routes tasks directly based on rules, returns results as-is without processing.

```
User → Claude (route) → @codex (execute) → User
```

**Best for:**
- Simple, direct task forwarding
- When you want raw output from the target agent
- High-throughput scenarios

### Off Mode (Default)

No automatic delegation. User must explicitly use @agent patterns.

## Commands

| Command | Description |
|---------|-------------|
| `synapse delegate` | Show current delegation status |
| `synapse delegate status` | Show current configuration |
| `synapse delegate set <mode>` | Set delegation mode |
| `synapse delegate off` | Disable delegation |

### Examples

```bash
# Check current status
synapse delegate

# Set orchestrator mode (project scope)
synapse delegate set orchestrator

# Set orchestrator mode (user scope)
synapse delegate set orchestrator --scope user

# Disable delegation
synapse delegate off
```

## Configuration Files

### Mode Setting

Stored in `.synapse/settings.json`:

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true"
  },
  "delegation": {
    "mode": "orchestrator"
  }
}
```

Search order (highest priority first):
1. `.synapse/settings.local.json` (project local)
2. `.synapse/settings.json` (project)
3. `~/.synapse/settings.json` (user)

### Delegation Rules

Stored in `.synapse/delegate.md`:

```markdown
# My Project Delegation Rules

All coding tasks (file editing, creation, refactoring) should go to Codex.
Research and web searches should go to Gemini.
Code reviews stay with Claude.
```

Search order:
1. `.synapse/delegate.md` (project)
2. `~/.synapse/delegate.md` (user)

## Writing Effective Rules

### Be Specific About Task Types

```markdown
# Good
ファイルの編集やリファクタリングはCodexに依頼する

# Bad
難しいことはCodexに依頼する
```

### Clarify Boundaries

```markdown
# Good
新規ファイル作成はCodexに、既存ファイルの分析は自分で行う

# Bad
コーディングはCodexに（曖昧）
```

### Include Fallback Behavior

```markdown
コーディングはCodexに
リサーチはGeminiに
上記に該当しない場合は自分で処理する
```

## How It Works

1. **Session Start**: Synapse loads settings and delegate.md
2. **Rule Injection**: Delegation rules are added to Claude's initial instructions
3. **Task Analysis**: Claude analyzes each incoming task against the rules
4. **Delegation**: If a rule matches, Claude uses `@agent` pattern to forward
5. **Result Handling**:
   - Orchestrator: Claude integrates the result before reporting
   - Passthrough: Result is forwarded directly

## Status Display

Run `synapse delegate` to see current configuration:

```
=== Delegation Configuration ===
Mode: orchestrator
Instructions: .synapse/delegate.md
Status: active

Rules:
  # Delegation Rules
  コーディングはCodexに任せる
  リサーチはGeminiに依頼する
================================
```

## Troubleshooting

### Delegation not working

1. Check mode is set:
   ```bash
   synapse delegate status
   ```

2. Verify delegate.md exists:
   ```bash
   cat .synapse/delegate.md
   ```

3. Verify target agent is running:
   ```bash
   synapse list
   ```

### Rules not matching as expected

Claude interprets rules contextually. If delegation isn't happening:

1. Make rules more specific
2. Add explicit examples in delegate.md
3. Use clearer task categories

## Examples

### Development Team Setup

`.synapse/settings.json`:
```json
{
  "delegation": {
    "mode": "orchestrator"
  }
}
```

`.synapse/delegate.md`:
```markdown
# Development Delegation

設計とコードレビューは自分で行う。
実装（ファイル編集、新規作成）はCodexに依頼する。
技術調査やドキュメント作成はGeminiに依頼する。
```

### Research-Focused Setup

`.synapse/delegate.md`:
```markdown
# Research Delegation

Web検索や調査タスクはGeminiに転送する。
それ以外は自分で処理する。
```

### Coding-Only Delegation

`.synapse/delegate.md`:
```markdown
# Coding Delegation

コーディング作業（Edit, Write, Bash）はすべてCodexに任せる。
結果を確認してからユーザーに報告する。
```
