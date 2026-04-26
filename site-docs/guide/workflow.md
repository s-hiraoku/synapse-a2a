# Workflows

## Overview

Synapse workflows let you save reusable multi-step message sequences as YAML files and replay them with a single command. Instead of manually typing `synapse send` for each step of a recurring process, define the steps once and run the workflow whenever you need it.

Storage: `.synapse/workflows/` (project-local) or `~/.synapse/workflows/` (user-global)

## Create a Workflow

```bash
synapse workflow create review-and-test
```

This generates a template YAML file at `.synapse/workflows/review-and-test.yaml` (project scope, default). Edit the file to define your steps:

```yaml
name: review-and-test
description: "Send review to Claude, then tests to Gemini"
steps:
  - target: claude
    message: "Review the changes in src/ for correctness and style"
    priority: 4
    response_mode: wait
  - target: gemini
    message: "Write tests for the latest changes in src/"
    response_mode: silent
```

You can choose a different scope:

```bash
synapse workflow create review-and-test --user     # ~/.synapse/workflows/
synapse workflow create review-and-test --force     # Overwrite existing
```

!!! note "Workflow naming rules"
    Workflow names must start with an alphanumeric character and contain only alphanumeric characters, dots, hyphens, or underscores (e.g., `review-and-test`, `daily_check.v2`).

## YAML Format

Each workflow file has these top-level fields:

| Field | Required | Description |
|-------|:--------:|-------------|
| `name` | Yes | Workflow identifier (matches the filename) |
| `description` | No | Human-readable description |
| `steps` | Yes | Ordered list of message steps |
| `trigger` | No | Natural-language trigger condition for skill auto-matching (e.g., `"when CI fails"`) |
| `auto_spawn` | No | If `true`, automatically spawn agents that are not running when executing steps |

Each step supports the following fields:

| Field | Required | Default | Description |
|-------|:--------:|:-------:|-------------|
| `kind` | No | `send` | Step type: `send` or `subworkflow` |
| `target` | Yes | -- | Agent name, ID, type-port, type, or `self` |
| `message` | Yes | -- | Message content to send |
| `priority` | No | `3` | Priority level 1-5 |
| `response_mode` | No | `notify` | `wait`, `notify`, or `silent` |
| `auto_spawn` | No | `false` | If `true`, auto-spawn the target agent if not running (step-level override) |
| `workflow` | Yes for `subworkflow` | -- | Child workflow name to execute |

For `kind: send`, use the regular `target` and `message` fields.

For `kind: subworkflow`, use `workflow` and omit `target` and `message`:

```yaml
steps:
  - kind: subworkflow
    workflow: review-and-test
```

Nested workflows are expanded recursively at run time. The runner rejects cycles such as `A -> B -> A` and limits nesting depth to 10 workflows.

