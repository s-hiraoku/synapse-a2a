# Spawn Zone Tiling 仕様

## 概要

`synapse spawn` で複数エージェントを順次起動する際のペイン配置戦略。
ユーザーの作業ペインを保護しながら、スポーンしたエージェント群を自動タイル配置する。

## 課題

従来の実装では `synapse spawn` が常に同一方向（水平）に分割していたため、
3つ以上のエージェントを起動すると細長いペインが並び、視認性が低下していた。
タイルレイアウトは `synapse team start`（一括起動）でのみ適用され、個別の `synapse spawn` 呼び出しでは機能しなかった。

現在は `synapse spawn` を個別に呼んだ場合でも、2つ目以降のエージェント起動時に自動的に `tmux select-layout tiled` が適用される（新しいCLIフラグは不要）。

## 設計: スポーンゾーン

### コンセプト

「スポーンゾーン」は、spawn されたエージェントが配置される領域。
ユーザーの作業ペインとは分離され、ゾーン内でのみタイリングが行われる。

### tmux 実装

#### 環境変数

- `SYNAPSE_SPAWN_PANES`: スポーンゾーンのペインID一覧（カンマ区切り）
  - 例: `%5,%8,%12`
  - `spawn_agent()` が自動管理（新規ペインIDを検出・追加）

#### フロー

1. **初回スポーン** (`SYNAPSE_SPAWN_PANES` 未設定):
   - 現在のペイン (`$TMUX_PANE`) を `-h` で水平分割
   - 新規ペインIDを `SYNAPSE_SPAWN_PANES` に記録

2. **2回目以降** (`SYNAPSE_SPAWN_PANES` 設定済み):
   - `tmux list-panes -F "#{pane_id} #{pane_width} #{pane_height}"` でペイン情報取得
   - `SYNAPSE_SPAWN_PANES` に含まれるペインのみをフィルタ
   - 最大面積（`width × height`）のペインを選択
   - アスペクト比で分割方向を決定:
     - `width >= height * 2` → `-h`（水平分割）
     - それ以外 → `-v`（垂直分割）
   - 新規ペインIDを `SYNAPSE_SPAWN_PANES` に追加
   - **自動タイル**: spawn 完了後、`_post_spawn_tile()` が `tmux select-layout tiled` を実行し、スポーンゾーン内のペインを均等配置する。これにより `synapse spawn` を個別に複数回呼んでも、`synapse team start` と同等のタイルレイアウトが自動適用される

#### ペインタイトル

作成された各ペインには `tmux select-pane -T` で自動的にタイトルが設定される。
`_pane_title()` ヘルパー（`terminal_jump.py`）が以下の形式で生成:

- `synapse(profile)` — 名前なし
- `synapse(profile:name)` — 名前付き

tmux の `pane-border-format` に `#{pane_title}` を含めることで、ペイン境界にエージェント名が表示される。

#### ペインID追跡

```python
# spawn.py
panes_before = _get_tmux_pane_ids()       # spawn 前のペインID集合
subprocess.run(...)                         # 実際のスポーン
new_pane = _get_new_tmux_pane_id(panes_before)  # 差分で新規ペインID検出
os.environ["SYNAPSE_SPAWN_PANES"] += f",{new_pane}"
```

### iTerm2 実装

セッション数に基づく交互分割:
- 1セッション（初回）→ `split vertically`（横並び）
- 2セッション以降 → 偶数: `split vertically`, 奇数: `split horizontally`

### Ghostty 実装

環境変数カウンタ (`SYNAPSE_GHOSTTY_PANE_COUNT`) に基づく交互分割:
- 初回 → `Cmd+D`（右分割）
- 2回目 → `Cmd+Shift+D`（下分割）

### zellij 実装

ペイン数に基づく交互分割:
- 奇数ペイン → `--direction right`
- 偶数ペイン → `--direction down`

## レイアウト例

```
4エージェント起動時:
┌──────────┬─────┬────┐
│          │ A1  │ A3 │
│  ユーザー  ├─────┼────┤
│          │ A2  │ A4 │
└──────────┴─────┴────┘
```

## 影響範囲

- `synapse/terminal_jump.py`: `_get_tmux_auto_split()` にスポーンゾーンフィルタ追加、`create_tmux_panes()` に初回/2回目以降の分岐、`_pane_title()` でペインタイトル自動設定
- `synapse/spawn.py`: `_get_tmux_pane_ids()`, `_get_new_tmux_pane_id()` 追加、スポーンゾーン追跡ロジック、`_post_spawn_tile()` で自動タイル適用、`spawn_agent()` が spawn 後に `_post_spawn_tile()` を呼び出し
- `tests/test_auto_layout.py`: 29テスト（全ターミナル対応）

## layout パラメータとの関係

| layout 値 | 動作 |
|-----------|------|
| `"auto"` | スポーンゾーンタイリング（`synapse spawn` のデフォルト） |
| `"horizontal"` | 常に水平分割（`synapse team start` のデフォルト） |
| `"vertical"` | 常に垂直分割 |
| `"split"` | 従来の分割 |
