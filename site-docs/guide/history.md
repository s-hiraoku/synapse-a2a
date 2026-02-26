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
```

## Configuration

```bash
# Disable history (not recommended)
SYNAPSE_HISTORY_ENABLED=false synapse claude

# Default: enabled
SYNAPSE_HISTORY_ENABLED=true
```

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
  --priority 3 --from $SYNAPSE_AGENT_ID --no-response

# 3. Monitor progress
synapse list
git status && git log --oneline -5

# 4. Send follow-up
synapse send gemini "Status update?" \
  --priority 4 --from $SYNAPSE_AGENT_ID --response

# 5. Review completion
synapse history list --agent gemini --limit 5
```
