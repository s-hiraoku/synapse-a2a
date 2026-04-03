# Cross-Agent Scenarios

Real-world workflows where multiple agents collaborate — each leveraging its own LLM's strengths.

!!! tip "Prerequisites"
    Make sure you have at least two agents running. See [Quick Start](../getting-started/quickstart.md) to get started.

---

## Scenario 1: Cross-Review

**Claude implements, Gemini reviews** — different LLMs catch different classes of bugs.

### Why different agents?

Each LLM has distinct blind spots. Claude may optimize for readability while Gemini flags edge-case logic errors. Cross-review surfaces issues that a single model would miss.

### Steps

```mermaid
sequenceDiagram
    participant User
    participant Claude as Claude (Cody)
    participant Gemini as Gemini (Gem)

    User->>Claude: "Add input validation to /api/upload"
    Claude->>Claude: Implements validation logic
    Claude->>Gemini: synapse send Gem "Review this" --attach upload.py --wait
    Gemini->>Gemini: Analyzes code from a different LLM perspective
    Gemini-->>Claude: Returns review findings
    Claude->>Claude: Addresses feedback
    Claude->>Gemini: synapse send Gem "Review the fix" --attach upload.py --wait
    Gemini-->>Claude: "LGTM — all issues resolved"
```

### Commands

**1. Start both agents:**

```bash
# Terminal 1
synapse claude --name Cody --role "feature implementation"

# Terminal 2
synapse gemini --name Gem --role "code reviewer"
```

**2. After Claude finishes implementation, request review:**

```bash
synapse send Gem "Review this file for security issues, edge cases, and error handling" \
  --attach src/api/upload.py --wait
```

**3. Gemini responds with findings. Claude fixes and re-requests:**

```bash
synapse send Gem "I've addressed your feedback. Please re-review" \
  --attach src/api/upload.py --wait
```

### Expected Result

```
Task synapse-gemini-8110-a1b2 → completed

Response:
## Review Findings

1. **Missing size limit** — `upload_file()` accepts any size. Add `MAX_UPLOAD_SIZE` check.
2. **Path traversal** — filename is used directly in `os.path.join()`. Use `secure_filename()`.
3. **No content-type validation** — MIME type is trusted from client. Verify with `python-magic`.

Severity: 2 high, 1 medium
```

!!! info "When to use `--wait` vs `--notify`"
    Use `--wait` for reviews where you need the result before continuing. Use `--notify` (default) if you want to keep working while the review happens in the background.

---

## Scenario 2: Delegation Chain

**Manager delegates implementation and testing to specialized agents** — each focused on what they do best.

### Why different agents?

A manager agent (Claude in delegate-mode) coordinates without editing files directly. Codex excels at focused implementation. Gemini provides independent test coverage.

### Steps

```mermaid
sequenceDiagram
    participant Manager as Claude (Claud)
    participant Codex as Codex (Cody)
    participant Gemini as Gemini (Gem)
    participant SM as Shared Memory

    Manager->>Codex: synapse send Cody "Implement OAuth2" --silent
    Codex->>Codex: Implements feature
    Codex->>SM: synapse memory save oauth-pattern "Use PKCE flow" --notify
    Codex-->>Manager: Done
    Manager->>Gemini: synapse send Gem "Write tests" --silent
    Gemini->>SM: synapse memory show oauth-pattern
    Gemini->>Gemini: Writes tests using shared knowledge
    Gemini-->>Manager: Done
    Manager->>Manager: Verifies all tasks done
```

### Commands

**1. Start the team with names and roles:**

```bash
synapse team start \
  claude:Claud:synapse-manager:task-coordinator \
  codex:Cody::implementation \
  gemini:Gem::test-writer \
  --layout split
```

**2. Delegate to specialists:**

```bash
synapse send Cody "Implement OAuth2 with PKCE flow for /api/auth" --silent
synapse send Gem "Write tests for the OAuth2 feature once implementation is done." --silent
```

