# Development Documents

This directory contains internal development documents and drafts.

For user guides, see the [`/guides`](../guides/) directory.

## Contents

## Operational Notes

- Save-on-exit prompt for interactive agents:
  `Save this agent definition for reuse? [y/N]:`
- Displayed only for interactive `synapse <profile>` exits with a configured name.
- Not displayed in `--headless`, non-TTY sessions, or when stopping via
  `synapse stop ...` / `synapse kill ...`.

### プロジェクト哲学

- `project-philosophy.md` - **Synapse A2A プロジェクトの哲学と設計原則**
  - A2A プロトコル完全準拠（A2A-First）の考え方
  - 設計判断の基準
  - ロードマップとの整合性

### 設計ドキュメント

- `design/canvas.md` - **Synapse Canvas 設計ドキュメント**
  - 共有ビジュアル出力サーフェス（Canvas Message Protocol）
  - 26 コンテンツフォーマット + 6 テンプレート（briefing, comparison, dashboard, plan, slides, steps）
  - ブラウザ UI（SPA ルーティング、SSE リアルタイム更新、キャッシュバスティング）
  - CLI コマンドリファレンス（`synapse canvas serve/mermaid/markdown/briefing/...`）

- `a2a-design-rationale.md` - **A2A プロトコル準拠性と設計思想の分析**
  - Synapse A2A の PTY ラッピングアプローチの正当性
  - Google A2A 公式仕様との比較
  - Opaque 原則への適合性

- `agent-card-context.md` - **Agent Card Context 拡張（x-synapse-context）**
  - A2A 準拠のシステムコンテキスト伝達
  - PTY 出力を最小限に抑える設計
  - ブートストラップメッセージの仕組み

### ビジョンドキュメント

- `external-agent-connectivity.md` - **外部A2Aエージェント連携ビジョン**
  - SaaS/クラウドサービス連携のユースケース
  - B2B、IoT、専門AIモデル連携の可能性
  - エコシステム成熟の時間軸予測
  - Synapse A2A の戦略的ポジション

### 仕様ドキュメント

- `universal-agent-communication-spec.md` - Universal agent communication specification
- `input-routing-spec.md` - Input routing specification
- `agent-teams-adoption-spec.md` - **Agent Teams 機能採用仕様書**
  - Claude Code Agent Teams の分析と Synapse A2A への採用設計
  - B1-B6 の各機能仕様（Shared Task Board, Quality Gates, Plan Approval 等）
- `tornado-adoption-spec.md` - **tornado 機能採用仕様書**
  - [mizchi/tornado](https://github.com/mizchi/tornado) の設計分析と採用判断
  - TaskBoard 拡張: `fail_task()`, `reopen_task()`, `priority` カラム
  - Coordinator + TaskBoard による Kanban ワークフローパターン（委任は TaskBoard 登録が必須）
  - Soft Interrupt: `synapse interrupt` CLI コマンド（`send -p 4 --silent` の簡易版）
  - Token/Cost Tracking: `synapse/token_parser.py` スケルトン（`TokenUsage` + `parse_tokens()` レジストリ）

### リリース

- `release.md` - **リリースガイド**
  - PyPIへのリリース手順
  - GitHub Actions による自動 Publish
  - バージョニングとトラブルシューティング

### 実装ドキュメント

- `admin-command-center.md` - **Canvas Agent Control (Admin Command Center) ガイド**
  - ブラウザからエージェントにコマンド送信・レスポンス表示
  - Reply ベース方式（`synapse reply` を活用、PTY 出力は使わない）
  - API リファレンス、UI コンポーネント、設計判断

- `file-safety.md` - **File Safety（ファイル競合防止）ユーザーガイド**
  - ファイルロックと変更追跡でマルチエージェント競合を防止
  - CLI コマンドと Python API の詳細リファレンス
  - ワークフロー例とトラブルシューティング

### コラボレーション設計

- **プロアクティブコラボレーション** — エージェントがタスク開始前にコラボレーションの機会を自動評価
  - コラボレーション判断フレームワーク（自分で実行/委任/ヘルプ要請/進捗報告/知識共有）
  - クロスモデル生成推奨（異なるモデルタイプで品質向上 + レート制限分散）
  - ワーカーエージェントの自律性（マネージャーだけでなくワーカーも spawn/委任可能）
  - 必須クリーンアップ（spawn したエージェントは完了後に必ず kill）
  - 設定ファイル: `.synapse/default.md`, `synapse/templates/.synapse/default.md`
  - スキル: `plugins/synapse-a2a/skills/synapse-a2a/SKILL.md`, `plugins/synapse-a2a/skills/synapse-manager/SKILL.md`

- セッション履歴機能 Phase 2 は PR #34 で実装済み（キーワード検索、統計情報、エクスポート、クリーンアップ機能）

### ターミナル・ペイン管理

- `spawn-zone-tiling.md` - **スポーンゾーンタイリング仕様**
  - `synapse spawn` のペイン自動タイル配置
  - スポーンゾーンの概念と `SYNAPSE_SPAWN_PANES` 環境変数
  - tmux / iTerm2 / Ghostty / zellij 各ターミナルの実装詳細

### 開発ツール

- `claude-code-worktree.md` - **Claude Code ワークツリー機能の仕組み**
  - Git worktree を活用した分離作業環境の内部構造
  - ディレクトリ構造・ライフサイクル・命名規則の解説
  - マルチエージェント並行作業での活用と Synapse A2A への統合構想

### アセット

- `Gemini_Generated_Image_*.png` - Design assets
