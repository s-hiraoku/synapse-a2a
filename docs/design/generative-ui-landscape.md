# Generative UI Landscape (2025-2026)

LLM が「テキストではなく UI」を出力する技術の現状調査。
Synapse Canvas の設計にあたり、関連技術を整理した。

---

## 背景：なぜ Generative UI なのか

現在の LLM の主な出力形式は Markdown ベースのテキスト。しかし、AI モデルがコンテンツだけでなくユーザー体験全体を生成するという「Generative UI」は、従来の静的な UI を超える新しいモダリティとして注目されている。たとえば「天気を教えて」と聞いたら、テキストではなくインタラクティブな天気カードが返ってくるようなイメージ。

---

## 技術アプローチの分類

現在の主なアプローチは大きく 3 つに分類できる。

| アプローチ | 概要 | 代表 |
|---|---|---|
| コード生成型 | LLM が HTML/CSS/JS を直接生成し、ブラウザでレンダリング。最も自由度が高いが、生成時間やバグのリスクがある | Google Gemini 3 |
| 宣言的仕様型 | LLM が JSON/XML で UI の構造を宣言し、クライアント側のレンダラーがコンポーネントにマッピング。安定性は高いが表現の幅は限定的 | A2UI, Thesys C1 |
| Tool Call マッピング型 | LLM の Tool Call 結果を開発者が事前定義した React コンポーネントにマッピング。開発者の制御が強いが、事前定義が必要 | Vercel AI SDK |

---

## 各技術の詳細

### 1. Google Gemini 3 Generative UI

最も大規模に実用化を進めているのが Google。2025 年 11 月、Gemini 3 のローンチとともに Generative UI の実装が Gemini アプリと Google 検索の AI Mode に展開された。

**アプローチ**: LLM に HTML/CSS/JS を直接生成させる。

**構成要素**:
- サーバーが画像生成や Web 検索などのツールアクセスを提供
- 詳細なシステムプロンプトでフォーマットやツール仕様を指定
- ポストプロセッサで共通の問題を修正

**展開例**:
- Gemini アプリ内「Dynamic View」: Gemini 3 がコーディングしてカスタム UI を生成
- Gemini アプリ内「Visual Layout」: マガジン風のレイアウトにスライダーやフィルターを追加
- AI Mode: 三体問題の物理シミュレーション、ローン計算ツール等をリアルタイム生成

**評価**: 生成速度を考慮しなければ、Generative UI の出力は標準的な Markdown 出力と比べて人間の評価者に圧倒的に好まれ、人間の専門家が作成したものと 44% のケースで同等と評価された。

### 2. Google A2UI (Agent-to-User Interface)

2025 年 12 月、Google が A2UI をオープンソースプロジェクトとして公開。エージェントが UI ウィジェットを生成し、フロントエンドに送信するための宣言的な仕様。

**アプローチ**: コード生成ではなく UI の宣言的記述。

**特徴**:
- ウィジェットのカタログから UI を構成
- adjacency list model（フラットなコンポーネント定義で LLM が生成しやすい）
- Surface 概念（独立した UI 領域を複数管理）
- A2A プロトコルの Extension として DataPart に埋め込み可能
- バージョン: v0.8 (stable) → v0.9 (draft)

**参考**:
- https://a2ui.org/
- https://a2ui.org/specification/v0.8-a2ui/
- https://github.com/google/A2UI

### 3. AG-UI (Agent-User Interaction Protocol)

CopilotKit が中心となって開発。エージェントバックエンドとユーザー向けアプリケーションの間の双方向ランタイム接続を提供するプロトコル。

**A2UI との関係**: AG-UI が配信メカニズム（トランスポート層）、A2UI が UI の定義（ペイロード）という棲み分け。

**イベントタイプ**:
- テキストメッセージのストリーミング
- ツール呼び出し
- 状態差分（STATE_DELTA）の送信
- INTERRUPT イベントによるヒューマン・イン・ザ・ループ

**統合**: Microsoft Agent Framework、LangGraph など主要フレームワークとの統合が進行中。