**4. Codex shares learned patterns via Shared Memory:**

```bash
synapse memory save oauth-pkce \
  "Use PKCE with S256 challenge. Token endpoint: /oauth/token" \
  --tags auth,oauth --notify
```

**5. Monitor progress:**

```bash
synapse list                    # Agent status
synapse memory search "oauth"   # Shared knowledge
```

---

## Scenario 3: Bug Hunt

**Production bug reported** — Claude diagnoses, Codex fixes, Gemini writes regression tests.

### Why different agents?

Time-critical bugs benefit from parallel investigation. Claude's reasoning strength identifies root causes. Codex applies targeted fixes. Gemini ensures the fix doesn't break anything else. `synapse interrupt` and priority levels coordinate urgent work.

### Steps

```mermaid
sequenceDiagram
    participant User
    participant Claude as Claude (Claud)
    participant Codex as Codex (Cody)
    participant Gemini as Gemini (Gem)

    User->>Claude: "Users report 500 on /api/orders"
    Claude->>Claude: Investigates logs + code
    Claude->>Claude: Root cause: race condition in order locking
    Claude->>Codex: synapse send Cody "Fix race condition" --silent
    Claude->>Gemini: synapse interrupt Gem "Regression test needed"
    Codex->>Codex: Applies fix
    Codex-->>Claude: synapse reply "Fixed — added SELECT FOR UPDATE"
    Gemini->>Gemini: Writes regression test
    Gemini-->>Claude: synapse reply "Tests pass — 3 cases added"
    User->>User: synapse trace <task_id>
```

### Commands

**1. Agents are already running. Check status:**

```bash
synapse list
```

**2. Interrupt Gemini's current work (urgent):**

```bash
synapse interrupt Gem "Drop current work. Production bug: 500 errors on /api/orders. \
  Write regression tests for order creation and concurrent access."
```

**3. Claude identifies the root cause and delegates the fix:**

```bash
synapse send Cody "Fix race condition in src/orders/service.py:create_order(). \
  The issue: concurrent requests create duplicate orders because there's no row-level lock. \
  Solution: add SELECT FOR UPDATE in the transaction." --silent
```

**4. Attach relevant files for context:**

```bash
synapse send Cody "Here's the current implementation and the error log" \
  --attach src/orders/service.py \
  --attach /tmp/error-log-snippet.txt \
  --silent
```

**5. Track everything with trace:**

```bash
synapse trace <task_id>
```

### Expected Result

```bash
$ synapse trace abc123
┌─ Task abc123 ─────────────────────────────────────────┐
│ Subject: Fix race condition in order creation          │
│ Status:  completed                                     │
├────────────────────────────────────────────────────────┤
│ Timeline:                                              │
│  14:01  Claude → Codex: "Fix race condition..."        │
│  14:01  Claude → Gemini: interrupt "Drop current..."   │
│  14:03  Codex: modified src/orders/service.py          │
│  14:04  Codex → Claude: reply "Fixed"                  │
│  14:06  Gemini: created tests/test_order_race.py       │
│  14:07  Gemini → Claude: reply "Tests pass — 3 cases"  │
├────────────────────────────────────────────────────────┤
│ Files Modified:                                        │
│  src/orders/service.py (Codex)                         │
│  tests/test_order_race.py (Gemini)                     │
└────────────────────────────────────────────────────────┘
```

---

## Scenario 4: Parallel Refactoring

**Large-scale refactoring split across agents** — each handles a different module using worktree isolation.

### Why different agents?

A single agent refactoring a large codebase is slow and error-prone. Splitting by module lets agents work in parallel on isolated git worktrees, preventing merge conflicts. Each agent brings its strengths — Codex for mechanical refactoring, Claude for architectural decisions, Gemini for API surface changes.

### Steps

