# A2A 関連タスク

このディレクトリには、Synapse A2A の A2A プロトコル対応に関するタスクと改善計画を管理します。

## 完了した機能

### Agent Card Context Extension (x-synapse-context)

**目的**: 初回インストラクションを PTY に表示せず、A2A プロトコル準拠の方法で渡す

**実装**:
- Agent Card に `x-synapse-context` 拡張フィールドを追加
- システムコンテキスト（ID、ルーティングルール、他エージェント）を埋め込み
- ブートストラップは最小限（curl コマンドのみ表示）
- AI エージェントは Agent Card を HTTP で取得

詳細: [docs/agent-card-context.md](../../docs/agent-card-context.md)

---

## ファイル一覧

| ファイル | 説明 |
|----------|------|
| `wrapper-improvements.md` | ラッパー機能の改善ロードマップ |
| `cost-analysis.md` | 難易度・コスト・ROI分析 |

### 設計書 (designs/)

| ファイル | 説明 |
|----------|------|
| `designs/phase1-design.md` | Phase 1: 基本機能強化（出力ルーティング、エラー検出、HTTPS） |
| `designs/phase2-design.md` | Phase 2: UX改善（SSE、構造化パーサー、input_required） |
| `designs/phase3-design.md` | Phase 3: エンタープライズ機能（認証、Push通知、gRPC） |

## 目標

**Synapse A2A を「A2A 非対応 CLI エージェントを A2A エコシステムに参加させるラッパー」として完成させる**

## 現状の課題（サマリー）

### 高優先度
1. CLI 出力からの `@agent` 自動ルーティング
2. エラー状態の検出と `failed` ステータス
3. HTTPS 対応

### 中優先度
4. SSE ストリーミング
5. 出力パーサー（構造化 Artifact）
6. `input_required` 状態の検出

### 低優先度
7. 認証/認可
8. Push Notifications
9. gRPC 対応

## 関連ドキュメント

- [A2A 設計思想と準拠性分析](../../docs/a2a-design-rationale.md)
- [Google A2A プロトコル互換性ガイド](../../guides/google-a2a-spec.md)
- [アーキテクチャ](../../guides/architecture.md)
