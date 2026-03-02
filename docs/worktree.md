# Synapse-native Worktree

## Overview

Synapse-native Worktree provides agent-agnostic git worktree isolation for all CLI agents
(Claude, Gemini, Codex, OpenCode, Copilot). Each agent gets its own checkout directory
under `.synapse/worktrees/<name>/` with a dedicated branch `worktree-<name>`.

Unlike Claude Code's built-in `--worktree` (which only works for Claude Code and uses
`.claude/worktrees/`), Synapse's worktree management works across all agent types.

## Architecture

```
.synapse/worktrees/
├── bright-falcon/     # Auto-generated name
│   └── (full repo checkout on branch worktree-bright-falcon)
├── feature-auth/      # Explicit name
│   └── (full repo checkout on branch worktree-feature-auth)
```

### Lifecycle

1. **Create**: `git worktree add .synapse/worktrees/<name> -b worktree-<name> origin/main`
   - The base branch is determined by `get_default_remote_branch()` with a 3-step fallback:
     1. `git symbolic-ref refs/remotes/origin/HEAD` (validated to exist locally)
     2. `origin/main` (if the ref exists locally)
     3. `HEAD` (last resort)
2. **Run**: Agent process runs with `cwd` set to the worktree directory
3. **Register**: Registry includes `worktree_path`, `worktree_branch`, and `worktree_base_branch` fields
4. **Cleanup**: On agent exit or `synapse kill`, two-layer change detection decides the action:
   - **Layer 1 — uncommitted changes**: `git status --porcelain` in the worktree directory
   - **Layer 2 — new commits**: `git log <base_branch>..HEAD --oneline` to detect commits beyond the base branch
   - **No changes AND no new commits** → auto-delete worktree and branch
   - **Changes or commits exist (interactive)** → prompt to keep or remove
   - **Changes or commits exist (non-interactive/headless)** → keep worktree, print path and branch

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SYNAPSE_WORKTREE_PATH` | Absolute path to the worktree directory |
| `SYNAPSE_WORKTREE_BRANCH` | Branch name (e.g., `worktree-bright-falcon`) |
| `SYNAPSE_WORKTREE_BASE_BRANCH` | Base branch the worktree was created from (e.g., `origin/main`). Used for commit detection at cleanup time. |

## CLI Usage

### spawn（単一エージェント）

```bash
# 自動名で worktree 作成（例: .synapse/worktrees/bold-hawk/）
synapse spawn claude --worktree

# 明示的な名前を指定
synapse spawn claude --worktree feature-auth --name Auth --role "auth implementation"

# 短縮フラグ
synapse spawn gemini -w
```

### team start（複数エージェント）

各エージェントが個別の worktree を取得するため、ファイル編集の競合が起きない。

```bash
# 自動名（例: claude → bold-hawk, gemini → calm-fox）
synapse team start claude gemini --worktree

# 名前プレフィックス指定（task-claude-0, task-gemini-1 のように生成）
synapse team start claude gemini --worktree task
```

### プロファイルショートカット

```bash
# 現在のターミナルで worktree 内のエージェントを直接起動
synapse claude --worktree my-feature

# 他のフラグと組み合わせ
synapse gemini --worktree review --name Reviewer --role "code reviewer"
```

### API（プログラマティック spawn）

```bash
# 自動名で worktree 作成
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "worktree": true}'

# 明示名で worktree 作成
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "codex", "worktree": "helper-task"}'
```

レスポンスに `worktree_path`、`worktree_branch`、`worktree_base_branch` が含まれる:

```json
{
  "agent_id": "synapse-gemini-8110",
  "port": 8110,
  "terminal_used": "tmux",
  "status": "submitted",
  "worktree_path": "/repo/.synapse/worktrees/bold-hawk",
  "worktree_branch": "worktree-bold-hawk",
  "worktree_base_branch": "origin/main"
}
```

## Use Cases

### 1. 実装 + テストの並行作業

実装担当とテスト担当が同じファイルを触る心配なく同時作業できる。

```bash
synapse team start claude:Implementer gemini:Tester --worktree

# Implementer → .synapse/worktrees/<name-1>/ で機能実装
# Tester      → .synapse/worktrees/<name-2>/ でテスト作成
# 完了後、各ブランチを main にマージ
```

### 2. コードレビューの分離

レビュー担当がメインの作業ディレクトリを汚さずにチェックできる。

```bash
synapse spawn claude --worktree review --name Reviewer --role "code reviewer"

# Reviewer は worktree-review ブランチで動作
# レビューコメントの作成・修正提案が本体に影響しない
```

### 3. 複数機能の同時開発

異なる機能を独立したブランチで同時に進められる。

```bash
synapse spawn claude --worktree auth --name AuthDev --role "implement auth"
synapse spawn gemini --worktree api --name APIDev --role "implement API endpoints"

# 各エージェントが独立したブランチで作業
# synapse list で [WT] インジケーターにより一目で識別可能
```

### 4. Claude Code の --worktree との使い分け

```bash
# Synapse worktree: 全エージェント共通、Synapse が管理
synapse spawn gemini --worktree

# Claude Code worktree: Claude Code のみ、Claude Code が管理
synapse spawn claude -- --worktree

# 通常は Synapse の --worktree を使う（エージェント非依存）
# Claude Code 固有機能が必要な場合のみ -- --worktree を使う
```

## API

### POST /spawn

```json
{
  "profile": "gemini",
  "worktree": true
}
```

Response includes `worktree_path`, `worktree_branch`, and `worktree_base_branch` fields.

### Registry

Agents running in worktrees have additional fields in their registry JSON:

```json
{
  "worktree_path": "/repo/.synapse/worktrees/bright-falcon",
  "worktree_branch": "worktree-bright-falcon",
  "worktree_base_branch": "origin/main"
}
```

### synapse list

Worktree agents show `[WT]` prefix in the WORKING_DIR column:

```
TYPE    NAME    PORT  STATUS  WORKING_DIR
claude  -       8100  READY   [WT] bright-falcon
gemini  -       8110  READY   synapse-a2a
```

## Comparison with Claude Code --worktree

| Feature | Synapse `--worktree` | Claude Code `-- --worktree` |
|---------|---------------------|---------------------------|
| Directory | `.synapse/worktrees/` | `.claude/worktrees/` |
| Manager | Synapse | Claude Code |
| Supported Agents | All | Claude Code only |
| Cleanup | Synapse exit/kill (uncommitted changes + commit detection) | Claude Code session end |

## Module Reference

- `synapse/worktree.py` — Core worktree operations (`create_worktree`, `cleanup_worktree`, `has_worktree_changes`, `has_new_commits`, `has_uncommitted_changes`, `get_default_remote_branch`)
- `synapse/spawn.py` — `spawn_agent(worktree=...)` parameter
- `synapse/cli.py` — `--worktree` / `-w` flag
- `synapse/registry.py` — `worktree_path`, `worktree_branch`, `worktree_base_branch` fields
- `synapse/terminal_jump.py` — `extra_env` passthrough
- `synapse/a2a_compat.py` — `SpawnRequest.worktree`, `SpawnResponse.worktree_*`
- `synapse/commands/list.py` — `[WT]` display indicator
