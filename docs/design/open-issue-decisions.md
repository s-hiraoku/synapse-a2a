# Open Issue Decisions

This document captures decision artifacts for open issues whose main outcome is
research, RFC triage, or a large staged migration rather than one isolated code
change. It keeps the backlog actionable by separating "implemented now" from
"defer with a concrete re-entry condition".

## #18 Dependency Dashboard

Renovate currently reports no open or pending branches. Treat the dashboard as a
standing maintenance issue, not a product feature. Completion action for this
round: verify the dashboard has no pending branches and leave future dependency
updates to Renovate PRs rather than bundling unrelated upgrades into feature PRs.

Re-entry condition: Renovate opens a branch or the dashboard lists a blocked
manual update.

## #48 Unified database

Full consolidation of registry JSON, history, file safety, workflow runs, wiki,
and session stores into one SQLite database remains a breaking migration. The
safe staged path is:

1. Keep existing stores as source of truth.
2. Add shared read-only inventory first; Canvas DB browser already exposes the
   current SQLite stores for inspection.
3. Add a unified schema and migration verifier before moving writes.
4. Migrate one bounded store at a time, starting with low-risk session metadata.

This PR advances the storage story with shared session handoff
(`SYNAPSE_SHARED_SESSION_DIR`, `session publish/import`) but deliberately does
not migrate existing databases into a single file.

Re-entry condition: create a dedicated migration PR with a schema manifest,
backup/restore tests, downgrade behavior, and per-store migration tests.

## #159 Compliance and permissions

The draft's core concepts map onto current code as follows:

| Draft concept | Current artifact |
| --- | --- |
| Provider-specific policy | `PolicyEngine` facade and approval-gate profile overrides |
| Permission prompts | WAITING detection and A2A `input_required` mapping |
| Auto approval/denial | Approval Gate actions and profile `deny_response` |
| Operator escape hatch | `dialog-respond` and `send-keys` for TUI dialogs |
| Visibility | `synapse list`, `status --json`, Canvas Agent Control |

The remaining `manual` / `prefill` / `auto` compliance-mode split is useful but
should be implemented as a dedicated settings migration, because it changes
whether Synapse may inject and submit input. Until then, the current behavior
stays backward compatible and visible through policy/status surfaces.

Re-entry condition: implement `permissions.defaultMode`-style provider modes
with parser tests, profile tests, and startup banner tests.

## #217 Go rewrite RFC

Decision: do not rewrite Synapse A2A in Go now.

Rationale:

- The largest benefit is packaging as a single binary.
- The current Python implementation has broad tests and many PTY edge cases
  already fixed.
- A rewrite would reintroduce risk in PTY handling, A2A compatibility, registry
  semantics, and Canvas integration.

Preferred path:

1. Continue decomposing Python modules and tightening types.
2. Improve packaging independently if distribution becomes the main blocker.
3. Reconsider Go only when a measured packaging or runtime bottleneck outweighs
   the cost of maintaining two implementations.

## #406 Agent browser

Decision: treat external agent-browser integration as an adapter opportunity,
not a core replacement for Canvas.

Current fit:

- Canvas already provides the browser-based shared surface for cards, workflows,
  agent control, and system inspection.
- The Adapter interface added in this PR gives a future place to connect a
  browser-native agent runtime without changing A2A core routing.

Preferred integration shape:

1. Expose an `AgentAdapter` for the browser agent endpoint.
2. Translate Agent Browser sessions into standard A2A tasks and artifacts.
3. Render browser artifacts in Canvas via existing HTML artifact support.

Re-entry condition: choose a concrete Agent Browser API contract and add adapter
tests against that contract.

## #434 everything-claude-code patterns

Decision: several patterns have already been adopted in Synapse-native form.

| Pattern from research issue | Synapse artifact |
| --- | --- |
| Continuous learning | Observation store, `learn`, `instinct`, `evolve`, probabilistic recall |
| Hook profiles | `SYNAPSE_HOOK_PROFILE` and minimal/standard/strict hook filtering |
| Agent definitions | `synapse agents`, `agents.json`, saved-agent petname alias |
| Multi-agent orchestration | `spawn`, `team start`, worktrees, workflows, multiagent patterns |
| Skill architecture | Harness manager, skill manager, skill create launch-agent |
| Session/state | session save/restore/resume and shared session handoff |
| Security / permission lessons | PolicyEngine, Approval Gate, WAITING diagnostics |

Deferred items are evaluation suites and a richer context-budget subsystem.
Those should be separate features because they need product-level UX decisions,
not only plumbing.

## #512 Claude Agent SDK

Decision: keep Agent SDK integration as an optional workflow/backend extension,
not as the default A2A runtime.

Rationale:

- Synapse must stay vendor-neutral across Claude, Codex, Gemini, OpenCode, and
  Copilot.
- Agent SDK is promising for headless Claude-only execution, workflow steps, and
  CI use cases.
- Existing A2A routing, Canvas, registry, and workflow DAG behavior already
  cover the cross-vendor coordination layer.

Preferred path:

1. Add a `WorkflowStepExecutor` abstraction only when a real SDK backend is
   implemented.
2. Let Agent SDK-backed steps opt in per workflow or per step.
3. Keep PTY/A2A execution as the default backend for cross-vendor workflows.

Re-entry condition: add a minimal Agent SDK PoC behind an optional dependency
and prove one workflow step can run headlessly with deterministic task status.
