# Canvas Interactive Cards

Canvas のインタラクティブ機能に関する設計ドキュメント。

---

## Part 1: HTML Artifact Support（実装済み）

### 概要

既存の `format: "html"` の sandboxed iframe を強化し、Claude.ai の Artifacts のようなインタラクティブな HTML/JS/CSS をサンドボックス内で動かせるようにする。新フォーマットは追加せず、既存インフラを最大限再利用する方針。

### 実装内容

#### テーマ同期 (parent → iframe via postMessage)

`formatCanvasHTMLDocument()` が全 HTML コンテンツに以下を注入:

1. **CSS 変数** — `--bg`, `--fg`, `--border` をダーク/ライト両テーマで定義。エージェント生成 HTML がこれらを参照可能
2. **テーマリスナー** — `postMessage` で `{ type: "synapse-theme", theme: "dark"|"light" }` を受信し、`data-theme` 属性と `colorScheme` を切り替え
3. **テーマブロードキャスト** — テーマトグルクリック時に全 `.format-html iframe` へ新テーマを送信
4. **初期テーマ送信** — `iframe.onload` で現在のテーマを送信

#### 自動リサイズ (iframe → parent via postMessage)

1. **ResizeObserver スクリプト注入** — iframe 内の `body` の高さ変更を検知し、`{ type: "synapse-resize", height: N }` を親に通知
2. **グローバル message リスナー** — 親が `synapse-resize` メッセージを受信し、対応する iframe の `style.height` を更新
3. **overflow 対応** — `body` の `overflow: hidden` を一時的に `visible` に切り替えて正確な `scrollHeight` を取得

#### CSS ダークモード対応

`[data-theme="dark"] .format-html iframe` に `background: #1a1a2e` を設定。

#### Full Document の正規化

`<!doctype html>` や `<html>` を含む full document は、`<head>` と `<body>` の中身を抽出して fragment と同じラッピングパスを通す。これにより head-semantics の問題（CSS カスケード競合、CSP、スクリプト順序）を回避する。

**注意:** 以前の `body { overflow: hidden; }` + `body > :first-child { min-height: 100% }` は、ユーザーコンテンツの最初の子要素を viewport 全体に引き伸ばし、後続要素をクリップしてしまうバグがあったため削除。canvas ビューでは `html, body { height: 100%; margin: 0; }` のみ注入する。

### セキュリティ

- `sandbox="allow-scripts"` を維持。`allow-same-origin` は追加しない
- `postMessage` は `"*"` ターゲット（iframe origin が `null` のため）
- メッセージリスナーは `e.data.type` でフィルタリング

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `synapse/canvas/static/canvas.js` | `formatCanvasHTMLDocument` 拡張, `renderHTML` 初期テーマ送信, テーマトグルでブロードキャスト, resize リスナー |
| `synapse/canvas/static/canvas.css` | ダークモード iframe 背景色 |
| `tests/canvas_frontend_artifact_test.js` | Node.js フロントエンドテスト（5件） |
| `tests/test_canvas_artifact.py` | Python テスト（プロトコル3件 + フロントエンド1件） |

### 使用例

```bash
curl -X POST http://localhost:3000/api/cards -H 'Content-Type: application/json' -d '{
  "type": "render",
  "agent_id": "test-agent",
  "agent_name": "TestAgent",
  "title": "Interactive Counter",
  "tags": ["artifact"],
  "content": [{"format": "html", "x_title": "React Counter", "body": "<!doctype html>..."}]
}'
```

エージェント生成 HTML は `var(--bg)`, `var(--fg)`, `var(--border)` を使ってテーマ対応可能。

---

## Part 2: 双方向インタラクティブカード（設計中）

### 背景

Canvas は 27 種類のコンテンツフォーマットをサポートしているが、すべて **一方向（Agent → Browser）** の表示専用。ユーザーがカード上のボタンを押したり、フォームに入力してエージェントに返答する仕組みがない。

Claude の Tool Use 確認 UI（Allow/Deny）や Artifacts のインタラクティブコンポーネントを参考に、エージェントがユーザーに確認・選択・入力を求められる双方向カードを実現する。

## データフロー

```
Agent → POST /api/cards (format="interactive")
                ↓
        SQLite 保存 + nonce 自動付与
                ↓ SSE card_created
Browser: renderInteractive() → ボタン/フォーム表示
                ↓ ユーザー操作
Browser → POST /api/cards/{card_id}/action
                ↓ nonce 検証
        state="responded" に更新
                ↓ SSE card_updated → UI 再描画
                ↓ A2A /tasks/send → Agent に通知
```

## プロトコル拡張

### FORMAT_REGISTRY

`"interactive"` を `body_type="object"` で追加。`body.widget` で widget 種別を分岐する（`chart` が `body.type` で分岐するのと同じパターン）。

### ContentBlock 拡張フィールド

既存の `x_` prefix 規約に従い、3 フィールドを追加:

| フィールド | 型 | 説明 |
|-----------|------|------|
| `x_interaction_state` | `"pending" \| "responded" \| "expired"` | インタラクション状態 |
| `x_interaction_nonce` | `str` | サーバー生成の使い捨てトークン |
| `x_interaction_response` | `dict` | ユーザーの回答データ |

### Widget 種別と Body Schema

#### confirm

確認ダイアログ（Claude の Tool Use 承認 UI 風）。

```json
{
  "widget": "confirm",
  "prompt": "Allow file edit?",
  "confirm_label": "Allow",
  "deny_label": "Deny"
}
```

Response: `{"action": "confirm"}` or `{"action": "deny"}`

#### button-group

