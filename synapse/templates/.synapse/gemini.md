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

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response command: python -m synapse.tools.a2a send --target SENDER_ID YOUR_RESPONSE

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use the @agent pattern to send messages to other agents:
- `@claude message` - Send with flow setting (a2a.flow in settings.json)
- `@claude --response message` - Wait for response (roundtrip)
- `@claude --no-response message` - Fire and forget (oneway)

FLOW SETTINGS (.synapse/settings.json):
- `roundtrip`: Always wait for response
- `oneway`: Never wait for response (fire and forget)
- `auto`: Per-message control with --response/--no-response flags (default waits)

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: python -m synapse.tools.a2a list

For advanced features (history, file-safety, delegation), refer to synapse documentation.
