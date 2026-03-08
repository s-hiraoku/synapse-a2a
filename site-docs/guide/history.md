# History & Tracing

## Overview

Synapse automatically tracks task history — every message sent, received, and processed. History is enabled by default since v0.3.13.

Storage: `~/.synapse/history.db` (SQLite)

## Listing History

```bash
synapse history list                         # Recent tasks
synapse history list --agent claude          # Filter by agent
synapse history list --limit 20              # Limit results
```

## Task Details

```bash
synapse history show <task_id>
```

Shows the full task record including input, output, metadata, and timestamps.

## Search

```bash
synapse history search "authentication"
synapse history search "Auth" --case-sensitive    # Match exact case
synapse history search "auth" --agent gemini
synapse history search "OAuth JWT" --logic AND    # Both terms
synapse history search "OAuth JWT" --logic OR     # Either term
```

## Statistics

```bash
synapse history stats                        # Overall statistics
synapse history stats --agent gemini         # Per-agent stats
```

Includes task counts, success rates, and token usage when data is available.

## Export

```bash
synapse history export --format json         # Export to JSON
synapse history export --format csv          # Export to CSV
```

## Task Tracing

Trace a task across history and file modifications:

```bash
synapse trace <task_id>
```

This cross-references:

- Task history (input, output, timing)
- File Safety records (which files were modified, by whom)
- Related tasks and dependencies

## Cleanup

```bash
synapse history cleanup --days 30            # Remove records older than 30 days
synapse history cleanup --max-size 100       # Keep database under 100MB
synapse history cleanup --days 90 --dry-run  # Preview what would be deleted
```

## Advanced Usage

### Keyword Search

Search for specific implementation details across all past tasks:

```bash
# Search input and output for "OAuth"
synapse history search "OAuth"

# Multiple terms with logical AND
synapse history search "OAuth" "JWT" --logic AND
```

### Statistics and Token Usage

Monitor agent productivity and estimated costs:

```bash
synapse history stats
synapse history stats --agent gemini
```

If token usage data is available (detected in agent output), the stats command will show a **TOKEN USAGE** section with estimated costs per agent.

### Data Export for Analysis

Export history to standard formats for external review or training:

```bash
# JSON for programmatic analysis
synapse history export --format json --output audit_log.json

# CSV for spreadsheet review
synapse history export --format csv --agent reviewer > review_stats.csv
```

## Data Lifecycle

### Automatic Maintenance

Synapse maintains the history database automatically to prevent disk bloat:

- **Indexing**: Task ID, timestamps, and agent names are indexed for fast searching.
- **WAL Mode**: SQLite Write-Ahead Logging allows background agents to write history without blocking CLI reads.

### Manual Cleanup

If the database grows too large, use the cleanup command:

```bash
# Remove everything older than 30 days
synapse history cleanup --days 30

# Force cleanup without confirmation
synapse history cleanup --days 14 --force

# Preview what will be deleted
synapse history cleanup --days 90 --dry-run
```

## Configuration

```bash
# Disable history (not recommended)
SYNAPSE_HISTORY_ENABLED=false synapse claude

# Default: enabled
SYNAPSE_HISTORY_ENABLED=true
```

## Completion Callback (`--silent`)

When you send a message with `--silent`, the sender's history initially records the task as `sent`. Once the receiver finishes processing, a best-effort callback updates the sender-side history:

```
sent  →  completed / failed / canceled
```

**How it works:**

1. Sender dispatches a fire-and-forget message; history records status as `sent`
2. Receiver processes the task and reaches a terminal state (`completed`, `failed`, or `canceled`)
3. Receiver sends `POST /history/update` to the sender (UDS first, HTTP fallback)
4. Sender's history record is updated to the final status

**Best-effort delivery:** If the sender is offline or unreachable when the callback fires, the history record stays as `sent`. No retries are attempted.

!!! tip
    Use `synapse history list` to check whether delegated tasks have been updated. Records still showing `sent` may indicate the callback was not delivered.

## Monitoring Delegated Tasks

When orchestrating multiple agents, use history to track progress:

```bash
# Real-time agent status
synapse list

# Task history by agent
synapse history list --agent gemini
synapse history list --agent codex

# Task details
synapse history show <task_id>

# Statistics
synapse history stats
synapse history stats --agent gemini
```

## Delegation Workflow Example

```bash
# 1. Check agent availability
synapse list

# 2. Delegate task
synapse send gemini "Write tests for X" \
  --priority 3 --silent

# 3. Monitor progress
synapse list
git status && git log --oneline -5

# 4. Send follow-up
synapse send gemini "Status update?" \
  --priority 4 --wait

# 5. Review completion
synapse history list --agent gemini --limit 5
```
