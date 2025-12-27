# Multi-Agent Setup Guide

このガイドでは、Claude / Codex / Gemini の3つのエージェントを同時に起動し、
相互通信できる状態にするまでを **丁寧に** まとめています。

---

## 全体像

- Synapse は各 CLI を **PTY でラップ**して起動します。
- 起動したエージェントは `~/.a2a/registry/` に登録されます。
- 端末内の `@Agent` 入力や HTTP API を介して相互にメッセージ送信できます。

---

## 1. 前提条件

### 対応 OS / Python

- macOS / Linux（Windows は WSL2 推奨）
- Python 3.10+

### 必須 CLI ツール

| エージェント | CLI コマンド | 公式リンク |
|------------|-------------|-----------|
| Claude | `claude` | https://claude.ai/code |
| Codex | `codex` | https://github.com/openai/codex |
| Gemini | `gemini` | https://github.com/google/gemini-cli |

---

## 2. インストール

```bash
pip install -r requirements.txt
```

CLI を使う場合は editable install を推奨します。

```bash
pip install -e .
```

---

## 3. 起動（インタラクティブ）

各エージェントを **別ターミナル** で起動します。

```bash
# Terminal 1
synapse claude --port 8100

# Terminal 2
synapse codex --port 8101

# Terminal 3
synapse gemini --port 8102
```

起動後の挙動:

- 各 CLI は通常通り利用可能
- `@Agent` 入力は A2A メッセージとして送信
- 送信先は `~/.a2a/registry/` に登録されたエージェント

補足:
- `@Agent` は **行単位** で判定されます（Enter で送信）
- 正しく判定されない場合は、先頭から `@agent` で書いているか確認してください

---

## 4. 端末内での A2A 送信

インタラクティブ起動中の端末で、以下のように使います。

```text
@codex この設計をレビューして
@claude --response "PTY 関連の修正案を出して"
```

補足:
- `--response` は「相手の返信をこの端末に返す」オプションです
- 返信は相手が `IDLE` になるのをポーリングして取得します
- 返答が長い/処理が長い場合は、戻りが遅くなることがあります

---

## 5. 外部から送信（CLI / HTTP）

### CLI で送信

```bash
synapse list
synapse send --target codex --priority 1 "設計を書いて"
```

### HTTP で送信

```bash
curl -X POST http://localhost:8101/message \
  -H "Content-Type: application/json" \
  -d '{"content": "設計を書いて", "priority": 1}'
```

---

## 6. ステータス確認

```bash
curl http://localhost:8100/status
# {"status": "BUSY", "context": "..."}
```

- `status` は `IDLE` / `BUSY` を返します
- `context` は直近の出力の一部です

---

## 7. 優先度（Priority）

| Priority | 動作 | 用途 |
|----------|------|------|
| 1-4 | stdin に書き込み | 通常の通信 |
| 5 | SIGINT を送ってから書き込み | 強制介入 / 停止 |

---

## 8. よくある問題

- 端末描画が崩れる / 入力欄が乱れる
- ポートが使われている
- エージェントが見つからない

詳しくは `guides/troubleshooting.md` を参照してください。
