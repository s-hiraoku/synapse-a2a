# Shared Memory — エージェント間知識共有 仕様書

## 概要

Synapse A2A の複数エージェントが協調作業する際に、セッション間・エージェント間で学んだ知識を共有する仕組みを提供する。

**設計方針**: SQLite DB + A2A ブロードキャスト通知
- 検索性: key, tags, content をまたいだ全文検索
- メタデータ: 誰がいつ書いたか、何回更新したか
- 並行書き込み安全性: SQLite WAL モード
- パターン一貫性: TaskBoard/History/FileSafety と同じ設計

## アーキテクチャ

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Claude      │     │  Gemini     │     │  Codex      │
│  Agent       │     │  Agent      │     │  Agent      │
└──────┬───────┘     └──────┬──────┘     └──────┬──────┘
       │                    │                    │
       ├────── synapse memory save ──────────────┤
       ├────── synapse memory search ────────────┤
       ├────── synapse memory list ──────────────┤
       │                    │                    │
       ▼                    ▼                    ▼
  ┌──────────────────────────────────────────────────┐
  │          .synapse/memory.db (SQLite WAL)          │
  │                                                    │
  │  memories table:                                   │
  │  ┌────┬─────┬─────────┬────────┬──────┬─────────┐ │
  │  │ id │ key │ content │ author │ tags │ timestamps│ │
  │  └────┴─────┴─────────┴────────┴──────┴─────────┘ │
  └──────────────────────────────────────────────────┘
```

## DB スキーマ

```sql
CREATE TABLE IF NOT EXISTS memories (
    id         TEXT PRIMARY KEY,          -- UUID
    key        TEXT NOT NULL UNIQUE,      -- 検索用キー (例: "auth-pattern")
    content    TEXT NOT NULL,             -- メモリ本文
    author     TEXT NOT NULL,             -- agent_id (例: synapse-claude-8100)
    tags       TEXT DEFAULT '[]',         -- JSON配列 (例: ["architecture","auth"])
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_memory_key ON memories(key);
CREATE INDEX IF NOT EXISTS idx_memory_author ON memories(author);
```

- `save()` は `INSERT ... ON CONFLICT(key) DO UPDATE` で UPSERT
- `tags` は JSON 配列文字列 (`json.dumps()`/`json.loads()`)

## コア API: `SharedMemory` クラス

ファイル: `synapse/shared_memory.py`

```python
class SharedMemory:
    def __init__(self, db_path=None, enabled=True)
    def _get_connection() -> sqlite3.Connection  # WAL mode
    def _init_db()                                # テーブル作成
    @classmethod
    def from_env(cls)                             # SYNAPSE_SHARED_MEMORY_*
    @staticmethod
    def _row_to_dict(row) -> dict

    # CRUD
    def save(key, content, author, tags=None) -> dict    # UPSERT on key
    def get(id_or_key) -> dict | None                     # ID or key lookup
    def list(author=None, tags=None, limit=50) -> list
    def search(query) -> list                             # LIKE on key+content+tags
    def delete(id_or_key) -> bool
    def stats() -> dict                                   # 件数、著者別、タグ別
```

## CLI コマンド

```bash
synapse memory save <key> <content> [--tags tag1,tag2] [--notify]
synapse memory list [--author <id>] [--tags <tags>] [--limit <n>]
synapse memory show <id_or_key>
synapse memory search <query>
synapse memory delete <id_or_key> [--force]
synapse memory stats
```

- `--notify` フラグ: 保存後に `synapse broadcast` で通知メッセージ送信

## REST API エンドポイント

```
GET  /memory/list?author=...&tags=...&limit=50
POST /memory/save         {key, content, tags?, notify?}
GET  /memory/search?q=...
GET  /memory/{id_or_key}
DELETE /memory/{id_or_key}
```

- 既存の `Depends(require_auth)` を適用

## 設定

### paths.py 追加

```python
def get_shared_memory_db_path() -> str:
    return _resolve_path(
        "SYNAPSE_SHARED_MEMORY_DB_PATH",
        Path(".synapse") / "memory.db",
    )
```

### settings.py 追加

```python
"SYNAPSE_SHARED_MEMORY_ENABLED": "true",
"SYNAPSE_SHARED_MEMORY_DB_PATH": ".synapse/memory.db",
```

## インストラクション注入

ファイル: `synapse/templates/.synapse/shared-memory.md`

```markdown
SHARED MEMORY (Cross-Agent Knowledge Base):
  synapse memory save <key> "<content>" [--tags tag1,tag2]  - Save knowledge
  synapse memory list [--author <id>]                       - List memories
  synapse memory search <query>                             - Search knowledge
  synapse memory show <key>                                 - View details
```

条件: `SYNAPSE_SHARED_MEMORY_ENABLED=true` の時のみ注入

## ファイル一覧

| ファイル | 種別 | 説明 |
|----------|------|------|
| `synapse/shared_memory.py` | NEW | SharedMemory コアクラス |
| `synapse/paths.py` | MODIFY | `get_shared_memory_db_path()` 追加 |
| `synapse/settings.py` | MODIFY | デフォルト設定 + instruction injection |
| `synapse/cli.py` | MODIFY | `synapse memory` サブコマンド群 |
| `synapse/a2a_compat.py` | MODIFY | `/memory/*` API エンドポイント |
| `synapse/templates/.synapse/shared-memory.md` | NEW | インストラクション テンプレート |
| `tests/test_shared_memory.py` | NEW | SharedMemory クラスのテスト |
| `tests/test_cli_memory.py` | NEW | CLI コマンドのテスト |
| `tests/test_memory_api.py` | NEW | API エンドポイントのテスト |

## テスト計画

### test_shared_memory.py
- DB 初期化 / from_env / disabled noop
- CRUD: save, upsert, get by id/key, list (filter), search, delete
- stats (件数、著者別、タグ別)

### test_cli_memory.py
- save / save with tags / list / list filter / show / search / delete / delete --force / stats

### test_memory_api.py
- list / save / search / get / delete / auth required

## 実装順序

1. テスト作成: `test_shared_memory.py` → `test_cli_memory.py` → `test_memory_api.py`
2. コア実装: `shared_memory.py` → `paths.py` → `settings.py`
3. CLI: `cli.py` に `synapse memory` サブコマンド追加
4. API: `a2a_compat.py` にエンドポイント追加
5. インストラクション注入: テンプレート作成 + `settings.py` 拡張
6. 統合テスト: 全テスト通過確認
