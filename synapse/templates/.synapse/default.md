[SYNAPSE A2A AGENT CONFIGURATION]
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

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response: Use the send command below to reply to the sender

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use this command to communicate with other agents (works in sandboxed environments):

```bash
synapse send <AGENT> "<MESSAGE>" [--from <SENDER>] [--priority <1-5>] [--response | --no-response] [--reply-to <TASK_ID>]
```

Target formats (in priority order):
- Full ID: `synapse-gemini-8110` (always works)
- Type-port: `gemini-8110` (when multiple agents of same type exist)
- Agent type: `gemini` (only when single instance exists)

Parameters:
- `--from, -f`: Your agent ID (for reply identification) - **always include this**
- `--priority, -p`: 1-4 normal, 5 = emergency interrupt (sends SIGINT first)
- `--response`: Roundtrip mode - sender waits, **receiver MUST reply** using `--reply-to`
- `--no-response`: Oneway mode - fire and forget, no reply expected (default)
- `--reply-to`: Attach response to a specific task ID (use this when replying to `--response` requests)

IMPORTANT: Always use `--from` to identify yourself. When replying to a `--response` request, use `--reply-to <task_id>` to link your response.

Examples:
```bash
# Send message to Gemini (identifying as Claude)
synapse send gemini "What is the best practice for error handling in Python?" --from claude

# Background task
synapse send codex "Run the test suite and commit if all tests pass" --from claude

# Parallel delegation
synapse send gemini "Research React best practices" --from claude
synapse send codex "Refactor the auth module" --from claude

# Emergency interrupt (priority 5)
synapse send codex "STOP" --priority 5 --from claude

# Wait for response (roundtrip)
synapse send gemini "Analyze this" --response --from claude

# Reply to a --response request (use task_id from [A2A:task_id:sender])
synapse send claude "Here is my analysis..." --reply-to abc123 --from gemini
```

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: synapse list

For advanced features (history, file-safety, delegation), use synapse-a2a skill.