```mermaid
sequenceDiagram
    participant Manager as Claude (Claud)
    participant C1 as Codex (Cody)
    participant C2 as Codex 2 (Rex)
    participant Gemini as Gemini (Gem)

    Manager->>Manager: Plans refactoring scope
    Manager->>C1: "Refactor backend services" (worktree)
    Manager->>C2: "Refactor data models" (worktree)
    Manager->>Gemini: "Refactor API layer" (worktree)
    C1->>C1: Works in isolated worktree
    C2->>C2: Works in isolated worktree
    Gemini->>Gemini: Works in isolated worktree
    C1-->>Manager: "Backend done"
    C2-->>Manager: "Models done"
    Gemini-->>Manager: "API done"
    Manager->>Manager: Merges all worktrees
```

### Commands

**1. Spawn agents with worktree isolation:**

```bash
synapse spawn codex -w Cody --name Cody --role "backend refactoring"
synapse spawn codex -w Rex --name Rex --role "data model refactoring"
synapse spawn gemini -w Gem --name Gem --role "API layer refactoring"
```

**2. Delegate each module:**

```bash
synapse send Cody "Refactor all service classes in src/services/ to use dependency injection. \
  Replace direct imports with constructor injection." --silent

synapse send Rex "Rename all SQLAlchemy models from CamelCase to snake_case table names. \
  Update foreign key references." --silent

synapse send Gem "Migrate all Flask routes in src/api/ to use APIRouter pattern. \
  Group by domain (users, orders, products)." --silent
```

**3. Monitor progress across all agents:**

```bash
synapse list
synapse broadcast "Status update — how far along are you?" --wait
```

**4. After all agents finish, merge worktree branches:**

```bash
git merge worktree-Cody
git merge worktree-Rex
git merge worktree-Gem
```

### Expected Result

Three agents work simultaneously in isolated worktrees under `.synapse/worktrees/`. No file conflicts during development. Manager merges the branches once all agents report completion.

---

## Scenario 5: Documentation Sweep

**Code changed, docs must follow** — Codex updates code, Gemini updates docs, Claude verifies consistency.

### Why different agents?

Documentation drift is one of the most common tech debt sources. By assigning a dedicated agent to docs, you guarantee that every code change has a corresponding doc update. Claude as verifier catches inconsistencies that neither the implementer nor the doc writer would notice alone.

### Steps

```mermaid
sequenceDiagram
    participant Codex as Codex (Cody)
    participant Gemini as Gemini (Gem)
    participant Rex as Codex 2 (Rex)
    participant SM as Shared Memory

    Codex->>Codex: Adds new /api/webhooks endpoint
    Codex->>SM: synapse memory save webhook-api "POST /api/webhooks - payload schema" --notify
    Codex->>Gemini: synapse send Gem "Update API docs for new webhook endpoint" --silent
    Gemini->>SM: synapse memory show webhook-api
    Gemini->>Gemini: Updates docs/api.md and README
    Gemini->>Rex: synapse send Rex "Verify docs match implementation" --wait
    Rex->>Rex: Cross-checks code vs docs
    Rex-->>Gemini: "Docs missing error response codes — add 400/422 examples"
    Gemini->>Gemini: Fixes docs
    Gemini-->>Rex: "Updated — all response codes documented"
```

### Commands

**1. Start the team:**

```bash
synapse team start codex:Cody::implementation gemini:Gem::documentation codex:Rex::doc-verification --layout split
```

**2. After Codex implements the feature, share context:**

```bash
synapse memory save webhook-api \
  "New endpoint POST /api/webhooks. Accepts JSON payload with 'url', 'events[]', 'secret'. \
  Returns 201 with webhook ID. Errors: 400 invalid URL, 422 unknown event type." \
  --tags api,webhook --notify
```

**3. Delegate doc writing:**

```bash
synapse send Gem "New webhook endpoint added. Check shared memory for 'webhook-api'. \
  Update docs/api.md with endpoint reference and README.md with a usage example." --silent
```

