# CLAUDE.md

## Development Flow

1. Write tests first → confirm spec → implement → pass all tests
2. **Default base branch is `main`** for all PRs
3. Do NOT change branches during active work without user confirmation (worktree agents are exempt; A2A explicit instructions override)

## Project Overview

**Mission: Enable agents to collaborate on tasks without changing their behavior.**

Synapse A2A wraps CLI agents (Claude Code, Codex, Gemini, OpenCode, Copilot) with PTY and enables inter-agent communication via Google A2A Protocol. P2P architecture, no central server.

## Commands

```bash
uv sync                                  # Install
pytest                                    # All tests
pytest tests/test_foo.py -v               # Specific file
pytest -k "test_bar" -v                   # Pattern match
```

## Architecture

```
synapse/
├── cli.py              # Entry point
├── controller.py       # PTY management, status detection
├── server.py           # FastAPI A2A endpoints
├── a2a_compat.py       # A2A protocol (Agent Card, Task API)
├── a2a_client.py       # Client for other A2A agents
├── registry.py         # File-based agent discovery
├── shell.py            # Interactive shell with @Agent routing
├── shared_memory.py    # Cross-agent knowledge base (SQLite)
├── spawn.py            # Agent spawning
├── worktree.py         # Synapse-native git worktree isolation
├── workflow.py         # Workflow definition & execution
├── workflow_db.py      # Workflow run persistence (SQLite)
├── workflow_runner.py  # Step-by-step workflow executor
├── agent_profiles.py   # Saved agent definitions (reusable templates)
├── transport.py        # Transport abstraction layer
├── observation.py      # PTY/A2A signal observation for learning
├── pattern_analyzer.py # Observation pattern analysis
├── instinct.py         # Learned instinct persistence
├── evolve.py           # Instinct → skill candidate evolution
├── skills.py           # Skill discovery, deploy, import, skill sets
├── history.py          # Task history tracking
├── file_safety.py      # Multi-agent file locking & change tracking
├── reply_stack.py      # Reply routing stack
├── hooks.py            # Quality gate hooks (on_idle, on_task_completed)
├── settings.py         # Runtime settings management
├── config.py           # Configuration loading
├── mcp/                # MCP server (bootstrap instruction distribution)
├── canvas/             # Shared visual output surface
│   ├── server.py       #   FastAPI app factory & middleware
│   ├── protocol.py     #   Canvas Message Protocol
│   ├── store.py        #   Card storage
│   ├── export.py       #   Card download/export
│   ├── ogp.py          #   OGP link preview enrichment
│   ├── routes/         #   Route modules (admin, cards, db, workflow)
│   ├── templates/      #   HTML templates (index.html)
│   └── static/         #   Modular CSS (8 files) & JS (8 files)
├── commands/           # CLI command implementations
│   ├── merge.py        #   Worktree merge command
│   └── renderers/      #   Output renderers (rich_renderer)
├── profiles/           # YAML configs per agent type
├── proto/              # gRPC Protocol Buffers
├── tools/              # A2A CLI tools (a2a.py + a2a_helpers.py)
└── templates/          # Project template files
```

## Core Design Principles

**A2A Protocol First**: All communication uses Message/Part + Task format per Google A2A spec. Extensions use `x-` prefix.

**Reuse Existing Infrastructure**: 新機能は既存の仕組みを最大限活用すること。独自パイプラインを新設する前に、既存のプロトコル・エンドポイント・UIコンポーネントで実現できないか必ず検討する。

- **通信**: エージェント間の reply/send 機構（reply stack, sender_endpoint, `/tasks/send`）を使う。PTY 出力の直接読み取りで代替しない
- **UI**: Canvas の既存コンポーネント（バブル、スピナー、テーブル、SSE broadcast 等）を再利用する。同じ役割の新コンポーネントを作らない — トンマナの統一性が崩れ、実装コストも増える
- **データ取得**: A2A API（task.artifacts, task.message）から構造化データを取得する。ターミナル生出力のクリーニングで代替しない

## Port Ranges

| Agent | Ports |
|-------|-------|
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex | 8120-8129 |
| OpenCode | 8130-8139 |
| Copilot | 8140-8149 |

## Skill Update Rules

`plugins/synapse-a2a/skills/` がスキルのソースオブトゥルース。スキル更新は必ず `plugins/` 側を編集し、`sync-plugin-skills` で同期。

`.claude/skills/` や `.agents/skills/` に開発専用スキルを置く場合は、`npx skills add` の候補に出ないように SKILL.md の frontmatter に `metadata.internal: true` を付ける。

## References

詳細なコマンドリファレンス、プロファイル設定、テスト手順は以下を参照:
- [docs/synapse-reference.md](docs/synapse-reference.md)
