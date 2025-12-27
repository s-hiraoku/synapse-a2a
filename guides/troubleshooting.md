# Troubleshooting

Synapse A2A でよくある問題とその対処法をまとめています。

---

## 1. PTY / TUI の描画問題

### 1.1 画面が崩れる / 更新されない

```mermaid
flowchart TB
    Problem["画面が崩れる"]
    Check1{"TERM 設定?"}
    Check2{"submit_sequence?"}
    Check3{"ウィンドウサイズ?"}

    Problem --> Check1
    Check1 -->|"未設定"| Fix1["TERM=xterm-256color 追加"]
    Check1 -->|"設定済み"| Check2
    Check2 -->|"\\n"| Fix2["\\r に変更"]
    Check2 -->|"\\r"| Check3
    Check3 -->|"不正"| Fix3["ターミナルをリサイズ"]
```

**症状**:
- 画面が真っ黒になる
- 表示が更新されない
- カーソル位置がずれる

**対処法**:

1. **TERM 環境変数を確認**

```yaml
# synapse/profiles/claude.yaml
env:
  TERM: "xterm-256color"
```

2. **submit_sequence を変更**

TUI ベースの CLI は `\r` を使用します。

```yaml
submit_sequence: "\r"
```

3. **ターミナルをリサイズ**

PTY はウィンドウサイズを同期しています。リサイズすると再描画されることがあります。

---

### 1.2 入力欄が複数表示される

**症状**:
- 入力プロンプトが重複して表示される
- 入力位置が分からなくなる

**原因**:
Claude Code CLI など Ink ベースの TUI で発生する既知の問題です。

**対処法**:
- CLI を最新版にアップデート
- ターミナルを再起動
- 別のターミナルエミュレータを試す

---

### 1.3 日本語が文字化けする

**症状**:
- 日本語が正しく表示されない
- 文字が豆腐になる

**対処法**:

```yaml
env:
  LANG: "ja_JP.UTF-8"
  LC_ALL: "ja_JP.UTF-8"
  TERM: "xterm-256color"
```

---

## 2. エージェント検出の問題

### 2.1 @Agent が「not found」になる

```mermaid
flowchart TB
    Error["[✗ agent not found]"]
    Check1{"ローカルエージェント<br/>起動済み?"}
    Check2{"外部エージェント<br/>登録済み?"}
    Check3{"エージェント名正しい?"}

    Error --> Check1
    Check1 -->|"No"| Check2
    Check1 -->|"Yes"| Check3
    Check2 -->|"No"| Fix2["synapse external add で登録"]
    Check2 -->|"Yes"| Check3
    Check3 -->|"No"| Fix3["正しいエージェント名/alias を使用"]
```

**確認コマンド**:

```bash
# ローカルエージェント一覧を確認
synapse list

# 外部エージェント一覧を確認
synapse external list

# ローカル Registry ファイルを確認
ls -la ~/.a2a/registry/
cat ~/.a2a/registry/*.json | jq .

# 外部 Registry ファイルを確認
ls -la ~/.a2a/external/
cat ~/.a2a/external/*.json | jq .
```

**対処法**:

1. ローカルエージェントの場合: `synapse list` で起動確認
2. 外部エージェントの場合: `synapse external list` で登録確認
3. エージェント名（タイプ/alias）が正しいか確認

---

### 2.2 synapse list に表示されない

**症状**:
- エージェントを起動したが `synapse list` に出てこない

**原因候補**:
- 起動が正常に完了していない
- Registry への登録が失敗している
- 古い Registry ファイルが残っている

**対処法**:

```bash
# Registry ディレクトリをクリーンアップ
rm -rf ~/.a2a/registry/*

# エージェントを再起動
synapse claude --port 8100
```

---

### 2.3 古いエージェント情報が残る

**症状**:
- 停止したはずのエージェントが `synapse list` に表示される

**対処法**:

```bash
# Registry ファイルを手動削除
rm ~/.a2a/registry/<agent_id>.json

# または全てクリア
rm -rf ~/.a2a/registry/*
```

---

## 3. ネットワーク/ポートの問題

### 3.1 ポートが使用中

**症状**:
```
Error: Address already in use
```

**確認コマンド**:

```bash
# ポートを使用しているプロセスを確認
lsof -i :8100

# プロセスを強制終了
kill -9 <PID>
```

**対処法**:

1. 既存のプロセスを終了
2. 別のポートを使用

```bash
synapse claude --port 8200
```

---

### 3.2 HTTP リクエストがタイムアウトする

**症状**:
- `curl` がタイムアウトする
- `@Agent` の送信が失敗する

**確認コマンド**:

```bash
# サーバーが応答するか確認
curl -v http://localhost:8100/status
```

**対処法**:

1. エージェントが起動しているか確認
2. ファイアウォール設定を確認
3. ポート番号が正しいか確認

---

## 4. 状態検出の問題

### 4.1 IDLE にならない（永久に BUSY）

```mermaid
flowchart TB
    Problem["永久に BUSY"]
    Check1{"idle_regex 正しい?"}
    Check2{"プロンプト表示される?"}

    Problem --> Check1
    Check1 -->|"No"| Fix1["プロンプトに合わせて修正"]
    Check1 -->|"Yes"| Check2
    Check2 -->|"No"| Fix2["CLI が正常に動作しているか確認"]
```

**原因**:
`idle_regex` が CLI のプロンプトと一致していない

**確認方法**:

```bash
# CLI を直接起動してプロンプトを確認
claude

# 表示されるプロンプト
# > _
```

**対処法**:

```yaml
# プロンプトに合わせて修正
idle_regex: "> $"

# 複数パターンに対応
idle_regex: "(> |>>> )$"
```

---

### 4.2 --response でレスポンスが返ってこない

**症状**:
- `@agent --response` がタイムアウトする
- レスポンスが空になる

**原因候補**:
- 相手エージェントが IDLE にならない
- 処理時間が 60 秒を超えている
- ネットワークの問題

**対処法**:

1. 相手エージェントの状態を確認

```bash
curl http://localhost:8101/status
```

2. 長時間の処理は手動でポーリング

```bash
# ステータスを監視
watch -n 1 'curl -s http://localhost:8101/status | jq .'
```

---

## 5. 入力の問題

### 5.1 @Agent が認識されない

**症状**:
- `@agent` を入力しても通常のテキストとして扱われる

**原因候補**:
- 行頭から `@` で始まっていない
- スペースや不可視文字が含まれている

**対処法**:

- 必ず行頭から `@agent` を入力
- コピー&ペーストではなく手入力で試す

```text
# 正しい例
@codex メッセージ

# 間違った例
 @codex メッセージ  ← 先頭にスペース
```

---

### 5.2 日本語入力（IME）の問題

**症状**:
- 日本語入力時に挙動がおかしくなる
- 確定前の文字が表示されない

**原因**:
入力が 1 文字ずつ処理されるため、IME の挙動と干渉する場合があります。

**対処法**:
- メッセージを事前に入力してからペースト
- 英語でメッセージを記述

---

## 6. ログとデバッグ

### 6.1 ログファイルの場所

| ログ | パス |
|------|------|
| エージェントログ | `~/.synapse/logs/<profile>.log` |
| InputRouter ログ | `~/.synapse/logs/input_router.log` |

### 6.2 デバッグコマンド

```bash
# InputRouter ログをリアルタイム監視
tail -f ~/.synapse/logs/input_router.log

# エージェントログを確認
synapse logs claude -f

# Registry の状態を確認
cat ~/.a2a/registry/*.json | jq .

# ステータスを継続監視
watch -n 1 'curl -s http://localhost:8100/status | jq .'
```

### 6.3 詳細デバッグ

```bash
# フォアグラウンドで起動（ログが見える）
synapse start claude --port 8100 --foreground

# HTTP リクエストの詳細
curl -v http://localhost:8100/message \
  -H "Content-Type: application/json" \
  -d '{"content": "test", "priority": 1}'
```

---

## 7. よくある質問 (FAQ)

### Q1. 複数の同じエージェントを起動できる？

**A**: 可能ですが、異なるポートと作業ディレクトリが必要です。

```bash
# ディレクトリ 1
cd /project1
synapse claude --port 8100

# ディレクトリ 2
cd /project2
synapse claude --port 8200
```

---

### Q2. Windows で使える？

**A**: WSL2 を推奨します。Windows ネイティブでは PTY の動作が異なるため、問題が発生する可能性があります。

---

### Q3. Priority 5 で止まらない

**A**: SIGINT を無視する CLI があります。その場合は手動で Ctrl+C を押すか、プロセスを強制終了してください。

```bash
synapse stop claude
# または
kill -9 <PID>
```

---

### Q4. API サーバーだけ起動したい

**A**: `synapse start` でバックグラウンド起動できます。

```bash
synapse start claude --port 8100
```

---

## 8. 外部エージェントの問題

### 8.1 外部エージェントの発見に失敗する

**症状**:

```
Failed to discover agent at http://example.com
```

**原因候補**:

- URL が間違っている
- エージェントが起動していない
- ネットワーク接続の問題
- Agent Card (`/.well-known/agent.json`) が提供されていない

**確認コマンド**:

```bash
# Agent Card が取得できるか確認
curl http://example.com/.well-known/agent.json
```

**対処法**:

1. URL が正しいか確認（末尾のスラッシュに注意）
2. 対象サーバーが起動しているか確認
3. ファイアウォール/ネットワーク設定を確認

---

### 8.2 外部エージェントへのメッセージ送信に失敗する

**症状**:

- `@external_alias` でエラーになる
- `synapse external send` がタイムアウトする

**確認コマンド**:

```bash
# 外部エージェントの情報を確認
synapse external info <alias>

# 直接 API を叩いて確認
curl -X POST http://<agent_url>/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "test"}]}}'
```

**対処法**:

1. エージェントが応答しているか確認
2. エージェントの URL が変更されていないか確認
3. 必要に応じて再登録: `synapse external remove <alias>` → `synapse external add ...`

---

### 8.3 外部エージェントの登録情報をクリアしたい

**対処法**:

```bash
# 個別削除
synapse external remove <alias>

# 全てクリア
rm -rf ~/.a2a/external/*
```

---

## 9. 問題報告

問題が解決しない場合は、以下の情報を添えて報告してください：

1. OS とバージョン
2. Python バージョン
3. Synapse A2A バージョン
4. 使用している CLI ツール
5. エラーメッセージ
6. `~/.synapse/logs/input_router.log` の内容
7. 外部エージェントの問題の場合: 対象 URL と Agent Card

---

## 関連ドキュメント

- [profiles.md](profiles.md) - プロファイル設定
- [usage.md](usage.md) - 使い方詳細
- [architecture.md](architecture.md) - 内部アーキテクチャ
