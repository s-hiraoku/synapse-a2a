# Generative UI Landscape

## Overview

This page surveys the current landscape of Generative UI technologies (2025-2026) — where LLMs output structured UI rather than plain text. This research informed the design decisions behind Synapse Canvas.

## Technology Approaches

Current approaches fall into three categories:

| Approach | Description | Examples |
|---|---|---|
| **Code Generation** | LLM generates HTML/CSS/JS directly, rendered in browser. Maximum freedom but risk of bugs. | Google Gemini 3 |
| **Declarative Specification** | LLM declares UI structure in JSON/XML, client maps to components. Stable but limited expression. | A2UI, Thesys C1 |
| **Tool Call Mapping** | LLM tool call results mapped to pre-defined React components. Strong developer control. | Vercel AI SDK |

## Technologies Evaluated

### Google Gemini 3 Generative UI

The largest-scale production implementation. Gemini 3 directly generates HTML/CSS/JS for custom UI rendering.

- **Deployed in**: Gemini app "Dynamic View", Google Search AI Mode
- **Approach**: Server provides tool access (image generation, web search), detailed system prompt specifies format, post-processor fixes common issues
- **Evaluation**: Generative UI output was overwhelmingly preferred over standard Markdown by human evaluators

### Google A2UI (Agent-to-User Interface)

Open-source declarative UI specification (v0.8-0.9) for agents to generate UI widgets.

- **Model**: Adjacency list (flat component definitions optimized for LLM generation)
- **Integration**: Embeds in A2A protocol as `DataPart` with `application/json+a2ui` content type
- **Surface concept**: Manages multiple independent UI regions
- **References**: [a2ui.org](https://a2ui.org/), [GitHub](https://github.com/google/A2UI)

### AG-UI (Agent-User Interaction Protocol)

Developed by CopilotKit. Provides bidirectional runtime connection between agent backends and user-facing applications.

- **Relationship to A2UI**: AG-UI is the transport layer, A2UI is the payload definition
- **Event types**: Text streaming, tool calls, state deltas (STATE_DELTA), INTERRUPT for human-in-the-loop
- **Integrations**: Microsoft Agent Framework, LangGraph

### MCP Apps

Official MCP extension (v1.1). MCP servers provide HTML bundles as `ui://` resources, rendered in sandboxed iframes within MCP clients.

- **Approach**: Full HTML/CSS/JS freedom with postMessage bidirectional communication
- **Supported clients**: Claude, Claude Desktop, VS Code Copilot, Goose, Postman
- **References**: [MCP Docs](https://modelcontextprotocol.io/extensions/apps/overview), [GitHub](https://github.com/modelcontextprotocol/ext-apps)

### Vercel AI SDK

Tool Call results mapped to pre-defined React components via React Server Components.

- **AI SDK 6**: Agent abstraction drives tool definitions, API responses, and UI components with type safety

### Thesys C1

API that outputs structured UI components (forms, tables, charts) instead of plain text.

- **Approach**: Specification-based (JSON/XML UI spec), rendered by React SDK
- **Integration**: OpenAI-compatible endpoint (baseURL swap)

## Decisions for Synapse Canvas

| Technology | Decision | Rationale |
|---|---|---|
| Gemini 3 Generative UI | Reference only | Code generation approach reflected in `html` format |
| A2UI | Deferred | Adjacency list model too complex for CLI agents. Canvas purpose is display, not interactive UI construction |
| AG-UI | Deferred | Bidirectional communication not needed (Canvas is display-only). Revisit when adding card interactivity |
| MCP Apps | Deferred | PTY agents are not MCP clients. Sandboxed iframe approach adopted for `html` format security |
| Vercel AI SDK | Reference only | Tool Call to UI mapping concept reflected in format registry |
| Thesys C1 | Reference only | Specification-based approach similar to Canvas Message Protocol |

## Where Canvas Fits

Synapse Canvas is a hybrid of all three approaches:

- **Declarative specification**: `format + body` JSON protocol declares structure
- **Code generation**: `html` format allows full HTML/CSS/JS expression (escape hatch)
- **Tool call mapping**: Format registry maps body content to renderers

The fundamental difference from the technologies above: **Synapse agents are CLI tools (Claude Code, Codex, etc.), not LLMs directly generating UI**. Agents post to Canvas via CLI commands. Simplicity for agents (one command to post) is the top priority.

## Future Considerations

- **A2UI integration**: When A2A protocol standardizes A2UI as an extension, Canvas could auto-render A2A communication results
- **Bidirectional interaction**: When cards need interactivity (button presses triggering agent actions), MCP Apps' postMessage pattern is a reference model
