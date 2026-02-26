# site-docs ページ一覧

このファイルは GitHub Pages サイト（`site-docs/`）の全ページとその役割を定義する。
`mkdocs.yml` の nav 構造に対応している。

## Home

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `index.md` | ランディングページ、プロジェクト概要、機能ハイライト | 新機能追加、README.md 変更 |

## Getting Started

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `getting-started/installation.md` | インストール手順、前提条件 | `pyproject.toml` 依存関係変更、インストール方法変更 |
| `getting-started/quickstart.md` | 初回ユーザー向けクイックスタート | 基本コマンド変更、セットアップ手順変更 |
| `getting-started/setup.md` | インタラクティブセットアップ | `synapse init` / 初回セットアップ変更 |

## Core Concepts

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `concepts/architecture.md` | システムアーキテクチャ、コンポーネント構成 | `synapse/` モジュール構成変更、新コンポーネント追加 |
| `concepts/a2a-protocol.md` | A2A プロトコル設計思想、準拠性 | `a2a_compat.py` 変更、A2A 仕様対応変更 |
| `concepts/profiles.md` | エージェントプロファイルの概念説明 | `synapse/profiles/*.yaml` 変更、新エージェント追加 |
| `concepts/philosophy.md` | プロジェクト哲学・設計原則 | 設計方針の変更 |

## User Guide

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `guide/agent-management.md` | エージェント起動・停止・名前付け・監視 | `cli.py` 変更、`commands/list.py` 変更、エージェント管理コマンド変更 |
| `guide/communication.md` | メッセージ送受信、ブロードキャスト、返信 | `synapse send/reply/broadcast` 変更、通信プロトコル変更 |
| `guide/agent-teams.md` | チーム機能（B1-B6）、delegate mode | `task_board.py`, `hooks.py`, `approval.py`, `spawn.py` 変更 |
| `guide/task-board.md` | 共有タスクボード | `task_board.py` 変更、タスク CLI 変更 |
| `guide/file-safety.md` | ファイル競合防止機能 | `file_safety.py` 変更、`docs/file-safety.md` 変更 |
| `guide/skills.md` | スキル管理（発見・デプロイ・作成） | `skills.py` 変更、`commands/skill_manager.py` 変更 |
| `guide/history.md` | タスク履歴、トレース機能 | `history.py` 変更、履歴 CLI 変更 |
| `guide/settings.md` | 設定ガイド（`.synapse/settings.json`） | 設定項目追加・変更、テンプレート変更 |

## Reference

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `reference/cli.md` | CLI コマンド完全リファレンス | `cli.py` 変更、`commands/*.py` 変更、新コマンド追加 |
| `reference/api.md` | API エンドポイント完全リファレンス | `server.py` 変更、`a2a_compat.py` 変更、新エンドポイント追加 |
| `reference/configuration.md` | 設定リファレンス（環境変数・設定ファイル） | 設定項目追加、`paths.py` 変更、`config.py` 変更 |
| `reference/profiles-yaml.md` | プロファイル YAML スキーマ | `profiles/*.yaml` 変更、idle detection 変更 |
| `reference/ports.md` | ポート範囲リファレンス | プロファイルのポート範囲変更、新エージェント追加 |

## Advanced

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `advanced/external-agents.md` | 外部エージェント連携 | `docs/external-agent-connectivity.md` 変更、外部連携機能追加 |
| `advanced/authentication.md` | 認証・API キー管理 | `synapse auth` 変更、認証方式変更 |
| `advanced/webhooks.md` | Webhook 機能 | Webhook エンドポイント変更、`guides/enterprise.md` 変更 |
| `advanced/worktree.md` | Git Worktree 分離 | `docs/claude-code-worktree.md` 変更、worktree 機能変更 |
| `advanced/enterprise.md` | エンタープライズ機能概要 | `guides/enterprise.md` 変更、エンタープライズ機能追加 |

## Standalone

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `troubleshooting.md` | トラブルシューティング | 新しい問題・解決策の発見 |
| `changelog.md` | リリースノート・変更履歴 | 各リリース時、`CHANGELOG.md` 変更 |

## ページ数サマリー

| セクション | ページ数 |
|-----------|---------|
| Home | 1 |
| Getting Started | 3 |
| Core Concepts | 4 |
| User Guide | 8 |
| Reference | 5 |
| Advanced | 5 |
| Standalone | 2 |
| **合計** | **28** |

## MkDocs 設定

- **設定ファイル**: `mkdocs.yml`（プロジェクトルート）
- **docs_dir**: `site-docs`
- **テーマ**: Material for MkDocs
- **ビルドコマンド**: `uv run mkdocs build --strict`
- **ローカルプレビュー**: `uv run mkdocs serve`