**参考**:
- https://www.copilotkit.ai/blog/build-with-googles-new-a2ui-spec-agent-user-interfaces-with-a2ui-ag-ui

### 4. MCP Apps

MCP の official extension (v1.1)。MCP サーバーが HTML バンドルを `ui://` リソースとして提供し、MCP クライアント（Claude Desktop 等）が sandboxed iframe で会話内に描画する。

**アプローチ**: HTML/CSS/JS で表現力無制限。postMessage による双方向通信。

**特徴**:
- ツールが `_meta.ui.resourceUri` で UI リソースを参照
- sandboxed iframe でセキュリティ担保
- 対応クライアント: Claude, Claude Desktop, VS Code Copilot, Goose, Postman
- フレームワーク自由（React, Vue, Svelte, vanilla JS）

**参考**:
- https://modelcontextprotocol.io/extensions/apps/overview
- https://github.com/modelcontextprotocol/ext-apps

### 5. Vercel AI SDK — Tool Call ベースの Generative UI

Vercel は AI SDK 3.0 の時点で Generative UI の概念を導入。React Server Components を活用して LLM のレスポンスをストリーミング React コンポーネントにマッピング。

**アプローチ**: LLM の Tool Call 結果を事前定義した React コンポーネントにマッピング。

**特徴**:
- Tool Call がトリガーとなり、ツール結果に応じてカスタムコンポーネントをレンダリング
- AI SDK 6 では Agent 抽象化が導入、同じツール定義がエージェントロジック・API レスポンス・UI コンポーネントすべてを型安全に駆動

### 6. Thesys C1

LLM の応答をプレーンテキストの代わりにフォーム、テーブル、チャート、レイアウトなどの構造化 UI コンポーネントとしてリアルタイム出力する API。

**アプローチ**: コード生成ではなく仕様ベース。

**特徴**:
- C1 API にプロンプトを送ると JSON/XML ベースの UI 仕様が返される
- React SDK がレンダリング
- OpenAI 互換エンドポイント（baseURL 差し替えで導入可能）

### 7. その他

- **fka.dev プロトタイプ**: LLM が利用可能な UI コンポーネント情報を受け取り、意図を認識して構造化 JSON として UI 仕様を生成。MCP サーバー連携も想定。
- **llm-ui (React ライブラリ)**: LLM のストリーミング出力からパターンを検出してブロック単位でレンダリング。コードブロックのシンタックスハイライト等を自動処理。

---

## Synapse Canvas との関係

### 採用判断

| 技術 | 判断 | 理由 |
|---|---|---|
| Gemini 3 Generative UI | 参考のみ | コード生成型のアプローチは `html` format として反映済み |
| A2UI | 見送り | CLI エージェントには adjacency list model が複雑すぎる。Canvas の目的と不一致 |
| AG-UI | 見送り | 双方向通信は今は不要（Canvas は表示専用）。将来インタラクション追加時に再検討 |
| MCP Apps | 見送り | PTY エージェントは MCP クライアントではない。sandboxed iframe の考え方は採用済み |
| Vercel AI SDK | 参考のみ | Tool Call → UI マッピングの考え方は format レジストリとして反映 |
| Thesys C1 | 参考のみ | 仕様ベースのアプローチは Canvas Message Protocol に類似 |

### Synapse Canvas の位置づけ

Synapse Canvas は上記 3 アプローチのハイブリッド:
- **宣言的仕様型**: `format + body` の JSON プロトコルで構造を宣言
- **コード生成型**: `html` format で自由な表現が可能（脱出ハッチ）
- **Tool Call マッピング型**: format レジストリで body → レンダラーをマッピング

ただし上記技術群との根本的な違いは、**Synapse のエージェントは CLI ツール（Claude Code, Codex 等）であり、LLM が直接 UI を生成するのではなく、エージェントが CLI コマンドで Canvas に投稿する**という点。エージェント側の使いやすさ（1 コマンドで投稿）を最優先にしている。

---

## 調査日

2026-03-07
