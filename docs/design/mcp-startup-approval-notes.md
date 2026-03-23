# MCP Startup Approval Notes

初回起動時の bootstrap と approval の検討メモ。

> Status: implemented
>
> 現在の実装では、`resume` は従来通り初期送信と approval をスキップし、
> MCP bootstrap 検出時は full instructions の代わりに最小 PTY bootstrap を送り、
> approval も維持する。

## 現状

- `--resume` 系では初期インストラクションを送らず、approval も出さない
- Synapse MCP bootstrap 設定が検出されると、full initial instructions の代わりに最小 PTY MCP bootstrap を送る
- approval prompt は `skip_initial_instructions` が `False` の場合に表示される

実装上の意味:

- `resume` は「以前承認済みで、再送もしない」ので現状仕様は妥当
- MCP 検出時は「bootstrap が不要」ではなく、「長い初期インストラクションを PTY に流し込まない」だけと考えるべき
- そのため、MCP 検出時に approval ごと消えないようにする

## 問題

今回の議論で確認できた点は次の通り。

1. MCP bootstrap でも、初回にまったく何も送らないのは不自然
2. 少なくとも最小 bootstrap は必要
3. その bootstrap を PTY に流すなら、approval の対象から外す理由は薄い
4. `resume` は例外で、従来通り approval 不要のままでよい

## 望ましい方向

`resume` と `MCP bootstrap` を同じ `skip_initial_instructions` に畳み込まない。

分けるべき責務:

- `resume`
  - 初期 bootstrap を送らない
  - approval も不要
- `MCP bootstrap`
  - 長い full instructions は送らない
  - 代わりに最小 bootstrap を送る
  - approval は維持する

## 最小 bootstrap のイメージ

初回に PTY へ送る内容は、full instructions ではなく導線に絞る。

- 自分の agent ID
- 読むべき MCP resource
- 最初に呼ぶべき MCP tool

たとえば:

```text
[SYNAPSE MCP BOOTSTRAP]
You are synapse-codex-8120.
Read synapse://instructions/default.
Then call bootstrap_agent().
Follow the returned instruction_resources before starting work.
```

## テストで固定したい仕様

1. `resume` は引き続き初期 bootstrap も approval もスキップする
2. MCP 検出時は `skip_initial_instructions=True` にしない
3. MCP 検出時でも `approvalMode=required` なら approval prompt を出す
4. MCP 検出時は full instructions ではなく最小 bootstrap を送る

## 備考

このメモの内容に沿って、`resume` と `MCP bootstrap` の起動分岐を分離した。
