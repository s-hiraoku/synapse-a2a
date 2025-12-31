# エンタープライズ機能ガイド

> **Synapse A2A のセキュリティ・通知・高性能通信機能**

本ガイドでは、本番環境やエンタープライズユースケース向けの機能について解説します。

---

## 目次

- [概要](#概要)
- [認証・認可 (API Key)](#認証認可-api-key)
- [Webhook 通知](#webhook-通知)
- [gRPC サポート](#grpc-サポート)
- [セキュリティベストプラクティス](#セキュリティベストプラクティス)

---

## 概要

Synapse A2A は以下のエンタープライズ機能を提供します：

| 機能 | 説明 | ユースケース |
|------|------|-------------|
| **API Key 認証** | エンドポイントへのアクセス制御 | 本番環境でのセキュリティ確保 |
| **Webhook 通知** | タスク完了時の外部通知 | CI/CD 連携、監視システム |
| **gRPC** | 高性能バイナリプロトコル | 大量リクエスト、低レイテンシ要件 |

---

## 認証・認可 (API Key)

### 概要

API Key 認証により、Synapse A2A のエンドポイントへのアクセスを制御できます。

```
┌─────────────┐     X-API-Key: xxx     ┌─────────────────┐
│   Client    │ ─────────────────────► │  Synapse A2A    │
│             │                        │  (認証有効)      │
└─────────────┘                        └─────────────────┘
       │                                      │
       │  401 Unauthorized                    │ 200 OK
       └──────────────────────────────────────┘
```

### クイックスタート

#### 1. 認証を有効にして起動

```bash
# 環境変数で設定
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS=my-secret-key-1,my-secret-key-2

# エージェント起動
synapse claude
```

#### 2. API Key でリクエスト

```bash
# ヘッダーで指定（推奨）
curl -H "X-API-Key: my-secret-key-1" \
  http://localhost:8100/tasks

# クエリパラメータで指定
curl "http://localhost:8100/tasks?api_key=my-secret-key-1"
```

### 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `SYNAPSE_AUTH_ENABLED` | 認証を有効化 | `false` |
| `SYNAPSE_API_KEYS` | 有効な API Key（カンマ区切り） | なし |
| `SYNAPSE_ADMIN_KEY` | 管理者用 API Key | なし |
| `SYNAPSE_ALLOW_LOCALHOST` | localhost からのアクセスを許可 | `true` |

### API Key の種類

#### 通常の API Key

タスク操作に必要な基本的な権限を持ちます。

```bash
SYNAPSE_API_KEYS=key1,key2,key3
```

#### Admin Key

全ての操作（Webhook 管理含む）が可能です。

```bash
SYNAPSE_ADMIN_KEY=super-secret-admin-key
```

### 保護されるエンドポイント

| エンドポイント | 必要な認証 |
|---------------|-----------|
| `POST /tasks/send` | API Key |
| `GET /tasks/{id}` | API Key |
| `GET /tasks` | API Key |
| `POST /tasks/{id}/cancel` | API Key |
| `GET /tasks/{id}/subscribe` | API Key |
| `POST /tasks/send-priority` | API Key |
| `POST /webhooks` | Admin Key |
| `DELETE /webhooks/{id}` | Admin Key |

### localhost 自動許可

開発環境では `localhost` からのリクエストを自動許可できます（デフォルト有効）。

```bash
# localhost 許可を無効化（本番環境推奨）
export SYNAPSE_ALLOW_LOCALHOST=false
```

### エラーレスポンス

```json
// 401 Unauthorized - API Key なし
{
  "detail": "API key required"
}

// 401 Unauthorized - 無効な API Key
{
  "detail": "Invalid API key"
}

// 403 Forbidden - 権限不足
{
  "detail": "Admin privileges required"
}
```

---

## Webhook 通知

### 概要

タスクの状態変化を外部 URL に通知できます。CI/CD パイプラインや監視システムとの連携に便利です。

```
┌─────────────────┐    task.completed    ┌─────────────────┐
│  Synapse A2A    │ ───────────────────► │  Your Server    │
│                 │                      │  (Webhook URL)  │
└─────────────────┘                      └─────────────────┘
       │
       │  署名検証: X-Webhook-Signature
       │  リトライ: 最大3回（指数バックオフ）
       │
```

### クイックスタート

#### 1. Webhook を登録

```bash
curl -X POST http://localhost:8100/webhooks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{
    "url": "https://your-server.com/webhook",
    "events": ["task.completed", "task.failed"],
    "secret": "your-webhook-secret"
  }'
```

レスポンス:

```json
{
  "id": "wh_abc123",
  "url": "https://your-server.com/webhook",
  "events": ["task.completed", "task.failed"],
  "active": true,
  "created_at": "2025-12-31T12:00:00Z"
}
```

#### 2. Webhook を受信

```python
# Flask での例
from flask import Flask, request
import hmac
import hashlib

app = Flask(__name__)
WEBHOOK_SECRET = "your-webhook-secret"

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    # 署名を検証
    signature = request.headers.get("X-Webhook-Signature")
    payload = request.get_data()

    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, f"sha256={expected}"):
        return "Invalid signature", 401

    # イベントを処理
    event = request.json
    print(f"Received: {event['event_type']} for task {event['task_id']}")

    return "OK", 200
```

### イベントタイプ

| イベント | 発火タイミング | ペイロード |
|---------|---------------|-----------|
| `task.completed` | タスクが正常完了 | task_id, artifacts |
| `task.failed` | タスクが失敗 | task_id, error |
| `task.canceled` | タスクがキャンセル | task_id |

### Webhook ペイロード

```json
{
  "event_type": "task.completed",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-12-31T12:00:00Z",
  "data": {
    "status": "completed",
    "artifacts": [
      {
        "type": "text",
        "data": {"content": "Task output..."}
      }
    ]
  }
}
```

### 署名検証

Webhook リクエストには HMAC-SHA256 署名が含まれます。

```
X-Webhook-Signature: sha256=abc123...
```

検証方法:

```python
import hmac
import hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")
```

### リトライ機能

配信失敗時は指数バックオフでリトライします：

| リトライ | 待機時間 |
|---------|---------|
| 1回目 | 1秒後 |
| 2回目 | 2秒後 |
| 3回目 | 4秒後 |

### Webhook 管理 API

#### 一覧取得

```bash
curl http://localhost:8100/webhooks \
  -H "X-API-Key: your-admin-key"
```

#### 削除

```bash
curl -X DELETE http://localhost:8100/webhooks/wh_abc123 \
  -H "X-API-Key: your-admin-key"
```

#### 配信履歴

```bash
curl http://localhost:8100/webhooks/deliveries \
  -H "X-API-Key: your-admin-key"
```

レスポンス:

```json
[
  {
    "id": "del_xyz789",
    "webhook_id": "wh_abc123",
    "event_type": "task.completed",
    "status": "success",
    "status_code": 200,
    "attempts": 1,
    "created_at": "2025-12-31T12:00:00Z"
  }
]
```

---

## gRPC サポート

### 概要

gRPC は HTTP/2 ベースの高性能 RPC フレームワークです。大量のリクエストや低レイテンシ要件がある場合に有効です。

```
┌─────────────────┐     Protocol Buffers    ┌─────────────────┐
│  gRPC Client    │ ◄─────────────────────► │  Synapse gRPC   │
│  (任意の言語)    │         HTTP/2          │  Server         │
└─────────────────┘                         └─────────────────┘
                                                   │
                                            Port: REST + 1
                                            (例: 8101)
```

### インストール

gRPC は**オプショナル依存**です。必要な場合のみインストールしてください。

```bash
# uv
uv pip install synapse-a2a[grpc]

# pip
pip install synapse-a2a[grpc]
```

### 利用可能な RPC

Protocol Buffers 定義 (`synapse/proto/a2a.proto`):

```protobuf
service A2AService {
    // エージェント発見
    rpc GetAgentCard(GetAgentCardRequest) returns (GetAgentCardResponse);

    // タスク管理
    rpc SendMessage(SendMessageRequest) returns (SendMessageResponse);
    rpc GetTask(GetTaskRequest) returns (GetTaskResponse);
    rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);
    rpc CancelTask(CancelTaskRequest) returns (CancelTaskResponse);

    // ストリーミング（SSE の代替）
    rpc Subscribe(SubscribeRequest) returns (stream TaskStreamEvent);

    // Priority 拡張
    rpc SendPriorityMessage(SendPriorityMessageRequest) returns (SendMessageResponse);
}
```

### メッセージ定義

#### Task

```protobuf
message Task {
    string id = 1;
    string context_id = 2;
    string status = 3;  // submitted, working, completed, failed, canceled
    Message message = 4;
    repeated Artifact artifacts = 5;
    TaskError error = 6;
    google.protobuf.Timestamp created_at = 7;
    google.protobuf.Timestamp updated_at = 8;
    google.protobuf.Struct metadata = 9;
}
```

#### Message と Part

```protobuf
message Message {
    string role = 1;  // "user" or "agent"
    repeated Part parts = 2;
}

message Part {
    oneof part {
        TextPart text_part = 1;
        FilePart file_part = 2;
    }
}

message TextPart {
    string type = 1;  // "text"
    string text = 2;
}

message FilePart {
    string type = 1;  // "file"
    string name = 2;
    string mime_type = 3;
    bytes data = 4;
}
```

### Python クライアント例

```python
import grpc
from synapse.proto import a2a_pb2, a2a_pb2_grpc

# チャネル作成（REST port + 1）
channel = grpc.insecure_channel('localhost:8101')
stub = a2a_pb2_grpc.A2AServiceStub(channel)

# Agent Card 取得
response = stub.GetAgentCard(a2a_pb2.GetAgentCardRequest())
print(f"Agent: {response.agent_card.name}")

# メッセージ送信
request = a2a_pb2.SendMessageRequest(
    message=a2a_pb2.Message(
        role="user",
        parts=[
            a2a_pb2.Part(
                text_part=a2a_pb2.TextPart(
                    type="text",
                    text="Hello from gRPC!"
                )
            )
        ]
    )
)
response = stub.SendMessage(request)
print(f"Task ID: {response.task.id}")

# ストリーミング購読
for event in stub.Subscribe(a2a_pb2.SubscribeRequest(task_id=response.task.id)):
    print(f"Event: {event.event_type}")
    if event.event_type == "done":
        break
```

### ポート設定

| プロトコル | ポート | 備考 |
|-----------|--------|------|
| REST (HTTP) | 8100 | メインポート |
| gRPC | 8101 | REST + 1 |

カスタムポート:

```bash
synapse claude --port 9000  # REST: 9000, gRPC: 9001
```

### REST vs gRPC

| 観点 | REST | gRPC |
|-----|------|------|
| プロトコル | HTTP/1.1 | HTTP/2 |
| データ形式 | JSON | Protocol Buffers |
| ストリーミング | SSE | Bidirectional |
| クライアント生成 | 手動 | 自動（protoc） |
| ブラウザ対応 | 完全 | grpc-web 必要 |
| 性能 | 良好 | 高速 |

**推奨**:
- 一般的なユースケース → REST
- 高性能要件、多言語クライアント → gRPC

---

## セキュリティベストプラクティス

### 本番環境チェックリスト

```bash
# 1. 認証を有効化
export SYNAPSE_AUTH_ENABLED=true

# 2. 強力な API Key を使用
export SYNAPSE_API_KEYS=$(openssl rand -hex 32)
export SYNAPSE_ADMIN_KEY=$(openssl rand -hex 32)

# 3. localhost 自動許可を無効化
export SYNAPSE_ALLOW_LOCALHOST=false

# 4. HTTPS を使用
synapse start claude \
  --ssl-cert /path/to/cert.pem \
  --ssl-key /path/to/key.pem

# 5. Webhook に署名を設定
curl -X POST http://localhost:8100/webhooks \
  -d '{"url": "...", "secret": "$(openssl rand -hex 32)"}'
```

### API Key 管理

```bash
# キーのローテーション
# 1. 新しいキーを追加
export SYNAPSE_API_KEYS=old-key,new-key

# 2. クライアントを更新

# 3. 古いキーを削除
export SYNAPSE_API_KEYS=new-key
```

### ネットワーク設定

```bash
# ローカルのみ（デフォルト）
synapse claude --host 127.0.0.1

# 全インターフェース（LAN 内）
synapse claude --host 0.0.0.0

# 本番環境ではリバースプロキシ推奨
# nginx → synapse (localhost)
```

### ログ設定

```bash
# 詳細ログ
export SYNAPSE_LOG_LEVEL=DEBUG

# 認証イベントをログ
# → synapse.auth モジュールのログを確認
```

---

## トラブルシューティング

### 認証エラー

```bash
# 401 Unauthorized
curl -v http://localhost:8100/tasks
# → X-API-Key ヘッダーを確認

# API Key が正しいか確認
echo $SYNAPSE_API_KEYS
```

### Webhook 配信失敗

```bash
# 配信履歴を確認
curl http://localhost:8100/webhooks/deliveries

# よくある原因:
# - URL が到達不能
# - タイムアウト（10秒）
# - 署名検証失敗
```

### gRPC 接続エラー

```bash
# gRPC がインストールされているか確認
python -c "import grpc; print(grpc.__version__)"

# ポートが正しいか確認（REST + 1）
curl http://localhost:8100/status  # REST
# gRPC は 8101
```

---

## 関連ドキュメント

- [基本的な使い方](usage.md)
- [アーキテクチャ](architecture.md)
- [トラブルシューティング](troubleshooting.md)
- [Google A2A 仕様](google-a2a-spec.md)
