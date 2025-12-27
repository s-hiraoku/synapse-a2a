# Universal Agent Communication Specification

## Overview

任意のターミナルから `@Agent` 構文でエージェントに指示を送り、レスポンスを受け取る仕組みの仕様。

## Goals

1. **ターミナル非依存**: VS Code、iTerm2、Terminal.app など任意のターミナルで動作
2. **シンプルな構文**: `@Gemini 明日の天気は？` のような自然な入力
3. **双方向通信**: 指示を送るだけでなく、回答を受け取ることも可能
4. **モード切替**: 回答の表示先を選択可能

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     User's Terminal A                           │
│  $ synapse-shell                                                │
│  synapse> @Gemini 明日の天気は？                                 │
│           ↓                                                     │
│     [Input Hook: @Agent 検知]                                   │
│           ↓                                                     │
│     [synapse-send → HTTP POST]                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   Synapse A2A Server                            │
│  - Agent Registry (discovery)                                   │
│  - Message Router                                               │
│  - Response Collector                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Agent Process (Gemini)                         │
│  $ synapse start gemini                                         │
│  [PTY Controller] ← メッセージ受信                               │
│  [Gemini CLI] → 回答生成                                        │
│  [Output Monitor] → 回答をキャプチャ                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   Response Routing                              │
│  Mode: "display" → Agent の画面に表示（デフォルト）              │
│  Mode: "return"  → 指示元の Terminal A に返す                   │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. synapse start

エージェントをバックグラウンドで起動し、レジストリに登録する。

```bash
# 基本的な起動
synapse start gemini

# ポート指定
synapse start gemini --port 8102

# フォアグラウンド（出力を見る）
synapse start gemini --foreground
```

**実装詳細:**
- PTYでエージェントCLIをラップ
- FastAPIサーバーを起動（メッセージ受信用）
- レジストリに登録（`~/.a2a/registry/`）
- 出力をバッファリング（レスポンス返却用）

### 2. synapse-shell

`@Agent` 構文を認識するインタラクティブシェル。

```bash
$ synapse-shell
synapse> echo "Hello"
Hello
synapse> @Gemini 明日の天気は？
[Sending to Gemini...]
synapse> @Claude --return このコードをレビューして
[Waiting for response...]
Claude: コードは問題ありません。
synapse>
```

**実装詳細:**
- Python の `cmd` または `prompt_toolkit` ベース
- 入力が `@` で始まる場合、A2A送信にルーティング
- `--return` フラグで回答を待機

### 3. Shell Hook (Optional)

既存シェル（bash/zsh）に組み込むフック。

```bash
# .bashrc / .zshrc に追加
eval "$(synapse shell-hook)"
```

**動作:**
- `preexec` フックで入力をチェック
- `@Agent` パターンにマッチしたら `synapse-send` を実行
- 元のコマンドはキャンセル

### 4. Response Modes

| Mode | 動作 | 使用例 |
|------|------|--------|
| `display` | エージェントの画面に表示（デフォルト） | `@Gemini 調べて` |
| `return` | 指示元のターミナルに返す | `@Gemini --return 調べて` |
| `broadcast` | 全エージェントに通知 | `@all 作業終了` |

### 5. Response Collection

エージェントの回答をキャプチャして返却する仕組み。

**方法1: Idle検知ベース**
- エージェントがIDLE状態になったら、前回のメッセージ以降の出力を回答として返す

**方法2: 明示的なマーカー**
- エージェントが `[RESPONSE_END]` のようなマーカーを出力

**方法3: タイムアウト**
- 一定時間出力がなければ回答完了とみなす

## API Endpoints

### POST /message

```json
{
  "content": "明日の天気は？",
  "priority": 1,
  "response_mode": "return",
  "callback_url": "http://localhost:9000/response"
}
```

### GET /status

```json
{
  "status": "IDLE",
  "context": "...(last 2000 chars)..."
}
```

### GET /response/{request_id}

```json
{
  "request_id": "abc123",
  "status": "completed",
  "response": "明日は晴れです。最高気温は..."
}
```

## CLI Commands

```bash
# エージェント管理
synapse start <profile>       # エージェント起動
synapse stop <profile>        # エージェント停止
synapse list                  # 起動中エージェント一覧
synapse logs <profile>        # ログ表示

# メッセージ送信
synapse send <target> <message>           # メッセージ送信
synapse send <target> --return <message>  # 回答を待つ

# シェル
synapse-shell                 # インタラクティブシェル起動

# シェルフック
synapse shell-hook            # bash/zsh用フック出力
```

## Configuration

`~/.synapse/config.yaml`:

```yaml
default_response_mode: display
response_timeout: 30  # seconds
shell_prompt: "synapse> "

agents:
  gemini:
    port: 8102
    auto_start: true
  claude:
    port: 8100
    auto_start: false
```

## Implementation Phases

### Phase 1: Basic Infrastructure
- [x] Server with --port option
- [x] Profile system (claude, codex, gemini)
- [x] A2A tool for sending messages
- [ ] `synapse start` command (daemonize)

### Phase 2: Interactive Shell
- [ ] `synapse-shell` with @Agent detection
- [ ] Basic response collection (idle-based)
- [ ] `--return` flag support

### Phase 3: Shell Integration
- [ ] bash/zsh hook (`synapse shell-hook`)
- [ ] Response streaming
- [ ] Broadcast mode

### Phase 4: Advanced Features
- [ ] WebSocket for real-time responses
- [ ] Multi-agent orchestration
- [ ] VS Code extension