**4. Request verification:**

```bash
synapse send Rex "Cross-check docs/api.md and src/api/webhooks.py. \
  Verify all endpoints, parameters, and error codes are documented." \
  --attach docs/api.md --attach src/api/webhooks.py --wait
```

### Expected Result

Documentation stays synchronized with code changes. The verifier catches mismatches before they reach production docs.

---

## Scenario 6: Security Audit Pipeline

**Multi-agent security review** — each agent audits a different attack surface.

### Why different agents?

Security audits benefit from diverse perspectives. One agent focuses on authentication, another on injection vulnerabilities, a third on dependency risks. Running them in parallel gives broad coverage quickly.

### Steps

```mermaid
sequenceDiagram
    participant Lead as Claude (Claud)
    participant A1 as Gemini (Gem)
    participant A2 as Codex (Cody)
    participant A3 as Codex 2 (Rex)

    Lead->>A1: "Audit authentication & authorization"
    Lead->>A2: "Audit for injection vulnerabilities"
    Lead->>A3: "Audit dependencies for known CVEs"
    A1->>A1: Reviews auth flows
    A2->>A2: Scans for SQL/XSS/command injection
    A3->>A3: Checks dependency versions
    A1-->>Lead: Auth findings
    A2-->>Lead: Injection findings
    A3-->>Lead: Dependency findings
    Lead->>Lead: Consolidates security report
```

### Commands

**1. Assign agents to audit tasks:**

```bash
synapse send Gem "Audit all authentication and authorization code. \
  Check: session fixation, CSRF protection, password hashing, token expiry. \
  Report findings as HIGH/MEDIUM/LOW." --wait

synapse send Cody "Scan the codebase for injection vulnerabilities. \
  Check: raw SQL queries, unsanitized user input in templates, shell commands with user input. \
  Report findings as HIGH/MEDIUM/LOW." --wait

synapse spawn codex --name Rex --role "dependency security"
synapse send Rex "Review requirements.txt and uv.lock for known CVEs. \
  Flag any dependencies older than 6 months. Report findings." --wait
```

**3. Consolidate results:**

```bash
synapse memory save security-audit-2026-03 \
  "Auth: 2 HIGH, 1 MEDIUM. Injection: 1 HIGH. Deps: 3 MEDIUM (outdated packages)" \
  --tags security,audit --notify
```

### Expected Result

Three parallel audit streams complete faster than a single sequential review. Findings are saved to Shared Memory for the team to reference during remediation.

---

## Scenario 7: Competitive Analysis (LLM vs LLM)

**Same prompt, different models** — compare approaches from Claude, Gemini, and Codex side-by-side.

### Why different agents?

When you're unsure about the best approach for a complex problem, send the same prompt to multiple agents and compare their solutions. Different LLMs often take fundamentally different approaches — one may favor simplicity, another performance, another extensibility.

### Steps

```mermaid
sequenceDiagram
    participant User
    participant Claude as Claude
    participant Gemini as Gemini
    participant Codex as Codex

    User->>Claude: "Design a rate limiter"
    User->>Gemini: "Design a rate limiter"
    User->>Codex: "Design a rate limiter"
    Claude->>Claude: Token bucket approach
    Gemini->>Gemini: Sliding window approach
    Codex->>Codex: Fixed window approach
    Claude-->>User: Solution A
    Gemini-->>User: Solution B
    Codex-->>User: Solution C
    User->>User: Picks the best approach
```

### Commands

**1. Start all three agents:**

```bash
synapse team start claude gemini codex --all-new
```

**2. Broadcast the same design challenge:**

```bash
synapse broadcast "Design a rate limiter for our API. Requirements: \
  - 100 requests per minute per API key \
  - Must handle burst traffic gracefully \
  - Should work in a distributed environment (multiple servers) \
  Write the implementation in src/middleware/rate_limiter.py" --wait
```

