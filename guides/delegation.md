# Delegation Guide

エージェント間の自動タスク委任機能のガイドです。

## 概要

Delegation（委任）は、Claudeが受け取ったタスクを自動的に他のエージェント（Codex, Gemini）に振り分ける機能です。

**設定の2つの要素:**

| 設定 | 保存場所 | 役割 |
|------|----------|------|
| **有効化** | `.synapse/settings.json` | `delegation.enabled: true` で有効化 |
| **ルール** | `.synapse/delegate.md` | 誰に何を任せるか（自然言語で記述） |

> **重要**: `delegation.enabled: true` の場合のみ、`delegate.md` のルールが初期インストラクションに含まれます。

---

## 関連設定: A2A Flow

委任とは独立して、エージェント間通信の応答動作を `a2a.flow` で制御できます。

| 設定 | 説明 |
|------|------|
| `a2a.flow: roundtrip` | 常に結果を待つ |
| `a2a.flow: oneway` | 常に転送のみ（結果を待たない） |
| `a2a.flow: auto` | メッセージごとに `--response`/`--no-response` フラグで制御 |

```json
{
  "a2a": {
    "flow": "auto"
  },
  "delegation": {
    "enabled": true
  }
}
```

---

## クイックスタート

### Step 1: 設定ファイルを編集

`.synapse/settings.json`:

```json
{
  "a2a": {
    "flow": "auto"
  },
  "delegation": {
    "enabled": true
  }
}
```

### Step 2: ルールを作成

`.synapse/delegate.md` を作成：

```markdown
# Delegation Rules

コーディング作業（ファイルの編集、新規作成）はCodexに任せる。
調査やドキュメント検索はGeminiに依頼する。
コードレビューは自分（Claude）で行う。
```

### Step 3: エージェントを起動

```bash
# Terminal 1
synapse codex

# Terminal 2
synapse claude
```

Claudeが自動的にルールに従ってタスクを振り分けます。

---

## @agent パターンでの応答制御

委任時に応答を待つかどうかを制御できます：

```text
@codex --response ファイルを修正して     # 結果を待って受け取る
@gemini --no-response 調査を開始して      # 転送のみ（結果を待たない）
@codex ビルドして                          # a2a.flow 設定に従う
```

### Flow 設定との組み合わせ

| `a2a.flow` | フラグなし | `--response` | `--no-response` |
|------------|-----------|--------------|-----------------|
| `roundtrip` | 待つ | 待つ | 待たない |
| `oneway` | 待たない | 待つ | 待たない |
| `auto` | 待つ（デフォルト） | 待つ | 待たない |

---

## 設定ファイル

### 有効化設定 (settings.json)

`.synapse/settings.json`:

```json
{
  "delegation": {
    "enabled": true
  }
}
```

**検索順序（優先度高い順）:**
1. `.synapse/settings.local.json`（プロジェクトローカル）
2. `.synapse/settings.json`（プロジェクト）
3. `~/.synapse/settings.json`（ユーザー）

### ルール定義 (delegate.md)

`.synapse/delegate.md`:

```markdown
# My Delegation Rules

コーディングはCodexに任せる。
リサーチはGeminiに依頼する。
```

**検索順序:**
1. `.synapse/delegate.md`（プロジェクト）
2. `~/.synapse/delegate.md`（ユーザー）

---

## 効果的なルールの書き方

### 具体的に書く

```markdown
# Good
ファイルの編集やリファクタリングはCodexに依頼する

# Bad
難しいことはCodexに依頼する
```

### 境界を明確に

```markdown
# Good
新規ファイル作成はCodexに、既存ファイルの分析は自分で行う

# Bad
コーディングはCodexに（曖昧）
```

### フォールバックを含める

```markdown
コーディングはCodexに
リサーチはGeminiに
上記に該当しない場合は自分で処理する
```

### 応答制御の指示を含める

```markdown
# 結果の統合が必要な場合
コーディングはCodexに依頼し、結果を待って確認する（--response）

# 並列実行する場合
複数の調査タスクはGeminiに順次転送する（--no-response）
```

---

## 動作の仕組み

1. **起動時**: Synapseがsettings.jsonとdelegate.mdを読み込む
2. **ルール注入**: `delegation.enabled: true` の場合、委任ルールがClaudeの初期インストラクションに追加される
3. **タスク分析**: Claudeが受け取ったタスクをルールと照合
4. **委任実行**: ルールにマッチしたら `@agent` パターンで転送
5. **応答制御**: `a2a.flow` 設定または `--response`/`--no-response` フラグに従う

---

## トラブルシューティング

### 委任が動作しない

1. 設定を確認:
   ```bash
   cat .synapse/settings.json | grep -A2 delegation
   ```

2. delegate.md の存在確認:
   ```bash
   cat .synapse/delegate.md
   ```

3. 対象エージェントの起動確認:
   ```bash
   synapse list
   ```

### ルールが期待通りにマッチしない

- ルールをより具体的に記述
- delegate.md に明示的な例を追加
- タスクカテゴリを明確化

### 応答が返ってこない

- `a2a.flow` 設定を確認（`oneway` だと結果を待たない）
- `--response` フラグを明示的に使用

---

## 設定例

### 開発チーム構成

`.synapse/settings.json`:
```json
{
  "a2a": {
    "flow": "auto"
  },
  "delegation": {
    "enabled": true
  }
}
```

`.synapse/delegate.md`:
```markdown
# Development Delegation

設計とコードレビューは自分で行う。
実装（ファイル編集、新規作成）はCodexに依頼する（--response で結果を確認）。
技術調査やドキュメント作成はGeminiに依頼する。
```

### リサーチ特化

```markdown
# Research Delegation

Web検索や調査タスクはGeminiに転送する。
複数の調査を並列で実行する場合は --no-response を使う。
それ以外は自分で処理する。
```

### コーディング委任

```markdown
# Coding Delegation

コーディング作業（Edit, Write, Bash）はすべてCodexに任せる。
結果を確認してからユーザーに報告する（--response を使用）。
```