`target` follows the standard Synapse target resolution rules. For matching priority and ambiguity behavior, see [Agent Identity](agent-identity.md#target-resolution).

When `auto_spawn` is enabled, `target` is also used as the spawn profile name if the agent is not already running. In that case, prefer a profile name such as `claude`, `gemini`, or `codex` rather than a custom name, Runtime ID, or type-port shorthand.

!!! note "Bare-type targets respect the caller's working directory (#568)"
    When a step uses a bare type like `target: claude` or `target: codex`, the workflow runner restricts the match to agents whose `working_dir` matches the caller's CWD. This prevents `synapse workflow run` from accidentally dispatching to an unrelated agent of the same type running in another project (e.g. a `nix-claude` in `~/nix-config`), and lets `auto_spawn` correctly create a fresh agent in the workflow's CWD when no local match exists. `agent_id` and custom-name targets continue to match globally; `target: self` is unchanged.

### Example: Security Audit Pipeline

```yaml
name: security-audit
description: "Sequential security audit across three agents"
steps:
  - target: Gem
    message: "Audit authentication and authorization code. Report HIGH/MEDIUM/LOW findings."
    priority: 4
    response_mode: wait
  - target: Cody
    message: "Scan for injection vulnerabilities (SQL, XSS, command injection). Report findings."
    priority: 4
    response_mode: wait
  - target: Rex
    message: "Review dependencies for known CVEs. Flag packages older than 6 months."
    priority: 4
    response_mode: wait
```

### Example: CI Fix Sequence

```yaml
name: fix-ci-and-verify
description: "Fix CI failures then verify with tests"
steps:
  - target: claude
    message: "Run /fix-ci to diagnose and fix the current CI failure"
    response_mode: wait
  - target: gemini
    message: "Run the full test suite and report any remaining failures"
    response_mode: wait
```

### Example: Reusable Parent Workflow

```yaml
name: review-fix-verify
description: "Compose existing workflows into one reusable pipeline"
steps:
  - kind: subworkflow
    workflow: review-and-test
  - kind: subworkflow
    workflow: fix-ci-and-verify
```

### Self-Target Steps (`target: self`)

A workflow step can target the agent that is running the workflow itself by using `target: self`. This is useful for post-implementation workflows where the calling agent needs to perform a step on its own codebase (e.g., running a linter or generating documentation) as part of a larger multi-agent pipeline.

```yaml
name: implement-and-verify
description: "Implement feature, then self-verify with tests"
steps:
  - target: gemini
    message: "Implement the feature described in the plan card"
    response_mode: wait
  - target: self
    message: "Run the test suite and verify all tests pass"
    response_mode: wait
```

When the workflow runner encounters `target: self`, it automatically spawns a **helper agent** of the same type as the calling agent. The helper runs in a separate process to avoid deadlock (since the calling agent is blocked waiting for the workflow to complete). One helper is reused across all self-target steps in the same workflow run, and is shut down in a `finally` block when the workflow completes (success or failure).

!!! warning "Helper agent is a separate process"
    `target: self` does **not** execute the step inside the calling agent's process. A new agent is spawned and the message is sent to it via A2A. This means:

    The helper agent has a **separate context** and does not share conversation history or in-memory state.
    It runs in the **same working directory** as the calling agent, so file changes are visible to both.
    While running, it appears in `synapse list` as `wf-helper-<workflow>-<id>`.
    If you need full prior context, avoid `self` and target an existing running agent explicitly.

!!! note "Auto-detection"
    If a step's target resolves to the calling agent (by name, ID, or type when only one agent of that type is running), the runner automatically treats it as a self-target step. You can use `target: self` explicitly to make the intent clear.

??? info "Design note: why not execute in-process?"
    A natural question is: why not skip the helper and execute `target: self` steps directly inside the calling agent? There are several reasons this is not feasible with the current architecture:

    **1. Deadlock** — LLM CLI agents (Claude Code, Codex, Gemini CLI) are single-turn: they process one prompt at a time. When a workflow step uses `response_mode: wait`, the runner polls the target's task endpoint until the task completes. If the target is the same agent, the agent is blocked polling itself while also unable to process the incoming message — a classic deadlock.

    **2. Context pollution** — Running all steps in one agent context accumulates output from every step (documentation generation, git operations, CI checks, etc.) into a single context window. This wastes tokens, introduces noise, and risks exceeding context limits. A helper starts with a clean context per step.

    **3. Fault isolation** — If step 3 corrupts the agent's state (e.g., a bad git operation), steps 4 and 5 are affected. With a helper, the caller remains unaffected and can retry or skip.

    **4. Reentrancy** — A step might invoke a skill that itself triggers another workflow. In-process execution has no natural guard against infinite recursion; the helper model uses a depth limit (`SYNAPSE_WORKFLOW_HELPER_DEPTH`) that is straightforward to enforce across process boundaries.

    **Recommended alternative**: Instead of `target: self`, use an explicit agent target like `target: codex` to send the message to an already-running agent. This avoids helper spawn overhead, prevents deadlock, keeps context clean, and gives you control over which agent handles each step.

    ```yaml
    # Preferred: use an existing agent instead of self
    steps:
      - target: codex
        message: "/release"
        response_mode: wait
    ```

## List Workflows

```bash
synapse workflow list                              # Both scopes
synapse workflow list --project                    # Project scope only
synapse workflow list --user                       # User scope only
```

In interactive terminals, workflows are displayed in a Rich TUI table with name, step count, scope, and description. Non-interactive environments (pipes, CI) fall back to plain-text tabular output.

## Show Workflow Details

```bash
synapse workflow show review-and-test
```

Displays the workflow name, scope, description, and each step's target, priority, and response mode.

## Run a Workflow

```bash
synapse workflow run review-and-test
```

### Async Mode

Run a workflow in the background and check its status later:

```bash
synapse workflow run review-and-test --async
# Returns a run_id immediately

synapse workflow status <run_id>
```

This is useful for long-running pipelines where you don't want to block the terminal.

### Sequential Execution

Steps execute sequentially. Each step sends an A2A request directly to the target agent over HTTP with the configured target, message, priority, and response mode.
If a step uses `kind: subworkflow`, Synapse loads the child workflow and executes its send steps inline before continuing.

When a step uses `response_mode: wait`, the runner polls the target agent's task endpoint until the task reaches a terminal state (`completed`, `failed`, or `canceled`). This ensures that subsequent steps only run after the previous step's agent has finished processing. The poll timeout is 10 minutes per step; if exceeded, the step is treated as completed (best-effort).

### Dry Run

Preview what would happen without sending any messages:

```bash
synapse workflow run review-and-test --dry-run
```

Dry run output includes nested `subworkflow` entries and the send steps they expand into.

### Auto-Spawn Agents

If a target agent is not running, use `--auto-spawn` to spawn it automatically before sending the message. The target name is used as the profile name for spawning:

```bash
synapse workflow run review-and-test --auto-spawn
```

You can also enable auto-spawn at the workflow or step level in YAML (see [YAML Format](#yaml-format)) so that `--auto-spawn` is not required on the command line.

### Continue on Error

By default, the workflow stops on the first failed step. Use `--continue-on-error` to execute all steps regardless of failures:

```bash
synapse workflow run review-and-test --continue-on-error
```

When nested workflows are used, `--continue-on-error` applies to child steps too.

## Run from Canvas

Workflows can also be executed from the Canvas browser UI at `#/workflow`. Select a workflow from the list and click **Run**.

Both CLI and Canvas workflow execution send A2A requests directly to target agents over HTTP, with `response_mode: wait` polling for task completion. Canvas sets sender metadata `sender_id=canvas-workflow`, `sender_name=Workflow`, and `sender_endpoint=http://localhost:<canvas-port>`, so agents can reply back to Canvas with `synapse reply`. Key differences from CLI execution:

- **Background execution**: Steps run asynchronously; the UI updates in real-time via SSE
- **Reply routing**: Replies go back to Canvas, not to the agent that happens to be running the Canvas server
- **Step output**: Successful steps show the accepted task summary returned by the target agent
- **Error translation**: Delivery errors are converted to human-readable messages
- **Toast notifications**: A notification appears when the run completes or fails
- **Auto-spawn**: Honors both workflow-level and step-level `auto_spawn` settings
- **Persistent history**: Execution history is stored in a SQLite database (`.synapse/workflow_runs.db`) so past runs survive server restarts. The in-memory cache holds up to 50 recent runs; older runs remain queryable from the database.

!!! warning "Agent name conflicts"
    If an agent with the same name exists in a different directory (e.g., a worktree), Canvas will report an error: *"Agent 'X' already exists in a different directory."* Rename the workflow target or stop the conflicting agent.

See [Canvas -- Workflow View](canvas.md#workflow-view-workflow) for the UI documentation.

## Sync Workflows to Skills

Synapse can auto-generate SKILL.md files from workflow YAML definitions, bridging workflows into the skill discovery system used by Claude Code and other MCP-aware agents. This means workflows become discoverable as skills and can be triggered by agents automatically.

```bash
synapse workflow sync
```

This command:

1. Scans all workflows in project and user scopes
2. Generates `SKILL.md` files in `.claude/skills/<name>/` and `.agents/skills/<name>/`
3. Removes orphaned auto-generated skills whose workflow YAML no longer exists
4. Skips directories containing hand-written (non-autogenerated) skills

Auto-generated skills are marked with `<!-- synapse-workflow-autogen -->` and should not be edited manually -- changes are overwritten on the next sync.

!!! tip "Automatic sync on create/delete"
    `synapse workflow create` and `synapse workflow delete` automatically sync the corresponding skill. Use `synapse workflow sync` to batch-sync all workflows or clean up orphans.

### Trigger Field

The `trigger` field adds a natural-language condition to the generated SKILL.md description, helping agents match the workflow to incoming tasks:

```yaml
name: fix-ci-and-verify
description: "Fix CI failures then verify with tests"
trigger: "when CI fails or tests are broken"
auto_spawn: true
steps:
  - target: claude
    message: "Run /fix-ci to diagnose and fix the current CI failure"
    response_mode: wait
  - target: gemini
    message: "Run the full test suite and report any remaining failures"
    response_mode: wait
```

After running `synapse workflow sync`, this workflow appears as a skill with the description: *"Workflow: Fix CI failures then verify with tests. Use this skill when: when CI fails or tests are broken. Triggered by /fix-ci-and-verify command."*

## Delete a Workflow

```bash
synapse workflow delete review-and-test            # Prompts for confirmation
synapse workflow delete review-and-test --force     # Skip confirmation
```

## Scope Options

Workflow commands support two mutually exclusive scope flags:

| Flag | Description |
|------|-------------|
| `--project` | Project scope (default for create): `.synapse/workflows/` in the current repository |
| `--user` | User scope: `~/.synapse/workflows/` for cross-project reuse |

When loading or listing, project scope takes precedence over user scope if both contain a workflow with the same name.

!!! tip "Sharing workflows"
    Project-scope workflow files live in `.synapse/workflows/` and can be committed to version control. This lets team members share reusable multi-agent procedures.

## Workflows vs Sessions

Both workflows and sessions capture reusable team configurations, but they serve different purposes:

| Feature | Workflows | Sessions |
|---------|-----------|----------|
| **What it saves** | A sequence of messages to send | A snapshot of running agents |
| **When to use** | Repeatable task pipelines (review, audit, deploy) | Restore a team configuration (agents + roles) |
| **Storage format** | YAML (human-editable) | JSON (machine-generated) |
| **Execution** | Sends messages to already-running agents | Spawns agents from scratch |

A typical pattern is to restore a session (to bring up agents) and then run a workflow (to kick off a task sequence):

```bash
synapse session restore review-team --worktree
# Wait for agents to become READY...
synapse workflow run review-and-test
```

## Patterns

### Morning Standup

```yaml
name: standup
description: "Daily status check across the team"
steps:
  - target: Cody
    message: "Status update: what did you work on yesterday and what's planned for today?"
    response_mode: wait
  - target: Gem
    message: "Status update: what did you work on yesterday and what's planned for today?"
    response_mode: wait
  - target: Rex
    message: "Status update: what did you work on yesterday and what's planned for today?"
    response_mode: wait
```

### Review-Then-Fix

```yaml
name: review-fix
description: "Claude reviews, then Codex fixes any issues found"
steps:
  - target: claude
    message: "Review src/ for bugs, security issues, and code smells. Save findings to the LLM Wiki."
    priority: 4
    response_mode: wait
  - target: codex
    message: "Query the LLM Wiki for review findings and fix all HIGH severity issues."
    response_mode: wait
```

## Smart Suggest

When using MCP bootstrap, the `analyze_task` MCP tool can automatically suggest task splits for complex prompts. The tool always returns a `delegation_strategy` (`self`, `subagent`, or `spawn`) indicating whether the agent should handle the task alone, use a built-in subagent, or delegate via `synapse spawn`/`synapse team start`. When a prompt triggers Smart Suggest (based on file count, multi-directory changes, missing tests, prompt length, or keyword matching), the agent also receives a suggested breakdown (design/implement/verify) that can be turned into a Plan Card.

This complements workflows by automating the initial task decomposition step. While workflows define fixed, reusable sequences, Smart Suggest dynamically analyzes each prompt, recommends a delegation strategy, and proposes ad-hoc task splits when the work appears large enough.

See [MCP Bootstrap Setup](mcp-setup.md#mcp-tools) for details on the `analyze_task` tool, and [Canvas -- Plan Template](canvas.md#plan) for Plan Card documentation.

## Related Pages

- [Communication](communication.md) -- message sending, priority levels, response modes
- [Session Save/Restore](session.md) -- save and restore team configurations
- [Cross-Agent Scenarios](cross-agent-scenarios.md) -- real-world multi-agent workflows
- [Canvas](canvas.md) -- shared visual output surface, including Plan Cards
- [Skills](skills.md) -- skill discovery, deployment, and workflow-to-skill sync
- [CLI Commands](../reference/cli.md#workflows) -- full command reference