複数選択肢のボタン群。

```json
{
  "widget": "button-group",
  "prompt": "Which strategy?",
  "buttons": [
    {"id": "a", "label": "Strategy A", "style": "primary"},
    {"id": "b", "label": "Strategy B", "style": "default"},
    {"id": "c", "label": "Cancel", "style": "danger"}
  ]
}
```

Response: `{"action": "a"}`

#### form

入力フォーム。

```json
{
  "widget": "form",
  "prompt": "Configure deployment",
  "fields": [
    {"id": "env", "type": "text", "label": "Environment", "required": true},
    {"id": "replicas", "type": "number", "label": "Replicas", "default": 3},
    {"id": "notes", "type": "textarea", "label": "Notes"}
  ],
  "submit_label": "Deploy"
}
```

Response: `{"fields": {"env": "production", "replicas": 3, "notes": ""}}`

#### select

選択リスト。

```json
{
  "widget": "select",
  "prompt": "Select target branch",
  "options": [
    {"id": "main", "label": "main"},
    {"id": "develop", "label": "develop"}
  ],
  "multiple": false
}
```

Response: `{"selected": "main"}` (multiple: `{"selected": ["main", "develop"]}`)

### 共通オプション

| フィールド | 型 | 説明 |
|-----------|------|------|
| `callback_task_id` | `str?` | エージェントのタスク ID と紐付け（`in_reply_to` に使用） |

## API エンドポイント

### POST /api/cards/{card_id}/action

ユーザーのインタラクション結果を受け取る。

**Request**:
```json
{
  "block_index": 0,
  "nonce": "abc123",
  "response": {"action": "confirm"}
}
```

**処理フロー**:
1. カード存在確認
2. ブロックが `format="interactive"` かつ `state="pending"` であることを検証
3. nonce 照合
4. `x_interaction_state` → `"responded"`, `x_interaction_response` に回答格納
5. `x_interaction_nonce` クリア（消費済み）
6. SSE `card_updated` ブロードキャスト
7. `_resolve_agent_endpoint()` でエージェント特定、A2A `/tasks/send` で通知

**エージェントへの通知メッセージ**:
```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "data", "data": {
      "type": "canvas_interaction",
      "card_id": "<card_id>",
      "widget": "confirm",
      "response": {"action": "confirm"}
    }}]
  },
  "metadata": {
    "sender": {"sender_id": "canvas-ui", "sender_name": "Canvas"},
    "in_reply_to": "<callback_task_id>"
  }
}
```

**レスポンスコード**:
- 200: 成功
- 400: ブロックが interactive でない
- 403: nonce 不一致
- 404: カード未存在
- 409: 既に responded

## セキュリティ

- **Nonce**: サーバー側で `uuid4()[:16]` を自動生成。クライアントは生成不可。使用後に消費されリプレイ攻撃を防止
- **二重送信防止**: `state="responded"` のブロックへのアクションは 409 で拒否
- **所有権**: カードの `agent_id` を使ってエージェントを特定。他エージェントのカードは操作不可

## フロントエンド

### renderInteractive(wrap, block, options)

`renderBlock()` の switch 文に `case "interactive"` を追加して呼び出す。

**状態別表示**:
- `pending`: アクティブな UI 要素（ボタン、フォーム等）
- `responded`: 選択結果を読み取り専用で表示（選んだボタンがハイライト）
- `expired`: グレーアウト + "Expired" バッジ

**Widget 別レンダリング**:
- `confirm`: 2 ボタン横並び（Allow/Deny 風、glassmorphism スタイル）
- `button-group`: ボタン群（primary/default/danger バリアント）
- `form`: ラベル付きフィールド + Submit ボタン
- `select`: ラジオボタン（≤5 件）またはドロップダウン（>5 件）

### submitInteraction(cardId, blockIndex, nonce, response)

`POST /api/cards/{cardId}/action` を呼び出し、即座にボタンを disable。`card_updated` SSE で自動再描画。

## 定数

```python
VALID_WIDGETS = {"confirm", "button-group", "form", "select"}
VALID_INTERACTION_STATES = {"pending", "responded", "expired"}
MAX_BUTTONS = 10
MAX_FORM_FIELDS = 20
MAX_SELECT_OPTIONS = 50
VALID_BUTTON_STYLES = {"primary", "default", "danger"}
VALID_FIELD_TYPES = {"text", "number", "textarea"}
```

## 修正対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `synapse/canvas/protocol.py` | interactive フォーマット + ContentBlock 拡張 + バリデーション |
| `synapse/canvas/store.py` | `update_block_interaction()` メソッド |
| `synapse/canvas/server.py` | nonce 自動付与 + `/api/cards/{card_id}/action` |
| `synapse/canvas/static/canvas.js` | `renderInteractive()` + `submitInteraction()` |
| `synapse/canvas/static/canvas.css` | インタラクティブコンポーネントスタイル |
| `tests/test_canvas_interactive.py` | 新規テストファイル |

## 再利用する既存関数

| 関数 | ファイル | 用途 |
|------|---------|------|
| `_resolve_agent_endpoint()` | `server.py:133` | agent_id → endpoint 解決 |
| `_broadcast_event()` | `server.py:58` | SSE ブロードキャスト |
| `validate_message()` | `protocol.py:221` | バリデーションパイプライン |
| `ContentBlock.to_dict()` | `protocol.py:116` | シリアライズ |
| `CanvasMessage.from_dict()` | `protocol.py:165` | デシリアライズ |
| Admin send パターン | `server.py:1160-1208` | A2A メッセージ構築 + httpx 送信 |
