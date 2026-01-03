# エージェントアイデンティティとルーティング設計

このドキュメントでは、Synapse A2A におけるエージェントの識別とメッセージルーティングの設計について説明します。

## 背景と課題

### 問題

1. **自分宛てかどうかの判断ができない**
   - Gemini上で `@claude タスクを止めて` と入力すると、Gemini自身がそれを実行してしまう
   - 各エージェントが「自分宛てか他者宛てか」を判断できていなかった

2. **同じタイプのエージェントが複数ある場合の区別**
   - Claude A（ポート8100）と Claude B（ポート8101）がある場合
   - `@Claude` ではどちらを指しているか区別できない

3. **ファイル参照との混同**
   - `@test.md` などのファイル参照と `@agent` の構文が混同される可能性

## 解決策

### ユニークID形式

```
synapse-{モデル名}-{ポート番号}
```

例：
- `synapse-claude-8100`
- `synapse-gemini-8101`
- `synapse-codex-8102`

### 特徴

| 項目 | 説明 |
|------|------|
| **プレフィックス** | `synapse-` でファイル参照と区別 |
| **モデル名** | 何のエージェントかが一目でわかる |
| **ポート番号** | 同一マシンで重複しないのでユニーク保証 |

## アーキテクチャ

### ID生成フロー

```
┌────────────────┐      ┌────────────────┐
│   CLI起動      │──────▶│  AgentRegistry │
│ synapse claude │      │  get_agent_id()│
│ --port 8100    │      └────────┬───────┘
└────────────────┘               │
                                 ▼
                    ┌────────────────────────┐
                    │ synapse-claude-8100    │
                    └────────────────────────┘
```

### インストラクション送信フロー

```
┌──────────────────┐
│  Agent 起動      │
│  (PTY spawn)     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  READY検出       │
│  (初回のみ)      │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  [SYNAPSE A2A] あなたのアイデンティティ:          │
│  - ID: synapse-claude-8100                       │
│  - タイプ: claude                                │
│                                                  │
│  ルーティングルール:                              │
│  - @synapse-claude-8100 → 自分宛て。実行する      │
│  - @synapse-gemini-8101 → 他のエージェント宛て。   │
│    A2Aで転送のみ。自分では実行しない              │
└──────────────────────────────────────────────────┘
```

## 実装詳細

### 変更ファイル

| ファイル | 変更内容 |
|----------|----------|
| `synapse/registry.py` | `get_agent_id()` を `synapse-{type}-{port}` 形式に変更 |
| `synapse/controller.py` | 最初のREADY状態時にインストラクションを自動送信 |
| `synapse/cli.py` | 新しいID形式を使用 |
| `synapse/server.py` | 新しいID形式を使用 |
| `synapse/a2a_compat.py` | Agent Card に `agent_id`, `addressable_as` を追加 |
| `synapse/input_router.py` | `synapse-` プレフィックス付きIDでのマッチング対応 |

### ID生成

```python
# synapse/registry.py
def get_agent_id(self, agent_type: str, port: int) -> str:
    """Generates a unique agent ID in format: synapse-{agent_type}-{port}."""
    return f"synapse-{agent_type}-{port}"
```

### インストラクション送信

```python
# synapse/controller.py
def _send_identity_instruction(self):
    """Send identity and routing instructions to the agent on first IDLE."""
    instruction = f"""[SYNAPSE A2A] あなたのアイデンティティ:
- ID: {self.agent_id}
- タイプ: {self.agent_type}

ルーティングルール:
- @{self.agent_id} → これはあなた宛て。実行する
- {other_examples} など → 他のエージェント宛て。A2Aで転送のみ。自分では実行しない
"""
    self.write(instruction, self._submit_seq)
```

### Agent Card 拡張

```json
{
  "name": "Synapse Claude",
  "url": "http://localhost:8100",
  "extensions": {
    "synapse": {
      "agent_id": "synapse-claude-8100",
      "addressable_as": [
        "@synapse-claude-8100",
        "@claude"
      ]
    }
  }
}
```

### メッセージルーティング

```python
# synapse/input_router.py
# Matching priority:
# 1. Exact match on agent_id (e.g., synapse-claude-8100)
# 2. Match on agent_type (e.g., claude)
```

## 使用例

### 単一エージェント環境

```bash
# 起動
synapse claude --port 8100

# メッセージ送信（どちらでも可）
@claude ファイルを確認して
@synapse-claude-8100 ファイルを確認して
```

### 複数エージェント環境

```bash
# 起動
synapse claude --port 8100  # synapse-claude-8100
synapse claude --port 8101  # synapse-claude-8101
synapse gemini --port 8200  # synapse-gemini-8200

# 特定のエージェントに送信
@synapse-claude-8100 タスクAを実行
@synapse-claude-8101 タスクBを実行
@synapse-gemini-8200 タスクCを実行
```

## インストラクション送信のタイミング

TUIアプリ（claude code, codex, gemini CLI）では従来のテキストプロンプトがないため、
**出力停止検出**によりインストラクション送信のタイミングを決定します。

### 動作フロー

```
1. エージェント起動
2. startup_delay 待機（デフォルト3秒、geminiは8秒）
3. 出力バッファを監視
4. output_idle_threshold（1.5秒）出力がなければ「入力待ち」と判断
5. インストラクションを送信
```

### プロファイル設定

```yaml
# gemini.yaml
command: "gemini"
idle_regex: "> $"
submit_sequence: "\r"
startup_delay: 8  # 起動が遅いため長めに設定
```

## 制限事項

- インストラクションはテキストとして送信されるため、エージェントがそれを「理解」して従うかはエージェント側の実装に依存する
- 起動時間がプロファイルの `startup_delay` より長い場合、出力停止検出が遅れる可能性がある
