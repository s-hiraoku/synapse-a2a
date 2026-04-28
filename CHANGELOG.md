# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Artifact text formatting now strips PTY control bytes before persisting or returning A2A output, preventing raw terminal redraw content from leaking into `recent_messages` (#664).

## [0.31.0] - 2026-04-28

This release rolls up a "status precision" family that sharpens what `synapse list` / `synapse status` show during long-running and rate-limited work, plus a new one-shot `synapse watchdog check` command for surfacing stuck agents. Status precision now covers `RATE_LIMITED` (#561), the `SENDING_REPLY` sub-state (#644), HTTP `input_required` (#651), and a true PTY-level interrupt path with `mode=pty|signal|auto` (#647). Observability of recent messages is hardened by including parent-side A2A sends (#659), keeping `output_text` reserved for agent responses (#660), and using millisecond-precision history timestamps (#661). The default agent instructions also now describe `synapse memory` as legacy in favor of LLM Wiki (#527). Includes the previously unreleased READY-send delay (#467), the workflow target-resolution fix (#568), and the `/dev-issue` skill that were staged on `main` after the 0.29.0 tag but never shipped.

### Added

- `synapse watchdog check` command for one-shot stuck-agent detection (#646). Stage 1 MVP scans every live agent, prints `ID / STATUS / UPTIME / SAME_STATUS_FOR / LAST_OUTBOUND / ALARM`, and flags `RATE_LIMITED > 30m`, `SENDING_REPLY > 60s`, `PROCESSING > 30m` with no outbound A2A in 10m, and "spawn never ready". `--alarm-only` filters; `--json` emits an array. Stage 2-4 (background daemon, push notifications, multi-watchdog locking, automatic recovery) are future work.
- Surface HTTP task `input_required` state in `synapse list` / `synapse status` so a parent operator sees the approve URL without an extra HTTP query (#651).
- Surface child agent reply-send stalls via `SENDING_REPLY` sub-state and per-agent Recent Messages filter (#644).
- True PTY-level interrupt API (`mode=pty|signal|auto`) for stuck agents (#647). Per-profile defaults for Claude, Codex, Gemini, Copilot, and OpenCode preserve existing SIGINT broadcast behavior for signal-mode callers.
- Surface LLM provider rate limits as `RATE_LIMITED` agent status (#561). Overrides `PROCESSING` / `READY` / `WAITING_FOR_INPUT` until the agent recovers.
- Delay sends to READY agents to avoid interrupting user input (#467).
- **`/dev-issue <number>` slash command (skill):** bootstraps a new issue implementation in one step — fetches the issue and related closed PRs in parallel, greps the repo for code hotspots from the body, infers a branch prefix from labels and a slug from the title, generates a structured task brief at `/tmp/issue<num>-task.md` (mirroring the handwritten brief format used in recent issue → codex spawn flows like #467), creates a fresh branch from latest `origin/main`, and (by default) spawns a codex agent with `synapse spawn codex --task-file ... --notify`. Supports `--solo` (skip spawn) and `--dry-run` (brief only, no branch / no spawn). Canonical at `plugins/synapse-a2a/skills/dev-issue/SKILL.md`, mirrored to `.agents/skills/dev-issue/` and `.claude/skills/dev-issue/` via sync.

### Changed

- Default agent instructions (`synapse://instructions/default`) now describe `synapse memory` as legacy and direct callers needing that interface to fetch `synapse://instructions/shared-memory` explicitly. New agents are guided to LLM Wiki by default; the `synapse memory` CLI commands and the `shared-memory` MCP resource are unchanged for backward compatibility (#527).

### Fixed

- `recent_messages` timestamps now use millisecond precision so rapid history writes within the same second can still be ordered distinctly (#661).
- Parent-side `synapse send` observations no longer write placeholder text into `output_text`, keeping recent message output reserved for agent responses (#660).
- `synapse status <agent> --json` recent messages now include parent-side A2A sends to the agent (#659).
- `clear_reply_target()` now swallows cleanup `PermissionError`/`OSError` failures so sandbox unlink errors no longer mask successful reply sends (#653).
- Workflow target type resolution now respects the caller working directory (#568).
- `HistoryManager.list_observations` now applies a SQL `LIMIT` again so callers (`synapse status`, `synapse watchdog check`) no longer read the entire observations table on every invocation. With `agent_id` set, a generous prefetch buffer keeps the post-filter accurate.

### Refactored

- `Controller.interrupt` and `Controller.interrupt_via_pty` share a `_mark_interrupt_dispatched` helper for the post-interrupt PROCESSING status update, removing duplicated lock + dispatch tail.
- `synapse/a2a_compat.py` and `synapse/controller.py` now use the `READY` / `PROCESSING` / `DONE` constants from `synapse.status` for status comparisons (replaces residual string literals).

### Documentation

- Address CodeRabbit feedback on the skills-role RFC (#625 follow-up, #657): correct the future-dated "2026-04-21 時点" reference, reflow a CommonMark line break that rendered as an unintended space, and clarify local dev policy precedence.

## [0.29.0] - 2026-04-26

Minor release surfacing the `WAITING_FOR_INPUT` agent status for non-permission A2A `input_required` waits (#538) and closing the registry status drift that left `synapse list` showing stale `PROCESSING` after every task in `task_store` had finalised (#569). Together they make `synapse list` a faithful view of `task_store` reality across both forward (working → terminal) and sideways (input_required → permission vs non-permission) transitions. No detection-logic changes outside the A2A status callback path; controller PTY scope is unchanged.

### Added

- **`WAITING_FOR_INPUT` agent status (#538):** non-permission A2A `input_required` tasks now surface as a distinct registry/list/status state, while permission prompts keep the existing `WAITING` state.

### Fixed

- **Agent registry status sync (#569):** A2A status callbacks now demote stale registry `PROCESSING` / `WAITING_FOR_INPUT` states back to `READY` when the task store is non-empty and all tasks are terminal, preventing `synapse list` from showing active work after every task has completed.

## [0.28.3] - 2026-04-26

Patch release for the Phase 1.5 polish work tracked in #635 / #630 and merged via #638. Operationally focused: warns less right after PtyRenderer boot, honors `HOME` overrides in tests, lets cron capture JSON reports atomically, and documents the `--timeout 0` fast-fail mode so operators don't read it as "no timeout". No detection-logic changes; Phase 2 remains out of scope.

### Added

- **`synapse waiting-debug collect --timeout SECONDS`** — override the HTTP timeout used when querying `/debug/waiting` on each registered agent. Default is now **5.0 s** (previously hard-coded 3.0 s), which eliminates a common warn-flood immediately after PtyRenderer boots when agents can't respond within 3 s (#635).
- **`synapse waiting-debug report --out PATH`** — write the aggregated JSON report to a file instead of stdout. When `--out` is set, stdout is kept empty so the flag is safe to use from cron/scripting without capturing mixed text/JSON output (#635).

### Changed

- **`synapse/commands/waiting_debug.py::default_waiting_debug_path()`** — the default JSONL path (`~/.synapse/waiting_debug.jsonl`) is now resolved lazily per call rather than at module import time. Tests and tools that export `HOME=/tmp/...` now actually redirect collection/reporting instead of silently using the real home. The module-level `DEFAULT_WAITING_DEBUG_PATH` constant is removed — callers either pass `out_path=` / `input_path=` explicitly or let the class resolve the default internally (#635).
- **`WaitingDebugReporter._record_is_since` — warn on unparseable `collected_at`:** records whose timestamp can't be parsed are still skipped, but now emit `Warning: record at line N has unparseable collected_at: '<value>' (<reason>)` to stderr, matching the existing behavior for invalid JSONL lines (#635).
- **`waiting-debug collect --timeout` argparse validation:** negative values are now rejected at argparse time (`--timeout must be >= 0`) instead of being passed through to `urllib`. Zero is still accepted and forwarded as the deliberate "fail fast / never wait" mode (#635, CodeRabbit follow-up).
- **`waiting-debug report --out` is now atomic:** the JSON report is written to a sibling temp file and `os.replace`d into place, so concurrent readers (e.g. cron-driven dashboards) never see a half-written file (#635, CodeRabbit follow-up).

### Fixed

- **Closes #630 (Phase 1.5 persistence pipeline):** the Phase 1.5 collection pipeline shipped in #632 is now operationally stable with the polish above. Scheduling, retention, and SQLite export remain optional operator-side concerns (docs in `docs/phase15-collection.md`).
- **`WaitingDebugReporter._record_is_since` dead branch removed:** the `if collected_dt is None` check after `_parse_iso_datetime` was unreachable when `collected_at` is a `str` (the only path that reaches it), so the dead branch is gone (#635, CodeRabbit follow-up).

## [0.28.2] - 2026-04-24

Patch release rolling up the Phase 1.5 operational runbook, the Anthropic `--dangerously-skip-permissions` deprecation migration, a Copilot WAITING false-positive fix (bracketed-paste markdown echoes), the new auto-resolve-conflicts CI workflow, and post-release code cleanup across the command layer. No detection-logic changes to the WAITING pipeline itself; Phase 2 remains out of scope.

### Added

- **Phase 1.5 operational runbook (`docs/phase15-collection.md` + mirrors):** launchd scheduling recipe for macOS, CLI-bump requirement for the new `waiting-debug` verb, and the legacy `/debug/waiting` 404 caveat for agents that predate Phase 1 (plus a 503 case for v0.28.0+ agents whose controller lacks the `waiting_debug_snapshot` capability). Guides, skills, and `site-docs/troubleshooting.md` gain short callouts + cross-links so the operator path is navigable from either `synapse --help` or the site.
- **`guides/references.md` §1.26 `synapse waiting-debug`:** the CLI reference previously jumped from §1.25 to the API section without documenting the new subcommand.
- **Auto Resolve Mechanical Conflicts workflow (`.github/workflows/auto-resolve-conflicts.yml`, #633):** GitHub Actions workflow that detects merge conflicts on `push` to `main` and on `pull_request` events, then auto-resolves the three "mechanical" cases — `CHANGELOG.md` union-merge (new `scripts/merge_changelog.py`), `uv.lock` regeneration via `uv lock`, and version-line conflicts in `pyproject.toml` / `plugins/*/.claude-plugin/plugin.json` (new `scripts/merge_version_line.py`, picks the higher semver). Anything outside these patterns is left untouched and the PR gets a `needs-manual-rebase` label. Forks are skipped (no push permission via default `GITHUB_TOKEN`). Create the label once with `gh label create needs-manual-rebase --color d73a4a --description "Auto-resolve bailed out; manual merge/rebase required"`.

### Changed

- **Default auto-approve flag migration — Claude Code `--dangerously-skip-permissions` → `--permission-mode=auto`:** Anthropic deprecated the legacy flag in favor of the safety-classifier `auto` mode. `synapse/profiles/claude.yaml`, `synapse/settings.py` (`DEFAULT_SETTINGS` coordinator), and the `synapse-a2a` / `synapse-manager` skill references now ship the new flag by default. The legacy form is preserved in each profile's `alternative_flags` so in-flight scripts keep working. Gemini (`--approval-mode=yolo` over `--yolo`/`-y`) reflects the same upstream guidance. Existing `synapse spawn` / `synapse team start` invocations continue to auto-inject the flag — no user action required.
- **Copilot `waiting_detection.regex` hardened against bracketed-paste markdown echoes:** the prior regex matched any `^\s*\d+\.` line, so when the user pasted markdown numbered lists / blockquotes / bullets via `synapse send`, Copilot's bracketed-paste echo of the user's own message flipped status to WAITING and tricked the submit-confirmation loop into reporting success without re-pressing Enter. The regex is now anchored on Copilot's actual approval verbs (Yes/No/Allow/Deny/Approve/Skip) and `heuristic_fallback` is disabled for this profile (the generic `❯/›/●` anchors collide with Copilot's own input prompt redraws). Regression coverage added in `tests/test_compound_signal.py` and `tests/test_copilot.py`.
- **Copilot profile `long_submit_confirm_retries` tuning** and related `tests/test_auto_approve.py` adjustments to match the new auto-approve flag set.
- **`synapse/commands/status.py` + `synapse/commands/waiting_debug.py`: DRY the shared `_http_get_json` and `_format_counter` helpers.** `StatusCommand` now imports both from `waiting_debug` (single source of truth); `urllib.request` dropped from `status.py` as a consequence.
- **`synapse/utils.format_renderer_suffix()` extracted** and used from `synapse/commands/status.py`, `synapse/commands/list.py`, and `synapse/commands/renderers/rich_renderer.py` — the three independent implementations of `" (renderer: on/off)"` are now one helper.
- **`synapse/skills.parse_skill_frontmatter` no longer stores `""` for container-typed frontmatter keys;** behavior now matches the pre-existing "skip containers" comment. Shipped scalar-only frontmatter is unaffected; covered by existing `tests/test_skills.py::TestParseFrontmatter`.

### Fixed

- **`synapse/commands/waiting_debug.py::_iter_records` TOCTOU:** replaced `if not path.exists(): return []` followed by `path.open(...)` with `try: path.open(...) except FileNotFoundError`. Prevents the (unlikely) race where the JSONL is unlinked between the `exists()` probe and the `open()` call.
- **`synapse/canvas/server.py` noise removal:** deleted the `_load_json_mcp = _load_json_mcp_section` local alias (inlined into the four `lambda`s), and removed the WHAT-comment over the `tomllib` version check.

### Documentation

- **`guides/profiles.md`:** the `copilot.yaml` snippet now matches the shipped file (new anchored regex + `heuristic_fallback: false`) with operator-facing rationale. The prior snippet showed the pre-bracketed-paste-fix regex.
- **`guides/troubleshooting.md`:** two new operational callouts (Phase 1.5 CLI-bump requirement + legacy 404 caveat) with cross-links to `docs/phase15-collection.md`, matching the skill + site-docs narrative so guide users aren't left chasing "invalid choice" errors.
- **`site-docs/troubleshooting.md`:** new "WAITING Detection Diagnostics (v0.28.0+)" subsection consolidating `--debug-waiting`, `waiting-debug collect/report`, the `(renderer: off)` annotation, and cross-links to the agent-management guide + API reference + CLI reference.
- **`site-docs/reference/{api,cli-cheatsheet,cli}.md`:** `GET /debug/waiting` schema, `--debug-waiting` flag row, and new "Waiting-Debug (Phase 1.5 Collection)" CLI section with bump + legacy-404 admonitions.

### Tests

- **`tests/test_copilot.py::test_profile_waiting_regex_ignores_pasted_markdown`** — regression matrix of 10 pasted-markdown samples (numbered lists, blockquotes, bullets, mixed content) that must NOT match Copilot's waiting regex.
- **`tests/test_copilot.py::test_profile_disables_heuristic_fallback`** — guards the explicit `heuristic_fallback: false` invariant for Copilot.
- **`tests/test_compound_signal.py::WAITING_NEGATIVE_CASES`** — 6 new Copilot negative cases covering the same markdown-echo scenarios end-to-end through the compound-signal path.
- **`tests/test_claude_profile.py`** — new suite covering the `--permission-mode=auto` migration for the Claude profile and settings.
- **`tests/test_merge_changelog.py`, `tests/test_merge_version_line.py`:** coverage for the two new auto-resolve helper scripts used by the CI workflow.

## [0.28.1] - 2026-04-23

Patch release that rolls up the Phase 1 documentation coverage and Phase 1.5 collection pipeline that landed on `main` after the `v0.28.0` tag was cut. No code changes to the WAITING detection itself; Phase 2 (detection logic changes) remains out of scope.

### Added

- **`synapse waiting-debug` CLI — Phase 1.5 collection pipeline (#630, #632):** `synapse waiting-debug collect` appends per-agent `/debug/waiting` snapshots to `~/.synapse/waiting_debug.jsonl` (user-scoped so data accumulates across projects); `synapse waiting-debug report [--since] [--agent] [--json]` produces aggregate counts (profile, `pattern_source`, `path_used`, `confidence`, `idle_gate_drops`, `renderer_unavailable_agents`) for Phase 2 analysis. Collector continues on per-agent errors and skips empty attempts by default (`--include-empty` overrides). `.synapse/waiting_debug.*` added to `.gitignore`. New `docs/phase15-collection.md` documents the CLI plus cron and launchd scheduling recipes (5-minute cadence).

### Documentation

- **WAITING observability reference coverage (#608, #631):** `synapse-a2a` skill references (`api.md`, `commands.md`) now document `GET /debug/waiting` (response shape, field semantics, 503 fallback), the `--debug-waiting` flag and its aggregate output, the `renderer_available` JSON field, and the `WAITING (renderer: off)` plain-text annotation. `site-docs/guide/agent-management.md` gains new "Renderer Availability" and "WAITING Detection Diagnostics" subsections describing the pyte fallback, the `(renderer: off)` behavior, and how to read `--debug-waiting` aggregates + per-attempt rows. Canonical skill changes mirrored to `.agents/skills/` and `.claude/skills/`.

### Fixed

- **`tests/test_skill_structure.py::TestSyncedSkillParity` for externally-registered skills (#629):** the `opensrc` skill (registered from `vercel-labs/opensrc` into `.agents/skills/opensrc` and `.claude/skills/opensrc`) is not part of the `synapse-a2a` plugin distribution, so the `no_orphan_synced_skills` check was failing. Added `metadata.internal: true` plus `source` and `note` fields to the frontmatter; the test already exempts skills whose `metadata` contains `internal: true`.

## [0.28.0] - 2026-04-22

### Added

- **WAITING detection observability layer — Phase 1 (#608, #627):** `IdleDetector` now maintains an in-memory ring buffer of recent WAITING-detection attempts capturing `path_used` (renderer/strip_ansi), `renderer_on`, `pattern_matched`, `pattern_source` (primary/heuristic), `confidence`, `idle_gate_passed`, `new_data_hex_prefix` (raw 64-byte prefix), and `rendered_text_tail` (last 256 chars). `TerminalController` wraps `PtyRenderer` initialisation in try/except and exposes `renderer_available` so silent pyte failures become observable. New `/debug/waiting` endpoint returns `waiting_debug_snapshot()`; `synapse status <agent> --debug-waiting` prints recent attempts plus aggregates (total, match ratio, path usage, confidence distribution, idle-gate drops). `synapse list` / `synapse status` now annotate status with `(renderer: off)` and emit `renderer_available` in JSON. Phase 1 is observation only — detection logic, regexes, and `require_idle` gate are intentionally unchanged; Phase 2 will use the data collected here.
- **Canvas Skills Viewer (`#/harnesses/skills`):** new SPA sub-view that lists every discovered skill grouped by scope (User Global, Synapse Global, Plugin, and per-active-project), powered by per-project skill scans against `discover_skills()`. Frontmatter is parsed with PyYAML (replacing the prior hand-rolled regex), so quoted colons, multi-line values, and other YAML edge cases now parse correctly.
- **Canvas MCP Servers Viewer (`#/harnesses/mcp`):** new SPA sub-view that inventories MCP servers from every active project's `.mcp.json` plus the five user-scope agent configs (Claude Code `~/.claude.json`, Codex `~/.codex/config.toml`, Gemini `~/.gemini/settings.json`, OpenCode `~/.config/opencode/opencode.json`, and Claude Desktop `~/Library/Application Support/Claude/claude_desktop_config.json`). Env values are stripped to keys-only before reaching the UI.
- **`synapse canvas restart` command:** stop-then-start helper for the Canvas server, intended for the `⚠ STALE` case where an older process is still serving cached HTML/JS/CSS after an upgrade. Accepts `--port/-p` and `--no-open`.
- **Worktree-aware default scope on agent-profile save:** the "Save this agent definition?" prompt in `synapse spawn` now defaults to `user` scope inside a worktree (since project-scope profiles vanish on worktree cleanup) and to `project` otherwise. The prompt text inlines the rationale.

### Changed

- **Canvas registry scans consolidated into `_iter_registry_entries{,_with_errors}`:** three previously-duplicated "glob + json.loads + skip-on-error" loops in `canvas/server.py` are now a single iterator pair (one yields dicts, one yields parse errors too). `system_panel` also reuses one loaded entry list instead of re-scanning the registry on every `_collect_static_sections()` call.
- **Skills SKILL.md frontmatter parser switched to PyYAML.** `synapse/skills.py:parse_skill_frontmatter` now delegates to `yaml.safe_load` (with `yaml.YAMLError` as the failure path) and coerces all values to strings. Behavior is unchanged for the existing scalar-only frontmatter in shipped SKILL.md files.

### Documentation

- **Skills role responsibility-matrix RFC (#610):** new `docs/design/skills-role.md` defines skills as A2A presets layered on top of MCP and the CLI, draws explicit boundaries against MCP resources/tools, the CLI, and `gh skill` as the distribution layer, and establishes a drift-detection rule for orphan workflow-autogen skills.
- **Updated Canvas / Skills documentation across `docs/`, `guides/`, `README.md`, and `site-docs/`** to cover the new Harnesses sub-views, `synapse canvas restart`, and the per-project + per-user-agent MCP grouping.

### Removed

- **Orphan autogen skills `my-review` and `user-wf` (#610):** both shipped without backing `.synapse/workflows/*.yaml` and were never referenced from code or docs; deleted from the canonical plugin source and from `.claude/skills/` / `.agents/skills/` to satisfy the new drift rule.

### Fixed

- **Profile command tokenization (#614, #624):** profile command strings with multiple tokens (e.g. `python3 -u dummy_agent.py`) are now split with `shlex` before launch, so profile-defined arguments are executed correctly. (Subsumes the un-tagged `0.27.2` entry below.)
- **Canvas Mermaid render isolation (#398, #626):** a single malformed mermaid card no longer breaks valid diagrams rendered in the same batch — each render failure is isolated per-diagram.

## [0.27.2] - 2026-04-20

### Fixed

- Profile command strings with multiple tokens, such as `python3 -u dummy_agent.py`, are now split with `shlex` before launch so profile-defined arguments are executed correctly.

## [0.27.1] - 2026-04-19

### Documentation

- **Golden Path Quick Start in README (#604, #615):** new top-of-README four-command flow that spins up Claude + Codex agents and verifies cross-agent messaging via a `SYNAPSE_GOLDEN_PATH_OK` sentinel. Renames the former install-focused `## Quick Start` to `## Installation` so the new section owns the name that matches reader intent. Adds `examples/golden-path.md` as a copy-paste-ready recipe.
- **A2A concept overview page (#605, #616):** new `docs/a2a-overview.md` — a one-page explainer (What is A2A? / 3-step mental model / Mermaid diagram / minimum use case / where to go next) so newcomers can grasp the project in under five minutes without wading through the deeper rationale docs.
- **Terminology glossary (#612, #617):** new `docs/terminology.md` — a shared vocabulary reference covering the 16 core terms (Agent, Task, Message, Skill, Policy, Profile, Agent Card, Registry, Worktree, Workflow, Transport, File Safety, LLM Wiki, Shared Memory, Canvas, Readiness Gate) plus 9 supporting terms. Each entry is anchored to the code path / doc / CLI help where it actually lives, and the "Known Inconsistencies" section calls out the `Skill` dual-use and the `Shared Memory` (CLI-active but README-deprecated) trap.

### Tests

- **`test_lifespan` expectation realigned with `spawned_by` kwarg (#618, #620):** `Registry.register()` gained a `spawned_by` keyword in #601 so `server.py:189` now passes `spawned_by=os.environ.get("SYNAPSE_SPAWNED_BY") or None` at startup. The existing `test_lifespan` used `assert_called_with` (exact-match) and was not updated, which left `main` CI red and cascaded red CI onto every downstream PR. Adding `spawned_by=None` to the expectation restores the invariant and unblocks the whole PR queue.

## [0.27.0] - 2026-04-19

### Added

- **Orphan agent tracking + `synapse cleanup` command (#332, #601):** Every spawn now records `spawned_by: <parent_agent_id>` in the child's registry entry (via the new `SYNAPSE_SPAWNED_BY` env propagated by `synapse spawn`). `AgentRegistry.get_orphans()` returns children whose parent's registry entry is gone or whose parent PID is no longer alive. The new `synapse cleanup [--dry-run] [--force] [<agent>]` command lists or kills those orphans; `synapse list` also annotates orphan rows with `[ORPHAN]` and exposes `is_orphan` / `spawned_by` in `--json` output. An opt-in `SYNAPSE_ORPHAN_IDLE_TIMEOUT` env var lets `synapse list` opportunistically reap long-idle orphans.
- **Generic-prompt heuristic safety net for WAITING detection (#572, #594):** When a profile's `waiting_detection.regex` misses an unknown prompt, `IdleDetector` now falls back to a conservative cross-profile pattern set (numbered selectors `› 1.` / `❯ 1.` / `● 1.`, `[Y/N]` and `(Y/N)` brackets, `Press Enter`, `Do you want to`, `Would you like to`, `Allow ... ?`, numbered Yes/No/Allow/Deny/Approve/Skip). New `waiting_confidence` (1.0 for primary regex, 0.6 for heuristic) and `waiting_source` (`"regex"` / `"heuristic"` / `"none"`) fields are propagated through `IdleStateEvaluation` → `TerminalController` → permission notification metadata, so parent agents (e.g. Approval Gate) can weight detections. Per-profile `heuristic_fallback: true|false` controls opt-out (default true; `dummy` profile defaults false).

### Changed

- **`get_orphans()` and opportunistic cleanup accept a pre-loaded snapshot:** `AgentRegistry.get_orphans(agents=None)` and `opportunistic_cleanup_idle_orphans(agents=None)` now accept a pre-loaded `list_agents()` result so `synapse list` walks the registry directory once instead of three or four times. Backward compatible — existing callers keep working with the default.
- **`_GENERIC_PROMPT_PATTERNS` and confidence constants documented:** Each fallback pattern is now annotated with the profile / phrasing it targets, and `_HEURISTIC_CONFIDENCE` carries a comment explaining why heuristic detections sit at 0.6 (so consumers gating on `>= 0.8` default to trusting the profile-specific regex only).
- **`a2a_compat` waiting-source validation centralised:** Permission metadata now validates `waiting_source` against a single `_WAITING_SOURCE_VALUES` frozen set, removing the duplicated `{"regex","heuristic","none"}` literal that previously lived in two places.
- **`synapse list` import discipline:** the deferred import of `opportunistic_cleanup_idle_orphans` was hoisted to module scope, so a real ImportError surfaces instead of being silently swallowed by the surrounding `contextlib.suppress`.

### Fixed

- **Nested worktree path resolution (#546, #598):** `synapse spawn --worktree` from inside an existing worktree no longer creates `.synapse/worktrees/<parent>/.synapse/worktrees/<child>/`. New `synapse.worktree.get_main_repo_root()` uses `git rev-parse --git-common-dir` to resolve back to the original repo root, and `create_worktree` calls it instead of `get_git_root` (which is documented to return the *current* worktree, not the main checkout).
- **`Closes` auto-link on PR bodies:** PRs in this release follow the `Closes #N` literal-line convention (no markdown bold), so GitHub's auto-link reliably closes referenced issues — the workaround for the regression first observed on PR #588.

### Documentation

- **Subagent-over-spawn for same-model delegation (#595):** `plugins/synapse-a2a/skills/synapse-a2a/SKILL.md` (and the two deployment mirrors) plus the MCP bootstrap instructions (`synapse/templates/.synapse/default.md`) now explicitly steer Claude → claude (and Codex → codex) work to the in-process subagent (Agent / Task tool / subprocess) before reaching for `synapse spawn`. Spawning the same model on the same account doesn't distribute the rate-limit window — it doubles consumption against the same quota. `synapse spawn` remains the right tool for cross-model delegation, agents that lack subagent support, or persistent multi-task helpers.
- **Subagent worktree cd discipline (#547, #599):** added a "Worktree Discipline" section to the `synapse-a2a` skill telling subagents to NEVER `cd` into `.synapse/worktrees/<name>/` (use absolute paths instead) so the parent session's working directory survives subagent exploration. New `tests/test_skill_docs.py` locks the warning text down.
- READMEs (en/ja/zh/ko/es/fr), `guides/troubleshooting.md`, `docs/permission-detection-spec.md`, and `site-docs/{guide/agent-management.md, reference/cli.md, reference/cli-cheatsheet.md}` updated to surface the new `synapse cleanup` command, the `[ORPHAN]` annotation, and the heuristic fallback / confidence semantics.

### Tests

- **End-to-end verification of `post-impl` workflow (#531, #600):** added `tests/test_post_impl_workflow_e2e.py` (marked `@pytest.mark.e2e`, opt-in via `pytest -m e2e`) which exercises the full `_WorkflowHelper` lifecycle: 5-step progression, helper spawned-once / killed-once, no 409 on step 5, helper-vs-caller-endpoint dispatch. The test loads the real `.synapse/workflows/post-impl.yaml`, so any future change to its step shape will be caught at the assertion level.

## [0.26.5] - 2026-04-19

### Changed

- **Permission-notification dedupe path (#588 follow-up):** `_build_permission_metadata` is now pure and `_on_status_change` reads prior dedupe state directly from `task.metadata`, instead of round-tripping `notification_hash`/`notification_sent_at`/`notifications_sent` through the freshly built dict. The per-suppression `task_store.update_metadata` call is also dropped, so the lock is only acquired when an actual notification is emitted. Behaviour is unchanged — both within-window and same-payload-after-window dedupe still fire — and the `update_metadata` round-trip removal cuts contention under WAITING/READY oscillation.
- **PTY render hot loop (#590 follow-up):** `PtyRenderer.render()` no longer raises and catches `IndexError`/`AssertionError` for every empty or unexpectedly wide cell. The 80×24 = 1920-iteration loop now uses an early-return length check (`if not cell_data or any(wcwidth(c) != 0 for c in cell_data[1:])`), giving the same broken-cell substitution semantics without per-cell `try`/`except` cost.
- **Port manager scan (#584 follow-up):** `PortManager.get_running_instances()` collapses the previous `O(ports × agents)` nested scan into a single `agents.values()` pass with a `port`-keyed sort, preserving display order in the exhaustion error while skipping stale (`is_process_alive == False`) entries the same way.

### Added

- **`license: MIT` in every plugin SKILL.md frontmatter:** All 23 skills under `plugins/synapse-a2a/skills/` (and the byte-for-byte mirrors in `.agents/skills/` and `.claude/skills/`) now carry an explicit license field, addressing the only frontmatter-level warning surfaced by `gh skill publish --dry-run`. Skill consumers using `gh skill install` will see the license metadata after install, in line with the rest of the repository (`pyproject.toml` is `MIT`).

### Removed

- **Unused permission helpers:** `synapse/_pty_sanitize.py` no longer exports `looks_like_garbage()` or `printable_ratio()` — they were never wired into `_resolve_pty_context` or any other production caller after #588 landed. The `strip_control_bytes` / `tail_printable` / `printable_len` trio remains the public surface.

### Documentation

- **Pinning examples bumped to v0.26.4:** Six READMEs (en/ja/zh/ko/es/fr), `guides/settings.md`, and `docs/skills-management.md` now show `gh skill install ... --pin v0.26.4` so users land on the latest released tag. Bumped again to v0.26.5 in this release.
- **Permission-detection spec extended:** `docs/permission-detection-spec.md` now describes the #582/#586 sanitisation pipeline (pyte fallback → `_pty_sanitize.tail_printable` → 5s dedupe window) and the #529 codex approval-overlay markers (`permissions`, `host`, `patch`, `exec`).
- **Skill install path on the documentation site:** `site-docs/getting-started/installation.md` replaces the residual `npx skills add` snippet with the canonical `gh skill install ...` per-skill commands and links to `guide/skills-management.md` for the legacy migration matrix.
- **Site nav fix:** `mkdocs.yml` adds the previously orphaned `Skills Management: guide/skills-management.md` entry to the User Guide section so the page committed in 655c55b is reachable from the rendered site.
- **`gh skill` ecosystem verification:** Verified the full publish/install flow against `gh` 2.90.0:
  - `gh skill publish --dry-run` validates all 23 skills with no validation errors.
  - `gh skill search synapse-a2a` returns the published plugin set.
  - `gh skill install s-hiraoku/synapse-a2a <skill>@v0.26.4 --dir <path>` installs cleanly and injects `github-path` / `github-ref` / `github-repo` / `github-tree-sha` provenance metadata into the consumer's installed `SKILL.md`.
  - `gh skill update --dry-run` correctly reports `All skills are up to date.` against an installed snapshot.
  Remaining `--dry-run` advisories carried forward as follow-ups: `.agents/skills/` and `.claude/skills/` should eventually be untracked and gitignored (140 files currently mirrored in-repo as deployment artefacts — a structural change reserved for a dedicated PR), and tag protection rulesets should be configured in repo settings.

## [0.26.4] - 2026-04-19

### Fixed

- **PTY observation thread crash on empty cells (#590, #591):** `PtyRenderer.render()` no longer propagates `IndexError` when `pyte.Screen.display` encounters an empty stub cell left behind by a wide-character overwrite (common with codex's ratatui TUI). The renderer now iterates `self._screen.buffer` directly and substitutes blanks for cells whose `.data[0]` lookup would fail, so every agent's PTY capture loop survives the condition that previously terminated it.
- **Idle-state detection safety net (#591):** `TerminalController._check_idle_state` is now wrapped in a broad `try/except` that logs at WARNING with `exc_info=True` and — when non-empty PTY output is still arriving — conservatively demotes a `READY`/`WAITING` agent to `PROCESSING` (syncing the registry and dispatching status callbacks). A future renderer regression therefore degrades gracefully instead of leaving the agent advertised as available while its output stream is effectively broken.

### Dependencies

- Declared `wcwidth>=0.2.0` as a direct dependency — it was previously only transitive via `pyte`, but `PtyRenderer` now imports it directly.

## [0.26.3] - 2026-04-18

### Documentation

- **Skill distribution migrated to `gh skill install`** (requires `gh`
  CLI **2.90.0+**). `skills.sh` / `npx skills add` is now the legacy
  compatibility path. Adds new canonical doc `docs/skills-management.md`
  (mirrored at `site-docs/guide/skills-management.md`) covering
  version pinning with `--pin`, provenance metadata, cross-agent
  install (`--agent`), `gh skill update` drift detection, and
  maintainer-side `gh skill publish` workflow. All user-facing
  install snippets in `README.md`, `README.{ja,ko,zh,es,fr}.md`,
  `guides/usage.md`, `guides/settings.md`, `guides/references.md`,
  `site-docs/getting-started/quickstart.md`,
  `site-docs/getting-started/installation.md`,
  `site-docs/guide/skills.md`, and `site-docs/reference/cli.md`
  have been updated. Release `v0.26.2` was the first
  `gh skill`-published tag.

## [0.26.1] - 2026-04-17

### Documentation

- **Claude Code permission-mode spec update:** Refresh docs to reflect the six current permission modes (`default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`) and document the new `--permission-mode <mode>` launch flag and `permissions.defaultMode` settings key. `--dangerously-skip-permissions` continues to work as an alias for `--permission-mode bypassPermissions`, so Synapse's auto-approve injection is unchanged. Updates `docs/agent-permission-modes.md`, `site-docs/guide/agent-permission-modes.md`, the `synapse-manager` skill reference in all three mirrors (`.agents/`, `.claude/`, `plugins/synapse-a2a/`), and a clarifying comment in `synapse/profiles/claude.yaml`.

## [0.26.0] - 2026-04-17

### Added

- **Approval Gate policy expansion (#571 Phase 3, #578):** `classify_prompt` categorises PTY context into `permission_request`, `overwrite_confirm`, `dangerous_command`, `clarification_request`, `blocked`, or `unknown`. `profile_overrides` now accept a dict-of-dicts for per-prompt-class policy. `_is_high_risk` adds a safety floor that escalates destructive commands (`rm -rf`, `sudo`, `DROP TABLE`, `git push --force`) regardless of policy.
- **Pyte-backed virtual terminal for waiting_detection (#572, #575):** raw PTY output is replayed through a `pyte.Screen` so cursor-motion CSI sequences resolve to the final cell state before regex evaluation. Alt-screen buffer enter/leave is tracked. New `GET /debug/pty` endpoint exposes the rendered screen as JSON. New dependency: `pyte>=0.8.2`.
- **Multiagent patterns usability improvements (#574):** plan preview, samples, and guide for built-in coordination patterns.

### Fixed

- **Approval Gate escalation flood on blocked child states (#576):** blocked-state floor detects non-recoverable banners (`hit your usage limit`, `Upgrade to Pro`, `try again at … AM|PM`) and forces ESCALATE. `EscalationDeduper` (TTL 60s, keyed on `target_agent_id + sha1(pty_context)`) suppresses identical re-escalations.
- **Status sync divergence between controller and task_store (#569, #577):** `_on_status_change` now reverts `input_required` tasks to `working` on any exit from WAITING (previously only WAITING→PROCESSING was handled). Removed rogue write in `GET /tasks/{id}` that re-set `input_required` from stale PTY context.
- **Codex waiting_detection regex widened** to match the `hit your usage limit` OpenAI quota banner.

## [0.25.2] - 2026-04-15

### Added

- **Built-in CoordinationPattern library (#541, #560):** five ready-to-use multi-agent patterns (`agent-teams`, `generator-verifier`, `message-bus`, `orchestrator-subagent`, `shared-state`) are now registered via `synapse.patterns.BUILTIN_PATTERNS` and available through `synapse multiagent` (alias `synapse map`) for `init`, `run`, and management. Each pattern ships with unit and integration tests.
- **Automatic cleanup of long-message temp files (#559, #562):** `LongMessageStore` now throttles `cleanup_expired()` via a new `maybe_cleanup_expired()` helper (default 5-minute interval, 1/12 of the 1-hour TTL) that runs after every successful `store_message()` write, and also sweeps once when the singleton is first created so stale files from a previous process are reclaimed at startup. Prevents indefinite accumulation of files under `/tmp/synapse-a2a/messages`. `history.db` still holds the full message text, so cleanup is lossless.
- **`post-impl-claude` workflow (#566):** new `target: claude` variant that ends with `/autofix-pr` (a Claude Code built-in). Joins the existing `post-impl` (`target: self`) and `post-impl-codex` (`target: codex`) variants so file name, `target:` field, and execution semantics line up consistently.

### Changed

- **`post-impl` workflow variants realigned (#566):** `post-impl.yaml` is now the `target: self` in-process variant (was `target: codex`), and `post-impl-codex.yaml` is now `target: codex` (was `target: self`). `post-impl-codex` continues to use `/code-simplifier` per its Codex-specific notes. `synapse workflow sync` was run to propagate the rename to `.claude/skills/` and `.agents/skills/`, removing orphan `my-review/` and `user-wf/` skill directories in the process.

### Fixed

- **Parent-side permission handling no longer deadlocks on child `input_required` prompts (#571):** children now send structured escalation metadata, the Approval Gate can auto-dispatch approve/deny/escalate, and `synapse send --wait` stays alive until parent intervention or timeout.
- **`synapse list` Rich TUI redraws stay stable during status updates:** the list view now opens on the alternate screen so live redraws do not corrupt the main terminal buffer.
- **`synapse spawn` auto-approve flag collision:** `synapse spawn codex -- --dangerously-bypass-approvals-and-sandbox` (and similar overrides) no longer fails to start because the default `--full-auto` flag was being injected alongside the user's override. Each profile's `auto_approve` config can now declare `alternative_flags`, and `spawn.py` skips `cli_flag` injection when any known approval flag — primary or alternative, in `--flag` or `--flag=value` form — is already present in `tool_args`. Codex, Gemini, and Copilot profiles now list their mutually-exclusive approval flags; Claude and OpenCode need no alternatives.
- **`input_required` treated as transient for self-target workflow steps (#551, #564):** `synapse workflow run post-impl-codex` was failing at step 1 with `Agent requires permission approval` even though auto-approve was configured correctly. For steps with `target: self`, A2A self-injection produces a brief `input_required` window while the message is accepted, and the agent processes the message on its next turn — there is no external human to approve. `_poll_task_completion` now accepts a keyword-only `target_is_self` flag (forwarded by `_apply_task_result` via the existing `_is_self_target` helper) and treats `input_required` as a transient state in that case, continuing to poll instead of short-circuiting to failure. Non-self behavior is unchanged, so genuine "human stuck" signals still fast-fail. Brings the poller into agreement with `_wait_for_helper_idle`, which already treats `input_required` as blocking via `BLOCKING_TASK_STATES`.

### Dependencies

- Update `actions/upload-pages-artifact` to v5 (#565).

## [0.25.1] - 2026-04-12

### Fixed

- `synapse send` to Codex agents now handles HTTP 409 (agent busy) explicitly with a clear "Agent busy (working task). Retry after Ns" warning instead of silently failing as "local send failed" (#554)
- `send_to_local()` now logs diagnostic warnings at every failure path (UDS transport errors, HTTP status errors, missing UDS socket, outer request exceptions) instead of returning `None` without explanation; set `SYNAPSE_LOG_LEVEL=DEBUG` to see details (#542)
- `synapse send` now prints a clear warning when the sender agent cannot be auto-identified, advising users to set `SYNAPSE_AGENT_ID` or use `--from` (#543)
- `--message-file`, `--task-file`, and `--stdin` inputs no longer trigger false shell-expansion warnings on backticks or `$()` — `_warn_shell_expansion()` is now only applied to positional arguments where shell expansion is actually possible (#544)
- Codex agent status detection now uses hybrid idle detection (`strategy: "hybrid"` with `pattern_use: "startup_only"`) to avoid false READY transitions during LLM thinking time, while still avoiding the false positives that motivated the original timeout-only approach (#537)
- `"local send failed"` error now hints at `SYNAPSE_LOG_LEVEL=DEBUG` for diagnostic details
- Pre-existing mypy type error in `synapse/commands/spawn_cmd.py` (`port` variable redefinition) resolved

### Added

- `synapse send --task-file / -T PATH` flag reads a file as the message body, mirroring the flag on `synapse spawn` (#545)

### Changed

- `_resolve_message()` now returns `(message, source)` tuple so callers can branch on input source; `_warn_shell_expansion()` is skipped for non-positional sources
- UDS 409 handler normalized to `Retry-After` header casing for consistency with the TCP path
- `logger.warning` in the `retry_without_reply_to` 404 retry path converted from f-string to lazy `%s` formatting

### Documentation

- Document `--task-file` / `-T` flag across README, README.zh, `guides/usage.md`, `guides/references.md`, and `guides/a2a-communication.md`
- Add troubleshooting guidance for 409 busy errors, missing `SYNAPSE_AGENT_ID`, and `SYNAPSE_LOG_LEVEL=DEBUG` diagnostic usage in `guides/troubleshooting.md`
- Update `guides/profiles.md` Codex section to reflect hybrid idle detection configuration
- Remove stale `--task` / `--callback` flag rows from `guides/references.md` (conflicted with new `-T` alias)

### Tests

- Add 29 new test cases across `test_a2a_client.py` (6), `test_send_message_file.py` (9), `test_tools_a2a.py` (1), `test_compound_signal.py` (4), `test_interactive_idle_detection.py` (1), covering all failure paths and new behaviors
- Update existing `MagicMock`-based tests in `test_send_processing_wait.py` and `test_send_working_dir.py` to set `args.task_file = None` for the new `_resolve_message()` API

## [0.25.0] - 2026-04-11

### Added

- Multi-agent coordination patterns engine (`synapse/patterns/`) — declarative YAML-based pattern definitions with 5 built-in types: generator-verifier, orchestrator-subagent, agent-teams, message-bus, shared-state
- `synapse multiagent` CLI (aliased as `synapse map`) with `init`, `list`, `show`, `run`, `status`, `stop` subcommands for managing coordination patterns
- Canvas "Patterns" view — pattern list/detail UI with Mermaid architecture diagrams for each pattern type
- Canvas REST API: `GET /api/multiagent`, `GET /api/multiagent/{name}`, `GET /api/multiagent/runs`, `GET /api/multiagent/runs/{run_id}`
- `PatternStore` for project/user scoped YAML persistence with atomic writes
- `PatternRunner` for pattern execution lifecycle: spawn, communicate, track, and cleanup
- `CoordinationPattern` ABC with built-in agent spawn, A2A messaging, wiki, and canvas integration

### Tests

- Added comprehensive test suites: `test_pattern_base.py`, `test_pattern_store.py`, `test_pattern_runner.py`, `test_cmd_multiagent.py`, `test_canvas_multiagent.py`

## [0.24.2] - 2026-04-10

### Fixed

- `synapse list` table layout no longer breaks when agent status changes (READY → PROCESSING, etc.) — STATUS and CURRENT columns now use fixed widths to prevent layout shifts (#532)
- CURRENT column preview text is pre-truncated so elapsed time suffix is always visible
- Workflow `response_mode: wait` polling now treats `input_required` as terminal failure to avoid timeout waits (#533)
- Helper-idle checks now treat `input_required` as blocking, preventing new step dispatch to permission-stuck helpers (#533)
- Workflow helper spawning explicitly sets `auto_approve=True` to prevent permission-prompt stalls (#533)

### Refactored

- Extracted `_resolve_columns` helper in `RichRenderer` to deduplicate column-filtering logic
- Extracted `_find_column` and `_wide_console_and_renderer` test helpers

### Tests

- Added 4 tests for stable layout: fixed STATUS width, fixed CURRENT width, layout stability across all status transitions, preview pre-truncation with elapsed time

## [0.24.1] - 2026-04-10

### Added

- implement self-target helper agent + guidance reorg (#525)

### Documentation

- mark deprecation and add LLM Wiki migration guide (#528)
- add target: self helper agent reference section
- add shared memory deprecation note with LLM Wiki reference
- update changelog for v0.24.1 and add self target to workflow guide
- add self-target workflow note to README and deprecation banner to shared memory guide
- fix shared memory → LLM Wiki reference and changelog link path

### Fixed

- address CodeRabbit review — ICRNL actual clear, KKP in interactive mode (#524)
- auto-tile panes when synapse spawn is called multiple times (#507) (#520)
- prevent self-target deadlock and add target: self keyword (#521) (#526)

## [0.24.0] - 2026-04-09

### Added

- `synapse spawn` automatically applies `tmux select-layout tiled` when 2+ agents exist in the spawn zone, matching `team start` behavior (#507)

### Changed

- `_post_spawn_tile()` uses `SYNAPSE_SPAWN_PANES` tracking for spawn zone-aware tiling

### Tests

- Added 4 new tests: spawn zone-based tiling with existing panes, single spawn pane tiling, spawn_agent post-tile trigger, and first-spawn no-tiling

### Documentation

- Updated README, guides, site-docs, and spawn-zone-tiling docs

## [0.23.5] - 2026-04-08

### Fixed

- Copilot Enter key reliability: detect and handle KKP (Kitty Keyboard Protocol) re-activation after initial disable — Copilot's Ink TUI can re-push KKP after processing a prompt, causing subsequent `\r` submits to be silently re-encoded as CSI 13 u
- Add last-resort KKP force-disable + ICRNL re-clear + final CR retry when submit confirmation exhausts all retries
- Simplify elapsed time calculation in paste echo detection

### Tests

- Added `test_kkp_re_enable_detected_after_initial_disable` for KKP re-activation detection
- Updated 10 confirmation-failure tests to include last-resort KKP disable + CR writes
- Renamed `test_kkp_disable_only_once` → `test_kkp_disable_only_once_for_proactive`

## [0.23.4] - 2026-04-07

### Fixed

- `synapse spawn` called multiple times now automatically applies `tmux select-layout tiled` when 2+ agents exist in the spawn zone, matching `team start` behavior (#507)

### Changed

- `_post_spawn_tile()` now uses `SYNAPSE_SPAWN_PANES` tracking to determine total spawn zone pane count instead of relying solely on per-invocation count

### Tests

- Added 4 new tests: spawn zone-based tiling with existing panes, single spawn pane tiling, spawn_agent post-tile trigger, and first-spawn no-tiling

### Documentation

- Updated README, guides, site-docs, and spawn-zone-tiling docs to reflect automatic tile layout for individual `synapse spawn` calls

## [0.23.3] - 2026-04-07

### Fixed

- WAITING detection now strips ANSI escape sequences before regex matching, fixing unreliable approval prompt detection for TUI-based agents (ratatui, Ink, Bubble Tea) (#508)
- Updated Codex approval regex: added `Press [Ee]nter to confirm` and `Would you like to` patterns from latest codex-rs source (#508)
- Updated Gemini approval regex: added `Apply this change` and `Do you want to proceed` patterns from latest gemini-cli source (#508)

### Changed

- Auto-approve limits removed for spawned agents: `MAX_CONSECUTIVE` now defaults to 0 (unlimited) and `COOLDOWN` to 0.0 (no delay) — parent manages child approval as its responsibility (#508)
- pr-guardian: replaced sleep-based polling with `gh run watch` hybrid approach, reducing typical session cycles from 5-10 to 1-3 per PR (#518)

### Tests

- Added 21 new tests: ANSI-wrapped WAITING detection, per-profile regex validation against real approval prompts, unlimited approval behavior, and `_check_waiting_state` integration tests
- Extracted shared `_make_controller` test helper to module level

### Documentation

- Updated docs, README, guides, and site-docs to reflect unlimited auto-approve defaults and ANSI stripping improvement


## [0.23.2] - 2026-04-07

### Fixed

- Copilot CLI Enter key reliability: detect and disable Kitty Keyboard Protocol (KKP) which re-encodes Enter from `\r` to CSI 13 u, causing injected submits to be silently ignored
- Thread-safe KKP disable via `_disable_kkp()` helper with `RLock` to prevent PTY write interleaving between monitor and write threads

### Documentation

- Updated synapse-reference.md and README.md with KKP mitigation details for Copilot PTY behavior


## [0.23.1] - 2026-04-06

### Fixed

- `response_mode: wait` now correctly waits for task completion when the sender has no A2A server (e.g. `synapse workflow run` subprocess). Falls back to polling the target's task endpoint directly (#513)
- Polling loop exits early on `input_required` status instead of waiting until timeout

### Documentation

- Updated canvas-workflow design doc with target-side polling fallback and `input_required` exit behavior


## [0.23.0] - 2026-04-05

### Added

- Living Wiki: `source_files` and `source_commit` frontmatter fields for tracking which source code files a wiki page documents
- Stale page detection in `synapse wiki status` and `synapse wiki lint` — identifies pages whose tracked source files have changed
- `synapse wiki refresh [--apply]` command — lists stale pages and optionally updates `source_commit` to current HEAD
- `synapse wiki init` command — creates skeleton `synthesis-architecture.md` and `synthesis-patterns.md` pages with idempotent index entries
- `learning` page type for recording bug fixes and discovered patterns
- `GET /api/wiki/graph` Canvas endpoint — returns a Mermaid diagram of wiki page `[[wikilink]]` relationships

### Documentation

- Updated synapse-reference.md, README.md, llm-wiki.md with new wiki commands and features
- Updated site-docs CLI and API reference pages
- Added `source_files` and `source_commit` to wiki-schema.md frontmatter specification

## [0.22.0] - 2026-04-05

### Added

- `synapse worktree prune` CLI command — detects and removes orphan worktrees whose directories no longer exist
- `synapse worktree` subcommand group for worktree management

### Fixed

- Canvas Database view no longer lists `.db` files from `.synapse/worktrees/` directories


## [0.21.0] - 2026-04-05

### Added

- LLM Wiki — Knowledge Accumulation Layer (#506)
- `synapse wiki ingest/query/lint/status` CLI commands
- Canvas Knowledge view (`#/knowledge`) with Project/Global tabs
- MCP instruction `synapse://instructions/wiki`

### Fixed

- Deduplicated wiki frontmatter parsing, added TTL cache for `is_wiki_enabled()`
- Fixed timezone-aware timestamps and TOCTOU in wiki API


## [0.20.0] - 2026-04-05

### Added

- Permission detection: spawned agents automatically notify callers when stopped at a permission prompt (#492, #498)
  - `WAITING` status now maps to `input_required` A2A task state
  - `_on_status_change` sends `input_required` notification to `--notify`/`--wait` callers with PTY context
  - `POST /tasks/{id}/permission/approve` and `/deny` API endpoints for remote approval
  - `deny_response` added to all 5 agent profiles (claude, codex, gemini, opencode, copilot)
  - Agent instructions updated with PERMISSION HANDLING section

### Documentation

- Added `docs/permission-detection-spec.md` — technical specification
- Updated `docs/agent-permission-modes.md` — user guide for permission detection and status types

## [0.19.5] - 2026-04-04

### Fixed

- Tile layout pane creation for spawn and team start (#502)
  - Added caller-level tmux tiling (`select-layout tiled`) after individual worktree/different-args spawns
  - Added inter-command delay to prevent terminal split race conditions
  - Changed worktree spawn path from `check=False` to `check=True` to surface pane creation failures
  - Replaced unreliable Zellij pane count (`query-tab-names`) with env var counter

## [0.19.4] - 2026-04-03

### Added

- `synapse spawn --task` / `--task-file`: send task message automatically after agent becomes READY (#494)
- `synapse merge` command: merge worktree agent branches with `--all`, `--dry-run`, `--resolve-with` (#493)

### Documentation

- Updated README, guides, site-docs with `--task` and `synapse merge` usage

## [0.19.3] - 2026-04-03

### Added

- Auto-merge worktree branch on kill (#496)

### Fixed

- `synapse send` no longer blocks messages to worktree agents without `--force` (#497)
- Address CodeRabbit review — early return skips cleanup, test mismatch

## [0.19.2] - 2026-04-03

### Fixed

- **Unify `is_process_alive` with `is_process_running`**: `port_manager.py` `is_process_alive()` now delegates to `registry.py` `is_process_running()`, fixing `PermissionError` mishandling that caused live agents to be incorrectly unregistered (#495)
- Deferred `get_git_root()` call in `merge_worktree` to avoid unnecessary subprocess when no commits to merge

### Documentation

- Updated `guides/references.md` and `guides/usage.md` with `--no-merge` flag and auto-merge behavior
- Added `merge` parameter documentation to `cleanup_worktree` docstring

### Tests

- Aligned `wait_for_agent` mock with #495 fix in `test_spawn.py`

## [0.19.1] - 2026-04-03

### Added

- **Worktree auto-merge on kill**: `synapse kill` now automatically merges worktree branches back to the parent branch by default (#493)
- Uncommitted changes in worktrees are auto-committed as WIP before merge
- `--no-merge` flag on `synapse kill` to skip auto-merge and preserve the branch

### Documentation

- Added merge strategy comparison (Claude Code vs Synapse) to `docs/worktree.md`
- Updated `README.md`, `docs/synapse-reference.md`, and `docs/agent-teams-adoption-spec.md` with `--no-merge` flag
- Synchronized `site-docs/` with auto-merge documentation

### Tests

- Added `TestMergeWorktree` (5 tests) and cleanup merge tests (3 tests) in `test_worktree.py`
- Added kill merge tests (2 tests) in `test_cli_kill_jump.py`

## [0.19.0] - 2026-04-02

### Added

- **Worktree auto-recommendation**: `analyze_task` returns `recommended_worktree` field — `true` when delegation strategy is `spawn` or file conflict risk is high
- **Team start worktree default**: `synapse team start` now defaults to `--worktree` isolation; opt out with `--no-worktree`
- **Branch implies worktree**: `--branch` flag auto-enables `--worktree` in `synapse spawn` (no longer requires explicit `--worktree`)
- Worktree decision criteria documented in agent instruction template (`default.md`)

### Changed

- `--branch` without `--worktree` no longer errors — worktree is auto-enabled instead
- Agent instruction template (`default.md`) now includes worktree decision rules in Collaboration Decision Framework

### Documentation

- README, synapse-reference, guides, and site-docs updated to reflect worktree auto-recommendation, team start default, and `--no-worktree` opt-out

## [0.18.4] - 2026-04-01

### Documentation

- Bump package, plugin, and GitHub Pages version references to `0.18.4`

## [0.18.3] - 2026-04-01

### Fixed

- **OpenCode initial instruction injection**: when no `input_ready_pattern` is configured, Synapse now waits for timeout-based idle readiness before sending startup instructions (#477)
- **Copilot auto-approve flag**: switched spawned Copilot sessions to the canonical `--allow-all` launch flag and aligned observability/tests with the new behavior (#479)

### Documentation

- Updated permission-mode, profile, reference, and site docs to describe OpenCode timeout-idle startup readiness and Copilot `--allow-all`

## [0.18.2] - 2026-04-01

### Added

- **Canvas clipboard copy**: Copy card content to clipboard as Markdown via new copy button in card headers and spotlight view
- Shared `fetchCardExport()` helper and `createActionButton()` factory for download/copy buttons

## [0.18.1] - 2026-04-01

### Fixed

- **TUI artifact removal for OpenCode/Gemini**: Strip block element lines (U+2580-U+259F), geometric shape lines (U+25A0-U+25FF, U+2B1D), TUI frame content lines, and Gemini CLI input prompts from agent responses (#480)
- Extended `_BOX_CHARS` with rounded corner and heavy/dashed box-drawing variants (`╭╮╰╯┃╌╍╎╏`)
- Added `_is_tui_block_line()` for lines with minor ANSI residue (e.g. orphaned SGR `m` prefix)
- Added `_is_tui_frame_content_line()` to detect bordered TUI panel rows

### Tests

- Added `TestOpenCodeTuiArtifacts` (6 tests) and `TestGeminiTuiArtifacts` (7 tests) in `tests/test_output_parser.py`

## [0.18.0] - 2026-03-31

### Added

- **delegation_strategy in analyze_task**: MCP `analyze_task` tool now returns a `delegation_strategy` field ("self" / "subagent" / "spawn") to guide agents on whether to handle tasks themselves, use built-in subagents (Claude Code Agent tool, Codex subprocess), or spawn separate Synapse agents (#476)
- **Git diff heuristics**: `GitDiffStats` dataclass with `_get_git_diff_stats()` parses `git diff --numstat` for quantitative change metrics (files, lines, directory spread)
- **File conflict detection**: `_detect_file_conflicts()` queries `FileSafetyManager.list_locks()` to identify files locked by other agents; high conflict risk forces spawn + --worktree recommendation
- **Sequential dependency detection**: `_detect_dependencies()` analyzes Python imports and naming conventions (migration→service→test ordering) to build dependency graphs; prevents incorrect parallelization
- **New analyze_task parameters**: optional `files` (hint paths) and `agent_type` (subagent capability check) in MCP inputSchema
- **Enriched analyze_task output**: `context` section with `diff_stats`, `file_conflicts`, `dependencies`, `parallelizable`; `warnings` list for actionable alerts

### Changed

- **default.md decision framework**: replaced vague "5 min / 10 files" criteria with concrete thresholds — [DO IT YOURSELF] (≤3 files, ≤100 lines, 1 dir), [USE SUBAGENT] (4-8 files, ≤2 dirs, Claude/Codex only), [USE SYNAPSE SPAWN] (9+ files, 3+ dirs, cross-model)
- **spawning.md**: added subagent vs Synapse spawn comparison table with clear decision criteria
- **Smart Suggest instructions**: updated to explain delegation_strategy field and recommended actions per strategy
- **Configurable thresholds**: `delegation_thresholds` and `subagent_capable_agents` in `.synapse/suggest.yaml`

### Documentation

- Updated `docs/synapse-reference.md` with new analyze_task parameters and return fields
- Updated `README.md` Smart Suggest feature description

## [0.17.16] - 2026-03-31

### Added

- Auto-approve for spawned agents: `synapse spawn` and `synapse team start` now inject CLI-specific permission bypass flags by default (#469)
- Runtime WAITING auto-response: controller detects permission prompts and sends profile-specific approval response
- `--no-auto-approve` flag for `spawn` and `team start` to opt out of automatic approval
- `auto_approve` config section in all 5 agent profiles (claude, gemini, codex, copilot, opencode)
- Safety controls: max 20 consecutive auto-approvals, 2s cooldown, thread-safe with lock
- New docs: `docs/agent-permission-modes.md` — comprehensive CLI permission modes guide

### Changed

- Refactored spawn/team-start unification: `spawn_agent()` split into `prepare_spawn()` + `execute_spawn()`
- `cmd_team_start()` now uses shared spawn infrastructure (auto-approve, port allocation, worktree creation)
- Updated `auto-approve-flags.md` with corrected flags (Copilot: `--yolo`, OpenCode: env var)

### Removed

- Dead code: `_inject_ports()`, `_run_pane_commands()` (cli.py), `_get_new_tmux_pane_id()` (spawn.py)

## [0.17.15] - 2026-03-31

### Fixed

- OpenCode WAITING detection completely broken — was matching numbered lists but OpenCode uses horizontal button bar (`Permission Required`, `Allow (a)`, `Deny (d)`)
- Codex WAITING detection too generic — replaced broad `^\s+\d+\.` with Codex-specific `›` selector and approval text patterns
- Gemini WAITING regex matched unused `○` character and missed `Action Required` header

### Changed

- Copilot WAITING regex extended with agent-specific text patterns (`No, and tell Copilot`, `approve ... for the rest of the running session`)
- Gemini regex capturing group `()` → non-capturing `(?:)` for correctness

### Tests

- Add parametrized per-agent WAITING pattern tests (positive + negative + ANSI) loaded from YAML profiles
- Update OpenCode profile test to match new button-bar UI patterns

### Documentation

- Update README, site-docs profiles reference with corrected WAITING detection patterns
- Add `waiting_detection` blocks to site-docs profile examples (Gemini, Codex, OpenCode, Copilot)

## [0.17.14] - 2026-03-29

### Added

- Canvas post `--stdin` flag and `-` convention for piped input (#468)
- Canvas post `--example <format>` to print working examples (#468)
- MCP `canvas_post` tool for programmatic posting without shell escaping (#468)
- Template body schemas documented in agent instructions (#468)
- DB Browser shows global `~/.synapse/` databases with scope badge (#468)
- Spotlight badges always visible (format/template type + card position)

### Changed

- Split `canvas.js` (5,213 lines) into 8 modular script files (#468)
- Split `canvas.css` (4,629 lines) into 7 thematic CSS modules (#468)
- Split `server.py` routes into FastAPI APIRouter modules (#468)
- Extract `a2a.py` helpers into `a2a_helpers.py` module (#468)
- Centralize `CANVAS_CSS_FILES` / `CANVAS_JS_FILES` constants (#468)

### Fixed

- Spotlight template/nav badges visible as empty circles when hidden (#468)
- SQLite connection leak in DB Browser query endpoint (#468)

## [0.17.13] - 2026-03-29

### Added

- Canvas format/template selection guide in base instructions (always available)
- Same working directory agent collaboration guidance in base instructions
- Canvas Spotlight keyboard navigation (ArrowLeft/Right, Escape)
- Template visual differentiation with per-template accent colors
- Template badge display in Spotlight title bar
- Spotlight card transition animations (spotlight-swap CSS fix)
- Sorted cards cache with dirty-flag invalidation for efficiency

### Changed

- Rewrite proactive.md from checklist format to task-size x feature matrix with per-feature skip conditions
- Simplify Spotlight info bar: remove agent_id and card_id, add hover fade
- Extract shared `cardsByRecency` comparator to eliminate sort duplication

### Fixed

- Spotlight-swap animation CSS was missing (JS applied class but no CSS rule existed)
- Escape key now dismisses context menu and spotlight nav separately
- ArrowRight no longer skips index 0 when entering manual navigation
- Single-card case no longer shows "1/1" nav indicator

## [0.17.12] - 2026-03-28

### Added

- synapse config shows effective values with source, removes --scope

### Changed

- improve instructions and skills, add shared memory scope
- extract duplicated scope logic, fix BOOLEAN_ENV_VARS

### Documentation

- update site-docs for shared memory scope and config changes

### Fixed

- improve config system — add missing env vars, fix memory.db path, smart-merge on init
- clear stale text on bare CR in _render_buffer to prevent A2A noise

## [0.17.11] - 2026-03-27

### Fixed

- **Copilot CLI 1.0.12 instructions not executing** — Copilot CLI 1.0.12+ now enables bracketed paste mode (`ESC[?2004h`) on startup; updated profile to `bracketed_paste: true` so Synapse wraps injected text in `ESC[200~`/`ESC[201~` markers. Without markers, text was processed character-by-character through Ink's `useInput`, causing slash-command autocomplete and submit failures
- Slash escaping (`/` → fullwidth solidus) now skipped when bracketed paste is enabled, as pasted text goes through `usePaste` and does not trigger autocomplete

### Documentation

- Updated Copilot bracketed paste documentation across README, synapse-reference, guides/profiles, and site-docs (profiles, profiles-yaml, troubleshooting)

## [0.17.10] - 2026-03-27

### Changed

- **DB path management consolidated to `synapse/paths.py`** — all 7 databases now use centralized path functions with environment variable overrides. Removed hardcoded `DEFAULT_DB_PATH` from `shared_memory.py`, `workflow_db.py`, `file_safety.py`, `observation.py`, `instinct.py`
- **`memory.db` moved to user-global** (`~/.synapse/memory.db`) — cross-agent shared memory is now shared across projects. Other project-local DBs (`file_safety.db`, `workflow_runs.db`, `observations.db`, `instincts.db`) remain in `.synapse/`
- New environment variable `SYNAPSE_WORKFLOW_RUNS_DB_PATH` for workflow DB path override

### Fixed

- **Dashboard Recent History was always empty** — `canvas/server.py` hardcoded `.synapse/history.db` instead of the actual path `~/.synapse/history/history.db`
- Canvas dashboard hardcoded paths for `file_safety.db` and `memory.db` now use `paths.py`

### Removed

- Remaining task-board references from Canvas UI (protocol, export, JS, CSS, dashboard widget, HTML filter), tests, and documentation
- `synapse/shell_session.py` and `tests/test_shell_session.py` — unused dead code (`history.db` covers session management)
- `Shared Task Board` from CLI feature list and delegate mode instructions

### Documentation

- Updated DB architecture across all guides, site-docs, and plugin skills to reflect new paths
- Removed `synapse tasks` command documentation from references

## [0.17.9] - 2026-03-26

### Fixed

- Copilot CLI input not submitted via PTY — inject pipe feeds data through `pty._copy`'s select loop
- ICRNL guard now checks `submit_bytes == b"\r"` instead of `_bracketed_paste`
- Line-start `/` replacement (not all slashes) to prevent slash-command autocomplete
- Inject pipe setup wrapped in try/finally for reliable cleanup
- Raw mode applied to real stdin fd for correct keypress handling

## [0.17.8] - 2026-03-25

### Removed

- **Task Board subsystem** — `synapse/task_board.py`, `synapse tasks` CLI commands, `/tasks/board` API endpoints, auto-sync logic, Canvas dashboard widget, and all related configuration (`SYNAPSE_TASK_BOARD_ENABLED`, `SYNAPSE_TASK_BOARD_DB_PATH`). GitHub Issues will serve as the external work-item source going forward
- `--task` / `-T` flag on `synapse send` (created linked board tasks)
- `board_task_id` parameter from A2A client, utils, and tools
- `accept_plan` / `sync_plan_progress` functions from Canvas commands
- `site-docs/guide/task-board.md` documentation page

### Fixed

- Copilot CLI input not being submitted via PTY — inject pipe mechanism feeds data through `pty._copy`'s select loop

### Changed

- Proactive mode checklist no longer requires task board registration
- Default agent instructions template simplified (removed task board steps)
- Copilot profile: `bracketed_paste: false`, `input_ready_pattern: ❯`, slash replacement
- Long message file reference consolidated to single-line format

### Documentation

- Remove Task Board references from README, CLAUDE.md, plugin skills (14 files), site-docs (20 pages), and synapse-reference

## [0.17.7] - 2026-03-24

### Fixed

- Canvas Live Feed now renders briefing (and all template) cards with proper section grouping instead of flat block display
- Template cards in Live Feed no longer appear as individual messages — the entire template is rendered as a single card

### Changed

- Extract `renderTemplateOrBlocks` helper to eliminate 3x duplicated template rendering logic in canvas.js
- Add `normalizeCard` to parse `template_data` at ingest time instead of on every render
- Simplify `renderSpotlightContent` and `updateCardElement` to use shared helper

### Tests

- Add 7 briefing validation edge-case tests (negative index, float, bool, non-integer, duplicates, multi-section refs, round-trip)
- Add 2 briefing CLI regression tests (store round-trip, markdown export)

## [0.17.6] - 2026-03-24

### Fixed

- MCP bootstrap no longer silently skips approval prompts — resume and MCP bootstrap are now separate startup paths; MCP sends a minimal PTY bootstrap while keeping approval enabled
- Extract shared `MCP_INSTRUCTIONS_DEFAULT_URI` constant to prevent URI drift between MCP server and controller
- Add mutual exclusion invariant for `skip_initial_instructions` and `mcp_bootstrap` flags

### Changed

- Refactor `_send_identity_instruction` to use early-branch pattern, eliminating redundant `_mcp_bootstrap` guard
- Improve injection observability log to show `mode=mcp_bootstrap|full` instead of empty `files=[]`

### Documentation

- Update MCP bootstrap descriptions across README, design docs, site-docs, and plugin skill references to reflect minimal-bootstrap behavior

## [0.17.5] - 2026-03-24

### Added

- Persist workflow execution history to SQLite (#437) — runs survive server restarts

## [0.17.4] - 2026-03-23

### Fixed

- Copilot submit confirmation now treats repeated paste placeholders as still pending, so consecutive sends that reuse `[Paste #N ...]` or `[Saved pasted content ...]` labels continue retrying Enter until the prompt actually clears
- Remove dead `previous_tail` parameter from `_has_copilot_pending_placeholder` and simplify to `any()` idiom

## [0.17.3] - 2026-03-23

### Fixed

- Pane split direction not alternating when spawning multiple agents via `synapse spawn` or `synapse team start` in Ghostty, iTerm2, and Zellij terminals — all panes split in the same direction instead of tiling in a balanced grid
- iTerm2 `enumerate(agents[1:])` offset bug causing second agent to get wrong split direction in `not all_new` path

### Documentation

- Updated Ghostty pane creation info in site-docs to document `Cmd+Shift+D` and `--layout` support

### Tests

- Added multi-agent split alternation tests for Ghostty, iTerm2, and Zellij

## [0.17.2] - 2026-03-23

### Added

- Self-learning pipeline: PTY observation layer for cross-agent knowledge sharing
- Instinct system with confidence scoring (0.3–0.9) and pattern analyzer
- Evolution engine: cluster instincts into skills, auto-generate SKILL.md files
- Auto-distribute learned skills to .claude/skills/ and .agents/skills/
- Chart-to-markdown converter for canvas export

### Fixed

- Clear SYNAPSE_PROACTIVE_MODE_ENABLED in settings tests (15 test failures)
- Fence mermaid blocks in Markdown export
- Guard assertions after workflow test polling loops

## [0.17.1] - 2026-03-20

### Added

- Canvas Workflow view (`#/workflow`): split-panel UI for browsing, visualizing (Mermaid DAG), and executing workflows with real-time SSE progress updates
- Async workflow runner (`synapse/workflow_runner.py`): background execution engine with in-memory run tracking and LRU eviction
- 5 workflow API endpoints: `GET /api/workflow`, `GET /api/workflow/{name}`, `POST /api/workflow/run/{name}`, `GET /api/workflow/runs`, `GET /api/workflow/runs/{run_id}`
- `response_mode: wait` polling — workflow runner now polls target agent until task completion
- 409 (agent busy) retry with backoff in workflow step execution
- Phase 2 design document (`docs/design/canvas-workflow.md`)

### Changed

- Redesigned workflow runner to direct httpx POST with async polling

### Fixed

- Route canvas workflow replies through canvas
- Wait for agent ready before next step, retry on 409, fix Mermaid labels
- Mermaid selector, row highlight style, re-sync skill parity

## [0.17.0] - 2026-03-20

### Added

- Canvas card download feature: export cards as Markdown, JSON, CSV, HTML, or native format files
- New API endpoint `GET /api/cards/{card_id}/download?format={format}` with Content-Disposition headers
- Download buttons in Canvas card grid headers and Spotlight title bar (ph-download-simple icon)
- Format-aware export: 26 formats mapped to optimal file types, 6 templates export as Markdown or JSON
- Security hardening: filename sanitization (header injection prevention), base64 decode error handling, 50 MB export size limit
- `synapse/canvas/export.py` — new module with converter functions for all format groups (Markdown, native, JSON, CSV)

### Tests

- 43 unit tests in `tests/test_canvas_export.py` covering all format groups, templates, edge cases, and security scenarios

### Documentation

- Updated README.md, docs/design/canvas.md, docs/synapse-reference.md, guides/references.md
- Updated site-docs/guide/canvas.md with download feature documentation
- Updated plugin skills (SKILL.md, api.md, features.md) with download API reference

## [0.16.2] - 2026-03-20

### Added

- Canvas Admin UI: right-click context menu on agent rows with Kill Agent action
- Reusable confirm modal component (`showConfirmModal`) with glassmorphism design, Escape/click-away dismiss, and theme-aware styling
- Canvas Admin UI: `DELETE /api/admin/agents/{id}` integration for stopping agents from the browser

### Documentation

- Updated README.md, admin-command-center.md, and site-docs/guide/canvas.md with context menu documentation

## [0.16.1] - 2026-03-20

### Fixed

- Copilot CLI Enter key not executing after paste injection

## [0.16.0] - 2026-03-20

### Added

- `synapse reply --fail <reason>` flag for sending structured failed replies
- `MISSING_REPLY` auto-detection for wait/notify tasks completed without explicit reply
- `extra_metadata` parameter on `A2AClient.send_to_local()` for pass-through metadata
- `/tasks/{id}/reply` endpoint now accepts `status` and `error` fields for failed replies

### Fixed

- TOCTOU race in `_maybe_mark_missing_reply` guard by re-reading metadata from task store
- Reserved metadata keys (`response_mode`, `sender`, `in_reply_to`) protected from override via `extra_metadata`
- Sync path `_maybe_mark_missing_reply` now only runs for wait/notify modes (matching async path)

### Changed

- Extracted `_maybe_mark_missing_reply` helper to deduplicate guard condition across sync/async paths
- Error codes `MISSING_REPLY` and `REPLY_FAILED` defined as constants (`ERROR_CODE_*`)
- Metadata keys in `tools/a2a.py` now import constants from `a2a_compat.py`

### Documentation

- Documented `--fail` flag in README, guides, docs, and site-docs
- Added missing-reply behavior to response mode documentation

## [0.15.11] - 2026-03-20

### Changed

- Copilot submit now uses adaptive paste echo wait: polls PTY output for Ink TUI re-render after bracketed paste, then sends Enter — replaces fixed `write_delay` for more reliable timing
- TUI response cleaning (`clean_copilot_response`) now applies to all agents, fixing corrupted Codex and Claude Code replies

### Fixed

- Root logger calls in controller.py replaced with module logger, preventing WARNING messages from leaking into agent PTY output
- Registry sync failure demoted from WARNING to DEBUG (transient, expected)
- Pre-submit context captured before PTY writes so paste placeholders are correctly detected as incremental additions
- `[Unreleased]` compare link updated for v0.15.11

### Documentation

- Updated HANDOFF doc, synapse-reference, and README for adaptive paste echo wait, all-agent TUI cleaning, and module logger
- Plugin skills synced with paste echo wait and nudge timing descriptions

### Tests

- Added `_copilot_echo_context` test helper to simulate paste echo for Copilot write tests
- Added contract tests for `long_submit_confirm_timeout` and `long_submit_confirm_retries` profile keys

## [0.15.10] - 2026-03-20

### Changed

- Copilot submit path simplified: removed typed-input mode, `Ctrl+S` fallback, tmux typing delay override, and `submit_fallback_sequences` in favor of paste-plus-Enter only
- Inlined trivial `_submit_settle_delay` and `_submit_retry_delay_for` pass-through methods
- Pre-submit context capture now runs only for Copilot agents, avoiding unnecessary work for other agent types
- Optimized paste-placeholder detection with `search()` early-exit before `findall()` counting

### Documentation

- Updated `docs/synapse-reference.md` Copilot section and `site-docs/reference/profiles-yaml.md` schema for paste-only submit path and `long_submit_confirm_*` fields

## [0.15.9] - 2026-03-20

### Fixed

- Copilot sends now stay on bracketed paste plus Enter instead of mixing typed input, `Ctrl+S`, and alternate submit sequences
- Copilot submit confirmation now waits for prompt markers such as file-reference banners, `[Paste #N - X lines]`, and `[Saved pasted content to workspace ...]` to clear before treating the send as confirmed

### Documentation

- Updated core docs, site docs, and plugin skills to document Copilot's paste-plus-Enter submit path and marker-based confirmation rules

## [0.15.8] - 2026-03-20

### Added

- `synapse list --plain` for one-shot plain-text agent listings without entering the Rich TUI

### Fixed

- `synapse list` can now be forced into non-interactive mode with `SYNAPSE_NONINTERACTIVE=1`, so AI-controlled TTY sessions no longer hang in the interactive list UI

### Documentation

- Updated AI-facing guidance, plugin skills, and site docs to use `synapse list --json`, `synapse list --plain`, `synapse status <target> --json`, or MCP `list_agents` instead of bare `synapse list`

## [0.15.7] - 2026-03-20

### Changed

- Copilot now types short single-line messages instead of pasting them, prefers `Ctrl+S` when the footer advertises `ctrl+s run command`, and continues through submit retries as needed

### Fixed

- Interactive startup logging now switches to per-agent file logs before PTY handoff, so startup warnings no longer leak into interactive terminals
- Copilot submit confirmation no longer treats repeated WAITING output as success; it waits for visible progress or prompt disappearance
- Quota and limit errors now mark tasks as failed instead of returning a normal reply

### Documentation

- Updated core docs, site docs, and plugin skills to reflect the Copilot submit flow, startup log routing, and quota failure behavior

## [0.15.6] - 2026-03-19

### Added

- Live E2E GitHub Actions workflow for `claude`, `codex`, `gemini`, `opencode`, and `copilot`, gated by per-CLI auth secrets and explicit CLI installation
- Workflow regression tests covering CLI install steps, job timeouts, auth secret mapping, Copilot npm package installation, and CI fail-vs-skip behavior

### Fixed

- Copilot reply cleaning now strips additional TUI noise patterns including permission prompts, `Esc to stop`, and zero-width-space status bar fragments
- Copilot live E2E CI now installs the standalone `copilot` binary via `@github/copilot` instead of a `gh` extension mismatch
- Live E2E tests now fail in CI when a selected CLI is missing, preventing false-green workflow runs

## [0.15.5] - 2026-03-19

### Added

- `clean_copilot_response()` in `output_parser.py` — strips Ink TUI artifacts (spinners, box-drawing borders, status bars, input echo, re-render duplicates) from Copilot task responses
- Sent message metadata (`_sent_message`) stored in task for input echo removal during response cleaning
- Copilot Ctrl+S submit fallback — sends `\x13` (Ctrl+S "run command") as additional fallback when `\r` fails to trigger Ink TUI submission

### Fixed

- Copilot reply artifacts no longer contain TUI garbage (ANSI escapes, braille spinners, box-drawing borders, status bar text, model name fragments)
- Copilot input confirmation: added Ctrl+S as submit fallback for Copilot CLI 1.0.7 which uses Ink's `ctrl+s run command` binding
- Server-mode logging no longer leaks to stderr/PTY — logs redirect to `~/.synapse/logs/` to prevent corrupting agent TUI display
- Status bar regex tightened to avoid greedily consuming response text on the same line

## [0.15.4] - 2026-03-19

### Added

- add auto-spawn support to workflow run
- auto-generate SKILL.md from workflow YAML definitions

### Changed

- simplify workflow skill sync and update docs

### Documentation

- update InputRouter refs to Shell, fix stale links and badges

### Fixed

- Validate `auto_spawn` YAML field as boolean (reject string `"false"`)
- Deduplicate workflows by name in `sync_all_workflows` (project-first precedence)
- Use `yaml.safe_dump` for SKILL.md frontmatter to prevent YAML injection
- Guard against empty history in skill-creator `generate_report.py`
- Prevent path traversal in skill-creator `run_eval.py`
- Fix false negative in skill-creator tool detection loop

## [0.15.3] - 2026-03-18

### Added

- Agent Control drag-resize splitter: draggable separator between "Select Agent" and "Response" panels for adjustable height ratio, with localStorage persistence, keyboard support (Arrow keys), and `role="separator"` accessibility

### Changed

- History moved from top-level sidebar item to Canvas sub-menu (`nav-sub` class), with Canvas parent link staying active on History route and topbar showing "Canvas / History"

## [0.15.2] - 2026-03-18

### Added

- Name prompt placeholder: `Name [Enter = claude-agent]:` — auto-generates a suggested petname via `suggest_petname_ids()`, accepted with Enter
- Save ID prompt placeholder: `Saved agent ID [Enter = alice-reviewer]:` — suggests a petname based on name, role, skill set, and profile
### Changed

- Canvas menu: "Admin" renamed to "Agent Control" for clarity
- Canvas sidebar: "Agent Control" moved before "System" in menu order
- Extracted `_input_with_default()` helper to deduplicate prompt-with-default logic

## [0.15.1] - 2026-03-17

### Added

- Canvas `artifact` card format — interactive HTML/JS/CSS applications in sandboxed iframes (like Claude.ai Artifacts), distinct from `html` format for raw snippets
- Copilot submit fallback chain: `submit_fallback_sequences` profile field cycles through alternative submit sequences (`\n`, `\x1b\r`) on each confirmation retry instead of repeating the same `\r`
- `_get_retry_submit_bytes` helper method for submit retry sequence selection
- Context delta for task responses: `--wait`/`--notify` replies now prefer PTY output captured since task start, reducing status-line noise in responses

### Fixed

- MCP setup documentation: removed unnecessary `--agent-id`, `--agent-type`, `--port` options from all client configuration examples (auto-resolved from `$SYNAPSE_AGENT_ID`)
- Copilot PTY input not being processed when `\r` alone fails to trigger Ink TUI submission

### Documentation

- Simplified MCP client configuration across site-docs, docs, guides, and plugin skills
- Updated Card Gallery with artifact format sample (interactive counter)
- Updated `synapse-reference.md`, `HANDOFF_CLAUDE_ENTER_KEY_ISSUE.md`, and `profiles-yaml.md` with fallback sequence documentation
- Added `--wait`/`--notify` response behavior explanation to README (EN/KO)

## [0.15.0] - 2026-03-16

### Added

- Admin terminal jump: double-click agent row to jump to its terminal (`POST /api/admin/jump/{agent_id}`)
- Parent process chain detection (`_detect_terminal_from_pid_chain`) — walks PID ancestors to identify tmux, VS Code, Ghostty, iTerm2
- PID-to-TTY fallback (`_resolve_tty_from_pid`) for agents missing `tty_device` in registry
- Tmux host terminal activation — `open -a` + Ghostty/iTerm tab switching via AppleScript
- `_classify_terminal_string` helper to unify terminal name classification
- `replaceChildren` Element method in canvas test helpers (jsdom mock)

### Fixed

- System menu polling flicker: skip re-render when JSON response unchanged, use `replaceChildren` instead of `innerHTML=""`, scope `fadeIn` animation to first render only
- Table overflow on narrow screens: `table-layout: fixed` + `word-break` for general tables; Agent table uses `nowrap` + `overflow-x: auto` for horizontal scroll
- `system-group` grid overflow below 400px (`minmax(min(400px, 100%), 1fr)`)
- Test DB pollution: `test_canvas_server.py` wrote to production `task_board.db` (fixed with `monkeypatch.chdir(tmp_path)`); `test_response_option.py` triggered `--task` flag via `MagicMock` truthiness (fixed with `mock_args.task = False`)

### Changed

- `jump_to_terminal` resolves TTY once upfront and enriches `agent_info`, eliminating redundant `_resolve_tty_from_pid` subprocess calls
- `admin_jump_to_agent` endpoint uses `AgentRegistry().get_agent()` instead of raw JSON file reads
- `_detect_tmux_host_terminal` returns canonical `"iTerm2"` (was `"iTerm"`) for naming consistency

## [0.14.0] - 2026-03-15

### Added

- Canvas HTML Artifact Support: interactive HTML/JS/CSS in sandboxed iframes with parent-iframe theme sync via postMessage (CSS variables `--bg`, `--fg`, `--border`), auto-resize via ResizeObserver, dark mode iframe background, and full document normalization

### Changed

- `formatCanvasHTMLDocument` normalizes full HTML documents (`<!doctype html>`) to fragments, avoiding head-semantics issues (CSS cascade conflicts, overflow clipping)
- Extracted `broadcastThemeToIframes` helper to eliminate postMessage duplication
- ResizeObserver/setTimeout made conditional (ResizeObserver preferred, setTimeout as fallback)

## [0.13.0] - 2026-03-15

### Added

- Task Board UX improvements: `resolve_display_name` for dynamic agent name resolution, table-format CLI output with `--verbose`/`--format json`, `fail_reason` inline display (#394)
- Task Board grouping: `group_id`/`group_title`/`plan_id`/`component`/`milestone`/`external_ref` schema columns with filtering and `--group-by` CLI view (#396)
- `purge_stale` and `purge_by_ids` methods with `--older-than`/`--dry-run` CLI flags
- Canvas view toggle (Status | Group | Component) for task board dashboard widget
- `accept_plan` auto-sets `plan_id`/`group_id`/`group_title` on task creation

### Changed

- Use summary-slot pattern and lazy builders in `updateDashWidget`
- Cache `AgentRegistry` instance in `resolve_display_name` to avoid N+1 instantiation

### Fixed

- Preserve dashboard widget expand state across polling updates
- Canvas task view toggle state persists across polling refreshes

## [0.12.2] - 2026-03-15

### Added

- Canvas Admin Command Center — browser-based view (`#/admin`) for sending messages to agents
- Reply-based response flow using `synapse reply` mechanism (replaces PTY artifact polling)
- Admin API endpoints: `POST /tasks/send` (reply receiver), `GET /api/admin/replies/{id}` (polling)
- "Reuse Existing Infrastructure" design principle in CLAUDE.md and AGENTS.md
- Bootstrap instructions require `synapse reply` for admin messages

### Fixed

- Admin responses no longer contain terminal junk (ANSI escapes, status bars, spinners)
- Reply receiver applies `_strip_terminal_junk` to auto-notify artifact responses

## [0.12.1] - 2026-03-15

### Fixed

- Canvas Admin: IME composition handling prevents premature send during Japanese/Chinese input
- Canvas Admin: multi-artifact response extraction now iterates all artifacts
- Canvas Admin: BEL and terminal status bar junk stripped from agent responses
- Canvas Admin: double-send prevention (button/shortcut disabled while pending)
- Canvas Admin: removed stray `console.log` statements

### Changed

- Canvas Admin: agent selection uses clickable table rows (`system-agents-table` with sticky headers) instead of dropdown
- Canvas Admin: text input replaced with multi-line textarea (Cmd+Enter to send)
- Canvas Admin: glass-morphism styling unified with `--color-accent` CSS variables
- Canvas Admin: `/api/admin/agents` response now includes `role`, `skill_set`, `working_dir` fields

### Documentation

- Update Canvas Admin Command Center docs for bug fixes and UX improvements

## [0.12.0] - 2026-03-14

### Added

- add Copilot MCP support, Plan Card template, and smart-suggest design doc
- complete Plan Card template with step list renderer and CLI command
- add analyze_task MCP tool for smart task suggestions (Phase 3)
- add Plan accept and progress sync (Phase 4)

### Changed

- address code review findings from /simplify

### Documentation

- update all documentation for Smart Suggest, Plan Card, and Copilot MCP

## [0.11.21] - 2026-03-14

### Documentation

- add cross-worktree knowledge transfer scenario

## [0.11.20] - 2026-03-14

### Fixed

- Canvas stale process detection: add `asset_hash` to `/api/health` to detect servers serving outdated HTML/JS/CSS
- Canvas `ensure_server_running()` auto-replaces servers with mismatched asset hash
- Canvas `stop` escalates from SIGTERM to SIGKILL when process doesn't exit

### Changed

- Extract shared `compute_asset_hash()` to `synapse/canvas/__init__.py` (deduplicate server/CLI)
- Extract `_terminate_stale_canvas()` helper to consolidate stale-kill pattern
- Canvas `status` output now shows asset hash, match indicator, and STALE warning

### Documentation

- Update canvas docs, site-docs, CLI reference, and plugin skills for asset hash and SIGKILL fallback

## [0.11.19] - 2026-03-13

### Fixed

- Copilot CLI enter key not submitting — use bracketed paste mode for PTY input
- Increase `submit_retry_delay` from 50ms to 150ms for React render cycle
- Port availability check binds on `0.0.0.0` matching actual server address (fixes Errno 48)
- Remove `SO_REUSEADDR` from port check to avoid false positives
- Tmux pane titles persist with `allow-rename off` (prevents `python:3.13` overwrite)

### Tests

- Add bracketed paste wrapping tests for controller
- Add copilot profile validation tests

## [0.11.18] - 2026-03-13

### Fixed

- Port availability check now binds on `0.0.0.0` matching actual server address (fixes Errno 48)
- Remove `SO_REUSEADDR` from port check to avoid false positives
- Tmux pane titles now persist — `allow-rename off` prevents OSC escape overwrite (`python:3.13`)

## [0.11.17] - 2026-03-13

### Added

- Set tmux pane titles to show agent name (`synapse(claude)` or `synapse(claude:Reviewer)`)
- Auto-enable `pane-border-status` so pane titles are visible without manual tmux.conf changes

### Fixed

- Align `synapse list` help keybinding display

## [0.11.16] - 2026-03-13

### Fixed

- send submit_seq twice for Copilot CLI paste buffer flush
- validate submit_retry_delay is non-negative

## [0.11.15] - 2026-03-13

### Added

- `synapse list --json` flag for AI/script-friendly JSON output of agent list
- MCP `list_agents` tool for querying agent registry via MCP protocol
- Optional `status` filter parameter for MCP `list_agents` tool
- `registry_factory` dependency injection on `SynapseMCPServer` for testability

### Changed

- Refactor `SynapseMCPServer.call_tool()` from single-tool to dispatch pattern

### Documentation

- Update docs, guides, site-docs, and plugin skills for `--json` and MCP `list_agents`

### Tests

- Add `tests/test_cmd_list_json.py` — 5 tests for CLI JSON output
- Add `tests/test_mcp_list_agents.py` — 5 tests for MCP list_agents tool

## [0.11.14] - 2026-03-12

### Fixed

- improve pr-guardian CodeRabbit detection — separate CodeRabbit check from CI, add `coderabbit_check` status field
- fix `poll_pr_status.sh` to use `state` field instead of nonexistent `conclusion` in `gh pr checks --json`
- block `/fix-review` dispatch until CodeRabbit review is complete (not pending)
- strengthen `/fix-review` with mandatory code verification step before applying fixes

## [0.11.13] - 2026-03-12

### Added

- block-level `x_title` / `x_filename` metadata fields on ContentBlock for styled headers
- toast batching for burst SSE updates (300ms debounce window)
- SSE initial-connect dedup to prevent redundant `loadCards()` on first open
- `--no-open` flag for `synapse canvas serve` to suppress browser auto-open
- browser auto-open on `synapse canvas serve` via `threading.Timer`

### Changed

- consolidate `_block_dict` into `ContentBlock.to_dict()` (DRY across server/commands/protocol)
- use `const`/`let` instead of `var` in toast batching code

### Fixed

- mermaid rendering broken by metadata embedded in body — moved to block-level fields
- HTML iframe rendering in Canvas view uses full-document structure for consistent height
- remove canvas card height caps — charts expand to fill available space
- expand canvas image cards to available height

### Documentation

- update `docs/design/canvas.md` for metadata fields, toast batching, mermaid panel
- update site-docs guide and changelog for v0.11.13

### Tests

- tighten canvas chart height assertion
- add `TestCanvasServe` for `--port` and `--no-open` flags
- update frontend tests for `buildMetaRow`, mermaid-panel, options-based HTML detection

## [0.11.12] - 2026-03-11

### Fixed

- use task IDs in board examples and handle invalid UTF-8 agent files

## [0.11.11] - 2026-03-11

### Added

- Task Board coordination: `synapse tasks purge` command to delete tasks with optional `--status` filter
- Task-linked messaging: `synapse send --task` / `-T` flag auto-creates a board task and links it to the A2A message
- Auto-claim on receive: agents automatically claim board tasks when receiving `--task`-linked messages
- Auto-complete on finalize: board tasks are automatically completed when the linked A2A task finishes
- PTY `[Task: XXXXXXXX]` tag display for task-linked messages so agents can see which board task they're working on
- TaskBoard schema: `a2a_task_id` column for A2A transport task linking, `assignee_hint` column for pre-claim target hints
- TaskBoard methods: `purge()`, `set_assignee_hint()`, `link_a2a_task()`, `find_by_a2a_task_id()`
- `BOARD_TASK_METADATA_KEY` constant in `synapse/config.py` for the `x-board-task-id` metadata key
- add Anthropic official skill-creator plugin
- add pr-guardian skill with auto-trigger hook
- refine canvas saved agent scope badges
- auto-skip PTY bootstrap when MCP config is detected
- make task board mandatory for all delegations

### Changed

- `format_a2a_message()` accepts optional `board_task_id` parameter for task tag display
- `_build_a2a_cmd()` and `send_to_local()` accept `board_task_id` for metadata propagation
- Use `BOARD_TASK_METADATA_KEY` constant instead of raw `"x-board-task-id"` strings across 3 files
- Eliminate redundant `task_store.get()` call in `_finalize_working_task`
- Remove TOCTOU pre-check before `complete_task()` (atomic WHERE clause is sufficient)
- simplify canvas process management after code review

### Documentation

- Update README.md, synapse-reference.md, guides/references.md with task board coordination features
- Update site-docs: task-board guide, CLI reference, cheatsheet, communication guide, API reference
- Update plugin skills: synapse-a2a and synapse-manager skills with `--task` flag and purge command
- update Canvas documentation for stale process management

### Fixed

- resolve Canvas stale process problem with robust PID management
- ensure_server_running replaces stale Canvas on PID mismatch
- address PR review findings on docs accuracy and edge cases
- add PID_FILE/LOG_FILE patches and integration test for stale detection
- trim pr-guardian description to 500 chars and chmod utils.py
- relax description length limit to 700 chars
- align canvas saved agent payload and badge palette
- tighten synapse MCP bootstrap detection
- improve saved agent id prompt
- keep canvas sidebar collapse control inside panel
- keep canvas sidebar header contents inside panel
- restore compact canvas sidebar collapse state
- hide brand icon in compact canvas sidebar
- defer spotlight DOM clear to prevent blank fallback rendering
- resolve merge conflicts with main (canvas refactor + split profiles)
- reuse spotlight DOM frame instead of rebuilding on every render
- address canvas frontend review feedback
- resolve remaining merge conflict in system panel test
- Clean up `:memory:` artifact file and stale task board data (28 records)

### Tests

- cover canvas spotlight fallback for malformed cards
- Test isolation: `task_store._tasks.clear()` in `conftest.py` prevents cross-test contamination

## [0.11.10] - 2026-03-10

### Fixed

- Resolve test failures from CLAUDE.md slimdown and `LongMessageStore` singleton pollution across test files
- Add missing `user_dir` parameter to `SynapseSettings._load_instruction_file()`
- Tighten test assertions: storage doc check and MCP stdio protocol verification

### Documentation

- Add per-agent MCP configuration to Getting Started guides (installation, quickstart, multi-agent-setup)
- Fix broken design doc link in MCP setup guide
- Slim down MCP bootstrap design doc

## [0.11.9] - 2026-03-10

### Added

- MCP bootstrap server (`synapse mcp serve`) for stdio-based instruction distribution to MCP-capable clients
- MCP resources: default instructions + optional file-safety, shared-memory, learning, proactive instructions
- `bootstrap_agent()` MCP tool returning runtime context (agent_id, port, features)
- MCP client configuration for Gemini CLI and OpenCode

### Changed

- Cache `SynapseSettings` in MCP server to avoid re-reading config files per request
- Reuse `_extract_agent_type_from_id()` utility in `cmd_mcp_serve` (deduplicate inline parsing)
- Remove unused `get_base_instruction()` from `SynapseSettings`

### Documentation

- Slim down `AGENTS.md` from 127 to 53 lines (defer details to `CLAUDE.md`)
- Improve `code-simplifier` skill: better triggering, skill relationship table, prioritized checklist
- Add MCP bootstrap design doc (`docs/design/mcp-bootstrap.md`)

## [0.11.8] - 2026-03-09

### Fixed

- canvas stop prefers health endpoint for server detection, falls back to PID file
- verify canvas service identity before kill, add --port to stop

## [0.11.7] - 2026-03-09

### Fixed

- include canvas templates and static files in package data

## [0.11.6] - 2026-03-09

### Changed

- Increase MAX_BLOCKS_PER_CARD from 10 to 30 for richer composite cards

### Documentation

- add canvas card gallery page

### Fixed

- refresh dashboard file locks
- update markdown security test regex for rewritten simpleMarkdown
- address CodeRabbit review comments across canvas system
- address remaining review comments (docs accuracy, CSS, JS guards)
- dep-graph SVG responsive, inline markdown safety, ANSI span tracking
- sidebar layout, DOM update skip, docs accuracy, accessibility

## [0.11.5] - 2026-03-08

### Added

- add Dashboard view to Canvas with operational status separation
- expandable summary+detail widgets in Dashboard
- clickable task cards with detail view

### Changed

- extract createDashHeader helper and reuse formatElapsed

### Documentation

- strengthen task board guidance in skills

### Fixed

- show labeled task detail fields on card click

## [0.11.4] - 2026-03-08

### Added

- separate System panel into dedicated `#/system` route
- add extended System panel sections (skills, sessions, workflows, env, tips)
- glassmorphism redesign with iconography and a refined Canvas color palette
- use the Synapse SVG brand icon in the Canvas sidebar header

### Fixed

- decouple `Latest Posts` from dashboard filters
- stop showing filtered-out agent panels in `Agent Messages`
- remove pin-specific ordering and pin icon rendering from the Canvas frontend

## [0.11.3] - 2026-03-08

### Added

- **Canvas Templates**: 5 built-in layout templates (`briefing`, `comparison`, `dashboard`, `steps`, `slides`) for structured multi-block card display
- **`synapse canvas briefing` CLI command**: Post structured reports with sections, TOC, and collapsible content from JSON or file
- **Canvas cache-busting**: Static files served with `?v=timestamp` query params and `Cache-Control` headers to prevent stale browser cache
- **Canvas SSE reconnection**: `EventSource.onopen` handler re-syncs cards on reconnect, preventing empty canvas after server restart

### Changed

- **Template validation**: `CanvasMessage` extended with `template` (str) and `template_data` (dict) fields; validators enforce schema per template type (sections, sides, widgets, steps, slides)
- **Mermaid SVG sizing**: `runMermaid()` helper removes fixed height/width attributes from SVGs, letting diagrams auto-size based on complexity

### Fixed

- **Canvas View empty after server restart**: Browser cached old JS without SSE reconnection handler
- **Mermaid diagrams overlapping sections**: Template data not returned from API when server ran old code

### Documentation

- Updated `docs/design/canvas.md` with template system, cache-busting strategy, SSE reconnection, and Mermaid sizing
- Updated CLAUDE.md with Canvas test commands and CLI reference
- Updated README.md with Canvas feature row and CLI command table
- Updated plugin skills (`synapse-a2a`) with template documentation
- Updated GitHub Pages: `site-docs/index.md` (Canvas feature card), `site-docs/reference/cli.md`, `site-docs/reference/cli-cheatsheet.md`

## [0.11.2] - 2026-03-08

### Changed

- Task board lifecycle commands now accept unique short task ID prefixes for assign, complete, fail, and reopen operations
- Synapse skill guidance now uses tool-specific automation args wording and clarifies that OpenCode `--agent build` selects the build agent profile rather than acting as a universal skip-approval flag

### Fixed

- Canvas raw JSON posts now autofill `agent_name` from the registry when only `agent_id` is provided
- Canvas system panel now surfaces registry read and JSON parse errors instead of silently dropping broken entries

## [0.11.1] - 2026-03-08

### Added

- **Proactive Mode**: New `SYNAPSE_PROACTIVE_MODE_ENABLED` environment variable that injects mandatory Synapse feature usage instructions (task board, shared memory, canvas, file safety, delegation, broadcast) via `.synapse/proactive.md`

### Documentation

- Added proactive mode to CLAUDE.md, README.md, guides, plugin skills, and GitHub Pages site
- New `docs/proactive-mode-spec.md` specification document
- New `site-docs/guide/proactive-mode.md` user guide

### Tests

- Added `tests/test_proactive_mode.py` with 15 tests covering settings, injection, file lists, template structure, and independence from learning mode

## [0.11.0] - 2026-03-07

### Added

- **Canvas SPA routing**: Hash-based routing with `#/` (Canvas view — full-viewport latest card) and `#/dashboard` (Dashboard view with system panel, live feed, agent messages)
- **Canvas view**: Immersive full-screen projection of the latest agent card with ambient glow, title bar, floating info bar, and `prefers-reduced-motion` support
- **Highlight.js integration**: Syntax highlighting for `code` and `file-preview` card formats via CDN
- **Side-by-side diff renderer**: Replaced unified diff with left/right split view showing line numbers, additions, deletions, and context
- **HTML card full-height**: iframe fills Canvas view content area using CSS flex layout
- **Chart.js all types**: Support for bar, line, pie, doughnut, radar, polarArea, scatter, and bubble chart types

### Changed

- **Dashboard layout**: System panel fixed at top (max 40vh), live feed and agent messages scroll independently below
- **Canvas performance**: `renderCurrentView()` debounced with `requestAnimationFrame`; spotlight skips rebuild when displayed card unchanged; O(n) reduce replaces O(n log n) sort for latest card
- **iframe sandbox**: Reverted to `allow-scripts` only (removed `allow-same-origin` to prevent XSS via agent-generated HTML)
- **Diff pane construction**: Extracted `buildDiffPane()` helper to eliminate copy-paste DOM construction

### Documentation

- **docs/design/canvas.md**: Updated with SPA routing, side-by-side diff, highlight.js, and implementation phases
- **Plugin skills**: Updated `synapse-a2a` SKILL.md, `references/commands.md`, and `references/features.md` with Canvas features and all 18 formats
- **GitHub Pages**: Updated `site-docs/guide/canvas.md` with routing documentation and rendering details

## [0.10.1] - 2026-03-06

### Changed

- **Skill Progressive Disclosure**: Restructured `synapse-a2a` SKILL.md (877→159 lines) and `synapse-manager` SKILL.md (426→199 lines). Detailed content moved to `references/` subdirectories for on-demand loading, reducing context window consumption
- **synapse-a2a description**: Optimized with explicit trigger contexts ("Use this skill when...") for more reliable skill activation
- **synapse-manager description**: Added implementation task triggers for better activation on multi-phase plans
- **synapse-reinst description**: Added trigger contexts for lost identity and broken synapse send/reply scenarios
- **Why-driven documentation**: Replaced must-driven language ("EVERY EDIT NEEDS A LOCK") with explanatory language ("Locking prevents data loss when two agents edit the same file")

### Added

- **synapse-a2a references**: `collaboration.md`, `messaging.md`, `spawning.md`, `features.md` — detailed reference files for Progressive Disclosure
- **synapse-manager references**: `auto-approve-flags.md`, `worker-guide.md`, `features-table.md`, `commands-quick-ref.md`
- **synapse-manager scripts**: `wait_ready.sh` (readiness polling), `check_team_status.sh` (team status aggregation), `regression_triage.sh` (regression vs pre-existing failure classification)
- **Skill structure tests**: `tests/test_skill_structure.py` — validates description length, body line count, references existence, trigger contexts, and script permissions

### Removed

- **synapse-docs from plugins**: Moved to `.agents/skills/` only (dev-only skill, not distributed to users)

## [0.9.5] - 2026-03-06

### Fixed

- **Spawn pane layout** (#336): `synapse spawn` now creates side-by-side (horizontal) tmux panes instead of top-bottom
- **ANSI escape sequences in A2A replies** (#337): `get_context()` now strips ANSI escape codes, producing clean text for artifacts, history, and replies

### Changed

- **Task receipt collaboration flow**: agents now identify independent work units and delegate via `synapse spawn` + `synapse send --silent` when receiving tasks

## [0.9.4] - 2026-03-06

### Fixed

- **`synapse init` data loss**: `_copy_synapse_templates()` was replacing the entire `.synapse/` directory, destroying user-generated data (saved agent definitions, SQLite databases, sessions, workflows, worktrees). Changed to merge strategy that only overwrites template files.

### Changed

- **`parallel-docs-simplify-sync` skill**: replaced custom `code-simplifier` subagent with Claude Code built-in `/simplify` command

### Documentation

- Updated `synapse init` descriptions across guides, skills, and site-docs to reflect merge strategy behavior

## [0.9.3] - 2026-03-05

### Added

- **Proactive Collaboration Framework**: agents now receive a decision framework at startup for when to delegate, ask for help, report progress, and share knowledge
- **Cross-model spawn preference**: agents are guided to spawn different model types for diverse perspectives and rate limit distribution
- **Worker autonomy**: worker agents can now proactively spawn helpers, delegate subtasks, and request reviews — not just managers
- **USE SYNAPSE FEATURES ACTIVELY section**: explicit guidance for agents to use task board, shared memory, file safety, worktree, broadcast, and history
- **TRANSPORT column in text-mode `synapse list`**: non-TTY output now includes transport state (UDS→/→UDS/TCP→/→TCP) for scripted use

### Changed

- **synapse-manager Step 1**: managers now check existing agents in the same WORKING_DIR before spawning new ones
- **Mandatory cleanup**: all skill docs enforce `synapse kill <name> -f` after spawned agents complete work

### Documentation

- Added Collaboration Patterns section to synapse-a2a skill
- Added Worker Agent Guide to synapse-manager skill (receipt/during/completion/failure/no-manager)
- Updated site-docs: cross-agent-scenarios, agent-management, agent-teams, communication, skills, multi-agent-setup
- Enriched documentation from docs/ and guides/ sources

### Fixed

- Address review findings — webhook 4xx retry bug and doc corrections
- Address review round 2 — security, payload format, and consistency
- Address review round 3 — payload consistency and CSS consolidation

## [0.9.2] - 2026-03-04

### Added

- **Session Restore `--resume`**: resume each agent's CLI conversation session when restoring
  - `synapse session restore <name> --resume` — passes per-agent resume args (claude `--resume`/`--continue`, gemini `--resume`, codex `resume`/`resume --last`, copilot `--resume`)
  - `synapse session save` now captures `session_id` from the agent registry
  - `synapse session show` now displays `session_id` per agent
  - Shell-level time-guarded fallback: if resume fails within 10s, retries without resume args

## [0.9.1] - 2026-03-04

### Added

- **Saved Workflows** (`synapse workflow`): define and replay reusable message sequences to running agents
  - `synapse workflow create <name>` — generate a template YAML workflow
  - `synapse workflow list` — list saved workflows (Rich TUI table or plain-text fallback)
  - `synapse workflow show <name>` — display workflow steps and details
  - `synapse workflow run <name>` — execute steps sequentially via A2A send
  - `synapse workflow delete <name>` — remove saved workflows
  - `--dry-run` and `--continue-on-error` flags for run
  - Project/user scope storage (`.synapse/workflows/`, `~/.synapse/workflows/`)
- Enhance help discoverability for root/team/session commands

### Fixed

- `WorkflowStore.exists()` for file-existence checks (corrupted YAML no longer bypasses overwrite protection)
- Validate `WorkflowStep` target/message are `str` type, not just non-empty
- `_parse_file` warns and uses filename stem when YAML `name` field mismatches

### Documentation

- Add x-synapse-context Agent Card extension documentation
- Add workflow guide and CLI reference to GitHub Pages
- Update README, guides, CLAUDE.md, and plugin skills with workflow commands

## [0.9.0] - 2026-03-03

### Added

- **Session Save/Restore** (`synapse session`): save and restore team configurations as named snapshots
  - `synapse session save <name>` — capture running agent set (profiles, names, roles, ports, worktrees)
  - `synapse session list` — list saved sessions with agent counts
  - `synapse session show <name>` — display session details
  - `synapse session restore <name>` — re-spawn agents from saved configuration (with `--worktree` support)
  - `synapse session delete <name>` — remove saved sessions
  - Scope support: `--project` (default, `.synapse/sessions/`), `--user` (`~/.synapse/sessions/`), and `--workdir DIR` (custom project scope)

### Documentation

- Add Session Save/Restore guide (`site-docs/guide/session.md`)
- Update CLI reference, README, guides, and plugin skills with session commands

## [0.8.6] - 2026-03-03

### Changed

- Unify agent example names across all documentation with model-hinting English names (Claud, Cody, Rex, Gem)
- Replace saved agent definition names from Japanese (クラウド, コデクス, クォア, ジェミナ) to English

### Documentation

- Add "On-Demand Specialists" card to "Why Synapse?" section (saved templates, worktree isolation, API spawning)
- Update "Agent Management" card in Key Features to focus on delegate-mode
- Expand delegate-mode guide with architecture, config, and use cases
- Document `--agent`/`-A` flag for starting agents with saved agent definitions
- Document role file conventions: recommended directories (`./roles/`, `~/my-roles/`)
- Document petname ID format, scope precedence (project > user), `.agent` file format
- Update 7 site-docs files (agent-teams, cross-agent-scenarios, communication, agent-management, cli, api, worktree) with consistent agent names
- Update guides/ (references.md, usage.md) and CLAUDE.md with new agent IDs and names
- Sync plugin skills (synapse-a2a, synapse-manager) with updated agent names
- Fix spawn API example: correct profile/flag mismatch (Gemini profile with Claude-specific `--dangerously-skip-permissions`)
- Fix `synapse skills apply` example: use Codex agent name instead of Gemini-implying name
- Fix team start example: use canonical agent names (`Checker`, `Gem`) instead of ad-hoc role names
- Fix worktree branch naming in cross-agent scenarios: use explicit `-w <name>` to match `git merge` commands
- Fix `guides/references.md` annotation: clarify mixed spec format (saved_agent_name + profile:name)

## [0.8.5] - 2026-03-02

### Changed

- Replace copyrighted character names with generic English names (Alice, Bob, Charlie, Dave, Eve, Frank) across docs, tests, and agent definitions
- Replace Japanese role descriptions with English equivalents in `.agent` files and role templates

### Documentation

- Add skill installation guide (`npx skills add s-hiraoku/synapse-a2a`) to Getting Started, Quick Start, and Skills pages
- Add `synapse-reinst` to Built-in Skills section with admonition
- Remove `doc-organizer` from core skill install tables (not essential for A2A communication)
- Add prerequisites box to Quick Start page
- Add worktree profile shortcut examples to plugin skill commands reference

## [0.8.4] - 2026-03-02

### Added

- **Synapse-native worktree isolation** (`--worktree` / `-w`): all agent types (Claude, Gemini, Codex, OpenCode, Copilot) can now run in isolated git worktrees under `.synapse/worktrees/`
  - Auto-generated adjective-noun names or explicit `--worktree <name>`
  - Automatic cleanup on agent exit (prompts if unsaved changes or new commits exist)
  - Per-agent worktrees in `synapse team start --worktree`
  - API support via `POST /spawn` with `worktree` field
  - `[WT]` indicator in `synapse list`

### Fixed

- worktree name validation with regex whitelist to prevent path traversal
- `_try_cleanup_worktree` wrapped in try/except to prevent shutdown failures
- `has_uncommitted_changes`/`has_new_commits` return True on subprocess failure (defensive)
- initialize worktree locals before try block to prevent `UnboundLocalError` in finally
- handle empty `create_panes` return in team start worktree flow with rollback

## [0.8.3] - 2026-03-01

### Changed

- **Breaking**: unify `.gemini/skills/` into `.agents/skills/` — Gemini now uses the same skill directory as Codex, OpenCode, and Copilot
  - **Migration**: if you have skills in `.gemini/skills/`, copy or move them to `.agents/skills/`
  - TUI deploy indicators simplified from `[C✓ A✓ G·]` to `[C✓ A✓]`
- add `synapse-docs` skill to `plugins/` source of truth

### Fixed

- fix `AgentProfileStore` scope inconsistency — shutdown save now uses startup store's `project_root` instead of `Path.cwd()`

## [0.8.2] - 2026-03-01

### Changed

- unify agent identifier terminology across documentation
  - **Runtime ID** (`synapse-claude-8100`): temporary identifier generated at startup
  - **Agent ID** (`wise-strategist`): persistent identifier for saved agent definitions (formerly "petname")
- replace `--response`/`--no-response` flags with `--wait`/`--notify`/`--silent` response modes
  - `--wait`: synchronous blocking (replaces `--response`)
  - `--notify`: async notification on completion (new default)
  - `--silent`: fire-and-forget (replaces `--no-response`)
- add controller status-change callback for proactive task completion detection

### Fixed

- fix IDLE status bug in `map_synapse_status_to_a2a` — use actual status names (`READY`, `DONE`) instead of nonexistent `IDLE`

## [0.8.1] - 2026-02-28

### Fixed

- add missing `manager` and `documentation` skill set definitions to bundled defaults
- merge `coordinator` skill set into `manager` (adds `synapse-reinst` to manager)

### Documentation

- update skill set tables across all documentation to reflect 6 default sets
- clarify CHANGELOG wording to avoid coordinator skill set vs role confusion

## [0.8.0] - 2026-02-28

### Added

- add saved-agent manager (`synapse agents list/show/add/delete`) for reusable agent configurations (#307)
- add completion callback for `--no-response` task tracking (`POST /history/update`) (#308)
- add `synapse-manager` skill — structured 5-step multi-agent management workflow
- add `manager` and `documentation` skill sets for multi-agent management and docs-focused agents
- add `doc-organizer` skill — documentation audit, restructure, and deduplication
- include sender identification in PTY-injected A2A messages
- implement Ghostty split pane support for `team start` and `spawn`
- enforce agent name uniqueness across interactive start, spawn, and team start
- add save-on-exit prompt for interactive runs

### Changed

- extend `synapse spawn` and `synapse team start` to accept saved-agent ID/name
- move reply target persistence to dedicated `~/.a2a/reply/` directory (configurable via `SYNAPSE_REPLY_TARGET_DIR`)
- extract `build_sender_prefix` and unify reply path formatting
- always add `--no-setup --headless` for spawned agents
- simplify agent spec format to `profile[:name[:role[:skill_set[:port]]]]`
- harden registry writes with registry-wide lock and atomic name conflict rejection

### Fixed

- Ghostty `team start` now uses split panes (`Cmd+D`) instead of spawning new windows
- Ghostty commands injected via clipboard paste to avoid character mangling
- Ghostty panes auto-close on agent exit
- pass Ghostty `-e` arguments as separate argv entries
- pre-allocate ports in `team start` to avoid race conditions
- resolve shared memory bugs (#286-#291)
- resolve memory CLI tag parsing and broadcast notify issues
- correct soft interrupt priority (p5→p4) and unify PID matching terminology
- pass interactive setup name/role to TerminalController
- `registry.py` `list_agents()` handles `KeyError` gracefully for malformed registry files

### Documentation

- add saved-agent definitions management guide and CLI reference
- update docs, skills, and site for Ghostty spawn fixes
- document Ghostty focus-dependent targeting limitation
- sync sender identification format across all documentation

## [0.7.0] - 2026-02-28

### Added

- add GitHub Pages documentation site with MkDocs Material
- add `get_reply_target_dir()` to `synapse/paths.py` with `SYNAPSE_REPLY_TARGET_DIR` env var override
- add github-pages-sync skill for site-docs maintenance
- add shared memory for cross-agent knowledge sharing
- add `synapse-manager` skill — structured 5-step multi-agent management workflow (Delegate, Monitor, Verify, Feedback, Review)
- add `manager` skill set — combines synapse-a2a, synapse-manager, task-planner, agent-memory, and code-review for multi-agent management
- add `doc-organizer` skill — documentation audit, restructure, deduplication, terminology normalization, navigation improvement, and staleness detection
- add `documentation` skill set — combines synapse-a2a, project-docs, doc-organizer, api-design, and agent-memory for documentation-focused agents

### Documentation

- sync list and configuration docs with current implementation
- add shared memory feature to documentation
- add shared-memory commands and architecture to CLAUDE.md
- fix Material icon rendering by adding markdown attribute to HTML tags
- add shared memory feature card to site-docs homepage

### Fixed

- move reply target persistence from `~/.a2a/registry/` to `~/.a2a/reply/` to prevent `.reply.json` files from causing `KeyError: 'agent_id'` in `list_agents()`
- add `KeyError` to exception handling in `registry.py` `list_agents()` as defense-in-depth against malformed registry files
- address CodeRabbit review findings for GitHub Pages docs
- correct 16 documentation inaccuracies against actual codebase
- address CodeRabbit review findings for quickstart and agent-teams

## [0.6.12] - 2026-02-26

### Fixed

- Store long identity instructions in files via `LongMessageStore` to prevent Ink TUI from collapsing large paste into shortcut display and ignoring CR submit
- Increase Copilot CLI `write_delay` from 0.05s to 0.5s for reliable TUI rendering before CR
- Fix Update Installers workflow version extraction — fall back to `gh release view` when `head_branch` is not a version tag

### Tests

- Update identity instruction tests to verify file storage behavior
- Add `_read_stored_instruction` helper for reading stored file content in tests

## [0.6.11] - 2026-02-26

### Fixed

- use event-driven workflow chain for PyPI Trusted Publishing
- Copilot CLI initial instructions CR not submitted (#277)

## [0.6.10] - 2026-02-26

### Fixed

- Fix Copilot CLI `synapse send` not submitting `\r` — add per-profile `write_delay` configuration to control delay between data and submit_seq PTY writes
- Prevent REPLY EXPECTED marker duplication + add `PTY_WRITE_MAX` constant
- Chain publish and update-installers from auto-release workflow

### Changed

- Make `write_delay` configurable per agent profile YAML (`write_delay: 0.05` for Copilot, default 0.5s for Claude Code)

### Documentation

- Add `write_delay` profile setting to `CLAUDE.md` (Claude Code + Copilot sections)
- Add `write_delay` field documentation to `guides/profiles.md` (schema, field table, new section 3.4, Copilot section)
- Update `HANDOFF_CLAUDE_ENTER_KEY_ISSUE.md` with Bug 5 entry and `write_delay` docs

### Tests

- Add tests for custom write_delay, zero write_delay (skip sleep), and default write_delay behavior

## [0.6.9] - 2026-02-25

### Fixed

- Fix bracketed paste mode issue where submit_seq (CR) was ignored in Claude Code v2.1.52+ — split `write()` into separate data and submit_seq writes with `WRITE_PROCESSING_DELAY` (0.5s) delay between them

### Changed

- Extract `_write_all()` helper from `write()` for complete write retry loop
- Use named `logger` instead of bare `logging` in `write()` error handler for consistent log output

### Documentation

- Update `HANDOFF_CLAUDE_ENTER_KEY_ISSUE.md` with bracketed paste mode details and write strategy evolution table
- Add split write explanation to `CLAUDE.md` Claude Code profile section

## [0.6.8] - 2026-02-23

### Added

- Add working_dir mismatch warning to `synapse send` and `synapse interrupt` with `--force` bypass (#266)
- Add WORKING_DIR column to `synapse list` non-TTY text output
- Add learning mode with independent prompt improvement and translation flags (#268)

## [0.6.7] - 2026-02-23

### Added

- **Readiness Gate**: `/tasks/send` and `/tasks/send-priority` endpoints are blocked until agent completes initialization; returns 503 with `Retry-After: 5` when not ready; priority 5 and reply messages bypass the gate (#248)
- **Spawn CWD inheritance**: Spawned agents now inherit the parent's working directory (#248)
- **CI conflict detection**: `poll-pr-status.sh` hook monitors PR mergeable state and reports merge conflicts via systemMessage, suggesting `/fix-conflict` for auto-resolution
- **CodeRabbit review monitoring**: `poll-pr-status.sh` polls for CodeRabbit bot reviews, classifies inline comments by severity (bug/style/suggestion), and suggests `/fix-review` for actionable issues
- **`/fix-conflict` skill**: Auto-resolves merge conflicts via test merge, conflict analysis, resolution, local verification, and push
- **`/fix-review` skill**: Auto-fixes CodeRabbit bug/style comments with keyword-based classification; reports suggestions without modifying code
- **`/check-ci` extended**: Now shows merge conflict state and CodeRabbit review status alongside CI checks; `--fix` flag suggests all available fix commands in priority order
- **Tornado features**: Soft interrupt, token tracking, task board extensions (`get_task`, 404/409 split, Kanban example) (#260)
- **`--worktree` skill guidance**: Added worktree usage instructions to synapse-a2a skill (#253)
- **`parallel-docs-simplify-sync` skill**: Runs synapse-docs, code-simplifier, and sync-plugin-skills in parallel

### Fixed

- **iTerm2 spawn targeting**: Fixed AppleScript targeting tab instead of session (#248)
- **Shell-quoted CWD**: Fixed tmux, iTerm2, and Terminal.app spawn commands when CWD contains spaces (#248)
- **Hardcoded agent IDs**: Replaced hardcoded `--from` agent IDs with `$SYNAPSE_AGENT_ID` in agent-facing files
- **Task board API**: 404/409 split for task errors, `get_task` endpoint, validation and error handling improvements (#260)

### Refactored

- **`_mark_agent_ready()` helper**: Extracted from controller for cleaner readiness state management

### Documentation

- **Worktree/tool_args accuracy**: Corrected documentation that incorrectly claimed Synapse filters `--worktree` by agent type — Synapse forwards all `tool_args` to every agent; only Claude Code acts on `--worktree`
- **Safe worktree examples**: Added Claude-only alternative (`synapse team start claude -- --worktree`) alongside multi-agent examples to prevent errors on non-Claude CLIs
- **Worktree cleanup guidance**: Added branch merge/delete instructions after `synapse kill` in examples, headless cleanup caveat for `synapse spawn`
- **Gitignore recommendations**: Added `.claude/worktrees/` to recommended `.gitignore` entries; added `.venv/` to not-copied file examples for consistency
- **Cross-references**: Added link from team start worktree example to "Worktree の注意事項" section in `guides/usage.md`
- **Skill copy sync**: Synchronized .agents/ skill copies with canonical plugins/ source
- **CI Automation docs**: Added CI hooks/skills to CLAUDE.md architecture, README features/skills tables, and plugin skill references
- **Default base branch**: Explicitly documented `main` as default PR base branch in CLAUDE.md Branch Management Rules
- **Claude Code worktree technical guide**: Added `docs/HANDOFF_WORKTREE.md`
- **Skill update rules**: Added to CLAUDE.md and AGENTS.md

### Tests

- **Space-in-CWD tests**: Added for zellij/ghostty spawn with spaces in paths (#248)

## [0.6.6] - 2026-02-20

### Documentation

- **CLI docs consistency**: Added missing commands (`init`, `reset`, `broadcast`, `auth`, `kill`, `jump`, `rename`) to `guides/usage.md`, `guides/references.md`, and `CLAUDE.md`
- **Port table update**: Added `opencode` (8130-8139) and `copilot` (8140-8149) to `references.md` port table
- **Mermaid diagrams**: Updated command flowcharts in `usage.md` and `references.md` with all current commands
- **Graceful shutdown fix**: Corrected `synapse kill` description from "即時終了" to "グレースフルシャットダウン" in `usage.md`
- **Skill sync**: Synced `anthropic-skill-creator` plugin with `.agents` version (stricter name validation, YAML-safe description placeholder)

## [0.6.5] - 2026-02-20

### Fixed

- **Shell safety in ambiguous target errors**: Agent names with spaces or special characters are now `shlex.quote()`-d in `synapse send` command examples
- **Graceful shutdown flow**: Set `SHUTTING_DOWN` status before shutdown request, added grace period before SIGTERM, and SIGKILL escalation if process survives
- **Shutdown timeout budget**: HTTP wait, grace period, and escalation wait are now bounded within `timeout_seconds` so the total never exceeds the configured limit

## [0.6.4] - 2026-02-20

### Added

- **Spawn readiness warning**: `synapse spawn` now waits for agent registration and warns with concrete `synapse send` command examples if the agent is not yet ready (#244)
- **Tool args guardrails**: `_warn_synapse_flags_in_tool_args()` detects known Synapse flags (`--port`, `--name`, `--role`, etc.) accidentally placed after `--` separator (#244)

### Changed

- **Send target error UX**: `_format_ambiguous_target_error()` now shows runnable `synapse send` commands instead of just listing agent IDs (#244)

### Fixed

- **Copilot spawn parsing**: Fixed spawn command parsing for Copilot agent (#244)
- **Test assertion alignment**: Updated `test_ambiguous_target_shows_hint` and `test_update_status_file_permission_error` to match implementation (#244)

### Refactored

- **`cmd_kill` SIGTERM dedup**: Extracted shared SIGTERM sending logic from graceful/force branches in `cli.py`
- **`_print_observation_detail` helper**: Extracted identical observation display logic from `cmd_history_show` and `cmd_trace`
- **`_deploy_and_print` helper**: Consolidated shared deploy logic from `_do_deploy` and `_do_deploy_all` in skill_manager.py
- **Removed redundant imports**: Cleaned up duplicate `import re` in `tools/a2a.py` and `import shutil` in `skills.py`

### Documentation

- Updated test badge across all README translations (1389 → 1932 tests)
- Added v0.6.4 changelog entry for #244
- Added `test_copilot_spawn_fixes.py` to CLAUDE.md test commands
- Added git-cliff step to README Development & Release section
- Synced plugin skills with spawn readiness warning, tool_args guardrail, and send UX improvements

### Tests

- New `tests/test_copilot_spawn_fixes.py` (24 tests): parser guardrails, spawn readiness, send UX, CLI parse ordering, env encoding roundtrip (#244)

## [0.6.3] - 2026-02-19

### Added

- **git-cliff changelog generation**: `cliff.toml` config and `scripts/generate_changelog.py` wrapper for automated CHANGELOG.md generation from Conventional Commits (#242)

### Changed

- **Release workflow Step 1**: Updated to use `python scripts/generate_changelog.py` instead of manual changelog writing (#242)

### Fixed

- **Skill creator YAML template**: Quoted `description` field in `new_skill.sh` to prevent YAML array parsing (#242)
- **Skill creator name validation**: Reject leading/trailing/consecutive hyphens and purely numeric names (#242)
- **spawn/start `tool_args` passthrough**: `argparse.REMAINDER` now correctly handles named options and NUL bytes in env vars (#241)

### Documentation

- Updated release guide and `/release` skill with git-cliff generation steps (#242)

### Tests

- New `tests/test_generate_changelog.py` (15 tests): git-cliff binary detection, invocation wrapper, CHANGELOG update logic, CLI integration (#242)

## [0.6.2] - 2026-02-18

### Added

- **Agent directory deploy indicators**: Each skill row shows `[C✓ A✓ G·]` indicators for .claude/.agents/.gemini directory presence (#239)
- **Skill detail deploy status**: SYNAPSE scope skill detail view shows per-agent deployment status across user and project scopes (#239)
- **Deploy All action**: One-click deployment of a SYNAPSE skill to all agent directories in user scope, with confirmation prompt (#239)
- **`check_deploy_status()` helper**: New function in `skills.py` to check skill deployment across all agent directories (#239)

### Changed

- **Manage Skills TUI navigation**: Replaced flat skill list with scope-based submenu (Synapse → User → Project), PLUGIN scope excluded from end-user TUI (#239)
- **Python dependency**: Updated to Python 3.14 (#235)

### Fixed

- **`cmd_skills_move` dry-run order**: SYNAPSE/PLUGIN scope rejection now checked before dry-run branch to prevent misleading output (#239)
- **`_skills_menu` Back/Quit index**: Fixed off-by-one error in `build_numbered_items` footer index calculation (#239)
- **Path traversal in skill names**: `validate_skill_name()` now rejects `"."` and `".."` to prevent directory traversal (#239)
- **`create_skill` error handling**: `cmd_skills_create` and `_create_flow` now catch `ValueError` from `validate_skill_name` (#239)
- **CLAUDECODE env leak in spawn**: Unset `CLAUDECODE` env var in spawned agent commands to prevent nested-session detection failure (#238)

### Documentation

- Updated guides/usage.md and guides/references.md with scope submenu flow and agent directory indicator table (#239)
- Synced spawn docs across SKILL.md, commands.md, examples.md with `synapse reply` known limitation (#238)
- Added spawn troubleshooting section to guides/troubleshooting.md (#238)

### Tests

- Added `TestCheckDeployStatus` (6 tests) to `test_skills.py`: deployment detection across user/project scopes, shared agents dir, none dirs (#239)
- Added `TestManageSkillsDisplay` (6 tests) to `test_cmd_skill_manager.py`: skill labels, scope menu, detail header deploy status (#239)
- Added `test_reject_dot_and_dotdot` to `TestSkillNameValidation` (#239)
- Added CLAUDECODE env unset tests to `test_spawn.py` (#238)

## [0.6.1] - 2026-02-18

### Added

- **Auto GitHub Release workflow**: Creates git tag + GitHub Release automatically when `pyproject.toml` version changes on main (#234)

### Changed

- **Release process**: Tag creation and GitHub Release automated via `auto-release.yml`; manual steps reduced to version bump, changelog update, and PR merge (#234)

### Fixed

- **`extract_changelog` error handling**: Raises `ValueError` instead of `sys.exit(1)` for testability (#234)

### Documentation

- Updated release guide and READMEs for auto-release workflow (#234)

### Tests

- New `tests/test_extract_changelog.py`: changelog extraction script tests (#234)

## [0.6.0] - 2026-02-17

### Added

- **`synapse spawn` command**: Spawn a single agent in a new terminal pane (`synapse spawn claude --name Helper --role "task runner"`) with auto-assigned port, custom name/role, and skill set support (#195)
- **`POST /spawn` API endpoint**: Agents can programmatically spawn other agents via A2A protocol with `run_in_threadpool` for non-blocking execution
- **Headless mode (`--headless`)**: Spawned agents skip all interactive setup (name/role prompts, startup animation, approval prompts) while keeping A2A server and initial instructions active
- **Ghostty terminal support**: New `create_ghostty_window()` for spawning agents in Ghostty windows on macOS
- **Pane auto-close**: All supported terminals (tmux, zellij, iTerm2, Terminal.app, Ghostty) automatically close spawned panes when agent process terminates — zellij uses `--close-on-exit`, iTerm2/Terminal.app use `exec` to replace the shell process, Ghostty uses `; exit` suffix (clipboard-paste injection is incompatible with `exec`)
- **tool_args passthrough**: `synapse spawn` and `synapse team start` now accept `-- <args>` to pass CLI flags (e.g., `--dangerously-skip-permissions`) through to the underlying agent tool. Also available via `tool_args` field in `POST /spawn` and `POST /team/start` API endpoints (#229)
- **Injection observability**: Structured `INJECT/{RESOLVE,DECISION,DELIVER,SUMMARY}` log points in `_send_identity_instruction()` for diagnosing initial instruction injection failures (`grep INJECT` in logs) (#229)

### Changed

- **Agent spec format**: Extended to 6 colon-separated fields (`profile:name:role:skill_set:port:headless`)
- **`_build_agent_command()`**: Uses `sys.executable -m synapse.cli` for consistent Python environment across parent/child processes, with `use_exec` parameter for shell-based terminals
- **Port validation**: Agent spec port field validated with `isdigit()` to reject non-numeric values
- **`--skill-set` short flag**: Changed from `-ss` to `-S` for standard single-character convention
- **Logger unification**: `_send_identity_instruction()` now uses module-level `logger.*` consistently (was mixing `logging.*` and `logger.*`)
- **Code simplification**: Extracted focused helper methods in `controller.py` (`_wait_for_input_ready()`, `_build_identity_message()`), `terminal_jump.py` (`_get_spec_field()`), and `cli.py` (`_run_pane_commands()`) to improve readability

### Fixed

- **Zellij pane revival**: Added `--close-on-exit` to all `zellij run` commands to prevent panes from surviving after agent kill
- **Plugin skill sync**: .agents/skills/synapse-a2a/ (Gemini) references/file-safety.md was missing --wait lock examples that existed in the plugin source
- **Spawn error handling**: `subprocess.run` uses `check=True` for proper error propagation; empty `create_panes` result raises `RuntimeError`
- **`POST /spawn` error response**: Returns HTTP 500 (not 200) when `spawn_agent` fails
- **CLAUDE.md**: Removed duplicated "Agent Teams feature tests" block

### Documentation

- Added spawn documentation to SKILL.md, commands.md, api.md, examples.md (synced across 4 locations)
- Updated README.md (all 6 languages), CLAUDE.md, guides/usage.md, guides/references.md
- Documented Ghostty layout/all_new limitation in docstring

### Tests

- New `tests/test_spawn.py` (31 tests): CLI parsing with real argparse, core `spawn_agent()`, Ghostty panes, port validation, headless mode, `wait_for_agent()`
- New `tests/test_spawn_api.py` (6 tests): POST /spawn endpoint behavior, error handling, parameter pass-through
- Added `TestExecPrefixForPaneAutoClose` (8 tests): exec behavior verification per terminal type
- Added `test_zellij_close_on_exit_always_present` to `test_auto_spawn.py`
- New `tests/test_injection_observability.py` (16 tests): RESOLVE/DECISION/DELIVER/SUMMARY structured log verification
- New `tests/test_tool_args_passthrough.py` (25 tests): tool_args through _build_agent_command, create_panes, spawn_agent, CLI parsing, API models

## [0.5.2] - 2026-02-15

### Added

- **anthropic-skill-creator plugin skill**: Bundled Anthropic's skill creation methodology as a plugin skill (`plugins/synapse-a2a/skills/anthropic-skill-creator/`)
- **Create Skill guided flow**: `synapse skills create` shows step-by-step guidance for creating skills using `/anthropic-skill-creator` inside an agent
- **Shared TUI helpers**: Extracted `TERM_MENU_STYLES`, `MENU_SEPARATOR`, `build_numbered_items()` to `synapse/styles.py` for consistent menu styling

### Changed

- **Skill Manager TUI**: Added `[N]` keyboard shortcuts to all menus, matching config TUI pattern
- **Scope display**: Manage Skills now shows descriptive scope headers (e.g., "Synapse — Central Store (~/.synapse/skills/)")
- **Config TUI**: Unified menu styling with shared helpers from `synapse/styles.py`

### Documentation

- Updated `synapse skills create` description across README, CLAUDE.md, guides, and plugin skills
- Added `anthropic-skill-creator` to plugin README

## [0.5.1] - 2026-02-14

### Added

- **Vim-style navigation**: `hjkl` key bindings for `synapse list` interactive selection (Enter=jump, K=kill confirmation)
- **SSL/TLS options**: `--ssl-cert` and `--ssl-key` for `synapse start` command
- **File safety wait options**: `--wait-interval` for `synapse file-safety lock`

### Changed

- **Installation docs**: Unified macOS/Linux/WSL2 install section across all 6 language READMEs with pipx as recommended method
- **Homebrew formula**: Added Rust build dependency, `preserve_rpath`, and resource marker insertion
- **Config TUI**: Added `--no-rich` flag to use legacy questionary-based interface
- **History cleanup**: Added `--dry-run` and `--no-vacuum` options

### Fixed

- **Homebrew formula**: Switched to pip+venv pattern for reliable installation (#216)

### Documentation

- Synced plugin skill references (commands.md, file-safety.md) across all 3 scopes
- Updated footer hints in `synapse list` for new key bindings

## [0.5.0] - 2026-02-13

### Added

- **Homebrew formula**: `homebrew/synapse-a2a.rb` using `Language::Python::Virtualenv` pattern for native macOS installation via `brew install`
- **Scoop manifest**: `scoop/synapse-a2a.json` with venv-based installer, `checkver`, and `autoupdate` for Windows users
- **CI/CD workflow**: `.github/workflows/update-installers.yml` auto-generates PR to update formula/manifest on `v*` tag push
- **Helper scripts**: `scripts/patch_homebrew_formula.py` (patches poet-generated resource stanzas) and `scripts/update_scoop_manifest.py` (updates version/hash from PyPI)

### Changed

- **README.md install section**: Platform-specific install instructions (macOS Homebrew / Linux pipx / Windows Scoop+WSL2 / Developer) with upgrade and uninstall commands
- **guides/multi-agent-setup.md**: Added user-facing install section (Homebrew / pipx / Scoop) alongside existing developer section

### Removed

- `requirements.txt` — redundant with `pyproject.toml` dependencies, not referenced by any code or CI

### Documentation

- Updated README.zh.md and README.es.md install sections to match English README

## [0.4.4] - 2026-02-12

### Added

- **Skill set details in initial instructions**: When an agent starts with a skill set, the skill set name, description, and included skills are now included in the agent's initial instructions
- `format_skill_set_section()` utility function for formatting skill set information
- `skill_set` parameter on `TerminalController` to pass skill set through to instruction generation

### Documentation

- Updated CLAUDE.md startup sequence to mention skill set info
- Added skill set integration section to `guides/agent-identity.md`
- Added skill set instruction note to `guides/references.md`
- Synced plugin skills (SKILL.md, commands.md) to `.claude/` and `.agents/`

### Tests

- Added `tests/test_controller_skill_set.py` with 6 tests covering skill set in instructions

## [0.4.3] - 2026-02-12

### Added

- **Handoff-by-default for `synapse team start`**: 1st agent takes over current terminal via `os.execvp`, remaining agents start in new panes
- `--all-new` flag to restore previous behavior (all agents in new panes)
- Terminal.app (tabs) support for team start pane creation

### Changed

- Default `synapse team start` behavior: 1st agent = handoff (current terminal), rest = new panes
- Agent spec format extended to `profile[:name[:role[:skill_set]]]`

### Documentation

- Updated all 7+ documentation files for handoff behavior and `--all-new` flag
- Plugin skills: added missing commands (`delete`/`move` skill, `set show`, `trace`), `--message-file`/`--stdin`/`--attach` options, `SHUTTING_DOWN` status
- Fixed Zellij terminal jump description to match implementation

### Tests

- Added `TestAgentSpecParsing` for `profile:name:role:skill_set` format
- Added handoff and `--all-new` behavior tests

## [0.4.2] - 2026-02-12

### Added

- Bundled default skill set definitions at `synapse/templates/.synapse/skill_sets.json`
- Fallback loading of bundled skill sets when project `skill_sets.json` is missing
- Support for `profile:name:role:skill_set` format in `synapse team start`

### Changed

- Startup skill-set selector switched to `simple_term_menu` based TUI
- Skill-set selector row format simplified to `N. <name> - <count> skills`
- Team start pane creation support expanded to zellij

### Documentation

- Updated `guides/usage.md` and `guides/references.md` for team start and zellij behavior

### Tests

- Added/updated tests for skill-set loading fallback, skill-set selector TUI, and team start auto-spawn behavior

## [0.4.1] - 2026-02-11

### Added

- **zellij support for `synapse team start`**
  - Added pane creation command generation for zellij environments
  - Added `--layout` mapping for zellij (`horizontal` -> right, `vertical` -> down, `split` -> balanced alternating splits)

### Changed

- Updated team-start terminal support messaging to include zellij

### Documentation

- Added/updated `synapse team start` references in `guides/usage.md` and `guides/references.md`

### Tests

- Added zellij coverage in `tests/test_auto_spawn.py` for pane generation, layout direction handling, and team-start execution path

## [0.4.0] - 2026-02-10

### Added

- **B1: Shared Task Board** - SQLite-based task coordination for multi-agent workflows
  - `synapse tasks list/create/assign/complete` CLI commands
  - `GET/POST /tasks/board`, `/tasks/board/{id}/claim`, `/tasks/board/{id}/complete` API endpoints
  - Atomic task claiming, dependency tracking (`blocked_by`), auto-unblocking on completion
- **B2: Quality Gates (Hooks)** - Configurable shell hooks for status transition control
  - `on_idle` and `on_task_completed` hook types
  - Exit code semantics: 0=allow, 2=deny, other=allow with warning
  - Environment variables: `SYNAPSE_AGENT_ID`, `SYNAPSE_AGENT_NAME`, `SYNAPSE_STATUS_FROM`, `SYNAPSE_STATUS_TO`
- **B3: Plan Approval Workflow** - Human-in-the-loop plan review
  - `synapse approve/reject` CLI commands
  - `POST /tasks/{id}/approve`, `POST /tasks/{id}/reject` API endpoints
  - `plan_mode` metadata flag for plan-only instructions
- **B4: Graceful Shutdown** - Cooperative agent shutdown
  - `synapse kill` now sends A2A shutdown request before SIGTERM (30s timeout)
  - `SHUTTING_DOWN` status (red) added to agent status system
  - `-f` flag for immediate SIGKILL (previous behavior)
- **B5: Delegate/Coordinator Mode** - Role-based agent separation
  - `--delegate-mode` flag for `synapse <agent>` commands
  - Coordinators cannot acquire file locks (file editing denied)
  - Auto-injected `[COORDINATOR MODE]` instructions for task delegation
- **B6: Auto-Spawn Split Panes** - Multi-agent terminal setup
  - `synapse team start <agents...> [--layout split|horizontal|vertical]`
  - `POST /team/start` A2A endpoint for agent-initiated team spawning
  - Supports tmux, iTerm2, Terminal.app (fallback: background spawn)
- **`synapse skills` command** - Unified skill management with interactive TUI and non-interactive subcommands
  - `synapse skills list [--scope]` - Discover skills across all scopes (Synapse, User, Project, Plugin)
  - `synapse skills show <name>` - Show skill metadata and paths
  - `synapse skills delete <name>` - Delete a skill (with confirmation, plugin skills protected)
  - `synapse skills move <name> --to <scope>` - Move skills between User/Project scopes
  - `synapse skills deploy <name> --agent claude,codex --scope user` - Deploy from central store to agent directories
  - `synapse skills import <name>` - Import skills to central store (`~/.synapse/skills/`)
  - `synapse skills add <repo>` - Install from repository via `npx skills` with auto-import to central store
  - `synapse skills create` - Create new skill template (uses skill-creator if available)
  - `synapse skills set list` / `synapse skills set show <name>` - Skill set management
- **SYNAPSE skill scope** - New central skill store at `~/.synapse/skills/` with flat structure
  - Skills are deployed from central store to agent-specific directories (`.claude/skills/`, `.agents/skills/`)
  - `SYNAPSE_SKILLS_DIR` environment variable for path override
- **`synapse/skills.py`** - Core skill management module with discovery, deploy, import, create, and skill set CRUD
- **`synapse/commands/skill_manager.py`** - TUI and CLI command implementations for skill management

### Changed

- **`synapse/cli.py`** - Integrated `synapse skills` subcommand tree (list, show, delete, move, deploy, import, add, create, set)
- **`synapse/paths.py`** - Added `get_synapse_skills_dir()` for central skill store path resolution

### Removed

- **`synapse set skills`** - Removed separate skill set command tree; all functionality consolidated under `synapse skills`
- **`synapse/commands/skill_sets.py`** - Migrated to `skills.py` and `skill_manager.py`

### Documentation

- Updated `CLAUDE.md` with Agent Teams commands, architecture, and test entries
- Updated `README.md` feature table, CLI commands, and API endpoints
- Updated README.md, CLAUDE.md, guides/usage.md, guides/references.md with skill management commands
- Updated plugin skills (SKILL.md, references/commands.md) and synced to `.agents/` and `.claude/`
- Updated code-doc-mapping.md with skills.py and skill_manager.py entries

### Tests

- Added 19 tests for core skills module (SYNAPSE scope, deploy, import, create, add, skill set CRUD)
- Added 6 tests for skill manager commands (deploy, import, create, set list/show, synapse scope listing)

## [0.3.25] - 2026-02-09

### Fixed

- **`synapse reply` documentation** - `--from` flag was incorrectly shown as required; it is only needed in sandboxed environments (like Codex). Basic usage is just `synapse reply "<message>"`
- **`synapse send` template examples** - Fixed `--from claude` (agent type) to use agent ID format (`synapse-<type>-<port>`) or omit `--from` entirely (auto-detected via PID matching)
- **Updated 30 files** across all documentation, skills, README translations (ja/ko/es/zh/fr), guides, and templates

## [0.3.24] - 2026-02-08

### Added

- **synapse-reinst skill** - Re-inject initial instructions after `/clear` or context reset
  - Script reads environment variables (`SYNAPSE_AGENT_ID`, `SYNAPSE_AGENT_TYPE`, `SYNAPSE_PORT`) to restore agent identity
  - Fallback path with conditional section processing when synapse module is not importable
  - Deployed to `.claude/` and `.agents/` skill directories

### Changed

- **Migrate Codex skill directory** from `.codex/skills/` to `.agents/skills/` (official Codex CLI skill path)
  - Rename `_copy_skill_to_codex()` → `_copy_skill_to_agents()` in `cli.py`
  - Rename `_copy_claude_skills_to_codex()` → `_copy_claude_skills_to_agents()` in `cli.py`
- **Remove `.opencode/skills/`** - OpenCode auto-scans `.agents/skills/`, eliminating redundant copies
- **Update skill examples** to use `synapse send`/`synapse reply` commands exclusively
  - Replace all deprecated `@agent` patterns removed in v0.3.9
  - Add `--response`/`--no-response` flags and `synapse reply` examples
- **Update SKILL.md description** - Replace "routing @agent patterns" with "via synapse send/reply commands"
- **Update file-safety.md** - Replace `@gemini` pattern with `synapse send` command

### Removed

- Delete `.codex/` directory (migrated to `.agents/`)
- Delete `.opencode/` directory (redundant with `.agents/`)

### Documentation

- Update README.md and README.ja.md: `.codex/skills/` → `.agents/skills/`
- Update `guides/settings.md`: Codex skill path documentation
- Update `synapse-docs` skill references: code-doc-mapping.md, doc-inventory.md
- Update `opencode-expert` skill: add `.agents/skills/` to discovery paths
- Update `commands.md`: reset command description `.codex` → `.agents`

### Tests

- Add `tests/test_reinst_skill.py` with 9 test cases covering env var detection, registry lookup, instruction output, PID fallback, and edge cases
- Update `tests/test_settings.py`, `tests/test_cli.py`, `tests/test_cli_commands_coverage.py`, `tests/test_cli_extended.py` for `.codex` → `.agents` migration

## [0.3.23] - 2026-02-07

### Added

- **Reply target selection** - `synapse reply --to <sender_id>` to reply to a specific sender when multiple are pending
- **Reply target listing** - `synapse reply --list-targets --from <agent>` to show all pending senders
- **Configurable storage paths** - Override registry, external registry, and history DB paths via environment variables (`SYNAPSE_REGISTRY_DIR`, `SYNAPSE_EXTERNAL_REGISTRY_DIR`, `SYNAPSE_HISTORY_DB_PATH`)

### Changed

- **Simplify `paths.py`** - Extract `_resolve_path` helper to eliminate duplication across path resolution functions
- **Simplify `cli.py`** - De-duplicate `registry.unregister` calls and remove redundant `else` after `return`
- **Simplify `tools/a2a.py`** - Remove redundant `isinstance` type guards and unused variables
- **Move inline imports to module level** in `settings.py` for consistency

### Documentation

- Add external agent management commands (add, list, info, send, remove) to plugin skills
- Add authentication commands (setup, generate-key) to plugin skills
- Add logs, reset, resume mode, and file-safety cleanup-locks/debug commands to plugin skills
- Fix broadcast default priority documentation (3 → 1) to match implementation
- Add `--response` mode task creation flow and external agent endpoints to API reference

## [0.3.22] - 2026-02-06

### Fixed

- **Extra newline in CLI output** - `synapse send` / `synapse broadcast` no longer print double newlines
- **Error propagation** - `synapse send` and `synapse broadcast` now exit with non-zero code on failure (consistent with `synapse reply`)

### Changed

- **Refactor CLI a2a commands** - Extract shared helpers (`_get_a2a_tool_path`, `_run_a2a_command`, `_build_a2a_cmd`) to reduce duplication

### Documentation

- Add complete flags (`--from`, `--response`, `--no-response`) to broadcast command reference
- Fix inconsistent `DIR` → `WORKING_DIR` naming in skill documentation

## [0.3.21] - 2026-02-06

### Added

- **`synapse broadcast` command** - Send messages to all agents in the same working directory
  - `synapse broadcast "message" --from <agent_id>` - Send to all agents in current directory
  - `--cwd <path>` option to target a specific working directory
  - Useful for coordinating multiple agents working on the same project

### Removed

- **Gemini-specific instruction files** - Remove `gemini.md` templates in favor of unified default instructions

## [0.3.20] - 2026-02-05

### Fixed

- **Race condition in `synapse list`** - Add retry logic for port checks during agent status transitions
  - First port check uses 0.5s timeout, retry uses 1.0s timeout with 0.2s delay
  - Prevents false "agent dead" detection during PROCESSING → READY transitions
  - Improves reliability when multiple agents are starting simultaneously

### Added

- **Status timestamp tracking** - Add `status_updated_at` field to registry entries for debugging status transitions
- **Settings validation warnings** - Log warnings for unknown top-level keys in settings.json files
  - Helps catch typos and deprecated settings
  - Known keys: `env`, `instructions`, `approvalMode`, `a2a`, `resume_flags`, `list`

### Tests

- Add `TestPortCheckRetry` test class for port check retry logic
- Extract shared test helpers to reduce code duplication in test_cmd_list_watch.py

## [0.3.19] - 2026-02-04

### Removed

- **Delegation feature** - Remove auto-routing based on delegate.md rules
  - `synapse/delegation.py` and related tests
  - `delegate.md` template files
  - Delegation skill directories across all agent configs
  - `guides/delegation.md` guide
  - Delegation settings from settings.py and config TUI

### Changed

- Recommend using `--name` and `--role` flags (v0.3.11) for assigning specialized roles to agents instead of model-type-based delegation

### Documentation

- Update README and guides to remove delegation references
- Clarify one-way notifications vs delegated tasks

## [0.3.18] - 2026-02-04

### Documentation

- Add column descriptions to `synapse list --help` including EDITING_FILE requirement (#179)
- Add "Integration with synapse list" section to `synapse file-safety --help`
- Expand `synapse file-safety locks` help to mention EDITING_FILE column
- Add "List Integration" feature to README File Safety table
- Sync File Safety documentation across plugin skills

### Changed

- Simplify CLI with constants and data-driven patterns
  - Extract HISTORY_DISABLED_MSG and FILE_SAFETY_DISABLED_MSG constants
  - Consolidate subcommand help into subcommand_parsers dict
  - Use `name or agent_id` instead of ternary expressions

## [0.3.17] - 2026-02-03

### Fixed

- Type error in `synapse list` file safety lock lookup (removed redundant variable reassignment)
- Improve file-safety lock lookup with cleaner conditional expressions

### Changed

- Simplify non-interactive table output using data-driven column definitions
- Add `create_mock_list_locks` helper to test file for reduced duplication
- Add type annotations to test fixtures for better code quality

### Documentation

- Sync FILE_SAFETY env vars across documentation
- Add list category to synapse config TUI documentation

## [0.3.16] - 2026-02-02

### Added

- Long message file storage for TUI input limits
  - Messages exceeding ~200 characters are automatically stored in temporary files
  - Agents receive a file reference message instead of truncated content
  - Files are automatically cleaned up after TTL expires (default: 1 hour)
  - Configurable via `SYNAPSE_LONG_MESSAGE_THRESHOLD`, `SYNAPSE_LONG_MESSAGE_TTL`, `SYNAPSE_LONG_MESSAGE_DIR`

### Documentation

- Add long message handling documentation to skills and guides
- Update settings.md with new environment variables (Japanese)
- Sync plugin skills with long message feature documentation

## [0.3.15] - 2026-02-01

### Added

- File Safety instructions in default agent instructions (#168)
  - Add mandatory checklist for file locking before edits
  - Include lock/unlock commands in agent initial instructions
  - Prevents agents from forgetting to use file locking

### Changed

- Simplify code in core modules for improved readability
  - Extract `_format_ambiguous_target_error` helper in tools/a2a.py
  - Consolidate backspace key handling in list.py
  - Use walrus operator for regex match in registry.py
  - Simplify file path lookup in settings.py

### Documentation

- Improve file-safety.md with mandatory checklist and quick reference
- Update README test badge (1331 → 1389 tests)
- Add Task History and CURRENT column to Features table

## [0.3.14] - 2026-02-01

### Added

- Reply PTY injection for natural agent-to-agent conversation
  - When agent A sends a message with `--response` and agent B replies,
    the reply is written to agent A's PTY as `A2A: <message>`
  - Uses standard A2A: prefix for protocol consistency

- CURRENT column in `synapse list` display
  - Shows first 30 characters of the current task being processed
  - Helps users understand what each agent is working on

- History enabled by default
  - Task history is now enabled without setting environment variables
  - To disable, set `SYNAPSE_HISTORY_ENABLED=false` explicitly

### Fixed

- Use standard `A2A: ` prefix for PTY reply messages (protocol compliance)
- Task preview truncation to max 30 chars total (27 + "...")
- Handle undefined variables in conditional template sections
- Remove trailing newline from PTY reply content (let submit_seq handle it)
- Fix agent type regex to allow hyphens (e.g., `synapse-gpt-4-8120`)
- Normalize endpoint in `synapse reply` to avoid relative URL issues
- Fix `.serena/project.yml` empty base_modes/default_modes keys

### Documentation

- Update all documentation for history default change
- Update commands.md Output columns (ID, ROLE, CURRENT columns added)
- Sync skill files across all agent directories

## [0.3.13] - 2026-02-01

### Note

Features originally planned for v0.3.13 were consolidated into v0.3.14.
See v0.3.14 for reply PTY injection, CURRENT column, and history default changes.

## [0.3.12] - 2026-02-01

### Changed

- Refactor internal code for improved maintainability
  - Extract `format_role_section()` utility to reduce duplication between controller.py and instructions.py
  - Simplify `_evaluate_idle_status()` with dictionary lookup in controller.py
  - Extract `_determine_new_status()` helper for cleaner status transition logic
  - Simplify flow determination in tools/a2a.py with dictionary lookup
  - Extract sender validation helpers in tools/a2a.py

### Fixed

- Fix ruff linter errors in cli.py and instructions.py
  - Replace `try-except-pass` with `contextlib.suppress()` for cleaner exception handling
  - Remove extraneous f-string prefix from string without placeholders

### Documentation

- Synchronize `.synapse/` templates with source templates
  - Add role section (`{{#agent_role}}`) to default.md and gemini.md
  - Update `--response` / `--no-response` guidance with safer default recommendation
- Update skill files with consistent documentation across all agent directories
  - Sync synapse-a2a and delegation skills to .claude/ and .agents/

## [0.3.11] - 2026-02-01

### Added

- Add Agent Naming feature for easy agent identification (#171)
  - `--name` and `--role` options for `synapse <profile>` command
  - `--no-setup` flag to skip interactive name/role prompts
  - `synapse rename <target> --name <name> --role <role>` command
  - `synapse rename <target> --clear` to remove name and role
  - Custom names have highest priority in target resolution
- Add `synapse kill <target>` command with confirmation dialog
  - Kill by custom name, agent ID, type-port, or agent type
  - `-f` flag for force kill without confirmation
- Add `synapse jump <target>` command for terminal navigation
  - Jump by custom name, agent ID, or agent type
  - Supports iTerm2, Terminal.app, Ghostty, VS Code, tmux, Zellij

### Changed

- Update target resolution priority order:
  1. Custom name (highest priority, exact match, case-sensitive)
  2. Full agent ID (`synapse-claude-8100`)
  3. Type-port shorthand (`claude-8100`)
  4. Agent type (only if single instance)
- Display shows name if set, internal processing uses agent ID
  - Prompts show name (e.g., `Kill my-claude (PID: 1234)?`)
  - `synapse list` NAME column shows custom name or agent type

### Documentation

- Update all skill files with Agent Naming documentation
- Add "Name vs ID" specification to README, CLAUDE.md, and guides
- Update target resolution examples in all documentation

## [0.3.10] - 2026-01-30

### Added

- Add `[REPLY EXPECTED]` marker to A2A message format
  - Messages sent with `--response` flag now include `A2A: [REPLY EXPECTED] <message>`
  - Receiving agents can identify when a reply is required vs optional
  - Messages without the marker indicate delegation/notification (no reply needed)
- Add `/reply-stack/get` endpoint for peek-before-send pattern
  - Get sender info without removing (use with `/reply-stack/pop` after successful reply)

### Changed

- Refactor reply stack from LIFO stack to map-based storage
  - Multiple senders can coexist without overwriting each other
  - Same sender's new message overwrites previous entry
  - Only store sender info when `response_expected=True`
- Unify parameter naming: `reply_expected` → `response_expected` in `format_a2a_message()`
  - Consistent with `response_expected` metadata field used throughout the codebase

### Documentation

- Update all skill files with `[REPLY EXPECTED]` message format documentation
- Update guides and README with new message format examples
- Update terminology from "reply stack" to "reply tracking" in user-facing docs

## [0.3.9] - 2026-01-30

### Added

- Add approval mode for initial instructions (#165)
  - New `approvalMode` setting: `"auto"` (skip prompt) or `"required"` (show preview before sending)
  - Show instruction preview with file list before agent startup
  - Support `[Y/n/s]` prompt for approve, cancel, or skip options
  - Add `--auto-approve` and `--require-approval` CLI flags
- Add startup TUI animation with animated Synapse logo
  - Left-to-right sweep animation effect
  - Display quick reference commands after logo
- Add `input_ready_pattern` profile setting for TUI ready detection
  - Detect when agent's input area is ready before sending instructions
  - Pattern-based detection (e.g., `❯` for Claude) or timeout-based fallback

### Removed

- Remove @Agent pattern feature
  - Delete `input_router.py` and all @Agent routing code
  - Use `synapse send` command exclusively for inter-agent communication
  - Simplify controller by removing input parsing and action execution

### Documentation

- Update all skill files with `approvalMode` settings
- Update README and guides to use `synapse send` instead of @Agent syntax

## [0.3.8] - 2026-01-28

### Fixed

- Fix instruction file path display to correctly show user directory (`~/.synapse/`) vs project directory (`.synapse/`)
  - `synapse instructions files` now shows accurate file locations
  - `synapse instructions send` references correct paths in messages
  - Project directory takes precedence when file exists in both locations

### Documentation

- Update `guides/references.md` and skill references with new output examples

### Tests

- Add `TestInstructionFilePaths` test class for path resolution logic

### Chores

- Add `types-pyperclip` dev dependency for mypy type checking

## [0.3.7] - 2026-01-27

### Changed

- Simplify A2A reply flow with Reply Stack automation
  - Remove `--reply-to` option from `synapse send` command
  - Add `--from` flag to `synapse reply` for sandboxed environments (Codex)
  - Simplify message format from `[A2A:<task_id>:<sender_id>]` to `A2A: <message>`
- Agents no longer need to track task_id or sender_id for replies

### Documentation

- Add "Agent Ignorance Principle" to project philosophy
  - Agents operate as if standalone; Synapse handles all routing
- Update all agent skills and templates with simplified format
- Remove internal implementation details from skill references

## [0.3.6] - 2026-01-25

### Added

- Interactive filter and kill functionality for `synapse list` (#158)
  - Press `/` to filter agents by TYPE or DIR
  - Press `k` to kill selected agent (with confirmation)
  - ESC clears filter, `q` quits

### Fixed

- `synapse list` display corruption and keyboard navigation issues (#156)
  - Fix rendering artifacts when list updates
  - Improve arrow key navigation reliability

### Documentation

- Add resident agent memory usage note (#157)

## [0.3.5] - 2026-01-24

### Added

- GitHub Copilot CLI agent support
  - New agent profile: `synapse/profiles/copilot.yaml`
  - Port range 8140-8149 for Copilot instances
  - Full A2A protocol integration with `synapse copilot` command
  - Timeout-based idle detection (500ms) for interactive TUI

### Documentation

- Sync plugin skills with Copilot support across all agent directories
- Update `synapse list` documentation (auto-refresh is now default TUI behavior)
- Fix DONE status color (magenta → blue) to match README
- Add Copilot to all skill references (commands, API, delegation)

## [0.3.4] - 2026-01-23

### Documentation

- Update skill installation method to use skills.sh (`npx skills add s-hiraoku/synapse-a2a`)
- Rename "Claude Code Plugin" section to "Skills" in README
- Add skills.sh reference links (https://skills.sh/)

## [0.3.3] - 2026-01-23

### Added

- Gemini CLI skills support via `.gemini/skills/` directory
  - `synapse-a2a` skill for inter-agent communication
  - `delegation` skill for task delegation configuration
- Skills section in `GEMINI.md` and `synapse/templates/.synapse/gemini.md`

### Documentation

- Update README.md to note Gemini skills directory support alongside Codex

## [0.3.2] - 2026-01-23

### Changed

- Replace `--watch` mode with event-driven auto-update for `synapse list`
  - Use watchdog file watcher for instant registry change detection
  - Add 2-second fallback polling for reliability
  - Remove `--watch`, `--interval`, `--no-rich` CLI options
  - Rich TUI with auto-refresh is now the default behavior

### Fixed

- Disable WAITING status detection to fix false positives on startup (#140)

### Documentation

- Update README and guides for event-driven `synapse list`
- Add keyboard shortcuts: 1-9 select, Enter/j jump, ESC clear, q quit

## [0.3.1] - 2026-01-22

### Changed

- Use hyphenated "open-source" consistently in all documentation
- Clarify tool exclusions in OpenCode agents documentation (todowrite/todoread)
- Add `pattern_use: "never"` to OpenCode profile for schema compliance
- Document Synapse metadata field naming convention (non-x- prefixed fields in metadata namespace)

### Documentation

- Add OpenCode to delegation skill Available Agents table (port 8130-8139)
- Update sender_type enumeration to include "opencode" in API docs
- Synchronize opencode-expert skill across .claude, .codex, and .opencode directories

## [0.3.0] - 2026-01-22

### Added

- OpenCode agent support (#135)
  - New agent profile: `synapse/profiles/opencode.yaml`
  - Port range 8130-8139 for OpenCode instances
  - Full A2A protocol integration with `synapse opencode` command
  - OpenCode expert skill for comprehensive OpenCode guidance
- OpenCode skills for multi-agent environments
  - `.opencode/skills/synapse-a2a/` - Synapse A2A integration skill
  - `.opencode/skills/delegation/` - Task delegation skill
  - `.opencode/skills/opencode-expert/` - OpenCode CLI/tools/agents reference

### Changed

- Consolidated instruction templates: removed redundant `opencode.md`, uses `default.md`
- Updated `settings.json` template with OpenCode resume flags (`--continue`, `-c`)

### Documentation

- Added OpenCode to all documentation (README, guides, CLAUDE.md)
- Synchronized plugin skills with OpenCode references
- Added OpenCode port range (8130-8139) to all port documentation

### Tests

- Added 21 tests for OpenCode support (`tests/test_opencode.py`)
- Updated port manager tests for OpenCode port range

## [0.2.30] - 2026-01-21

### Added

- Rich TUI for `synapse config` command with keyboard navigation (#133)
  - Arrow keys (↑/↓) for cursor movement
  - Enter to select, ESC/q to go back
  - Number keys (1-9) for quick jumps
  - Box-style headers with status bar showing controls
- `simple-term-menu` dependency for terminal menu selection

### Changed

- Replace questionary-based config UI with simple-term-menu
- Extract helper methods in RichConfigCommand for cleaner code structure

## [0.2.29] - 2026-01-20

### Fixed

- AppleScript validation now checks for expected token in output
  - `_jump_iterm2` and `_jump_terminal_app` verify "found" response
  - Scripts returning "not found" now correctly return False
- DONE status color changed from blue to magenta for consistency with documentation
- Zellij terminal jump updated (CLI doesn't support direct pane focus)
  - Falls back to activating terminal app with pane ID logged for reference
- Markdown lint MD058: added blank lines before Agent Status tables in skill docs

### Changed

- `_run_applescript` now accepts optional `expected_token` parameter for output validation

### Documentation

- Update VS Code terminal jump description (activates window, not working directory)
- Update Zellij description to note CLI limitation for direct pane focus
- Sync skill documentation across .claude, .codex, and plugins directories

## [0.2.28] - 2026-01-19

### Added

- Terminal jump feature in `synapse list --watch` mode
  - Press `Enter` or `j` to jump directly to selected agent's terminal
  - Supports iTerm2, Terminal.app, Ghostty, VS Code, tmux, and Zellij
- Expanded 4-state agent status system
  - READY (green): Idle, waiting for input
  - WAITING (cyan): Awaiting user input (selection, confirmation prompts)
  - PROCESSING (yellow): Busy handling a task
  - DONE (magenta): Task completed (auto-clears after 10s)
- WAITING status detection via regex patterns in profile YAML
  - Claude: Selection UI (❯), checkboxes (☐/☑), Y/n prompts
  - Gemini: Numbered choices (●/○), Allow execution prompts
  - Codex: Numbered list selection
- Zellij terminal multiplexer support for terminal jump

### Fixed

- Ghostty terminal jump simplified to activate-only (AppleScript limitation)
- Working directory display shows only directory name in list view (full path in detail panel)

### Changed

- WAITING detection refactored from pattern list to single regex for accuracy

### Documentation

- Add Agent Monitor section to README.md and README.ja.md
- Update plugin skills with 4-state status and terminal jump documentation

## [0.2.27] - 2026-01-18

### Added

- Rich TUI for `synapse list --watch` with interactive features
  - Color-coded status display (READY=green, PROCESSING=yellow)
  - Row selection via number keys (1-9) to view full paths in detail panel
  - ESC key to close detail panel, Ctrl+C to exit
  - `--no-rich` flag for plain text output mode
  - TRANSPORT column shows real-time communication status (UDS→/→UDS, TCP→/→TCP)

### Changed

- Extract `_is_agent_alive` helper method in list.py to reduce duplication
- Consolidate `pkg_version` retrieval in list.py
- Simplify stale locks handling in rich_renderer.py
- Extract `_handle_task_response` helper in input_router.py

### Documentation

- Sync plugin skills with Rich TUI documentation
- Add Rich TUI features to Quick Reference (--no-rich, interactive mode)
- Document synapse config show --scope options
- Add synapse instructions send --preview to Quick Reference
- Document TUI categories in commands.md

## [0.2.26] - 2026-01-18

### Fixed

- Display response artifacts in `synapse send --response` mode
  - Response content from `task.artifacts` was not displayed to the user
  - Now shows response content with proper indentation for multiline output

## [0.2.25] - 2026-01-18

### Added

- PTY display `:R` flag to indicate response is expected
  - New format: `[A2A:<task_id>:<sender_id>:R]` when `response_expected=true`
  - Agents can now visually identify when `--reply-to` is required
- Failsafe retry for `--reply-to` 404 errors
  - When `--reply-to` target task doesn't exist (404), automatically retry as new message
  - Prevents message loss when receiver mistakenly uses `--reply-to` for `--no-response` messages

### Documentation

- Sync plugin skills with `.claude/skills/` and `.codex/skills/` directories
- Add `/tasks/create` endpoint to API reference in skill documentation
- Update short task ID documentation for `--reply-to` option
- Update agent templates (default.md, gemini.md) with `:R` flag documentation

## [0.2.24] - 2026-01-18

### Fixed

- Poll sender's server for reply when using `--response` flag
  - Problem: `synapse send --response` never received replies because it polled the target server instead of the sender's server where `--reply-to` stores the response
  - Solution: When `--response` is used, poll the sender's server for `sender_task_id` completion instead of the target server

## [0.2.23] - 2026-01-18

### Added

- Support prefix match for `--reply-to` short task IDs
  - Add `TaskStore.get_by_prefix()` method for case-insensitive prefix matching
  - PTY displays 8-char short IDs (e.g., `[A2A:54241e7e:sender]`)
  - `--reply-to 54241e7e` now works with short IDs displayed in PTY
  - Return 400 error for ambiguous prefixes (multiple matches)

### Documentation

- Sync .codex/skills with plugins and fix metadata field naming

## [0.2.22] - 2026-01-18

### Fixed

- Register task on sender's server for `--reply-to` to work
  - Problem: `--reply-to` always failed with "Task not found" because `sender_task_id` was created in the CLI process's in-memory task_store, which disappeared when the process exited
  - Solution: When `--response` is used, call `POST /tasks/create` on the sender's running agent server (via UDS or HTTP) instead of creating the task locally
  - The agent server's task_store persists as long as the agent is running, enabling `--reply-to` to find the task

### Added

- New `POST /tasks/create` endpoint to create task without sending to PTY
- `sender_endpoint` and `sender_uds_path` fields in sender_info for server-side task registration

### Changed

- Extract `_extract_sender_info_from_agent()` helper function to reduce code duplication

### Documentation

- Update task ownership design document with new server-side registration approach
- Update A2A communication guide with metadata structure changes
- Add `/tasks/create` to API reference

## [0.2.21] - 2026-01-18

### Documentation

- Clarify `--response` vs `--no-response` flag usage guidance
  - Add decision table for choosing the correct flag based on message intent
  - Rule: If your message asks for a reply, use `--response`
- Clarify `--reply-to` usage when receiving messages
  - Use `--reply-to` only when replying to questions/requests
  - Delegated tasks don't need a reply
- Sync changes across all skill files and templates

## [0.2.20] - 2026-01-17

### Fixed

- Redesign task ownership for `--reply-to` to work across agents
  - Tasks are now created on the **sender** side when using `--response` flag
  - `sender_task_id` is included in request metadata and displayed in PTY output
  - Enables `--reply-to` to work for same-type agent communication (e.g., claude-to-claude)

### Changed

- Simplify codebase by removing duplications
  - Consolidate duplicate artifact formatting functions in `a2a_compat.py`
  - Remove redundant regex search in `error_detector.py`
  - Consolidate exception handlers in `controller.py`
  - Remove redundant settings lookup in `input_router.py`

### Documentation

- Add task ownership design document (`docs/TASK_OWNERSHIP_DESIGN.md`)
- Add fallback strategy for `--reply-to` when sender didn't use `--response`
- Add receiving and replying section to A2A communication guide

## [0.2.19] - 2026-01-17

### Fixed

- Add type-port shorthand support for `synapse send` command
  - When multiple agents of the same type are running, use `claude-8100` format to target specific instances
  - Target resolution priority: Full ID > Type-port > Agent type
  - Show helpful hints when ambiguous target is detected

### Documentation

- Clarify `/tasks/send-priority` naming convention in API docs
  - Document that endpoint path intentionally omits `x-` prefix for URL readability
  - Note that `x-` prefix is used for metadata fields (`x-sender`, `x-response-expected`)
- Sync target format documentation across all files
  - README.md, CLAUDE.md, guides/references.md, skill files, templates

## [0.2.18] - 2026-01-17

### Fixed

- Fix `synapse config` saving "Back to main menu" as a settings key
  - questionary `Choice(value=None)` uses title as value, not None
  - Use sentinel value `_BACK_SENTINEL` to properly detect back navigation
- Fix confirm dialog in `synapse config` not exiting on Ctrl+C
  - Handle `None` return from `questionary.confirm().ask()`

### Documentation

- Add `--reply-to` parameter documentation for roundtrip communication
  - Essential for completing `--response` requests
  - Receiver MUST use `--reply-to <task_id>` to link their response
  - Updated: README.md, CLAUDE.md, guides, skill files, templates
- Clarify `--response` / `--no-response` flag descriptions
  - `--response`: Roundtrip mode - sender waits, receiver MUST reply
  - `--no-response`: Oneway mode - fire and forget (default)
- Fix Priority 5 sequence documentation in api.md
  - Corrected to: `controller.interrupt()` followed immediately by `controller.write()` (no waiting)
- Add `delegate.md` schema documentation to delegation skill
  - YAML frontmatter structure, field reference, rule evaluation

## [0.2.17] - 2026-01-16

### Added

- `synapse config` command for interactive settings management (#72)
  - TUI-based settings editor using questionary library
  - Edit user (`~/.synapse/settings.json`) or project (`./.synapse/settings.json`) settings
  - Categories: Environment Variables, Instructions, A2A Protocol, Delegation, Resume Flags
  - `synapse config show` displays current merged settings (read-only)
  - `synapse config show --scope user|project|merged` for scope-specific view

### Dependencies

- Add `questionary>=2.0.0` for interactive TUI prompts

## [0.2.16] - 2026-01-15

### Added

- Critical Write Protocol (Read-After-Write verification) in `.synapse/file-safety.md`
  - Agents must verify their writes by reading the file back immediately
  - Retry mechanism for failed or incorrect writes
  - New enforcement rule: "EVERY WRITE NEEDS VERIFICATION. NO EXCEPTIONS."

### Fixed

- Fix "EDITING FILE" not displaying in `synapse list` for some agents
  - `synapse file-safety lock` now correctly passes `agent_id` and `agent_type` to database
  - Support short agent names (e.g., "claude") by looking up live agents via `get_live_agents()`
  - Extract `agent_type` from agent_id format (`synapse-{type}-{port}`) as fallback
  - Refactored agent lookup logic into `_resolve_agent_info()` helper function

## [0.2.15] - 2026-01-15

### Fixed

- Pass registry to `send_to_local()` in `a2a.py send` command for transport display
  - TRANSPORT column was not updating because registry was not passed
  - Now correctly shows `UDS→` / `→UDS` during communication

## [0.2.14] - 2026-01-15

### Added

- Transport display retention feature for `synapse list --watch` mode
  - Communication events now persist for 3 seconds after completion
  - Makes it possible to observe brief communication events in real-time
  - New `registry.get_transport_display()` method with configurable retention period
  - Stores `last_transport` and `transport_updated_at` for retention logic

## [0.2.13] - 2026-01-15

### Added

- Real-time transport display in `synapse list --watch` mode
  - Show `UDS→` / `TCP→` for sending agent
  - Show `→UDS` / `→TCP` for receiving agent
  - Clear to `-` when communication completes
  - TRANSPORT column only appears in watch mode
- New `registry.update_transport()` method for tracking active communication
- Specification document: `docs/transport-display-spec.md`

## [0.2.12] - 2026-01-14

### Changed

- Unify response option flags between `synapse send` and `a2a.py send` (#96)
  - Replace `--return` flag with `--response/--no-response` flags
  - Default behavior is now "do not wait for response" (safer)
  - Both commands now have consistent flag names and defaults
- Update shell.py and shell_hook.py to use `--response` flag instead of `--return`

### Documentation

- Update all guides, skills, and templates to use new `--response/--no-response` flags
- Update `docs/universal-agent-communication-spec.md` with new flag names

## [0.2.11] - 2026-01-14

### Added

- `--reply-to` option for `a2a.py send` command to attach response to existing task (#99)
  - Enables agents to complete tasks by sending responses back to original task
  - Used for same-type agent communication (e.g., Claude to Claude)

### Fixed

- Accurate "EDITING FILE" display in `synapse list` using PID-based file locks (#100)
  - Only show files locked by the agent's own process tree
  - Filter out stale locks from other processes
- Same-type agent communication deadlock issue (#99)
  - Add `in_reply_to` metadata support for task completion

### Changed

- Refactor codebase by extracting helpers and reducing duplication (#98)
  - Add `A2ATask.from_dict()` class method
  - Add `_db_connection()` context manager for cleaner DB handling
  - Extract helper functions across multiple modules
  - Total: -109 lines of code while preserving functionality

### Tests

- Improve test coverage for logging, server, cli, and proto modules (#101)
- Fix proto import test failure in CI environment

## [0.2.10] - 2026-01-13

### Fixed

- `synapse send` command now works from any directory (#92)
  - Use package-relative path instead of hardcoded relative path
  - Remove unnecessary `PYTHONPATH` manipulation

## [0.2.9] - 2026-01-13

### Added

- `synapse init` now copies all template files from `templates/.synapse/` to target directory
  - Includes: `settings.json`, `default.md`, `delegate.md`, `file-safety.md`, `gemini.md`
  - Prompts for overwrite confirmation when `.synapse/` directory already exists

### Changed

- `synapse init` now checks for `.synapse/` directory existence (not just `settings.json`)
- Overwrite prompt now asks about the entire `.synapse/` directory

## [0.2.8] - 2025-01-13

### Added

- `synapse send` command with `--from` option for inter-agent communication (#86)
- `synapse instructions` command for manual instruction management (#87)
  - `synapse instructions show [agent]` - Display instruction content
  - `synapse instructions files [agent]` - List instruction files
  - `synapse instructions send <agent>` - Send instructions to running agent

### Fixed

- UDS server startup and socket existence checks (#89)
- Always allow HTTP fallback when UDS connection fails
- Set UDS directory permissions to 755 for sandboxed apps
- Move UDS socket to `/tmp/synapse-a2a/` for sandbox compatibility
- Update test mocks for UDS server startup
- Address CodeRabbit review comments on PR #89

### Changed

- Standardize on `synapse send` command across all documentation
- Recommend `synapse send` for inter-agent communication
- Clarify `@agent` pattern vs external A2A tool usage

### Documentation

- Add UDS transport layer and separate standard/extension endpoints
- Use `x-` prefix for Synapse extension fields in A2A metadata
- Add explicit READY status verification instructions
- Add Codex sandbox network configuration guide
- Update delegation skill and api.md documentation
- Sync skill files across .claude and plugins

## [0.2.6] - 2025-01-12

### Added

- Unix Domain Socket (UDS) transport for local A2A communication (#81)
  - Lower latency and overhead for same-machine agent communication
  - Automatic fallback to HTTP when UDS unavailable

### Fixed

- PID-based lock management for stale lock detection (#80)
  - Detect and clean up stale locks from crashed processes
  - Improve file safety reliability in multi-agent scenarios
- Enable history and file safety in default settings.json
- Add httpx to requirements (#83)
- Resolve AsyncMock RuntimeWarning in test_a2a_compat_extended (#84)
- Fix deprecated `asyncio.get_event_loop_policy` usage in conftest (#84)
- Fix deprecated `datetime.utcnow` usage in test_utils (#84)

### Changed

- Install gRPC dependency group to enable previously skipped tests (#84)
- Achieve 100% test pass rate (985 tests)

### Documentation

- Update file-safety guide with PID-based lock management (#82)

## [0.2.5] - 2025-01-12

### Fixed

- Handle `PermissionError` correctly in `is_process_running` (#75)
  - `PermissionError` from `os.kill(pid, 0)` means the process exists but we don't have permission to signal it
  - Previously this was incorrectly treated as "process not found", causing agents to wrongly delete other agents' registry files

## [0.2.4] - 2025-01-12

### Changed

- Separate `@agent` pattern (user PTY input) and `a2a.py send` (AI agent command)
  - `@agent` pattern no longer accepts `--response`/`--no-response` flags
  - AI agents use `python3 synapse/tools/a2a.py send` with explicit flags
- Refactor `delegation.mode` into two independent settings:
  - `a2a.flow` - Controls response behavior (roundtrip/oneway/auto)
  - `delegation.enabled` - Enables/disables automatic task delegation
- Remove `synapse delegate` CLI subcommand (use settings.json instead)

### Added

- `--response` / `--no-response` flags for `a2a.py send` command
- `a2a.flow` setting with three modes:
  - `roundtrip`: Always wait for response (flags ignored)
  - `oneway`: Never wait for response (flags ignored)
  - `auto`: AI decides via flags (default)
- New guide: `guides/a2a-communication.md`

### Documentation

- Update SKILL.md with AI judgment guidance for response control
- Update agent templates (gemini.md, default.md) with send command examples
- Clarify separation between user and AI agent communication methods

## [0.2.3] - 2025-01-11

### Added

- `synapse --version` flag to display version information (#66)
- `synapse stop` now accepts agent ID for precise control (#67)
  - Example: `synapse stop synapse-claude-8100`

### Documentation

- Enhanced `synapse stop --help` with detailed examples and tips

## [0.2.2] - 2025-01-11

### Fixed

- Add `httpx` to runtime dependencies (was causing ModuleNotFoundError) (#64)
- Remove `$schema` key from plugin.json (was causing installation error) (#62)
- Move type stubs (`types-pyyaml`, `types-requests`) from runtime to dev dependencies

### Documentation

- Improve CLI `--help` with detailed descriptions and examples (#63)

## [0.2.1] - 2025-01-11

### Added

- Agent-memory skill for knowledge persistence (#52)
- Claude Code plugin marketplace support (#51)
- `.synapse` templates for `synapse init` (#55)
- Skip initial instructions when resuming context (#54)

### Fixed

- Apply settings env before checking history enabled (#59)
- Support `--flag=value` forms in `is_resume_mode()`
- Add correct resume flags for codex and gemini
- Add `-r` flag for gemini based on agent feedback

### Changed

- Reorganize skills into plugins directory structure
- Reorganize skills with references pattern

### Documentation

- Update README and guides for Resume Mode
- Add instructions for Codex skill expansion via `.codex` directory
- Add release guide (#50)
- Enhance synapse-a2a and delegation skills with comprehensive features

## [0.2.0] - 2025-01-05

### Added

- File locking and modification tracking for multi-agent safety (#46)
- Session history persistence with search, cleanup, stats, and export (#30, #34)
- Automatic task delegation between agents (#42)
- A2A response mechanism for inter-agent communication (#41)
- `.synapse` settings for customizable instructions and env (#37)
- Skill installation to `synapse init/reset` commands
- Pre-commit hooks for ruff and mypy
- `synapse list` command with watch mode (#28)
- synapse-a2a skill with Phase 2 history features
- gRPC support for high-performance A2A communication
- Webhook notifications for task completion
- API Key authentication for A2A endpoints
- SSE streaming for real-time task output
- HTTPS support with SSL certificates
- Output parser for structured CLI output artifacts
- Error detection and failed status for tasks

### Fixed

- Race conditions and silent failures in `synapse list --watch` (#31)
- Gemini initial instruction delivery race condition (#32)
- Interactive mode idle detection and Gemini PROCESSING status
- All mypy type checking errors
- Ruff formatting and linting violations

### Changed

- Reorganize delegation config to `delegation.md` format
- Use file references for initial instructions to avoid PTY buffer limits
- Update Claude Code profile to use hybrid pattern + timeout detection

### Documentation

- Add File Safety user guide
- Add session history feature documentation
- Add testing guidelines for registry status updates
- Define project mission - enable agent collaboration without changing behavior

## [0.1.0] - 2024-12-28

### Added

- Initial release of Synapse A2A
- PTY wrapper for CLI agents (Claude Code, Codex, Gemini)
- Google A2A Protocol implementation
- Agent Card with context extension (`x-synapse-context`)
- `@agent` pattern routing for inter-agent communication
- File-based agent registry (`~/.a2a/registry/`)
- External A2A agent connectivity
- Profile-based configuration (YAML configs per agent type)
- Port range management per agent type
- Idle detection strategies (pattern, timeout, hybrid)

### Documentation

- A2A design documents and project guidelines
- External agent connectivity vision document
- PyPI publishing instructions

[Unreleased]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.31.0...HEAD
[0.31.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.29.0...v0.31.0
[0.29.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.28.3...v0.29.0
[0.28.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.28.2...v0.28.3
[0.28.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.28.1...v0.28.2
[0.28.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.28.0...v0.28.1
[0.28.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.27.2...v0.28.0
[0.27.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.27.1...v0.27.2
[0.27.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.27.0...v0.27.1
[0.27.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.26.5...v0.27.0
[0.26.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.26.4...v0.26.5
[0.26.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.26.3...v0.26.4
[0.26.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.26.2...v0.26.3
[0.26.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.26.1...v0.26.2
[0.26.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.26.0...v0.26.1
[0.26.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.25.2...v0.26.0
[0.25.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.25.1...v0.25.2
[0.25.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.25.0...v0.25.1
[0.25.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.24.2...v0.25.0
[0.24.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.24.1...v0.24.2
[0.24.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.24.0...v0.24.1
[0.24.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.23.5...v0.24.0
[0.23.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.23.4...v0.23.5
[0.23.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.23.3...v0.23.4
[0.23.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.23.2...v0.23.3
[0.23.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.23.1...v0.23.2
[0.23.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.22.0...v0.23.0
[0.22.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.5...v0.20.0
[0.19.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.4...v0.19.5
[0.19.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.3...v0.19.4
[0.19.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.2...v0.19.3
[0.19.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.1...v0.19.2
[0.19.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.0...v0.19.1
[0.19.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.4...v0.19.0
[0.18.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.3...v0.18.4
[0.18.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.2...v0.18.3
[0.18.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.1...v0.18.2
[0.18.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.0...v0.18.1
[0.18.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.16...v0.18.0
[0.17.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.15...v0.17.16
[0.17.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.14...v0.17.15
[0.17.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.13...v0.17.14
[0.17.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.12...v0.17.13
[0.17.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.11...v0.17.12
[0.17.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.10...v0.17.11
[0.17.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.9...v0.17.10
[0.17.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.8...v0.17.9
[0.17.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.7...v0.17.8
[0.17.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.6...v0.17.7
[0.17.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.5...v0.17.6
[0.17.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.4...v0.17.5
[0.17.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.3...v0.17.4
[0.17.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.2...v0.17.3
[0.17.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.1...v0.17.2
[0.17.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.0...v0.17.1
[0.17.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.16.2...v0.17.0
[0.16.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.16.1...v0.16.2
[0.16.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.16.0...v0.16.1
[0.16.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.11...v0.16.0
[0.15.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.10...v0.15.11
[0.15.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.9...v0.15.10
[0.15.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.8...v0.15.9
[0.15.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.7...v0.15.8
[0.15.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.6...v0.15.7
[0.15.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.5...v0.15.6
[0.15.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.4...v0.15.5
[0.15.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.3...v0.15.4
[0.15.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.2...v0.15.3
[0.15.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.1...v0.15.2
[0.15.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.0...v0.15.1
[0.15.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.12.2...v0.13.0
[0.12.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.12.1...v0.12.2
[0.12.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.21...v0.12.0
[0.11.21]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.20...v0.11.21
[0.11.20]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.19...v0.11.20
[0.11.19]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.18...v0.11.19
[0.11.18]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.17...v0.11.18
[0.11.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.16...v0.11.17
[0.11.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.15...v0.11.16
[0.11.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.14...v0.11.15
[0.11.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.13...v0.11.14
[0.11.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.12...v0.11.13
[0.11.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.11...v0.11.12
[0.11.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.10...v0.11.11
[0.11.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.9...v0.11.10
[0.11.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.8...v0.11.9
[0.11.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.7...v0.11.8
[0.11.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.6...v0.11.7
[0.11.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.5...v0.11.6
[0.11.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.4...v0.11.5
[0.11.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.3...v0.11.4
[0.11.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.2...v0.11.3
[0.11.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.1...v0.11.2
[0.11.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.5...v0.10.0
[0.9.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.6...v0.9.0
[0.8.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.12...v0.7.0
[0.6.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.11...v0.6.12
[0.6.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.10...v0.6.11
[0.6.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.9...v0.6.10
[0.6.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.8...v0.6.9
[0.6.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.7...v0.6.8
[0.6.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.6...v0.6.7
[0.6.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.5...v0.6.6
[0.6.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.4...v0.6.5
[0.6.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.3...v0.6.4
[0.6.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.4...v0.5.0
[0.4.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.25...v0.4.0
[0.3.25]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.24...v0.3.25
[0.3.24]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.23...v0.3.24
[0.3.23]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.22...v0.3.23
[0.3.22]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.21...v0.3.22
[0.3.21]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.20...v0.3.21
[0.3.20]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.19...v0.3.20
[0.3.19]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.18...v0.3.19
[0.3.18]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.17...v0.3.18
[0.3.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.16...v0.3.17
[0.3.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.15...v0.3.16
[0.3.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.14...v0.3.15
[0.3.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.13...v0.3.14
[0.3.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.12...v0.3.13
[0.3.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.11...v0.3.12
[0.3.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.10...v0.3.11
[0.3.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.9...v0.3.10
[0.3.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.8...v0.3.9
[0.3.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.30...v0.3.0
[0.2.30]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.29...v0.2.30
[0.2.29]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.28...v0.2.29
[0.2.28]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.27...v0.2.28
[0.2.27]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.26...v0.2.27
[0.2.26]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.25...v0.2.26
[0.2.25]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.24...v0.2.25
[0.2.24]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.23...v0.2.24
[0.2.23]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.22...v0.2.23
[0.2.22]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.21...v0.2.22
[0.2.21]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.20...v0.2.21
[0.2.20]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.19...v0.2.20
[0.2.19]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.18...v0.2.19
[0.2.18]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.17...v0.2.18
[0.2.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.16...v0.2.17
[0.2.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.15...v0.2.16
[0.2.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.14...v0.2.15
[0.2.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.13...v0.2.14
[0.2.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.12...v0.2.13
[0.2.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.11...v0.2.12
[0.2.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.10...v0.2.11
[0.2.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.7...v0.2.8
[0.2.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.3...v0.2.4
[0.23.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.23.0...v0.23.1
[0.2.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/s-hiraoku/synapse-a2a/releases/tag/v0.1.0
