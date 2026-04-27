# Changelog

For the complete changelog, see [CHANGELOG.md on GitHub](https://github.com/s-hiraoku/synapse-a2a/blob/main/CHANGELOG.md).

## Recent Highlights

### Unreleased

The next release rolls up a "status precision" family that sharpens what `synapse list` / `synapse status` show during long-running and rate-limited work, plus a new one-shot `synapse watchdog check` command for surfacing stuck agents. Status precision now covers `RATE_LIMITED` (#561), the `SENDING_REPLY` sub-state (#644), HTTP `input_required` (#651), and a true PTY-level interrupt path with `mode=pty|signal|auto` (#647). Observability of recent messages is hardened by including parent-side A2A sends (#659), keeping `output_text` reserved for agent responses (#660), and using millisecond-precision history timestamps (#661). The default agent instructions also now describe `synapse memory` as legacy in favor of LLM Wiki (#527).

- **Added**: `synapse watchdog check` (#646) — Stage 1 MVP one-shot CLI that scans every live agent and surfaces stuck-state suspicions via a heuristic table. Supports `--alarm-only` (only rows with an alarm) and `--json` (machine-readable output). Heuristics in priority order: (1) `RATE_LIMITED` for over 30 minutes, (2) `SENDING_REPLY` for over 60 seconds, (3) `PROCESSING` for over 30 minutes with no outbound A2A in the last 10 minutes, (4) spawn never reaching `READY` between 60 seconds and 5 minutes after registration. Stage 2-4 (background daemon, `synapse list --watch` integration, automatic recovery) ship in future PRs.
- **Added**: `last_status_change_at` field on registry entries, written only on real status transitions so no-op rewrites preserve the timestamp. Pre-existing entries with the field absent are skipped by duration-based heuristics rather than counted from epoch.
- **Added**: Surface HTTP task `input_required` state in `synapse list` / `synapse status` (#651) — the registry now mirrors active `input_required` task IDs and approve URLs in the new `input_required_tasks` field so a parent operator can see the approve URL without an extra HTTP query.
- **Added**: Surface child agent reply-send stalls via the `SENDING_REPLY` sub-state (#644) and per-agent Recent Messages filter. Sender briefly transitions to `SENDING_REPLY` during the outbound A2A POST and is restored to its previous status afterward; `DONE`, `SHUTTING_DOWN`, and `RATE_LIMITED` are never overwritten.
- **Added**: True PTY-level interrupt API (`mode=pty|signal|auto`) for stuck agents (#647). Per-profile `interrupt.default_mode` / `interrupt.pty_repeat` / `interrupt.graceful_supported` defaults for Claude, Codex, Gemini, Copilot, and OpenCode preserve existing SIGINT broadcast behavior for signal-mode callers while letting TUI agents receive a literal Ctrl+C through the PTY.
- **Added**: Surface LLM provider rate limits as `RATE_LIMITED` agent status (#561). Overrides `PROCESSING` / `READY` / `WAITING_FOR_INPUT` until the agent recovers; rendered bold magenta in `synapse list`.
- **Changed**: Default agent instructions (`synapse://instructions/default`) now describe `synapse memory` as legacy and direct callers needing that interface to fetch `synapse://instructions/shared-memory` explicitly (#527). New agents are guided to LLM Wiki by default; the `synapse memory` CLI commands and the `shared-memory` MCP resource are unchanged for backward compatibility.
- **Fixed**: `recent_messages` timestamps now use millisecond precision so rapid history writes within the same second can still be ordered distinctly (#661).
- **Fixed**: Parent-side `synapse send` observations no longer write placeholder text into `output_text`, keeping recent message output reserved for agent responses (#660).
- **Fixed**: `synapse status <agent> --json` recent messages now include parent-side A2A sends to the agent (#659) — the SQL filter previously dropped parent-saved rows before the Python `agent_id` post-filter could match them.
- **Fixed**: `clear_reply_target()` now swallows cleanup `PermissionError` / `OSError` failures so sandbox unlink errors no longer mask successful reply sends (#653).
- **Documentation**: Address CodeRabbit feedback on the skills-role RFC (#625 follow-up, #657): correct the future-dated reference, reflow a CommonMark line break that rendered as an unintended space, and clarify local dev policy precedence.

### v0.30.0

- **Added**: True PTY-level interrupt API (#647) — `POST /tasks/{id}/cancel` now accepts `mode=auto|pty|signal` and `repeat`, allowing stuck agents to receive Ctrl+C bytes through the PTY while preserving the legacy SIGINT path for `mode=signal`.
- **Added**: Profile-driven interrupt defaults — Claude, Codex, Gemini, Copilot, and OpenCode profiles now declare their default cancellation mode, PTY repeat count, and graceful-interrupt support.
- **Added**: `RATE_LIMITED` agent status (#561) — surfaces an LLM provider rate-limit signal as a distinct registry/list/status state, rendered bold magenta in `synapse list` so a quota-blocked agent is no longer indistinguishable from one actively `PROCESSING`.
- **Added**: `/dev-issue <number>` slash command skill — bootstraps issue implementation by fetching issue context, generating a task brief, creating a branch, and optionally spawning a Codex worker.
- **Fixed**: Workflow target type resolution now respects the caller working directory (#568), so bare `target: claude` / `target: codex` workflows do not dispatch to unrelated agents in other projects.
- **Changed**: Sends to READY agents are delayed briefly (#467) to avoid interrupting user input at a visible prompt.

### v0.29.0

- **Added**: `WAITING_FOR_INPUT` agent status (#538, #640) — non-permission A2A `input_required` tasks now surface as a distinct registry/list/status state, while permission prompts keep the existing `WAITING` state. Rendered as orange in the Rich TUI; included in `ALL_STATUSES` and exposed via `synapse list` / `synapse status` (text and `--json`).
- **Fixed**: Agent registry status sync (#569) — A2A status callbacks now demote stale registry `PROCESSING` / `WAITING_FOR_INPUT` states back to `READY` when the task store is non-empty and all tasks are terminal, preventing `synapse list` from showing active work after every task has completed.

### v0.28.3

- **Added**: `synapse waiting-debug collect --timeout SECONDS` — overrides the HTTP timeout used when querying `/debug/waiting` on each registered agent. Default raised from 3.0 s to **5.0 s**, which eliminates the common warn-flood immediately after PtyRenderer boots when agents can't respond within 3 s (#635).
- **Added**: `synapse waiting-debug report --out PATH` — writes the aggregated JSON report to a file instead of stdout. When `--out` is set, stdout stays empty so the flag is safe to use from cron / launchd without capturing mixed text/JSON output. The write is **atomic** (temp file + `os.replace`) so concurrent readers never see a half-written report (#635).
- **Changed**: `WaitingDebugReporter._record_is_since` — records whose `collected_at` can't be parsed are still skipped for `--since` filtering, but now emit `Warning: record at line N has unparseable collected_at: '<value>' (<reason>)` to stderr instead of being silently dropped. Matches existing behaviour for invalid JSONL lines (#635).
- **Changed**: `synapse.commands.waiting_debug.default_waiting_debug_path()` is resolved lazily per call; tests and tools that set `HOME=/tmp/...` now actually redirect collection/reporting instead of silently using the real home. New `SYNAPSE_WAITING_DEBUG_PATH` env var override is honored via `synapse/paths.py` (#635).
- **Changed**: `--timeout` argparse validation rejects negative values (`--timeout must be >= 0`); `--timeout 0` is preserved as the deliberate "fail fast / never wait" mode (urllib non-blocking) and is **not** equivalent to "no timeout" — omit the flag for the default 5 s budget (#635).
- **Fixed**: Closes #630 — Phase 1.5 persistence pipeline is now operationally stable with the polish above. Dead `if collected_dt is None: return False` branch in `_record_is_since` removed (unreachable when `collected_at` is `str`).

### v0.28.2

- **Changed**: Default auto-approve migration — Claude Code now injects `--permission-mode=auto` (classifier-gated) instead of the deprecated `--dangerously-skip-permissions`; Gemini switches to the unified `--approval-mode=yolo`. Legacy flags stay in each profile's `alternative_flags` so manual invocations aren't double-injected.
- **Fixed**: Copilot `waiting_detection.regex` no longer matches pasted markdown numbered lists / blockquotes / bullets (bracketed-paste echoes were flipping status to WAITING and short-circuiting submit-confirmation). Regex is now anchored on Copilot's actual approval verbs and `heuristic_fallback` is disabled for this profile. Regression coverage in `tests/test_copilot.py` and `tests/test_compound_signal.py`.
- **Added**: Phase 1.5 operational runbook — launchd macOS scheduling recipe, CLI-bump requirement for `waiting-debug`, and a legacy-404 caveat for pre-Phase-1 agents. Narrative cross-links added across guides, skills, and `site-docs/troubleshooting.md` so the operator path is reachable from either surface.
- **Changed**: Command-layer DRY pass — `format_renderer_suffix()` helper extracted in `synapse/utils.py`; the three duplicate `(renderer: on/off)` implementations across `status.py` / `list.py` / `rich_renderer.py` now share it. `_http_get_json` and `_format_counter` consolidated into `synapse.commands.waiting_debug` and imported by `status.py`.
- **Fixed**: `synapse/commands/waiting_debug.py::_iter_records` TOCTOU hardening (`FileNotFoundError` replaces pre-`exists()` probe).

### v0.28.1

- **Added**: `synapse waiting-debug` CLI — Phase 1.5 collection pipeline (#630, #632). `collect` appends `/debug/waiting` snapshots to `~/.synapse/waiting_debug.jsonl`; `report` prints aggregate counts (profile, `pattern_source`, `path_used`, `confidence`, `idle_gate_drops`, `renderer_unavailable_agents`) in text or JSON. `.synapse/waiting_debug.*` ignored; `docs/phase15-collection.md` documents cron and launchd scheduling at 5-minute cadence
- **Documentation**: WAITING observability reference coverage (#608, #631) — `synapse-a2a` skill `api.md` / `commands.md` document `GET /debug/waiting`, `--debug-waiting`, `renderer_available`, and `(renderer: off)`; `site-docs/guide/agent-management.md` gains "Renderer Availability" and "WAITING Detection Diagnostics" subsections
- **Fixed**: `TestSyncedSkillParity` for externally-registered skills (#629) — `opensrc` (from `vercel-labs/opensrc`) now carries `metadata.internal: true` in its frontmatter so the orphan-skill check correctly exempts it

### v0.28.0

- **Added**: WAITING detection observability layer — Phase 1 (#608, #627). `IdleDetector` ring buffer records each detection attempt with `path_used`, `renderer_on`, `pattern_matched`, `pattern_source`, `confidence`, `idle_gate_passed`, `new_data_hex_prefix`, `rendered_text_tail`. `TerminalController` wraps `PtyRenderer` initialisation in try/except and exposes `renderer_available`. New `/debug/waiting` endpoint and `synapse status <agent> --debug-waiting` surface recent attempts + aggregates (total / match ratio / path usage / confidence / idle-gate drops). `synapse list` / `synapse status` annotate status with `(renderer: off)` and emit `renderer_available` in JSON. Phase 1 is observation only — detection logic is unchanged
- **Added**: Canvas Skills Viewer (`#/harnesses/skills`) — new SPA sub-view that lists every discovered skill grouped by scope (User Global, Synapse Global, Plugin, per-active-project). SKILL.md frontmatter is parsed with PyYAML so quoted colons and multi-line values now parse correctly
- **Added**: Canvas MCP Servers Viewer (`#/harnesses/mcp`) — inventories MCP servers from every active project's `.mcp.json` plus five user-scope agent configs (Claude Code, Codex, Gemini, OpenCode, Claude Desktop). `env` values are stripped to keys-only before reaching the UI
- **Added**: `synapse canvas restart` — stop-then-start helper for the `⚠ STALE` case after upgrades. Accepts `--port/-p` and `--no-open`
- **Added**: Worktree-aware default scope on agent-profile save — the prompt now defaults to `user` inside a worktree (project scope vanishes on cleanup) and to `project` otherwise, with the rationale inlined in the prompt text
- **Changed**: Canvas registry scans consolidated into a single iterator pair (`_iter_registry_entries{,_with_errors}`) — three duplicated glob+parse loops collapsed; `system_panel` no longer re-scans the registry from `_collect_static_sections` on every cache refresh
- **Changed**: Skill SKILL.md frontmatter parser switched from a hand-rolled regex to `yaml.safe_load`. Behavior unchanged for shipped scalar-only frontmatter
- **Removed**: Orphan workflow-autogen skills `my-review` and `user-wf` per the responsibility-matrix RFC (#610) — both lacked backing `.synapse/workflows/*.yaml` and were unreferenced
- **Fixed**: Profile command strings with multiple tokens, such as `python3 -u dummy_agent.py`, are now split with `shlex` before launch so profile-defined arguments are executed correctly (subsumes the un-tagged 0.27.2 fix)

### v0.27.2

- **Fixed**: Profile command strings with multiple tokens, such as `python3 -u dummy_agent.py`, are now split with `shlex` before launch so profile-defined arguments are executed correctly

### v0.27.1

- **Documentation**: Golden Path "Quick Start" section at the top of README — four-command flow (`synapse start claude` / `start codex` / `list --plain` / `send ... --wait`) that verifies cross-agent messaging via a `SYNAPSE_GOLDEN_PATH_OK` sentinel; the former install-focused Quick Start is renamed to `Installation`. Adds `examples/golden-path.md` (#604, #615)
- **Documentation**: `docs/a2a-overview.md` — a one-page A2A concept explainer (What is A2A / 3-step mental model / Mermaid diagram / minimum use case / links to deeper docs) so newcomers can grasp the project in under five minutes (#605, #616)
- **Documentation**: `docs/terminology.md` — shared vocabulary reference for 16 core terms + 9 supporting terms, each anchored to the code path / doc / CLI help where it actually lives, plus a "Known Inconsistencies" section on the `Skill` and `Shared Memory` dual-use traps (#612, #617)
- **Tests**: `test_lifespan` expectation realigned with the `spawned_by` kwarg added in #601. `Registry.register()` now receives `spawned_by=os.environ.get("SYNAPSE_SPAWNED_BY") or None` at startup; the pre-existing exact-match `assert_called_with` was left behind and had turned `main` CI red. One-line fix unblocks the whole PR queue (#618, #620)

### v0.27.0

- **Added**: `synapse cleanup` for orphaned spawned agents — kills children whose `spawned_by` parent is gone or whose parent PID is dead. `synapse spawn` propagates `SYNAPSE_AGENT_ID` to the child as `SYNAPSE_SPAWNED_BY` so the registry records the parent-child link automatically. Supports `--dry-run`, per-agent target, opt-in `SYNAPSE_ORPHAN_IDLE_TIMEOUT` reaping, and `[ORPHAN]` annotations + JSON fields in `synapse list` (#332)
- **Added**: Worktree-aware agent-profile save defaults — the save-prompt default flips from `project` to `user` when running in a worktree (project scope is deleted on cleanup), and worktree cleanup copies any saved `*.agent` files back to the main repo as a safety net (main wins on collision). Detection is pure-Python — no per-prompt `git` subprocess (#410)
- **Fixed**: Nested-worktree path resolution — `synapse spawn --worktree` from inside a worktree now anchors the new worktree at the main repo root instead of accumulating nested `<wt-A>/.synapse/worktrees/<wt-B>/` paths (#546, #598)
- **Fixed**: `idle_detector` generic-prompt heuristic safety net + tighter WAITING-confidence threshold so transient single-prompt frames no longer flip status alone (#572, #594)
- **Documentation**: `synapse-a2a` skill now recommends Agent-tool / subprocess subagents over `synapse spawn` for same-model delegation (#595), and adds a "Worktree Discipline" section warning subagents never to `cd` into `.synapse/worktrees/` (the parent shell inherits the cwd change) (#547, #599)
- **Tests**: Opt-in pytest e2e for the `post-impl` workflow exercises `run_workflow` + `_WorkflowHelper` against the real `post-impl.yaml` without spawning live agents — asserts the #531 acceptance criteria (5 steps complete, helper spawned/killed exactly once, no 409 `Agent busy`) (#531, #600)

### v0.26.5

- **Changed**: Permission-notification dedupe path simplified — `_build_permission_metadata` is now pure and `_on_status_change` reads prior dedupe state directly from `task.metadata`. The per-suppression `task_store.update_metadata` call is also dropped, so the lock is only acquired when an actual notification is emitted. Behaviour unchanged (#588 follow-up)
- **Changed**: `PtyRenderer.render()` 80×24 cell loop no longer raises and catches `IndexError`/`AssertionError` for every empty/wide-stub cell — replaced with an early-return length check, removing per-cell `try`/`except` cost without changing the broken-cell substitution semantics (#590 follow-up)
- **Changed**: `PortManager.get_running_instances()` collapses the previous `O(ports × agents)` nested scan into a single `agents.values()` pass with a port-keyed sort (#584 follow-up)
- **Removed**: Unused `looks_like_garbage()` and `printable_ratio()` helpers in `synapse/_pty_sanitize.py` — never wired into production code after #588 landed
- **Documentation**: `docs/permission-detection-spec.md` now describes the #582/#586 sanitisation pipeline and the #529 codex approval-overlay markers; site-docs install path uses `gh skill install` consistently; `mkdocs.yml` exposes the previously orphaned Skills Management page in the User Guide nav
- **Added**: `license: MIT` frontmatter on every plugin `SKILL.md` (23 skills × canonical + 2 deployment mirrors). Skill consumers using `gh skill install` now see the license alongside the existing name/description metadata
- **Verified**: Full `gh skill` publish/install flow on `gh` 2.90.0 — `publish --dry-run` clean across 23 skills, `install`/`update`/`preview`/`search` all working with provenance metadata correctly injected into installed copies

### v0.26.4

- **Fixed**: PTY observation thread no longer crashes with `IndexError` when `pyte.Screen.display` hits an empty stub cell left over from a wide-char overwrite. `PtyRenderer.render()` iterates the buffer defensively and substitutes blanks for broken cells, keeping every agent's capture loop alive (#590, #591)
- **Fixed**: `TerminalController._check_idle_state` has a broad safety net — on detector failure it logs at WARNING and conservatively demotes `READY`/`WAITING` to `PROCESSING` whenever new PTY output is still arriving, so a stale status never misrepresents a busy agent as idle (#591)
- **Dependencies**: `wcwidth>=0.2.0` is now a direct dependency (previously transitive via `pyte`)

### v0.26.3

- **Skill distribution**: Migrated the canonical install path from `skills.sh` / `npx skills add` to GitHub CLI's **`gh skill install`** (requires `gh` 2.90.0+). New policy doc ([Skills Management](guide/skills-management.md)) covers pinning, provenance metadata, maintainer `gh skill publish`, and a migration matrix for existing `npx skills add` users. English + ja/ko/zh/es/fr READMEs, guides, and this site all reference the new command. `v0.26.2` was the first `gh skill`-published release.

### v0.26.1

- **Documentation**: Claude Code permission-mode docs refreshed to match the current 6-mode spec (`default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`), the new `--permission-mode <mode>` launch flag, and the `permissions.defaultMode` settings key. `--dangerously-skip-permissions` remains valid as an alias for `--permission-mode bypassPermissions`, so Synapse's auto-approve injection is unaffected.

### v0.26.0

- **Added**: Approval Gate policy expansion — prompt classification (`classify_prompt`), per-action dict-style `profile_overrides`, and risk classifier safety floor for destructive commands (#571 Phase 3, #578)
- **Added**: Pyte-backed virtual terminal for `waiting_detection` — resolves ratatui cursor-motion garbling, tracks alt-screen buffer, adds `GET /debug/pty` endpoint (#572, #575)
- **Fixed**: Approval Gate escalation flood — blocked-state floor + `EscalationDeduper` prevent children stuck on quota banners from flooding the parent inbox (#576)
- **Fixed**: Status sync between controller and task_store — `input_required` tasks now revert on any exit from WAITING, and `GET /tasks/{id}` no longer writes side effects (#569, #577)

### v0.25.2

- **Fixed**: Parent-side permission handling no longer deadlocks on child `input_required` prompts — children now send structured escalation metadata, the Approval Gate can auto-dispatch approve/deny/escalate, and `synapse send --wait` stays alive until parent intervention or timeout (#571)
- **Fixed**: `synapse list` Rich TUI now opens on the alternate screen, keeping live redraws stable during status updates
- **Fixed**: `synapse spawn` auto-approve flag collision — passing `--dangerously-bypass-approvals-and-sandbox` (or other alternative approval flags) no longer conflicts with the profile's default `--full-auto`. Profiles can now declare `alternative_flags`; injection is skipped when any known approval flag is already present, including `--flag=value` forms
- **Fixed**: `input_required` is treated as transient for `target: self` workflow steps — `synapse workflow run post-impl-codex` no longer fails at step 1 with a spurious permission-approval error; non-self behavior is unchanged (#551, #564)
- **Added**: Five built-in `CoordinationPattern` subclasses (`agent-teams`, `generator-verifier`, `message-bus`, `orchestrator-subagent`, `shared-state`) registered via `synapse.patterns.BUILTIN_PATTERNS` and runnable via `synapse multiagent` / `synapse map` (#541, #560)
- **Added**: Automatic cleanup of expired long-message temp files — `LongMessageStore` sweeps after writes (throttled 5 min) and at singleton init, preventing accumulation under `/tmp/synapse-a2a/messages` (#559, #562)
- **Added**: `post-impl-claude` workflow variant (`target: claude`, ends with `/autofix-pr`), completing the claude/codex/self trio (#566)
- **Changed**: `post-impl` workflow variants realigned so file name, `target:`, and execution semantics are consistent — `post-impl.yaml` is now `target: self`, `post-impl-codex.yaml` is now `target: codex` (#566)

### v0.25.1

- **Fixed**: `synapse send` to Codex agents no longer fails with cryptic "local send failed" — HTTP 409 (agent busy) is now surfaced as "Agent busy (working task). Retry after Ns" (#554)
- **Fixed**: `send_to_local()` logs diagnostic warnings at every failure path; set `SYNAPSE_LOG_LEVEL=DEBUG` for details (#542)
- **Fixed**: `synapse send` warns when sender agent cannot be identified, advising to set `SYNAPSE_AGENT_ID` (#543)
- **Fixed**: `--message-file`, `--task-file`, and `--stdin` inputs no longer trigger false backtick shell-expansion warnings (#544)
- **Fixed**: Codex agent status uses hybrid idle detection with startup-only pattern matching, improving status accuracy during LLM thinking time (#537)
- **Added**: `synapse send --task-file / -T PATH` flag mirroring the flag on `synapse spawn` (#545)

### v0.25.0

- **Added**: Multi-agent coordination patterns engine — declarative YAML-based patterns with 5 built-in types (generator-verifier, orchestrator-subagent, agent-teams, message-bus, shared-state)
- **Added**: `synapse multiagent` / `synapse map` CLI for managing coordination patterns
- **Added**: Canvas "Patterns" view with Mermaid architecture diagrams
- **Added**: Pattern REST API, `PatternStore`, `PatternRunner`, `CoordinationPattern` ABC
- **Tests**: Comprehensive test suites for patterns engine, CLI commands, and Canvas routes

### v0.24.2

- **Fixed**: `synapse list` table layout stable across status transitions — STATUS/CURRENT columns use fixed widths (#532)
- **Fixed**: Workflow `response_mode: wait` polling treats `input_required` as terminal failure (#533)
- **Fixed**: Helper-idle checks treat `input_required` as blocking to prevent dispatch to stuck helpers (#533)
- **Fixed**: Workflow helper spawning sets `auto_approve=True` to prevent permission-prompt stalls (#533)
- **Refactored**: Extracted `_resolve_columns` helper and test utilities

### v0.24.1

- **Added**: `target: self` keyword in workflow YAML — steps targeting the calling agent are routed to a helper agent to avoid deadlock (#521, #526)
- **Added**: Self-target helper agent — workflow runner automatically spawns a short-lived helper when a step targets the same agent that triggered the workflow (#525)
- **Changed**: Shared Memory marked as deprecated — use [LLM Wiki](design/llm-wiki.md) (`synapse wiki`) for new knowledge storage (#528)
- **Changed**: CLAUDE.md simplified — detailed reference moved to `docs/synapse-reference.md` (guidance reorg)
- **Removed**: Test-only workflow fixtures and orphan skills cleaned up


### v0.24.0

- **Added**: `synapse spawn` auto-tiles panes when 2+ agents exist in spawn zone, matching `team start` behavior (#507)
- **Changed**: `_post_spawn_tile()` uses `SYNAPSE_SPAWN_PANES` for spawn zone-aware tiling

### v0.23.5

- **Fixed**: Copilot KKP re-activation detection — Ink TUI can re-push KKP after processing a prompt, causing Enter key failures on subsequent sends
- **Fixed**: Last-resort KKP force-disable + ICRNL re-clear when submit confirmation exhausts all retries

### v0.23.4

- **Fixed**: `synapse spawn` auto-tiles panes when 2+ agents exist in spawn zone (#507) — previously only `team start` provided automatic tile layout
- **Changed**: `_post_spawn_tile()` uses `SYNAPSE_SPAWN_PANES` tracking for spawn zone-aware tiling

### v0.23.3

- **Fixed**: WAITING detection strips ANSI escape sequences for reliable TUI approval prompt matching (#508)
- **Changed**: Auto-approve defaults to unlimited for spawned agents (#508)
- **Changed**: pr-guardian uses `gh run watch` hybrid approach, reducing polling cycles (#518)

### v0.23.2

- **Fixed**: Copilot CLI Enter key reliability — detect and disable Kitty Keyboard Protocol (KKP)
- **Fixed**: Thread-safe PTY write via `_disable_kkp()` helper with `RLock`


### v0.23.1

- **Fixed**: `response_mode: wait` now correctly waits for task completion in `synapse workflow run` (#513)
- **Fixed**: Polling loop exits early on `input_required` status


### v0.23.0

- **Added**: Living Wiki — source file tracking (`source_files`/`source_commit` frontmatter), stale page detection, `synapse wiki refresh` command
- **Added**: `synapse wiki init` — scaffold architecture and patterns skeleton pages
- **Added**: `learning` page type for recording bug fixes and discovered patterns
- **Added**: `GET /api/wiki/graph` Canvas endpoint — Mermaid knowledge graph of wiki page links

### v0.22.0

- **Added**: `synapse worktree prune` — orphan worktree detection and cleanup
- **Fixed**: Canvas Database view excludes `.synapse/worktrees/` databases


### v0.21.0

- **Added**: LLM Wiki — Knowledge Accumulation Layer (#506). Agents build persistent, interlinked Markdown wikis at project and global scope
- **Added**: `synapse wiki ingest/query/lint/status` CLI commands
- **Added**: Canvas Knowledge view (`#/knowledge`) with Project/Global tabs, page list, detail, wikilinks
- **Added**: MCP instruction `synapse://instructions/wiki` for automatic wiki schema injection
- **Fixed**: Wiki code simplified — deduplicated frontmatter parsing, added TTL cache, fixed TOCTOU


### v0.20.0

- **Added**: Permission detection — spawned agents automatically notify callers when stopped at a permission prompt (#492, #498)
- **Added**: `POST /tasks/{id}/permission/approve` and `/deny` API endpoints for remote approval
- **Added**: `deny_response` profile config for all 5 agent types
- **Docs**: Permission detection spec and user guide

### v0.19.5

- **Fixed**: Tile layout pane creation for spawn and team start (#502)
- **Fixed**: Worktree spawn silent failures (check=False → check=True)
- **Fixed**: Zellij pane count detection (env var counter replaces unreliable CLI)

### v0.19.4

- **Added**: `synapse spawn --task` — send a task message immediately after the spawned agent becomes ready (#494)
- **Added**: `--task-file` and `--task-timeout` flags for `synapse spawn`
- **Added**: `--wait` / `--notify` / `--silent` response modes for spawn task delivery
- **Added**: `synapse merge` command — merge worktree agent branches independently (#493)
- **Added**: `--all`, `--dry-run`, and `--resolve-with` flags for `synapse merge`

### v0.19.3

- **Added**: Auto-merge worktree branch on kill (#496)
- **Fixed**: `synapse send` no longer blocks messages to worktree agents without `--force` (#497)

### v0.19.2

- **Fixed**: Unified `is_process_alive` with `is_process_running` to fix `PermissionError` mishandling (#495)
- **Fixed**: Deferred `get_git_root()` in `merge_worktree` to avoid unnecessary subprocess
- **Docs**: Updated guides with `--no-merge` flag and auto-merge behavior

### v0.19.1

- **Added**: Worktree auto-merge on `synapse kill` — worker branches are automatically merged back (#493)
- **Added**: Uncommitted changes auto-committed as WIP before merge
- **Added**: `--no-merge` flag to skip auto-merge
- **Fixed**: `is_process_alive()` no longer treats `PermissionError` as process dead — fixes false-negative liveness checks (#495)
- **Docs**: Merge strategy comparison (Claude Code vs Synapse), updated references across all docs

### v0.19.0

- **Added**: `analyze_task` returns `recommended_worktree` for context-aware worktree decisions
- **Added**: `synapse team start` defaults to `--worktree` isolation (`--no-worktree` to opt out)
- **Added**: `--branch` auto-enables `--worktree` in `synapse spawn`
- **Docs**: Full documentation update for worktree auto-recommendation across README, guides, and site-docs

### v0.18.4

- **Docs**: Synchronized package, plugin, and GitHub Pages version references for the `0.18.4` release

### v0.18.3

- **Fixed**: OpenCode startup instruction injection now waits for timeout-idle readiness when no `input_ready_pattern` is available (#477)
- **Fixed**: Copilot spawned sessions now use the canonical `--allow-all` auto-approve flag instead of the legacy alias (#479)
- **Docs**: Updated permission-mode, profile, and site reference examples to match the new startup and auto-approve behavior

### v0.18.2

- **Added**: Canvas clipboard copy — copy card content to clipboard as Markdown via new button in card headers and spotlight view

### v0.18.1

- **Fixed**: TUI artifact removal for OpenCode (Bubble Tea) and Gemini CLI (Ink) — block elements, geometric shapes, frame content lines, and input prompts are now stripped from agent responses (#480)
- **Tests**: 13 new tests for OpenCode and Gemini TUI artifact patterns

### v0.18.0

- **Added**: `delegation_strategy` in `analyze_task` — 3-tier recommendation (self/subagent/spawn) with git diff heuristics, file conflict detection, and dependency analysis (#476)
- **Added**: Subagent vs Synapse spawn decision framework in default.md and spawning.md
- **Changed**: Concrete thresholds replace vague criteria (≤3 files=self, 4-8=subagent, 9+=spawn)
- **Docs**: Updated synapse-reference.md and README.md with new analyze_task capabilities

### v0.17.16

- **Added**: Auto-approve for spawned agents — CLI permission bypass flags injected by default (#469)
- **Added**: Runtime WAITING auto-response with safety controls (max 20, 2s cooldown)
- **Added**: `--no-auto-approve` opt-out flag for `spawn` and `team start`
- **Changed**: Spawn/team-start unified via `prepare_spawn()` + `execute_spawn()`
- **Docs**: New `agent-permission-modes.md` guide for all 5 CLI permission systems

### v0.17.15

- **Fixed**: OpenCode/Codex/Gemini WAITING detection accuracy — patterns now match actual agent approval UIs
- **Changed**: Copilot WAITING regex extended with agent-specific text patterns
- **Tests**: Parametrized per-agent WAITING pattern tests loaded from YAML profiles

### v0.17.14

- **Added**: Canvas post `--stdin`, `--example`, MCP tool for better AI posting DX
- **Added**: DB Browser shows global `~/.synapse/` databases with scope badge
- **Changed**: Module split — canvas.js/css, server.py routes, a2a.py helpers extracted into smaller files
- **Fixed**: Spotlight badges visible as empty circles, SQLite connection leak

### v0.17.13

- **Added**: Canvas format/template selection guide in base instructions (always available, not just proactive mode)
- **Added**: Spotlight keyboard navigation (ArrowLeft/Right to browse cards, Escape to return)
- **Added**: Per-template accent colors and template badge in Spotlight title bar
- **Changed**: Proactive instructions rewritten from checklist to task-size x feature matrix
- **Changed**: Spotlight info bar simplified (hover fade, removed internal IDs)
- **Fixed**: Spotlight card transition animation was missing (CSS rule not defined)
- **Fixed**: Escape key and ArrowRight keyboard navigation edge cases

### v0.17.12

- **Added**: `synapse config` shows effective values with source annotations (`os.environ > local > project > user > default`)
- **Added**: Shared memory scope support (`--scope global|project|private`) for save, list, and search
- **Added**: 16 missing environment variables to DEFAULT_SETTINGS (paths, toggles, thresholds)
- **Added**: Smart-merge for `settings.json` on `synapse init` — preserves user values while adding new keys
- **Changed**: Instructions rewritten from mandatory to judgment-based (proactive.md, file-safety.md, shared-memory.md)
- **Changed**: Skills relaxed — "Mandatory Collaboration Gate" → "Recommended", test-first is preferred not required
- **Fixed**: `SYNAPSE_SHARED_MEMORY_DB_PATH` default corrected to `~/.synapse/memory.db` (user-global)
- **Fixed**: Bare CR in PTY `_render_buffer` now clears stale text, preventing status bar noise in A2A messages
- **Fixed**: MCP server error handling — `_settings()`, `list_agents()`, and git subprocess failures now logged

### v0.17.11

- **Fixed**: Copilot CLI 1.0.12 instructions not executing — enabled `bracketed_paste: true` for paste marker wrapping
- **Fixed**: Slash escaping skipped when bracketed paste is active (pasted text doesn't trigger autocomplete)
- **Docs**: Updated Copilot bracketed paste documentation across all references

### v0.17.10

- **Changed**: DB path management consolidated to `synapse/paths.py` — all databases use centralized path functions
- **Changed**: `memory.db` moved to user-global (`~/.synapse/memory.db`) for cross-project knowledge sharing
- **Fixed**: Dashboard Recent History was always empty (hardcoded wrong path for `history.db`)
- **Removed**: Remaining task-board references from Canvas UI, tests, and docs
- **Removed**: `shell_session.py` dead code (`history.db` covers session management)

### v0.17.9

- **Fixed**: Copilot CLI input not submitted via PTY — inject pipe mechanism for `pty._copy` integration
- **Fixed**: ICRNL guard, line-start slash replacement, raw mode on real stdin, inject pipe cleanup

### v0.17.8

- **Removed**: Task Board subsystem — `synapse tasks` CLI, `/tasks/board` API, Canvas dashboard widget, and all related config. GitHub Issues will serve as the external work-item source going forward
- **Fixed**: Copilot CLI input not submitted via PTY — inject pipe mechanism feeds data through `pty._copy`'s select loop
- **Changed**: Proactive mode and default instructions simplified (no task board steps)
- **Changed**: Copilot profile: `bracketed_paste: false`, `input_ready_pattern: ❯`, slash replacement
- **Docs**: Deep cleanup of task board references across README, skills, site-docs

### v0.17.7

- **Fixed**: Canvas Live Feed renders template cards (briefing, etc.) with proper section grouping instead of flat blocks
- **Changed**: Extract `renderTemplateOrBlocks` helper and `normalizeCard` for DRY template rendering
- **Tests**: Add 9 briefing regression tests (validation edge cases, store round-trip, markdown export)

### v0.17.6

- **Fixed**: MCP bootstrap no longer silently skips approval prompts — sends minimal PTY bootstrap while keeping approval enabled
- **Changed**: Extract shared `MCP_INSTRUCTIONS_DEFAULT_URI` constant; refactor `_send_identity_instruction` early-branch pattern
- **Docs**: Update MCP bootstrap descriptions across all documentation

### v0.17.5

- **Added**: Persistent workflow execution history — SQLite storage (`.synapse/workflow_runs.db`) so Canvas workflow runs and step results survive server restarts (#437)

### v0.17.4

- **Fixed**: Copilot submit confirmation now treats repeated paste placeholders as still pending, so consecutive sends with reused `[Paste #N ...]` labels keep retrying until the prompt clears
- **Fixed**: Remove dead `previous_tail` parameter and simplify to `any()` idiom

### v0.17.3

- **Fixed**: Canvas DB moved from project-local to user-global path

### v0.17.2

- **Added**: Self-learning pipeline — PTY observation layer, instinct system with confidence scoring, evolution engine for auto-generating skills
- **Added**: Cross-agent knowledge sharing — skills learned by one agent are auto-distributed to all agents (.claude/skills/ + .agents/skills/)
- **Fixed**: Settings tests — clear SYNAPSE_PROACTIVE_MODE_ENABLED env var leak

### v0.17.1

- **Added**: Canvas Workflow view (`#/workflow`) — split-panel UI with Mermaid DAG, async execution, real-time SSE progress
- **Added**: 5 workflow API endpoints for browsing and running workflows from the browser
- **Added**: `response_mode: wait` polling — workflow runner polls target agent until task completion
- **Added**: 409 (agent busy) retry with backoff in workflow step execution
- **Fixed**: Route canvas workflow replies through canvas, Mermaid labels, agent ready wait

### v0.17.0

- **Added**: Canvas card download — export any card as Markdown, JSON, CSV, HTML, or native format file via download button or API
- **Added**: `GET /api/cards/{id}/download?format=` endpoint with 26 format mappings and 6 template exports
- **Added**: Security hardening — filename sanitization, base64 error handling, 50 MB export size limit

### v0.16.2

- **Added**: Canvas Admin UI — right-click context menu on agent rows with Kill Agent action and custom confirm modal
- **Added**: Reusable `showConfirmModal` component with glassmorphism design and theme-aware styling

### v0.16.1

- **Fixed**: Copilot CLI Enter key not executing after paste injection — set slave PTY to raw mode before spawn, drain bracketed paste writes, and add settle delay for Ink's async input buffer commit

### v0.16.0

- **Added**: `synapse reply --fail <reason>` for sending structured failed replies
- **Added**: `MISSING_REPLY` auto-detection for wait/notify tasks completed without explicit reply
- **Fixed**: TOCTOU race in missing-reply guard; reserved metadata key protection
- **Changed**: Error codes and metadata keys extracted to shared constants

### v0.15.11

- **Changed**: Adaptive paste echo wait replaces fixed `write_delay` for Copilot — polls PTY output for Ink TUI re-render before sending Enter
- **Changed**: TUI response cleaning now applies to all agents, fixing corrupted Codex and Claude Code replies
- **Fixed**: Root logger calls replaced with module logger, preventing log leakage into PTY
- **Fixed**: Pre-submit context captured before PTY writes for correct placeholder detection

### v0.15.10

- **Changed**: Refinement of v0.15.9 — removed residual typed-input, `Ctrl+S` fallback, and tmux delay code paths; inlined trivial pass-through methods; optimized pre-submit context capture
- **Documentation**: Added `long_submit_confirm_*` fields to profiles-yaml schema reference

### v0.15.9

- **Fixed**: Copilot sends now use bracketed paste plus Enter exclusively, with marker-based submit confirmation that waits for prompt text, file-reference banners, and paste placeholders to clear
- **Documentation**: Updated core docs, site docs, and plugin skills to document Copilot's paste-plus-Enter submit path

### v0.15.8

- **Added**: `synapse list --plain` for one-shot plain-text agent listings without entering the Rich TUI
- **Fixed**: `synapse list` can now be forced into non-interactive mode with `SYNAPSE_NONINTERACTIVE=1`, preventing hangs in AI-controlled TTY sessions
- **Documentation**: Updated AI-facing guidance, plugin skills, and site docs to use `synapse list --json`, `synapse list --plain`, `synapse status <target> --json`, or MCP `list_agents`

### v0.15.7

- **Fixed**: Interactive startup logging now switches to per-agent file logs before PTY handoff, so startup warnings no longer leak into interactive terminals
- **Changed**: Copilot now types short single-line messages instead of pasting them, prefers Ctrl+S when the footer advertises `ctrl+s run command`, and continues through submit retries as needed
- **Fixed**: Copilot submit confirmation no longer treats repeated WAITING output as success; it waits for visible progress or prompt disappearance
- **Fixed**: Quota and limit errors now mark tasks as failed instead of returning a normal reply

### v0.15.6

- **Added**: Secret-gated live E2E GitHub Actions workflow for `claude`, `codex`, `gemini`, `opencode`, and `copilot`
- **Added**: Live E2E workflow validation for CLI installation, job timeout, and auth secret wiring
- **Fixed**: Copilot reply cleaning for new TUI noise patterns including permission prompts and `Esc to stop`
- **Fixed**: Copilot live E2E CI now installs the standalone `copilot` CLI and fails CI when a selected CLI is missing

### v0.15.5

- **Added**: `clean_copilot_response()` — strips Ink TUI artifacts (spinners, borders, status bars, input echo) from Copilot reply artifacts
- **Added**: Copilot Ctrl+S submit fallback for Copilot CLI 1.0.7 Ink TUI
- **Fixed**: Copilot reply artifacts no longer contain TUI garbage
- **Fixed**: Server-mode logging no longer leaks to PTY — redirected to `~/.synapse/logs/`

### v0.15.4

- **Added**: Auto-spawn support for workflow run — agents spawned on demand when not running
- **Added**: Workflow-as-skill auto-generation — SKILL.md created from workflow YAML for slash-command discovery
- **Added**: `synapse workflow sync` CLI command for bulk skill synchronization
- **Fixed**: YAML frontmatter injection prevention, `auto_spawn` boolean validation, skill-creator script hardening

### v0.15.3

- **Added**: Agent Control drag-resize splitter — draggable separator between panels with localStorage persistence and keyboard support
- **Changed**: History moved to Canvas sub-menu (`nav-sub` class)

### v0.15.2

- **Added**: Name prompt placeholder — auto-suggests a petname (e.g., `Name [Enter = claude-agent]:`)
- **Added**: Save ID prompt placeholder — suggests petname based on agent context
- **Changed**: Canvas menu "Admin" renamed to "Agent Control", reordered before System

### v0.15.1

- **Added**: Canvas `artifact` card format — interactive HTML/JS/CSS applications in sandboxed iframes (like Claude.ai Artifacts)
- **Added**: Copilot submit fallback chain — cycles through alternative submit sequences on each confirmation retry
- **Added**: Context delta for task responses — `--wait`/`--notify` replies prefer PTY output since task start
- **Fixed**: MCP setup docs — removed unnecessary `--agent-id`/`--agent-type`/`--port` from client config examples
- **Fixed**: Copilot PTY input not processed when `\r` alone fails to trigger Ink TUI submission

### v0.15.0

- **Added**: Admin terminal jump — double-click agent row to jump to its terminal (tmux, VS Code, Ghostty, iTerm2)
- **Added**: Parent process chain detection for accurate terminal identification
- **Fixed**: System menu polling flicker (JSON comparison, `replaceChildren`, scoped animation)
- **Fixed**: Table overflow on narrow screens (responsive wrapping, Agent table horizontal scroll)
- **Fixed**: Test DB pollution in `test_canvas_server` and `test_response_option`

### v0.14.0

- **Added**: Canvas HTML Artifact Support — interactive HTML/JS/CSS in sandboxed iframes with theme sync (`postMessage`), auto-resize (`ResizeObserver`), CSS variables (`--bg`, `--fg`, `--border`), and full document normalization
- **Changed**: Extracted `broadcastThemeToIframes` helper, conditional ResizeObserver/setTimeout

### v0.13.0

- **Added**: Task Board UX improvements — dynamic agent name resolution, table-format CLI with `--verbose`/`--format json`, `fail_reason` inline display
- **Added**: Task Board grouping — `group_id`/`component`/`milestone` columns, `--group-by` CLI view, Canvas view toggle (Status|Group|Component)
- **Added**: `purge_stale`/`purge_by_ids` with `--older-than`/`--dry-run` CLI flags
- **Changed**: Cached `AgentRegistry` in `resolve_display_name` to avoid N+1 instantiation
- **Fixed**: Canvas task view toggle state persists across polling refreshes
- **Fixed**: Canvas task card expand state preserved across polling updates
- **Fixed**: Task descriptions now render as Markdown in Canvas task cards
- **Fixed**: View toggle active tab contrast improved for clear visibility

### v0.12.2

- **Fixed**: Admin reply receiver now strips terminal junk from auto-notify artifact responses
- **Added**: "Reuse Existing Infrastructure" design principle in CLAUDE.md and AGENTS.md

### v0.12.1

- **Added**: Canvas Admin Command Center — browser-based view (`#/admin`) for sending messages to agents and managing agent lifecycle
- **Added**: Admin API endpoints on Canvas server (`/api/admin/agents`, `/api/admin/send`, `/api/admin/replies/{id}`, spawn/stop)
- **Changed**: Admin response flow replaced artifact-polling with reply-based architecture (`synapse reply` via `POST /tasks/send` callback), eliminating terminal junk issues
- **Added**: `link-preview` Canvas format with OGP metadata fetching and server-side enrichment
- **Added**: `synapse canvas link <url>` CLI command for posting rich link preview cards
- **Fixed**: SSRF redirect validation, streaming 64KB read, parallel OGP fetch, CSS token fix, test isolation
- **Fixed**: IME composition (Japanese/Chinese input) no longer triggers premature send
- **Fixed**: Double-send prevention when clicking Send rapidly

### v0.12.0

- **Added**: Smart Suggest — `analyze_task` MCP tool that analyzes user prompts and suggests team/task splits
- **Added**: Plan Card Canvas template with Mermaid DAG + step list + status tracking
- **Added**: `synapse canvas plan` CLI command for posting Plan Cards
- **Added**: `synapse tasks accept-plan` / `sync-plan` for Plan → Task Board integration
- **Added**: Copilot MCP bootstrap support (`~/.copilot/mcp-config.json`)
- **Changed**: Code quality improvements from `/simplify` review (public API usage, ID-based sync)

### v0.11.21

- **Documentation**: Add Scenario 9 — Cross-Worktree Knowledge Transfer (`--force`, `--message-file`)

### v0.11.20

- **Fixed**: Canvas stale process detection via `asset_hash` in `/api/health`
- **Fixed**: Canvas `stop` SIGKILL fallback when SIGTERM fails
- **Changed**: Canvas `status` shows asset hash match and STALE warning

### v0.11.19

- **Fixed**: Copilot CLI enter key not submitting — use bracketed paste mode for PTY input
- **Fixed**: Port availability check on `0.0.0.0` (fixes Errno 48)
- **Fixed**: Tmux pane titles persist with `allow-rename off`

### v0.11.18

- **Fixed**: Port availability check on `0.0.0.0` (fixes Errno 48)
- **Fixed**: Tmux pane titles persist with `allow-rename off`

### v0.11.17

- **Added**: Set tmux pane titles to show agent name (`synapse(claude)` or `synapse(claude:Reviewer)`)
- **Added**: Auto-enable `pane-border-status` so pane titles are visible without manual tmux.conf changes
- **Fixed**: Align `synapse list` help keybinding display

### v0.11.16

- **Fixed**: Send submit_seq twice for Copilot CLI paste buffer flush — resolves enter key not executing when sending messages via `synapse send`
- **Fixed**: Validate `submit_retry_delay` is non-negative in `TerminalController.__init__`

### v0.11.15

- **Added**: `synapse list --json` flag for AI/script-friendly JSON output of agent list
- **Added**: MCP `list_agents` tool for querying agent registry via MCP protocol
- **Changed**: Refactor `SynapseMCPServer.call_tool()` to dispatch pattern for extensibility
- **Documentation**: Update docs, guides, site-docs, and plugin skills for new features

### v0.11.14

- **Fixed**: PR Guardian now separates CodeRabbit check from CI checks and waits for review completion before dispatching `/fix-review`
- **Fixed**: `poll_pr_status.sh` uses `state` field (not `conclusion` which doesn't exist in `gh` CLI)
- **Fixed**: `/fix-review` skill now verifies each finding against current code before applying fixes

### v0.11.13

- **Added**: Block-level `x_title` / `x_filename` metadata fields on `ContentBlock` — styled header above any content block (replaces body-embedded metadata envelopes)
- **Added**: Toast batching for burst SSE updates — multiple card events within 300ms are collapsed into a single summary toast (e.g., "3 cards updated")
- **Added**: SSE initial-connect dedup — `loadCards()` is no longer called redundantly on the first SSE open, only on reconnect
- **Added**: `tip` card format for rendering helpful hints and tips
- **Added**: Browser auto-open on `synapse canvas serve` (suppress with `--no-open`)
- **Fixed**: Remove canvas card height caps — chart cards now expand to fill available space instead of being capped at 400px
- **Fixed**: Expand canvas image cards to available height — images use full viewport area in Canvas view
- **Fixed**: HTML iframe rendering in Canvas view uses full-document structure for consistent height

### v0.11.12

- **Fixed**: Use returned task IDs instead of numeric indices in skill docs and guides
- **Fixed**: Handle invalid UTF-8 `.agent` files in canvas saved agent reader
### v0.11.11

- **Added**: Anthropic official skill-creator plugin, pr-guardian skill with auto-trigger hook
- **Added**: `synapse tasks purge` command to remove all tasks from the Task Board
- **Added**: `--task` / `-T` flag for `synapse send` — link messages to Task Board entries
- **Added**: Auto-claim on receive and auto-complete on finalize for task-linked messages
- **Added**: TaskBoard schema columns `a2a_task_id` and `assignee_hint` for task-message linking
- **Added**: `[Task: XXXXXXXX]` PTY display prefix for task-linked messages
- **Added**: Auto-skip PTY bootstrap when MCP config detected, task board mandatory for delegations
- **Fixed**: Canvas stale process problem with robust PID management
- **Fixed**: Defer spotlight DOM clear to prevent blank fallback rendering
- **Changed**: Simplify canvas process management after code review
- **Documentation**: Update Canvas docs for stale process management


### v0.11.10

- **Fixed**: Test failures from CLAUDE.md slimdown and `LongMessageStore` singleton pollution
- **Fixed**: Missing `user_dir` parameter in `SynapseSettings._load_instruction_file()`
- **Fixed**: Tighten test assertions for storage doc and MCP stdio protocol verification
- **Documentation**: Add per-agent MCP configuration to Getting Started guides

### v0.11.9

- **Added**: MCP bootstrap server (`synapse mcp serve`) for stdio-based instruction distribution
- **Added**: MCP client configuration for Gemini CLI and OpenCode
- **Changed**: Cache `SynapseSettings` in MCP server, deduplicate agent_type parsing, remove dead code
- **Documentation**: Slim down `AGENTS.md`, improve `code-simplifier` skill, add MCP design doc

### v0.11.8

- **Fixed**: `synapse canvas stop` now detects server via health endpoint (works with foreground `serve`)
- **Fixed**: Verify `synapse-canvas` service identity before killing process
- **Fixed**: `canvas stop` accepts `--port` for non-default ports

### v0.11.7

- **Fixed**: Include canvas templates and static files in package data (fixes "template not found" on pip install)

### v0.11.6

- **Changed**: Increase `MAX_BLOCKS_PER_CARD` from 10 to 30 for richer composite cards

### v0.11.5

- **Added**: Dashboard view with expandable summary+detail widgets (Agents, Tasks, File Locks, Worktrees, Memory, Errors)
- **Added**: Clickable task cards with detail view (description, priority, created by, created at)
- **Changed**: Dashboard widgets use progressive disclosure — compact summary by default, full table on expand

### v0.11.4

- **Added**: Dedicated `#/system` route for the Canvas System panel
- **Added**: Expanded System view with skills, sessions, workflows, environment, and tips sections
- **Added**: Canvas UI visual refresh with glassmorphism accents, iconography, and a refined color palette
- **Fixed**: `Latest Posts` no longer follows dashboard filters; `Agent Messages` filters now hide non-target agent panels

### v0.11.3

- **Added**: Canvas Templates — 5 built-in templates (`briefing`, `comparison`, `dashboard`, `steps`, `slides`) for structured card layouts
- **Added**: `synapse canvas briefing` CLI command for posting structured reports with sections
- **Added**: Canvas cache-busting and SSE reconnection fixes for reliable browser display
- **Fixed**: Canvas View empty after server restart (stale JS cache)
- **Fixed**: Mermaid diagrams overlapping sections (auto-sizing SVGs)

### v0.11.2

- **Changed**: Task board lifecycle commands accept unique short task ID prefixes
- **Fixed**: Canvas raw JSON posts autofill `agent_name` from registry
- **Fixed**: Canvas system panel surfaces registry read errors

### v0.11.1

- **Added**: Completion callback for `--silent` sends — sender-side history is updated (`sent` -> `completed`/`failed`/`canceled`) via best-effort callback when the receiver finishes processing
- **Added**: `POST /history/update` API endpoint for receiver-to-sender history status notification
- **Added**: `HistoryManager.update_observation_status()` for atomic history record updates with metadata merge
- **Added**: Proactive Mode — `SYNAPSE_PROACTIVE_MODE_ENABLED=true` injects mandatory checklist for using all Synapse features (task board, shared memory, canvas, file safety, delegation, broadcast)
- **Added**: New proactive mode user guide and specification document

### v0.11.0

- **Added**: Canvas SPA routing — `#/` (full-viewport Canvas view) and `#/history` (History view with system panel, live feed, agent messages)
- **Added**: Highlight.js syntax highlighting for `code` and `file-preview` card formats, side-by-side diff renderer, HTML iframe full-height in Canvas view
- **Added**: Chart.js supports all types (bar, line, pie, doughnut, radar, polarArea, scatter, bubble)
- **Changed**: Content size limit increased from 500KB to 2MB per content block
- **Changed**: Theme toggle moved to header level (visible in both Canvas and History views)
- **Changed**: Canvas performance — debounced rendering, skip-unchanged spotlight, O(n) latest card lookup
- **Changed**: iframe sandbox reverted to `allow-scripts` only (security fix)
- **Fixed**: `from_dict` guards non-dict content input
- **Fixed**: `simpleMarkdown` blocks `javascript:` URLs (XSS hardening)
- **Fixed**: `card_id` is globally unique (not per-agent); server returns 403 on cross-agent reuse

### v0.10.1

- **Changed**: Skill Progressive Disclosure — `synapse-a2a` SKILL.md reduced from 877→159 lines, `synapse-manager` from 426→199 lines. Detail moved to `references/` for on-demand loading
- **Added**: Manager helper scripts (`wait_ready.sh`, `check_team_status.sh`, `regression_triage.sh`) for deterministic operations
- **Added**: Skill structure tests (`test_skill_structure.py`) enforcing Progressive Disclosure best practices
- **Fixed**: tmux pane scoped splitting — `split-window` now targets `$TMUX_PANE` so new panes stay next to the source pane instead of applying a global layout
- **Removed**: `synapse-docs` from plugins (dev-only, now in `.agents/skills/` only)

### v0.9.5

- **Fixed**: Spawn pane layout (#336) — `synapse spawn` creates side-by-side panes instead of top-bottom
- **Fixed**: ANSI escape sequences in A2A replies (#337) — `get_context()` strips ANSI codes
- **Changed**: Task receipt collaboration flow — agents delegate independent work units via `synapse spawn` + `synapse send --silent`

### v0.9.4

- **Fixed**: `synapse init` data loss — was replacing entire `.synapse/` directory, destroying saved agent definitions, databases, sessions, workflows, and worktrees. Now uses merge strategy (template files only).
- **Added**: `synapse status <target>` command — detailed single-agent view with uptime, current task elapsed time, recent messages, file locks, and task board assignments (supports `--json` output)
- **Added**: Compound signal status detection — PROCESSING-to-READY transitions now check `task_active` flag and file lock state to prevent premature status changes
- **Added**: WAITING detection improvements — fresh-output-only matching eliminates false positives from old buffer content; auto-expiry when pattern disappears from visible buffer
- **Added**: Elapsed time display in CURRENT column of `synapse list` (e.g., `Review code (2m 15s)`)
- **Changed**: `parallel-docs-simplify-sync` skill now uses Claude Code built-in `/simplify` instead of custom subagent

### v0.9.3

- **Added**: Proactive Collaboration Framework — agents receive a decision framework at startup for when to delegate, ask for help, report progress, and share knowledge
- **Added**: Cross-model spawn preference — agents are guided to spawn different model types for diverse perspectives and rate limit distribution
- **Added**: Worker autonomy — worker agents can proactively spawn helpers, delegate subtasks, and request reviews
- **Added**: USE SYNAPSE FEATURES ACTIVELY section — explicit guidance for task board, shared memory, file safety, worktree, broadcast, and history
- **Added**: TRANSPORT column in text-mode `synapse list` for scripted use
- **Changed**: synapse-manager Step 1 now checks existing agents before spawning
- **Changed**: Mandatory cleanup enforcement for spawned agents across all skill docs

### v0.9.2

- **Added**: `synapse session restore --resume` flag to resume each agent's CLI conversation session
  - Saved sessions now capture `session_id` from the agent registry
  - Per-agent resume args: Claude (`--resume`/`--continue`), Gemini (`--resume`), Codex (`resume`/`resume --last`), Copilot (`--resume`), OpenCode (no support)
  - Shell-level time-guarded fallback: if resume fails within 10 seconds, retries without resume args
- **Added**: `synapse session sessions` command to browse CLI tool session files from the filesystem
  - Supports Claude, Gemini, Codex, and Copilot session discovery
  - Filter by `--profile` and `--limit`; sorted by modification time (newest first)
- **Added**: Automatic `session_id` capture from CLI tool filesystems on agent startup (`synapse/session_id_detector.py`)
  - Background detection after readiness gate; stored in agent registry for use by `session save`
- **Changed**: `synapse session show` now displays `session_id` for each agent entry

### v0.9.1

- **Added**: Saved Workflows (`synapse workflow`) — define and replay reusable message sequences to running agents
- **Added**: Enhance help discoverability for root/team/session commands
- **Fixed**: Corrupted YAML no longer bypasses workflow overwrite protection
- **Fixed**: Validate WorkflowStep target/message are `str` type
- **Docs**: Add workflow guide and CLI reference to GitHub Pages

### v0.9.0

- **Added**: Session Save/Restore (`synapse session`) — save and restore team configurations as named snapshots
- **Docs**: Add Session Save/Restore guide, update CLI reference and plugin skills

### v0.8.6

- **Changed**: Unify agent example names with model-hinting English names (Claud, Cody, Rex, Gem)
- **Docs**: Expand delegate-mode guide with architecture, config, and use cases
- **Docs**: Document `--agent`/`-A` flag for starting agents with saved agent definitions
- **Docs**: Document role file conventions, petname ID format, scope precedence, `.agent` file format
- **Docs**: Update all site-docs, guides, CLAUDE.md, and plugin skills with consistent agent names

### v0.8.5

- **Changed**: Replace copyrighted character names with generic English names (Alice, Bob, Charlie, Dave, Eve, Frank)
- **Docs**: Add skill installation guide (`npx skills add`) to Getting Started and Skills pages
- **Docs**: Add `synapse-reinst` to Built-in Skills; remove `doc-organizer` from core install tables

### v0.8.4

- **Added**: Synapse-native worktree isolation (`--worktree` / `-w`) for all agent types
  - Isolated git worktrees under `.synapse/worktrees/` with auto-generated or explicit names
  - Automatic cleanup on exit; prompts if unsaved changes or new commits exist
  - Per-agent worktrees in `synapse team start --worktree`
  - API support via `POST /spawn` with `worktree` field
  - `[WT]` indicator in `synapse list`
- **Fixed**: Worktree name validation, defensive subprocess handling, cleanup error recovery

### v0.8.3

- **Breaking**: Unify `.gemini/skills/` into `.agents/skills/` — Gemini now uses the same skill directory as Codex, OpenCode, and Copilot
  - **Migration**: copy or move skills from `.gemini/skills/` to `.agents/skills/`
  - TUI deploy indicators simplified from `[C✓ A✓ G·]` to `[C✓ A✓]`
- **Changed**: Add `synapse-docs` skill to `plugins/` source of truth
- **Fixed**: `AgentProfileStore` scope inconsistency — shutdown save now uses startup store

### v0.8.2

- **Changed**: Unify agent identifier terminology — **Runtime ID** (`synapse-claude-8100`) vs **Agent ID** (`wise-strategist`)
- **Changed**: Response mode refactoring — replaced `--response`/`--no-response` flags with `--wait`/`--notify`/`--silent`
  - `--wait`: Synchronous blocking (replaces `--response`)
  - `--notify`: Async notification on completion (new default)
  - `--silent`: Fire-and-forget (replaces `--no-response`)
- **Fixed**: IDLE status bug in task completion detection
- **Added**: Controller status-change callback for proactive completion detection

### v0.8.1

- **Fixed**: Add missing `manager` and `documentation` skill set definitions to bundled defaults
- **Fixed**: Merge `coordinator` skill set into `manager` (adds `synapse-reinst`)
- **Docs**: Update skill set tables across all documentation to reflect 6 default sets

### v0.8.0

- **Added**: Saved Agent Manager — reusable agent configurations via `synapse agents` commands
- **Added**: Completion callback for `--silent` task tracking (`POST /history/update`)
- **Added**: Sender identification in PTY-injected A2A messages
- **Added**: Ghostty split pane support for `team start` and `spawn`
- **Added**: Agent name uniqueness enforcement across interactive start, spawn, and team start
- **Added**: Save-on-exit prompt for interactive named agents
- **Added**: `synapse-manager` skill — structured 5-step multi-agent management workflow
- **Added**: `manager` and `documentation` skill sets for multi-agent management and docs-focused agents
- **Added**: `doc-organizer` skill — documentation audit, restructure, and deduplication
- **Changed**: `synapse spawn` and `synapse team start` accept saved-agent ID/name
- **Changed**: Reply target persistence moved to dedicated `~/.a2a/reply/` directory
- **Changed**: Registry writes hardened with registry-wide lock and atomic name conflict rejection
- **Changed**: Agent spec format simplified to `profile[:name[:role[:skill_set[:port]]]]`
- **Fixed**: Ghostty split panes (`Cmd+D`) instead of new windows, clipboard paste for commands
- **Fixed**: Ghostty panes auto-close on agent exit
- **Fixed**: Port pre-allocation in `team start` to avoid race conditions
- **Fixed**: Shared memory bugs (#286-#291) and memory CLI tag parsing
- **Fixed**: Soft interrupt priority corrected (p5→p4)
- **Fixed**: `registry.py` `list_agents()` handles `KeyError` gracefully
- **Docs**: Saved-agent definitions guide and CLI reference

### v0.7.0

- **Added**: Shared Memory for cross-agent knowledge sharing (`synapse memory` commands)
- **Added**: GitHub Pages documentation site with MkDocs Material
- **Added**: github-pages-sync skill for site-docs maintenance
- **Docs**: Sync list and configuration docs with current implementation

### v0.6.12

- **Fixed**: Store identity instructions in files via LongMessageStore (prevents Ink TUI paste collapse)
- **Fixed**: Update Installers workflow version extraction with `gh release view` fallback
- **Fixed**: Copilot CLI write_delay increased to 0.5s for reliable submit
- **Tests**: Shared test helper `read_stored_instruction` in `tests/helpers.py`

### v0.6.11

- **Fixed**: Per-profile `write_delay` for Copilot CLI submit timing
- **Fixed**: Prevent REPLY EXPECTED marker duplication
- **Fixed**: PTY_WRITE_MAX constant for kernel buffer safety
- **Fixed**: Auto-release → publish → update-installers workflow chain

### v0.6.10

- **Added**: Injection observability with INJECT/* structured logs
- **Added**: Soft interrupt command (`synapse interrupt`)
- **Added**: Token/cost tracking skeleton (`TokenUsage` dataclass)

### v0.6.x Series

- Copilot CLI profile and spawn support
- Tool args passthrough (`synapse spawn claude -- --worktree`) — Synapse-native `--worktree` flag is now recommended; passthrough remains supported for Claude Code
- Send UX improvements (message-file, stdin, auto-temp)
- File attachment support (`--attach`)

### v0.5.x Series

- Agent Teams features (B1-B6)
- Shared Task Board with dependencies
- Quality Gates (hooks)
- Plan Approval workflow
- Graceful Shutdown
- Delegate Mode
- Auto-Spawn Panes

### v0.4.x Series

- Skills system with TUI manager
- Multi-scope skill deployment
- Skill sets for grouped capabilities
- Interactive setup with name/role

### v0.3.x Series

- Task history (enabled by default)
- File Safety system
- Learning mode
- Settings management TUI
- External agent connectivity

### v0.2.x Series

- Core A2A implementation
- Multi-agent communication
- Agent registry
- Priority levels
- @Agent pattern routing

## Version Policy

Synapse A2A follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)