**3. Compare results:**

```bash
# Check what each agent produced
synapse history list --agent claude --limit 1
synapse history list --agent gemini --limit 1
synapse history list --agent codex --limit 1

# Review the files each agent would create
git diff
```

!!! warning "File conflicts"
    When agents write to the same file, use worktree isolation (`--worktree`) to prevent conflicts. Without worktrees, the last agent to write wins.

### Expected Result

Three different implementations of the same feature, each reflecting the strengths of its underlying LLM. You pick the best approach or combine ideas from multiple solutions.

---

## Scenario 8: Continuous Integration Agent

**A dedicated agent monitors CI and auto-fixes failures** — the team never waits for a green build.

### Why different agents?

CI failures block the entire team. A dedicated CI agent can monitor GitHub Actions, diagnose failures, and either fix them directly or delegate to the right specialist. This keeps human developers (and other agents) focused on feature work instead of debugging flaky tests or lint errors.

### Steps

```mermaid
sequenceDiagram
    participant Dev as Claude (Claud)
    participant CI as Gemini (Gem)
    participant Fixer as Codex (Cody)

    Dev->>Dev: Pushes code
    CI->>CI: Detects CI failure via hook
    CI->>CI: Categorizes: lint / test / type-check
    alt Lint or format issue
        CI->>CI: Auto-fixes with /fix-ci
        CI->>Dev: synapse send Claud "Fixed lint errors, pushed"
    else Test failure
        CI->>Fixer: synapse send Cody "Fix failing test" --attach test_output.txt --silent
        Fixer->>Fixer: Diagnoses and fixes
        Fixer-->>CI: synapse reply "Fixed — test_auth was using stale fixture"
        CI->>Dev: synapse send Claud "Test failure fixed by Codex"
    end
```

### Commands

**1. Start the CI monitor agent:**

```bash
synapse gemini --name Gem --role "CI monitoring and triage"
```

**2. When CI fails, the monitor triages:**

```bash
# Gem detects failure and categorizes it
synapse send Gem "CI failed on branch feature/auth. \
  Check GitHub Actions logs and determine the failure category." --wait
```

**3. For simple fixes (lint/format), auto-fix:**

```bash
# Gem runs the fix-ci skill
synapse send Gem "Run /fix-ci to auto-fix the lint failure" --silent
```

**4. For complex failures, delegate:**

```bash
synapse send Cody "Fix the failing test in tests/test_auth.py. \
  Error: 'fixture user_session not found'. The fixture was renamed in the last commit." \
  --attach tests/test_auth.py --silent
```

**5. Notify the developer:**

```bash
synapse send Claud "CI is green again. Codex fixed a stale fixture reference in test_auth.py." --silent
```

### Expected Result

CI failures are detected, categorized, and fixed automatically. The developer gets a notification only when the fix is complete — no context-switching to debug CI issues.

---

## Scenario 9: Cross-Worktree Knowledge Transfer

**An agent in the main repo teaches a skill to an agent working in a different worktree** — knowledge flows across directory boundaries.

### Why different agents?

Agents spawned with `--worktree` operate in isolated directories under `.synapse/worktrees/`. They have their own branch and working copy, which means they're in a **different working directory** than the sender. Synapse automatically recognizes that worktree directories belong to the same repository, so **sends work without `--force`**. Use `--message-file` for complex content containing backticks or special characters.

This pattern is common when a manager agent discovers something useful — a workflow, a skill, a debugging technique — and needs to share it with workers in other worktrees.

### Steps

```mermaid
sequenceDiagram
    participant Manager as Claude (Claud) — main repo
    participant Worker as Codex (Cody) — worktree

    Manager->>Manager: Learns a new workflow (e.g., /release skill)
    Manager->>Manager: Writes instructions to a temp file
    Manager->>Worker: synapse send Cody --message-file /tmp/instructions.md --silent
    Worker->>Worker: Reads instructions and applies the knowledge
    Worker-->>Manager: synapse reply "Got it — I'll use /release for version bumps"
```

