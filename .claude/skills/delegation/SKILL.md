---
name: delegation
description: Configure automatic task delegation between agents. Use /delegate to set up rules for routing coding tasks to Codex, research to Gemini, etc. Supports orchestrator mode (Claude coordinates) and passthrough mode (direct forwarding).
---

# Delegation Skill

Configure automatic task delegation to other agents based on natural language rules.

## Session Startup Behavior

At session startup, check for existing delegation configuration:

```bash
cat ~/.synapse/delegation.md 2>/dev/null
```

If configuration exists:
1. Display current delegation mode and rules summary to user
2. Ask user: "委任設定が見つかりました。この設定を使用しますか？"
3. If user confirms, apply the delegation rules to current session behavior

## Commands

| Command | Description |
|---------|-------------|
| `/delegate` | Show current settings or start interactive setup |
| `/delegate orchestrator` | Set orchestrator mode (Claude coordinates) |
| `/delegate passthrough` | Set passthrough mode (direct forwarding) |
| `/delegate off` | Disable delegation |
| `/delegate status` | Show current configuration |

## Modes

### Orchestrator Mode
Claude analyzes each task, delegates to appropriate agent, waits for response, integrates results, and reports to user.

```
User → Claude (analyze & delegate) → @codex/@gemini → Claude (integrate) → User
```

### Passthrough Mode
Claude routes tasks directly based on rules, returns results as-is without processing.

```
User → Claude (route only) → @codex/@gemini → User
```

### Manual Mode (Default)
No automatic delegation. User must explicitly use @agent patterns.

## Setup Workflow

When user invokes `/delegate` or `/delegate <mode>`:

### Step 1: Select Mode
If mode not specified, ask user to choose:
- orchestrator: 分析・統合型（推奨）
- passthrough: 単純転送型
- off: 無効化

### Step 2: Define Rules (Natural Language)
Prompt user for delegation rules in natural language:

```
委任ルールを自然言語で記述してください。

例:
- コーディング作業（ファイルの編集、作成、リファクタリング）はCodexに任せる
- 調査やWeb検索はGeminiに依頼する
- コードレビューは自分（Claude）で行う
```

### Step 3: Save Configuration

```bash
mkdir -p ~/.synapse
cat > ~/.synapse/delegation.md << 'EOF'
# Delegation Configuration

mode: <selected_mode>

## Rules
<user's natural language rules>
EOF
```

### Step 4: Confirm and Apply
Display saved configuration and confirm activation.

## Applying Delegation Rules

When delegation is active, follow this process for each user request:

1. **Analyze the request** against configured rules
2. **Determine target agent** (codex, gemini, or self)
3. **Execute delegation**:
   - For codex/gemini: Use `@<agent> <task>` pattern
   - For self: Process directly

### Orchestrator Mode Behavior
```
1. Analyze user request
2. If matches delegation rule:
   a. Send to target agent: @codex <detailed task description>
   b. Wait for response
   c. Review and integrate response
   d. Report final result to user
3. If no match: Process directly
```

### Passthrough Mode Behavior
```
1. Analyze user request
2. If matches delegation rule:
   a. Forward to target agent: @codex <original request>
   b. Relay response directly to user
3. If no match: Process directly
```

## Configuration File Format

`~/.synapse/delegation.md`:
```markdown
# Delegation Configuration

mode: orchestrator

## Rules
コーディング作業はCodexに任せる。
調査やドキュメント検索はGeminiに依頼する。
コードレビューは自分で行う。
```

## Example Session

```
> /delegate orchestrator

委任ルールを自然言語で記述してください:
> コーディングはCodexに、リサーチはGeminiに任せる

✓ 設定を保存しました

現在の設定:
- モード: orchestrator
- ルール: コーディングはCodexに、リサーチはGeminiに任せる

この設定で委任を有効にしますか？ [Y/n]
> Y

✓ 委任が有効になりました
```

## Status Display

When `/delegate status` is invoked:

```
=== Delegation Configuration ===
Mode: orchestrator
Rules:
  コーディングはCodexに、リサーチはGeminiに任せる
Hooks: disabled
Status: active
================================
```

## Available Agents

Check available agents before delegation:
```bash
python3 synapse/tools/a2a.py list
```

Standard agent types:
- **codex**: Coding tasks (Edit, Write, refactoring)
- **gemini**: Research, web search, documentation
- **claude**: Code review, analysis, planning
