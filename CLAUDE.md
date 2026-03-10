# CLAUDE.md

## Development Flow

1. Write tests first → confirm spec → implement → pass all tests
2. **Default base branch is `main`** for all PRs
3. Do NOT change branches during active work without user confirmation

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
├── cli.py           # Entry point
├── controller.py    # PTY management, status detection
├── server.py        # FastAPI A2A endpoints
├── a2a_compat.py    # A2A protocol (Agent Card, Task API)
├── a2a_client.py    # Client for other A2A agents
├── registry.py      # File-based agent discovery
├── mcp/             # MCP server (bootstrap instruction distribution)
├── canvas/          # Shared visual output surface
├── commands/        # CLI command implementations
└── profiles/        # YAML configs per agent type
```

## Core Design Principle

**A2A Protocol First**: All communication uses Message/Part + Task format per Google A2A spec. Extensions use `x-` prefix.

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

## References

詳細なコマンドリファレンス、プロファイル設定、テスト手順は以下を参照:
- [docs/synapse-reference.md](docs/synapse-reference.md)