### Commands

**1. Spawn a worker in its own worktree:**

```bash
synapse spawn codex --worktree feature-api --name Cody --role "API implementation"
```

**2. Confirm the agent is ready and note its directory:**

```bash
synapse list
# TYPE    NAME    PORT  STATUS  WORKING_DIR
# codex   Cody    8120  READY   [WT] feature-api
# claude  Claud   8100  READY   synapse-a2a
```

**3. Prepare the message (avoids shell expansion issues with backticks/quotes):**

```bash
cat > /tmp/release-instructions.md << 'EOF'
## /release skill usage

Run `/release patch` to bump the patch version. This updates:
1. pyproject.toml
2. plugin.json
3. CHANGELOG.md (with reference link at bottom)
4. site-docs version references
5. mkdocs.yml repo_name

Important: always add the reference link definition at the end of CHANGELOG.md.
EOF
```

**4. Send across worktree boundaries:**

```bash
# Worktree agents are recognized automatically — no --force needed:
synapse send Cody --message-file /tmp/release-instructions.md --silent

# Inline message also works:
synapse send Cody "Use /release patch to bump the version" --silent
```

!!! info "Why `--message-file`?"
    Messages containing backticks, quotes, or code blocks can be mangled by shell expansion. `--message-file` reads the content as-is, bypassing the shell entirely. You can also pipe via `--stdin`: `echo "message" | synapse send Cody --stdin`.

### Expected Result

```
Success: Task created for codex (synapse-codex-8120)
  Task ID: e86929e4-...
  Status: working
```

The worker receives the instructions in its PTY and can apply the knowledge immediately — even though it's operating in a completely different directory.

### When to use this pattern

| Situation | Example |
|-----------|---------|
| Teaching a skill or workflow | Share `/release` usage with a new agent |
| Sending configuration or context | Pass environment details to a worktree agent |
| Sharing investigation results | Forward a root cause analysis to the fixer |
| Distributing templates | Send a code template for the agent to follow |

!!! tip "Alternatives to inline messages"
    Use `--attach` to send files directly without needing `--message-file`. For structured knowledge, `synapse memory save` is directory-agnostic and works across all agents regardless of directory.

---

## Proactive Collaboration Framework

Effective multi-agent work requires more than just sending messages. At the start of every task, each agent should evaluate whether to collaborate or work solo.

### Collaboration Decision Framework

| Situation | Action | Command Pattern |
|-----------|--------|-----------------|
| Small task within your expertise | Do it yourself | -- |
| Task outside your role | Delegate to a matching agent | `synapse send <target> "..." --silent` |
| Can run in parallel with your work | Delegate and continue | `synapse send <target> "..." --notify` |
| You are stuck or unsure | Ask for help | `synapse send <target> "..." --wait` |
| Completed a milestone | Report progress | `synapse send <requester> "Done: ..." --silent` |
| Discovered a pattern or pitfall | Share knowledge | `synapse memory save <key> "..." --tags ...` |

### Mandatory Collaboration Gate

For tasks with **3+ phases** or **10+ file changes**, agents MUST follow this gate before writing any code:

1. Run `synapse list` to check available agents
2. Run `synapse memory search "<topic>"` to check shared knowledge
3. Build an **Agent Assignment Plan** (see below) before writing any code
4. If no suitable agent exists, spawn a specialist with `synapse spawn`
5. Prefer a different model type for subtasks (diversity improves quality)

!!! warning "Do NOT skip this step"
    Single-agent execution of multi-phase plans leads to slower delivery, no parallel work, and missed review opportunities.

#### Agent Assignment Plan Template

Before starting multi-phase work, create a table mapping phases to agents:

