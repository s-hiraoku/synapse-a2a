# A2A 関連タスク

このディレクトリには、Synapse A2A の A2A プロトコル対応に関するタスクと改善計画を管理します。

## ファイル一覧

| ファイル | 説明 |
|----------|------|
| `wrapper-improvements.md` | ラッパー機能の改善ロードマップ |

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
