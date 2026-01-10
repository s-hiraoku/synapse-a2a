---
name: delegation
description: This skill configures automatic task delegation between agents in Synapse A2A. Use /delegate to set up rules for routing coding tasks to Codex, research to Gemini, etc. Supports orchestrator mode (Claude coordinates) and passthrough mode (direct forwarding). Includes agent status verification, priority levels, error handling, and File Safety integration.
---

# Delegation Skill

Configure automatic task delegation to other agents based on natural language rules, with built-in agent verification, priority management, and file conflict prevention.

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

| Command                  | Description                                      |
| ------------------------ | ------------------------------------------------ |
| `/delegate`              | Show current settings or start interactive setup |
| `/delegate orchestrator` | Set orchestrator mode (Claude coordinates)       |
| `/delegate passthrough`  | Set passthrough mode (direct forwarding)         |
| `/delegate off`          | Disable delegation                               |
| `/delegate status`       | Show current configuration and agent status      |

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

## Pre-Delegation Checklist

Before delegating any task, always perform these checks:

### 1. Verify Agent Availability

```bash
python3 synapse/tools/a2a.py list
```

Or use:

```bash
synapse list
```

Confirm target agent shows status: **READY**

Status meanings:

- **READY**: Agent is idle and can accept tasks
- **PROCESSING**: Agent is busy - wait or queue the task

### 2. Check File Safety (When Editing Files)

If the task involves file modifications, verify no conflicts:

```bash
# Check if target files are locked
synapse file-safety locks

# Get file context before editing
synapse file-safety history /path/to/file.py
```

### 3. Verify Branch Consistency

When delegating coding tasks, confirm the target agent is on the same branch:

```bash
git branch --show-current
```

Include branch information in the delegation message if needed.

## Applying Delegation Rules

When delegation is active, follow this process for each user request:

1. **Analyze the request** against configured rules
2. **Run pre-delegation checklist** (agent status, file locks)
3. **Determine target agent** (codex, gemini, or self)
4. **Select priority level** based on urgency
5. **Execute delegation** with appropriate method

### Orchestrator Mode Behavior

```
1. Analyze user request
2. Run pre-delegation checklist
3. If target agent not READY:
   a. Inform user: "対象エージェント(<agent>)は処理中です。待機しますか？"
   b. Wait or queue based on user preference
4. If matches delegation rule and agent is READY:
   a. Acquire file locks if needed (File Safety)
   b. Send to target agent with appropriate priority
   c. Wait for response (monitor with synapse list --watch)
   d. Review and integrate response
   e. Release file locks
   f. Report final result to user
5. If no match: Process directly
```

### Passthrough Mode Behavior

```
1. Analyze user request
2. Check agent availability (skip if not READY)
3. If matches delegation rule:
   a. Forward to target agent with original request
   b. Relay response directly to user
4. If no match: Process directly
```

## A2A Communication Methods

### Method 1: @Agent Pattern (Simple)

Use for quick, inline delegation:

```
@codex このファイルをリファクタリングして
@gemini このAPIについて調査して
```

### Method 2: A2A Tool (Advanced)

Use for priority control and complex tasks:

```bash
python3 synapse/tools/a2a.py send --target <agent> --priority <1-5> "<message>"
```

Examples:

```bash
# Normal task (priority 3)
python3 synapse/tools/a2a.py send --target codex --priority 3 "src/auth.pyをリファクタリングして"

# Urgent follow-up (priority 4)
python3 synapse/tools/a2a.py send --target gemini --priority 4 "進捗を教えて"

# Critical task (priority 5)
python3 synapse/tools/a2a.py send --target codex --priority 5 "緊急: 本番のバグを修正して"
```

## Priority Levels

| Priority | Use Case                       | Example                            |
| -------- | ------------------------------ | ---------------------------------- |
| 1-2      | Low priority, background tasks | ドキュメント整理、コード整形       |
| 3        | Normal tasks (default)         | 機能実装、バグ修正                 |
| 4        | Urgent follow-ups              | 進捗確認、追加指示                 |
| 5        | Critical/emergency tasks       | 本番障害対応、セキュリティ修正     |

## File Safety Integration

When delegating file modification tasks, use File Safety to prevent conflicts.

### Before Delegation

```bash
# Check existing locks
synapse file-safety locks

# Acquire lock for the target file
synapse file-safety lock /path/to/file.py <agent_name> --intent "Task description"
```

