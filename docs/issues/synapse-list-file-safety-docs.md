# Issue: synapse list と file-safety locks の関係性がヘルプで説明されていない

## 概要

`synapse list` コマンドの EDITING_FILE カラムと `synapse file-safety locks` コマンドの関係性がドキュメントやヘルプに記載されていないため、ユーザーが期待する動作と実際の動作にギャップが生じている。

## 現状の問題

### 1. EDITING_FILE カラムの表示条件が分かりにくい

- `synapse list` の EDITING_FILE カラムは `SYNAPSE_FILE_SAFETY_ENABLED=true` の時のみ表示される
- デフォルトでは `true` だが、これが明示的に説明されていない
- カラムが非表示の場合、なぜ非表示なのかの説明がない

### 2. ヘルプの情報不足

現状の `--help` では:
- コマンドの目的と操作方法は書いてある
- しかし「ロックと list 表示の関係」のような期待値や動作の仕組みまでは書いていない

### 3. ユーザーからのフィードバック

> この環境の synapse list（v0.3.17）の表示仕様だと、少なくとも今出ている列は CURRENT/WORKING_DIR までで、ファイルロックを EDITING_FILE として表示する挙動は確認できません（ロックは synapse file-safety locks 側の責務）。
> なので「EDITING_FILEに出るはず」は、別バージョン/別実装（または別UI）前提の可能性が高いです。
> --help については、コマンドの目的と操作は書いてある一方で「ロックと list 表示の関係」みたいな期待値までは書いていないので、確かに十分に親切とは言いづらいです。

## 提案する改善

### Option A: ヘルプの拡充

`synapse list --help` に以下の情報を追加:

```
EDITING_FILE Column:
  This column shows the file currently being edited by each agent.
  Requires: SYNAPSE_FILE_SAFETY_ENABLED=true (default)

  To manually manage locks:
    synapse file-safety locks        # List all active locks
    synapse file-safety lock <file>  # Acquire a lock
    synapse file-safety unlock       # Release a lock
```

### Option B: カラム非表示時のヒント表示

EDITING_FILE カラムが非表示の場合、フッターにヒントを表示:

```
Tip: Set SYNAPSE_FILE_SAFETY_ENABLED=true to show EDITING_FILE column
```

### Option C: synapse config への説明追加

`synapse config` の list.columns 設定画面で、各カラムの説明を表示する。

## 関連ファイル

- `synapse/commands/list.py` - list コマンドの実装
- `synapse/commands/renderers/rich_renderer.py` - カラム定義
- `synapse/cli.py` - file-safety コマンドのヘルプ

## バージョン

- v0.3.17

## Labels

- documentation
- enhancement
- good first issue
