# Multi-Agent Setup Guide

このガイドでは、Claude、Codex、Gemini の3つのエージェントを同時に起動し、相互通信させる方法を説明します。

## Prerequisites

以下のCLIツールがインストールされている必要があります：

| エージェント | CLI コマンド | インストール方法 |
|------------|-------------|----------------|
| Claude | `claude` | [Claude Code CLI](https://claude.ai/code) |
| Codex | `codex` | [OpenAI Codex CLI](https://github.com/openai/codex) |
| Gemini | `gemini` | [Gemini CLI](https://github.com/google/gemini-cli) |

## Profiles

各エージェントは `synapse/profiles/` にYAMLファイルとして定義されています。

### claude.yaml
```yaml
command: "claude"
idle_regex: "> $"
env:
  TERM: "xterm-256color"
```

### codex.yaml
```yaml
command: "codex"
idle_regex: "> $"
env:
  TERM: "xterm-256color"
```

### gemini.yaml
```yaml
command: "gemini"
idle_regex: "> $"
env:
  TERM: "xterm-256color"
```

### dummy.yaml (テスト用)
```yaml
command: "python3 -u dummy_agent.py"
idle_regex: "> $"
env:
  PYTHONUNBUFFERED: "1"
```

## Starting Multiple Agents

3つのエージェントを同時に起動するには、**異なるポート**で各サーバーを起動します。

### Terminal 1: Claude (port 8100)
```bash
python -m synapse.server --profile claude --port 8100
```

### Terminal 2: Codex (port 8101)
```bash
python -m synapse.server --profile codex --port 8101
```

### Terminal 3: Gemini (port 8102)
```bash
python -m synapse.server --profile gemini --port 8102
```

## Verifying Status

各エージェントのステータスを確認：

```bash
# Claude
curl http://localhost:8100/status

# Codex
curl http://localhost:8101/status

# Gemini
curl http://localhost:8102/status
```

## Agent-to-Agent Communication

### Using the A2A Tool

エージェント一覧を確認：
```bash
python3 synapse/tools/a2a.py list
```

別のエージェントにメッセージを送信：
```bash
# 通常メッセージ (priority 1)
python3 synapse/tools/a2a.py send --target claude --priority 1 "Hello Claude!"

# 緊急停止 (priority 5) - SIGINTを送信
python3 synapse/tools/a2a.py send --target gemini --priority 5 "Stop!"
```

### Direct HTTP API

```bash
# Claudeにメッセージを送信
curl -X POST http://localhost:8100/message \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello!", "priority": 1}'

# Geminiを緊急停止
curl -X POST http://localhost:8102/message \
  -H "Content-Type: application/json" \
  -d '{"content": "Stop!", "priority": 5}'
```

## Priority Levels

| Priority | 動作 | 用途 |
|----------|-----|------|
| 1-4 | メッセージをstdinに書き込み | 通常の通信 |
| 5 | SIGINT送信後、メッセージを書き込み | 緊急停止・介入 |

## Port Assignment Convention

推奨するポート割り当て：

| エージェント | ポート |
|------------|-------|
| Claude | 8100 |
| Codex | 8101 |
| Gemini | 8102 |
| Dummy (テスト) | 8199 |

## Troubleshooting

### "Profile not found" エラー
`synapse/profiles/` に該当のYAMLファイルが存在するか確認してください。

### ポートが既に使用されている
別のポートを指定するか、既存のプロセスを終了してください：
```bash
lsof -i :8100
kill <PID>
```

### エージェントが応答しない
ステータスを確認し、`IDLE` でない場合は priority 5 で介入：
```bash
curl http://localhost:8100/status
python3 synapse/tools/a2a.py send --target claude --priority 5 "Are you there?"
```
