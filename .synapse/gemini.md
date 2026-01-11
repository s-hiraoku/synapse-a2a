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

- **ONE-TIME RESPONSE & RESET**: Send your response to the sender ONLY ONCE when the task is complete. After sending, reset your task context and wait for new instructions. Do not send intermediate status updates unless explicitly requested.

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response command: python -m synapse.tools.a2a send --target SENDER_ID YOUR_RESPONSE

HOW TO SEND MESSAGES TO OTHER AGENTS:
When user types @agent message, use: python -m synapse.tools.a2a send --target AGENT MESSAGE

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: python -m synapse.tools.a2a list

For advanced features (history, file-safety, delegation), refer to synapse documentation.
