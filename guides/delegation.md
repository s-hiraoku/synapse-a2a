# Delegation Guide

エージェント間の自動タスク委任機能のガイドです。

## 概要

Delegation（委任）は、Claudeが受け取ったタスクを自動的に他のエージェント（Codex, Gemini）に振り分ける機能です。

**設定の2つの要素:**

| 設定 | 保存場所 | 役割 |
|------|----------|------|
| **モード** | `.synapse/settings.json` | 結果の扱い方（orchestrator/passthrough/off） |
| **ルール** | `.synapse/delegate.md` | 誰に何を任せるか（自然言語で記述） |

> **重要**: モードが `orchestrator` または `passthrough` の場合のみ、`delegate.md` のルールが適用されます。

---

## モードとルールの関係

```
┌─────────────────────────────────────────────────────────────────┐
│                    delegate.md (ルール)                          │
│  「コーディングはCodexに、リサーチはGeminiに」                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
              settings.json の mode で動作が決まる
                              ↓
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
   orchestrator          passthrough              off
   (結果を統合)          (そのまま転送)        (ルール無視)
```

### モード比較

| モード | delegate.md | 動作 |
|--------|-------------|------|
| `orchestrator` | ✅ 参照する | Claudeが結果を確認・統合して報告 |
| `passthrough` | ✅ 参照する | 結果をそのまま転送 |
| `off` | ❌ 参照しない | 自動委任なし（デフォルト） |

---

## orchestrator vs passthrough

### orchestrator モード（推奨）

Claudeが結果を**確認・統合**してからユーザーに報告します。

```
ユーザー: 「この関数を修正して」
    ↓
Claude: タスクを分析 → delegate.md のルールに従ってCodexに委任
    ↓
Codex: 修正を実行
    ↓
Claude: 結果を確認・統合して報告  ← Claudeが加工
    ↓
ユーザー: Claudeからの統合レポートを受け取る
```

**向いているケース:**
- 複雑なタスク（結果の確認が必要）
- マルチステップのワークフロー
- 結果をまとめて報告してほしい場合

### passthrough モード

結果を**そのまま**ユーザーに返します。

```
ユーザー: 「この関数を修正して」
    ↓
Claude: delegate.md のルールに従ってCodexに転送
    ↓
Codex: 修正を実行
    ↓
ユーザー: Codexの出力をそのまま受け取る  ← 加工なし
```

**向いているケース:**
- シンプルな転送
- Codex/Geminiの生の出力が欲しい場合
- 高スループットが必要な場合

---

## クイックスタート

### Step 1: モードを設定

```bash
synapse delegate set orchestrator
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

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `synapse delegate` | 現在の設定を表示 |
| `synapse delegate status` | 同上 |
| `synapse delegate set <mode>` | モードを設定 |
| `synapse delegate off` | 委任を無効化 |

### 例

```bash
# 現在の設定を確認
synapse delegate

# orchestrator モードに設定（プロジェクト）
synapse delegate set orchestrator

# orchestrator モードに設定（ユーザー全体）
synapse delegate set orchestrator --scope user

# 委任を無効化
synapse delegate off
```

---

## 設定ファイル

### モード設定 (settings.json)

`.synapse/settings.json`:

```json
{
  "delegation": {
    "mode": "orchestrator"
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

---

## 動作の仕組み

1. **起動時**: Synapseがsettings.jsonとdelegate.mdを読み込む
2. **ルール注入**: 委任ルールがClaudeの初期インストラクションに追加される
3. **タスク分析**: Claudeが受け取ったタスクをルールと照合
4. **委任実行**: ルールにマッチしたら `@agent` パターンで転送
5. **結果処理**:
   - orchestrator: 結果を統合して報告
   - passthrough: 結果をそのまま返す

---

## ステータス表示

```bash
synapse delegate
```

出力例:
```
=== Delegation Configuration ===
Mode: orchestrator
Instructions: .synapse/delegate.md
Status: active

Rules:
  # Delegation Rules
  コーディングはCodexに任せる
  リサーチはGeminiに依頼する
================================
```

---

## トラブルシューティング

### 委任が動作しない

1. モードを確認:
   ```bash
   synapse delegate status
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

---

## 設定例

### 開発チーム構成

`.synapse/settings.json`:
```json
{
  "delegation": {
    "mode": "orchestrator"
  }
}
```

`.synapse/delegate.md`:
```markdown
# Development Delegation

設計とコードレビューは自分で行う。
実装（ファイル編集、新規作成）はCodexに依頼する。
技術調査やドキュメント作成はGeminiに依頼する。
```

### リサーチ特化

```markdown
# Research Delegation

Web検索や調査タスクはGeminiに転送する。
それ以外は自分で処理する。
```

### コーディング委任

```markdown
# Coding Delegation

コーディング作業（Edit, Write, Bash）はすべてCodexに任せる。
結果を確認してからユーザーに報告する。
```
