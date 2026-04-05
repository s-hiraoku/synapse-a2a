# Claude Agent SDK × synapse-a2a 統合検討

## 概要

Claude Agent SDK（`claude_agent_sdk` / `@anthropic-ai/claude-code-sdk`）と synapse-a2a の統合可能性を調査・検討した結果をまとめる。将来、関連する要件が出てきた際の判断材料として残す。

## 背景

Agent SDK は Claude Code と同じエージェントループをプログラマティックに制御できる SDK。サブエージェント定義、セッション管理、Hook システム、MCP 統合などのマルチエージェント基盤を提供する。synapse-a2a との統合で新たな価値が出せるかを検討した。

## Agent SDK の主要機能

### サブエージェント定義
- `AgentDefinition` で description / tools / prompt / model / mcpServers を指定
- 親エージェントが Claude の判断でサブエージェントに自動デリゲート
- 各サブエージェントは独立コンテキストウィンドウ（親を汚染しない）

### セッション管理
- `session_id` で会話の復元（resume）・分岐（fork）が可能
- セッションはディスクに永続化される

### Hook システム
- `PreToolUse` / `PostToolUse` / `SubagentStart` / `SubagentStop` / `Notification` 等
- ライフサイクルイベントに外部からフック可能

### MCP 統合
- サブエージェント定義に `mcpServers` を渡せる
- 名前参照またはインライン定義でサーバーを指定

## 検討した統合方向（3パターン）

### Direction A: Agent SDK エージェントを A2A ノードとして公開

Agent SDK の `query()` を A2A の Task 実行エンドポイントとして公開。synapse の `MessageTransport` プロトコルの新実装（`AgentSDKTransport`）として差し込む。

```
[synapse send @sdk-agent "タスク"]
  → A2A Server (FastAPI)
    → Agent SDK query() + subagents
      → ResultMessage
    → synapse reply
```

**接続点:**
- `MessageTransport` プロトコル → `AgentSDKTransport` 実装
- `AgentDefinition` → Agent Card 変換
- Session ID ↔ A2A Task ID マッピング（TaskStore metadata）

### Direction B: Hook → A2A イベントブリッジ

Agent SDK の Hook callback から synapse の既存 API を呼ぶ。

- `SubagentStart` → `AgentRegistry.register()`
- `SubagentStop` → `_dispatch_task_event()`
- `PostToolUse` → `canvas_post()`

### Direction C: synapse MCP をサブエージェントに注入

既存の `SynapseMCPServer` を Agent SDK の `mcpServers` に渡し、サブエージェントが synapse ネットワーク内のエージェントを発見・通信できるようにする。

## 検討結果: リアルタイム協調での統合はメリットが薄い

### 理由: synapse-a2a が既に同等の機能を持つ

| やりたいこと | Agent SDK | synapse-a2a |
|---|---|---|
| タスク委譲 | `agents` パラメータ | `synapse spawn` + `synapse send` |
| コンテキスト分離 | サブエージェントごとに独立 | ワークツリー + 別プロセス |
| 結果統合 | 親が Agent ツール結果を受取 | `reply` で構造化レスポンス |
| ライフサイクル管理 | SDK が自動管理 | registry + hooks |
| 可視化 | 自前実装が必要 | Canvas が既存 |

### synapse-a2a が優位な点

- **ベンダー非依存**: Claude / Gemini / Codex / OpenCode / Copilot が参加可。Agent SDK は Claude 専用
- **P2P トポロジー**: 親エージェントがボトルネックにならない。Agent SDK は星型（親が全サブエージェントを制御）
- **既存エコシステム**: Canvas ダッシュボード、Registry、Hook 機構、MCP サーバーが成熟

### カスタムエージェント候補も検討したが…

PR レビュー・オーケストレーター、テスト障害分析、ドキュメント同期等を検討。いずれも `synapse spawn` + `synapse send` + `synapse team start` で実現可能であり、Agent SDK の独自価値が不明確。

## 有望な方向: Workflow 実行バックエンドとしての Agent SDK

### 現状の Workflow 実行の課題

現在の Workflow ランナー（`workflow_runner.py`）は以下の経路で実行:
1. CLI モード: `synapse send` を subprocess → PTY 注入
2. Canvas モード: HTTP `/tasks/send-priority` → PTY 注入

どちらも最終的に **PTY → ステータス推定（idle 検出）→ ポーリング** を通る。

### Agent SDK が解決できる課題

| 課題 | 現状 | Agent SDK バックエンド |
|---|---|---|
| ステップ完了判定 | PTY 出力からのステータス推定 | `ResultMessage.subtype === "success"` で確実判定 |
| エラーリカバリ | ステータス推定の誤判定リスク | `resume(session_id)` でセッション復元 |
| ステップ間データ受渡し | テキストベース（PTY 出力パース） | Artifact / JSON で構造化データ |
| Headless 実行 | PTY が必要（CI/CD で困難） | PTY 不要、API ネイティブ |
| 起動オーバーヘッド | spawn + PTY 確立 + ステータス安定待ち | `query()` 呼び出しのみ |
| 並列ステップ | 複数プロセス spawn が必要 | サブエージェントで in-process 並列 |

### 実装イメージ

```python
# workflow_runner.py に Agent SDK バックエンドを追加
class WorkflowStepExecutor(Protocol):
    async def execute(self, step: WorkflowStep) -> StepResult: ...

class PTYExecutor(WorkflowStepExecutor):
    """既存: synapse send 経由"""

class AgentSDKExecutor(WorkflowStepExecutor):
    """新規: Agent SDK query() 経由"""
    async def execute(self, step: WorkflowStep) -> StepResult:
        async for msg in query(prompt=step.message, options=...):
            if isinstance(msg, ResultMessage):
                return StepResult(
                    status="completed" if msg.subtype == "success" else "failed",
                    output=msg.result,
                    session_id=msg.session_id,  # リトライ用に保存
                )
```

