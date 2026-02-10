# Synapse A2A 新機能サマリー (v0.4.0)

このブランチ（`docs/agent-teams-adoption-spec`）で実装された、Claude Code の「Agent Teams」機能をベースとした新しい協調機能（魔法）のまとめです。

---

## 1. エージェント協調機能 (Agent Teams B1-B6)

### B1: 共有タスクボード (`synapse tasks`)
プロジェクト全体で共有されるタスク管理システムです。
- **SQLite バックエンド:** `.synapse/task_board.db` で安全に管理。
- **依存関係管理:** `blocked_by` により、前のタスクが終わるまで着手できない制御が可能。
- **原子的クレーム:** 複数のエージェントが同時に同じタスクを開始することを防止。
- **CLI/API:** `list`, `create`, `assign`, `complete` コマンドおよびREST APIを提供。

### B2: Quality Gates (フック機構)
エージェントのステータス遷移時に自動でチェックを実行します。
- **`on_task_completed`:** 作業完了時にテスト（`pytest` など）を実行し、失敗した場合は完了を拒否（修正を要求）。
- **`on_idle`:** アイドル時に次のタスクを自動で探しにいくなどの連携が可能。
- **環境変数:** フック内でエージェント名やステータスを参照可能。

### B3: プラン承認ワークフロー (`synapse approve/reject`)
実装前にエージェントのアプローチをレビューする仕組みです。
- **プランモード:** メッセージに `plan_mode: true` を含めることで、エージェントに「実装せずプランのみ作成」を指示。
- **人間による承認:** `synapse approve` で実装を許可し、`reject` で理由を添えて修正を依頼可能。

### B4: グレースフルシャットダウン
エージェントに安全な終了を促す仕組みです。
- **シャットダウン要求:** 即座に SIGKILL するのではなく、まず A2A メッセージで終了を依頼。
- **猶予時間:** エージェントが状態保存や報告を行うための時間（デフォルト30秒）を確保。
- **新ステータス:** `SHUTTING_DOWN` 状態を導入。

### B5: コーディネーター / デリゲートモード
役割分担を明確にする特別な動作モードです。
- **`--delegate-mode`:** コーディネーターとして起動し、自身でのファイル編集（ロック取得）を制限。
- **オーケストレーション:** `synapse send` を活用したタスクの分解と委譲に専念。

### B6: オートスポーン・画面分割 (`synapse team start`)
マルチエージェント環境を一瞬でセットアップします。
- **自動ペイン分割:** `tmux`, `iTerm2`, `Terminal.app` で画面を分割してエージェントを起動。
- **レイアウト指定:** `split`, `horizontal`, `vertical` などの配置を選択可能。

---

## 2. セキュリティと堅牢性

### シェルインジェクション対策
- `synapse/terminal_jump.py` において、`tmux` や `osascript`（AppleScript）を呼び出す際の引数を `shlex.quote()` で適切にエスケープ。
- 悪意あるエージェント名やコマンドによるOSコマンド注入を防止。

### テストスイートの拡充
- `test_task_board.py`
- `test_hooks.py`
- `test_plan_approval.py`
- `test_graceful_shutdown.py`
- `test_delegate_mode.py`
- `test_auto_spawn.py`
など、新機能の正常動作を保証する網羅的なテストを追加。

---

## 3. ドキュメントの更新
- **仕様書:** `docs/agent-teams-adoption-spec.md` で採用判断と設計詳細を記録。
- **更新履歴:** `CHANGELOG.md` に v0.4.0 の変更点を反映。
- **README:** 多言語対応（i18n）および `synapse reply --from` の記述を修正。

---
*提供: ずんだもん (synapse-codex-8120)*
*記録: フリーレン (synapse-gemini-8110)*
