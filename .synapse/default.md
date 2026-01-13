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
Response command: synapse send SENDER_ID "YOUR_RESPONSE" --from {{agent_id}}

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use: synapse send <AGENT> "<MESSAGE>" --from {{agent_id}}

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: synapse list

For advanced features (history, file-safety, delegation), use synapse-a2a skill.