### In Delegation Message

Include file context:

```
@codex src/auth.py をリファクタリングして。
注意: このファイルは現在ロックされていません。作業前にロックを取得してください。
最近の変更: claude が認証ロジックを修正 (2026-01-09)
```

### After Delegation Completes

```bash
# Verify changes were recorded
synapse file-safety history /path/to/file.py

# Release lock if held
synapse file-safety unlock /path/to/file.py <agent_name>
```

### Handling Lock Conflicts

If target file is locked by another agent:

```
ファイル /path/to/file.py は <agent> によってロックされています。
オプション:
1. 完了を待つ
2. 別のファイルを先に作業する
3. ロック保持者に確認する (@<agent> 進捗を教えて)
```

## Error Handling

### Agent Not Responding

If agent doesn't respond within reasonable time:

1. Check agent status:
   ```bash
   synapse list
   ```
2. If PROCESSING for too long, send priority 4-5 follow-up:
   ```bash
   python3 synapse/tools/a2a.py send --target <agent> --priority 4 "進捗を教えてください"
   ```
3. If agent appears stuck, inform user and suggest alternatives

### Agent Not Available

If target agent is not running:

```
対象エージェント (<agent>) が見つかりません。
解決策:
1. 別ターミナルで起動: synapse <agent>
2. 別のエージェントに委任
3. 手動で処理
```

### Task Failed

If delegated task fails:

1. Review error message from agent
2. Provide context and retry with adjusted instructions
3. If repeated failures, process directly or suggest user intervention

## Monitoring Delegated Tasks

### Real-time Status

```bash
# Watch agent status changes
synapse list --watch

# Check specific agent
synapse list | grep <agent>
```

### Task History

If history is enabled (`SYNAPSE_HISTORY_ENABLED=true`):

```bash
# Recent tasks by agent
synapse history list --agent <agent> --limit 10

# Task details
synapse history show <task_id>

# Statistics
synapse history stats --agent <agent>
```

### Git Activity

Monitor file changes from delegated tasks:

```bash
git status
git log --oneline -5
git diff
```

## Configuration File Format

`~/.synapse/delegation.md`:

```markdown
# Delegation Configuration

mode: orchestrator

## Rules

コーディング作業（ファイル編集、新規作成）は Codex に任せる。
調査、Web 検索、ドキュメント確認は Gemini に依頼する。
コードレビュー、設計判断は自分（Claude）で行う。

## File Safety

ファイル編集を伴うタスクは、委任前にロック状態を確認する。

## Priority Guidelines

- 通常タスク: priority 3
- フォローアップ: priority 4
- 緊急対応: priority 5
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

---

> ユーザー認証機能を実装して

[Pre-check]
- Codex: READY ✓
- File Safety: src/auth.py - ロックなし ✓

Codexにコーディングを委任します...
@codex ユーザー認証機能を実装してください。対象ファイル: src/auth.py
作業前にファイルロックを取得してください。

[Codex処理中... synapse list --watch で監視]

Codexからの応答:
- src/auth.py を作成
- tests/test_auth.py を作成
- ロックを解放済み

統合結果:
✓ ユーザー認証機能が実装されました
  - 新規ファイル: src/auth.py, tests/test_auth.py
  - テスト: 5件すべてパス
```

## Status Display

When `/delegate status` is invoked:

```
=== Delegation Configuration ===
Mode: orchestrator
Rules:
  コーディングはCodexに、リサーチはGeminiに任せる
Status: active

=== Available Agents ===
NAME     STATUS      PORT   WORKING_DIR
claude   READY       8100   /path/to/project
codex    READY       8120   /path/to/project
gemini   PROCESSING  8110   /path/to/project

=== File Safety ===
Active Locks: 1
  /path/to/api.py - gemini (expires: 12:30:00)
================================
```

## Available Agents

Standard agent types and their strengths:

| Agent    | Strengths                              | Port Range |
| -------- | -------------------------------------- | ---------- |
| **codex**  | Coding tasks, file editing, refactoring | 8120-8129  |
| **gemini** | Research, web search, documentation    | 8110-8119  |
| **claude** | Code review, analysis, planning        | 8100-8109  |

Check running agents:

```bash
python3 synapse/tools/a2a.py list
# or
synapse list
```
