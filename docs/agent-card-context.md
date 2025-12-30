# Agent Card Context Extension (x-synapse-context)

## 概要

Agent Card の拡張フィールド `x-synapse-context` を使用して、AI エージェントにシステムコンテキスト（ID、ルーティングルール、他エージェント情報）を非表示で渡す仕組み。

## 背景と動機

### 課題

従来の実装では、エージェントの初期化時に以下のような長いインストラクションを PTY に直接送信していた：

```
[SYNAPSE A2A] あなたのID: synapse-claude-8100

【ルーティングルール】
1. @synapse-claude-8100 宛て → あなた宛て。内容を実行してください。
2. @other-agent 宛て → 他エージェント宛て。以下のコマンドで転送:
...
```

**問題点**:
- ユーザーのターミナルに長いテキストが表示される
- 見た目が煩雑
- A2A プロトコルの標準的な方法ではない

### 解決策

A2A プロトコルの標準コンポーネントである **Agent Card** を拡張し、システムコンテキストを埋め込む。AI エージェントは Agent Card を HTTP で取得することで、PTY 出力なしに必要な情報を得られる。

## 設計

### x-synapse-context フィールド

Agent Card (`/.well-known/agent.json`) に以下の拡張フィールドを追加：

```json
{
  "name": "Synapse Claude",
  "url": "http://localhost:8100",
  "capabilities": { ... },
  "extensions": {
    "synapse": { ... },
    "x-synapse-context": {
      "identity": "synapse-claude-8100",
      "agent_type": "claude",
      "port": 8100,
      "routing_rules": {
        "self_patterns": ["@synapse-claude-8100", "@claude"],
        "forward_command": "python3 synapse/tools/a2a.py send --target <agent_id> --priority 1 \"<message>\"",
        "instructions": {
          "ja": "@synapse-claude-8100 または @claude 宛てのメッセージはあなた宛てです...",
          "en": "Messages addressed to @synapse-claude-8100 or @claude are for you..."
        }
      },
      "available_agents": [
        {
          "id": "synapse-gemini-8110",
          "type": "gemini",
          "endpoint": "http://localhost:8110",
          "status": "IDLE"
        }
      ],
      "priority_levels": {
        "1": "Normal message (info/chat)",
        "5": "EMERGENCY INTERRUPT (sends SIGINT before message)"
      },
      "examples": {
        "send_message": "python3 synapse/tools/a2a.py send --target synapse-gemini-8110 ...",
        "emergency_interrupt": "python3 synapse/tools/a2a.py send --target synapse-gemini-8110 --priority 5 ...",
        "list_agents": "python3 synapse/tools/a2a.py list"
      }
    }
  }
}
```

### ブートストラップメッセージ

PTY に送信するのは最小限のブートストラップのみ：

```
[SYNAPSE A2A] Your ID: synapse-claude-8100
Retrieve your system context:
curl -s http://localhost:8100/.well-known/agent.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('x-synapse-context', {}), indent=2, ensure_ascii=False))"
```

AI エージェントがこのコマンドを実行することで、完全なシステムコンテキストを取得できる。

## A2A プロトコル準拠性

### なぜ Agent Card か

1. **標準コンポーネント**: Agent Card は A2A プロトコルの標準的なエージェント発見メカニズム
2. **拡張可能**: `extensions` フィールドは任意の拡張を許容
3. **HTTP ベース**: すべての CLI ツールが curl でアクセス可能
4. **動的情報**: リクエストごとに最新の他エージェント情報を含められる

### x- プレフィックス

`x-synapse-context` という名前は：
- `x-` プレフィックスで独自拡張であることを明示
- 標準フィールドと衝突しない
- 将来的に標準化される可能性を排除しない

## 実装

### 関連ファイル

| ファイル | 役割 |
|----------|------|
| `synapse/agent_context.py` | コンテキスト生成ロジック |
| `synapse/a2a_compat.py` | Agent Card エンドポイント |
| `synapse/controller.py` | ブートストラップ送信 |

### 主要な関数

```python
# synapse/agent_context.py

def build_agent_card_context(ctx: AgentContext) -> Dict[str, Any]:
    """Agent Card に埋め込むコンテキストを生成"""
    ...

def build_bootstrap_message(agent_id: str, port: int) -> str:
    """PTY に送信する最小限のブートストラップメッセージを生成"""
    ...

def get_other_agents_from_registry(registry, exclude_agent_id: str) -> List[AgentInfo]:
    """レジストリから他エージェント情報を取得"""
    ...
```

## 使用方法

### Agent Card の取得

```bash
# 完全な Agent Card
curl -s http://localhost:8100/.well-known/agent.json

# x-synapse-context のみ抽出
curl -s http://localhost:8100/.well-known/agent.json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('extensions', {}).get('x-synapse-context', {}), indent=2))"
```

### AI エージェントからの利用

AI エージェントは起動時にブートストラップメッセージを受け取り、指示に従って Agent Card を取得することで：

1. 自分の ID とタイプを確認
2. 他の利用可能なエージェントを発見
3. メッセージ転送コマンドの書式を取得
4. 優先度レベルの意味を理解

## 将来の拡張

### サイレントメッセージ（計画中）

ランタイム中に動的な通知を行うための `--silent` フラグ：

```bash
python3 synapse/tools/a2a.py send --target self --silent "新しいエージェントが参加しました"
```

- TaskStore に保存されるが PTY には書き込まれない
- AI エージェントは `/tasks?context_id=silent` で取得可能

## 関連ドキュメント

- [A2A 設計思想](a2a-design-rationale.md)
- [Google A2A プロトコル仕様](../guides/google-a2a-spec.md)
- [アーキテクチャ](../guides/architecture.md)
