[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE - READ ONLY]
Agent: {{agent_id}} | Port: {{port}}

================================================================================
BRANCH MANAGEMENT - CRITICAL
================================================================================

- **Do NOT change branches during active work** - Stay on the current branch
- **If branch change is needed**, ask the user for confirmation first
- Before switching, ensure all changes are committed or stashed
- When receiving delegated tasks, work on the same branch as the delegating agent

================================================================================
A2A COMMUNICATION PROTOCOL
================================================================================

HOW TO RECEIVE AND REPLY TO A2A MESSAGES:
Input format: [A2A:<task_id>:<sender_id>] <message>

How to reply depends on whether the sender is waiting for a response:
- If sender used `--response` flag → they are waiting → use `--reply-to <task_id>`
- If sender did NOT use `--response` → they are NOT waiting → do NOT use `--reply-to`

Since you cannot know if `--response` was used, follow this rule:
**Always use `--reply-to` when replying.** If it fails, retry without `--reply-to`.

```bash
# First try with --reply-to
synapse send <sender_type> "<your reply>" --reply-to <task_id> --from <your_agent_type>

# If that fails, retry without --reply-to
synapse send <sender_type> "<your reply>" --from <your_agent_type>
```

Example - if you receive:
  [A2A:abc12345:synapse-claude-8100] Please analyze this code
Reply with:
  synapse send claude "Here is my analysis..." --reply-to abc12345 --from gemini

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use this command to communicate with other agents (works in sandboxed environments):

```bash
synapse send <AGENT> "<MESSAGE>" [--from <SENDER>] [--priority <1-5>] [--response | --no-response] [--reply-to <TASK_ID>]
```

Parameters:
- `target`: Agent ID (e.g., `synapse-claude-8100`) or type (e.g., `claude`)
- `--from, -f`: Your agent ID (for reply identification) - **always include this**
- `--priority, -p`: 1-4 normal, 5 = emergency interrupt (sends SIGINT first)
- `--response`: Roundtrip mode - sender waits, **receiver MUST reply** using `--reply-to`
- `--no-response`: Oneway mode - fire and forget, no reply expected (default)
- `--reply-to`: Attach response to a specific task ID (use this when replying to `--response` requests)

IMPORTANT: Always use `--from` to identify yourself. When replying to a `--response` request, use `--reply-to <task_id>` to link your response.

Examples:
```bash
# Send message to Claude (identifying as Gemini)
synapse send claude "What is the best practice for error handling in Python?" --from gemini

# Background task
synapse send codex "Run the test suite and commit if all tests pass" --from gemini

# Parallel delegation
synapse send claude "Research React best practices" --from gemini
synapse send codex "Refactor the auth module" --from gemini

# Emergency interrupt (priority 5)
synapse send codex "STOP" --priority 5 --from gemini

# Wait for response (roundtrip)
synapse send claude "Analyze this" --response --from gemini

# Reply to a --response request (use task_id from [A2A:task_id:sender])
synapse send claude "Here is my analysis..." --reply-to abc123 --from gemini
```

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: synapse list

For advanced features (history, file-safety, delegation), refer to synapse documentation.