Workflow YAML 側で `executor: agent-sdk` のようなフィールドを追加し、ステップごとにバックエンドを選択可能にする。

### この方向の注意点

- Agent SDK バックエンドは **Claude 専用**。Gemini / Codex ステップには使えない
- レート制限: サブエージェント並列実行でトークン消費が増える
- 既存の PTY バックエンドとの共存設計が必要

## 発展案: Workflow ランナー自体を Agent SDK 親エージェントにする

### 着想

Workflow の個々のステップを Agent SDK バックエンドで置き換えるだけでなく、**Workflow ランナー全体を Agent SDK の親エージェントとして実装**する案。各ステップをサブエージェントに委譲し、ステップ間の制御・エラーリカバリを LLM に任せる。

### 現状との比較

```
現状:
  Workflow YAML
    → workflow_runner.py (Python ループ)
      → synapse send (subprocess)
        → PTY エージェント
  制御: 逐次実行、固定ロジック

Agent SDK ランナー案:
  Workflow YAML
    → Agent SDK 親エージェント (Claude)
      ├─ サブエージェント A (step 1)
      ├─ サブエージェント B (step 2)
      └─ サブエージェント C (step 3)
  制御: Claude が依存関係を判断、並列化・リトライを自律決定
```

### メリット

1. **YAML 定義はそのまま活用可能** — パースして `AgentDefinition` に変換するだけ
2. **ステップ間依存の柔軟な制御** — 現在は sequential 固定だが、Claude が「step 1 と 2 は並列、step 3 は両方の結果待ち」と判断できる
3. **インテリジェントなエラーリカバリ** — 「step 2 が失敗 → step 1 の結果を踏まえて別アプローチで再試行」が可能
4. **Headless / CI 対応** — PTY 不要でパイプラインに組み込める

### 設計上の課題

**ベンダー横断ステップの扱い:**
Agent SDK サブエージェントは Claude のみ。Gemini / Codex への send ステップには synapse の既存インフラ（HTTP + PTY）が必要。

考えられる解決策:
- サブエージェントに synapse MCP を注入し、MCP ツール経由で `synapse send` を実行
- `kind: send` + 非 Claude ターゲットのステップは既存の HTTP 経路にフォールバック
- 親エージェントに synapse の `A2AClient` をカスタムツールとして提供

**コスト・レート制限:**
Workflow ランナー（親）+ 各ステップ（子）でトークン消費が N+1 倍になる。Max プランでもレート制限に注意。子エージェントに Haiku / Sonnet を使う、差分のみ渡す等の工夫が要る。

**制御の予測可能性:**
LLM にステップ制御を任せると、実行順序が非決定的になる可能性がある。重要なワークフローでは決定的実行が求められる場面もあるため、`strict_order: true` のようなオプションが必要。

### 実装イメージ

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

def workflow_to_agents(workflow: Workflow) -> dict[str, AgentDefinition]:
    """Workflow YAML のステップを AgentDefinition に変換"""
    agents = {}
    for i, step in enumerate(workflow.steps):
        if step.kind == "send":
            agents[f"step-{i}-{step.target}"] = AgentDefinition(
                description=f"Execute step {i}: send to {step.target}",
                prompt=step.message,
                tools=["Read", "Grep", "Glob", "Bash", "Edit", "Write"],
                model="sonnet",  # コスト最適化
            )
    return agents

async def run_workflow_via_sdk(workflow: Workflow):
    agents = workflow_to_agents(workflow)
    orchestrator_prompt = f"""
    以下の Workflow を実行してください。各ステップは対応するサブエージェントに委譲してください。
    依存関係がないステップは並列実行してください。

    Workflow: {workflow.name}
    Steps:
    {yaml.dump([s.model_dump() for s in workflow.steps])}
    """
    async for msg in query(
        prompt=orchestrator_prompt,
        options=ClaudeAgentOptions(
            agents=agents,
            allowed_tools=["Agent"],
        ),
    ):
        yield msg  # ストリーミングで進捗を返す
```

## 今後のアクション

- [ ] Workflow に executor 抽象層（Protocol）を導入する設計検討
- [ ] Agent SDK の `query()` を使った最小限の Workflow ステップ実行 PoC
- [ ] Session ID ↔ Workflow run_step の紐付けによるリトライ機構の設計
- [ ] CI/CD headless 実行のユースケース検証
- [ ] Workflow YAML → AgentDefinition 変換の設計（ベンダー横断ステップのフォールバック含む）
- [ ] 決定的実行 vs LLM 自律実行のモード切替設計

## 参考: Agent SDK が活きる synapse-a2a 外のユースケース

synapse-a2a との統合ではなく、Agent SDK 単体で活きる場面:
- SaaS バックエンドに Claude エージェントを組み込む
- CI/CD パイプラインで headless にエージェントを呼び出す
- Python/TypeScript アプリ内でのタスク自動化

## 関連リソース

- Agent SDK ドキュメント: https://docs.anthropic.com/en/docs/claude-code/sdk
- synapse-a2a Workflow: `synapse/workflow_runner.py`, `synapse/workflow.py`
- synapse-a2a Transport 抽象: `synapse/transport.py` (`MessageTransport` Protocol)
- synapse-a2a MCP: `synapse/mcp/server.py`
