[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE - READ ONLY]
Agent: {{agent_id}} | Port: {{port}}

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response command: python3 synapse/tools/a2a.py send --target SENDER_ID YOUR_RESPONSE

HOW TO SEND MESSAGES TO OTHER AGENTS:
When user types @agent message, use: python3 synapse/tools/a2a.py send --target AGENT MESSAGE

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: python3 synapse/tools/a2a.py list

TASK HISTORY (Enable with SYNAPSE_HISTORY_ENABLED=true):
  synapse history list [--agent <name>] [--limit <n>]    - List tasks
  synapse history search <keywords>                       - Search by keywords
  synapse history stats [--agent <name>]                  - View statistics
  synapse history export --format [json|csv] [--output <file>]  - Export data
  synapse history cleanup --days <n> [--force]            - Delete old tasks
