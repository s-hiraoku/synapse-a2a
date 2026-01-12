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
Use this command to communicate with other agents:

```bash
python3 synapse/tools/a2a.py send --target <AGENT> [--priority <1-5>] [--response|--no-response] "<MESSAGE>"
```

Parameters:
- `--target`: Agent ID (e.g., `synapse-gemini-8110`) or type (e.g., `gemini`)
- `--priority`: 1-4 normal, 5 = emergency interrupt (sends SIGINT first)
- `--response`: Wait for and receive response from target agent
- `--no-response`: Do not wait for response (fire and forget)

WHEN TO USE --response vs --no-response:

Use `--response` when:
- You need the result to continue your work
- The task is a question that requires an answer
- You need to verify the task was completed correctly
- The result will be integrated into your response to the user

Use `--no-response` when:
- The task is a background/fire-and-forget operation
- You're delegating work that doesn't need immediate feedback
- The other agent will report results through other means
- You're sending multiple parallel tasks

Examples:
```bash
# Need the answer - use --response
python3 synapse/tools/a2a.py send --target gemini --response "What is the best practice for error handling in Python?"

# Background task - use --no-response
python3 synapse/tools/a2a.py send --target codex --no-response "Run the test suite and commit if all tests pass"

# Parallel delegation - use --no-response
python3 synapse/tools/a2a.py send --target gemini --no-response "Research React best practices"
python3 synapse/tools/a2a.py send --target codex --no-response "Refactor the auth module"

# Emergency interrupt (priority 5)
python3 synapse/tools/a2a.py send --target codex --priority 5 "STOP"
```

FLOW SETTINGS (.synapse/settings.json):
- `roundtrip`: Always wait for response (flags ignored)
- `oneway`: Never wait for response (flags ignored)
- `auto`: You decide per-message using `--response`/`--no-response` flags (default)

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: python3 synapse/tools/a2a.py list

For advanced features (history, file-safety, delegation), use synapse-a2a skill.