| Phase | Agent | Rationale |
|-------|-------|-----------|
| Phase 1 tests | Codex | Test writing strength |
| Phase 1 impl | Claude | Complex refactoring |
| Phase 2 | Gemini | Independent feature, different model |
| Review | Codex | Fresh perspective from different model |

Then delegate each phase to the assigned agent via `synapse send`.

### Cross-Model Spawning

When spawning or delegating, prefer a **different model type** than your own. This provides two benefits:

1. **Diverse perspectives** -- Different LLMs have different strengths and blind spots. Claude excels at reasoning, Gemini at search and analysis, Codex at focused implementation.
2. **Rate limit distribution** -- Spreading token usage across providers avoids hitting rate limits on any single model. If one model is rate-limited, delegate to another type.

```bash
# Claude spawning a Gemini helper (cross-model)
synapse spawn gemini --name Reviewer --role "code reviewer"

# Gemini spawning a Codex helper (cross-model)
synapse spawn codex -w --name Impl --role "implementation"
```

### Worker Autonomy

Worker agents are not passive -- they can and should proactively collaborate:

- **Spawn helpers** for independent subtasks (prefer different model types)
- **Request reviews** from other agents (different models catch different issues)
- **Delegate out-of-scope work** instead of trying to handle everything
- **Share findings** via `synapse memory save` so the team benefits from your discoveries
- **Clean up after yourself** -- always kill agents you spawn when done: `synapse kill <name> -f`

```bash
# A worker agent spawning its own helper
synapse spawn gemini --name Helper --role "test writer"
synapse send Helper "Write unit tests for auth.py" --silent

# After the helper finishes
synapse kill Helper -f
```

### Use Synapse Features Actively

Beyond `send` and `reply`, agents should use the full set of coordination tools:

| Feature | When to Use | Command |
|---------|-------------|---------|
| **Shared Memory** | Save discoveries for the team | `synapse memory save <key> "..." --notify` |
| **File Safety** | Lock files before editing | `synapse file-safety lock <file> $SYNAPSE_AGENT_ID` |
| **Worktrees** | Parallel edits without conflicts | `synapse spawn <profile> --worktree` |
| **Broadcast** | Team-wide announcements | `synapse broadcast "..." --priority 4` |
| **History** | Review past work | `synapse history list --agent <name>` |

!!! tip "Mandatory Cleanup"
    Always kill agents you spawn after their work is complete. Orphaned agents waste memory (~12MB each), consume port slots (10 per type), and clutter `synapse list`.

## Tips for Effective Cross-Agent Collaboration

| Tip | Details |
|-----|---------|
| **Name your agents** | `--name Rex` is clearer than `codex-8120` in team communication |
| **Use priority levels** | Normal work at 3, urgent follow-ups at 4, production emergencies at 5 |
| **Share knowledge** | `synapse memory save` lets one agent's discoveries help the whole team |
| **Trace for auditing** | `synapse trace <task_id>` shows the full history of a task across agents |
| **Choose response mode wisely** | `--wait` when you need the result, `--silent` for fire-and-forget delegation |
| **Use worktrees for parallel edits** | `--worktree` prevents file conflicts when agents modify the same files |
| **Broadcast for team coordination** | `synapse broadcast` reaches all agents at once for status checks or announcements |
| **Automate with workflows** | `synapse workflow run` replays saved multi-step sequences so you don't re-type recurring pipelines |
| **Spawn cross-model** | Prefer different model types when spawning to diversify perspectives and distribute rate limits |
| **Clean up agents** | Always `synapse kill <name> -f` agents you spawn after their work is done |

## Related Pages

- [Communication](communication.md) — message sending, priority levels, reply tracking
- [Agent Teams](agent-teams.md) — team start, delegate mode, auto-spawn
- [Shared Memory](shared-memory.md) — cross-agent knowledge sharing
- [Workflows](workflow.md) — saved multi-step message sequences
- [History & Tracing](history.md) — task history, trace, statistics
