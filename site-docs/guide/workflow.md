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

Each workflow file has three top-level fields:

| Field | Required | Description |
|-------|:--------:|-------------|
| `name` | Yes | Workflow identifier (matches the filename) |
| `description` | No | Human-readable description |
| `steps` | Yes | Ordered list of message steps |

Each step supports the following fields:

| Field | Required | Default | Description |
|-------|:--------:|:-------:|-------------|
| `target` | Yes | -- | Agent name, ID, type-port, or type |
| `message` | Yes | -- | Message content to send |
| `priority` | No | `3` | Priority level 1-5 |
| `response_mode` | No | `notify` | `wait`, `notify`, or `silent` |

### Example: Security Audit Pipeline

```yaml
name: security-audit
description: "Parallel security audit across three agents"
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

## List Workflows

```bash
synapse workflow list                              # Both scopes
synapse workflow list --project                    # Project scope only
synapse workflow list --user                       # User scope only
```

In interactive terminals, workflows are displayed in a Rich TUI table with name, step count, scope, and description.

## Show Workflow Details

```bash
synapse workflow show review-and-test
```

Displays the workflow name, scope, description, and each step's target, priority, and response mode.

## Run a Workflow

```bash
synapse workflow run review-and-test
```

Steps execute sequentially. Each step calls `synapse send` with the configured target, message, priority, and response mode.

### Dry Run

Preview what would happen without sending any messages:

```bash
synapse workflow run review-and-test --dry-run
```

### Continue on Error

By default, the workflow stops on the first failed step. Use `--continue-on-error` to execute all steps regardless of failures:

```bash
synapse workflow run review-and-test --continue-on-error
```

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
    message: "Review src/ for bugs, security issues, and code smells. Save findings to shared memory."
    priority: 4
    response_mode: wait
  - target: codex
    message: "Check shared memory for review findings and fix all HIGH severity issues."
    response_mode: wait
```

## Related Pages

- [Communication](communication.md) -- message sending, priority levels, response modes
- [Session Save/Restore](session.md) -- save and restore team configurations
- [Cross-Agent Scenarios](cross-agent-scenarios.md) -- real-world multi-agent workflows
- [CLI Commands](../reference/cli.md#workflows) -- full command reference
