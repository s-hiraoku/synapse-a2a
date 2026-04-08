# Bug: `synapse workflow run` の `response_mode: wait` がタスク完了を待たない

## 概要

`synapse workflow run` で `response_mode: wait` のステップを実行すると、タスク完了を待たずに次のステップに進んでしまう。これにより、前のステップがまだ処理中のエージェントに次のメッセージを送ろうとして `local send failed` で失敗する。

## 再現手順

```bash
synapse workflow run post-impl
```

```
Running workflow 'post-impl' (5 steps)...
  Step 1/5: → claude (wait)
  ...
  Status: working
  Step 2/5: → claude (wait)
  Waiting for synapse-claude-8106 to become READY... (0s)
  Error sending message: local send failed
  Step 2 failed (exit 1).
```

Step 1 のタスクは実際には5分以上かかるが、ポーリングせず即座に Step 2 に進む。

## 原因

`a2a_client.py` の `send_to_local()` (line 464) で wait ポーリングが実行される条件:

```python
if wait_for_completion and response_mode == "wait" and sender_task_id:
```

**3つ目の条件 `sender_task_id` が None になるため、ポーリングがスキップされる。**

### なぜ sender_task_id が None になるか

`sender_task_id` は sender のサーバーにタスクを作成して取得する (line 316-363)。しかし:

1. `synapse workflow run` は subprocess で `synapse send` を実行する
2. `synapse send` の CLI プロセスには **A2A サーバーがない**（PTY ラップされたエージェントではない）
3. `sender_info` に `sender_endpoint` がないため、sender 側にタスクが作れない
4. `sender_task_id` が `None` のまま
5. ポーリング条件が false → タスク完了を待たずに return

### 影響範囲

- `synapse workflow run` の **全ての `response_mode: wait` ステップ**が影響を受ける
- エージェント間の `synapse send --wait` は sender 側にもサーバーがあるため正常に動作する
- Canvas からの workflow 実行も sender_endpoint を持つため正常

## 考えられる修正案

### 案 A: sender_task_id なしでもターゲットのタスクをポーリングする

sender にサーバーがない場合、ターゲット側のタスク ID (`task.id`) を使ってターゲットサーバーを直接ポーリングする。

```python
if wait_for_completion and response_mode == "wait":
    if sender_task_id and sender_endpoint:
        # 既存: sender サーバーをポーリング
        completed_task = self._wait_for_local_completion(sender_endpoint, sender_task_id, timeout)
    else:
        # フォールバック: ターゲットサーバーのタスクをポーリング
        completed_task = self._wait_for_local_completion(endpoint, task.id, timeout)
```

**メリット:** 最小限の変更。既存の sender ベースのフローは壊さない。
**リスク:** ターゲット側のタスクステータスが reply 後に更新されない場合、永遠にポーリングする可能性。

### 案 B: workflow_runner.py で独自にポーリングする

ワークフローランナー自体がタスク完了を HTTP でポーリングする。`synapse send` の wait 機能に依存しない。

```python
# workflow_runner.py
task = send_step(step)  # synapse send --notify で送信
poll_until_complete(task.endpoint, task.id, timeout=step.timeout)
```

**メリット:** ワークフローランナーが完全に制御できる。
**リスク:** 既存の workflow_runner.py の async 実行パスとの整合性が必要。

## 関連

- #512 (Agent SDK × synapse-a2a 統合検討) — Workflow 実行バックエンドの課題として記載済み
- timeout フィールド追加: `synapse/workflow.py` の `WorkflowStep.timeout` (同ブランチで実装済み)
