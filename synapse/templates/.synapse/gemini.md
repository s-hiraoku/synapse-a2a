[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE - READ ONLY]
Agent: {{agent_name}} | Port: {{port}} | ID: {{agent_id}}

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
Input format:
  A2A: <message>

Messages arrive as plain text with "A2A: " prefix.

HOW TO REPLY:
Use `synapse reply` to respond to the last received message:

```bash
synapse reply "<your reply>" --from <agent_type>
```

Synapse automatically tracks senders who expect a reply (messages with `[REPLY EXPECTED]` marker).
- `--from`: Your agent type (e.g., `gemini`, `claude`, `codex`, `opencode`, `copilot`)
- Required in sandboxed environments (like Codex)

Example - Question received:
  A2A: What is the project structure?
Reply with:
  synapse reply "The project has src/, tests/, docs/ directories..." --from gemini

Example - Delegation received:
  A2A: Run the tests and fix any failures
Action: Just do the task. No reply needed unless you have questions.

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use this command to communicate with other agents (works in sandboxed environments):

```bash
synapse send <AGENT> "<MESSAGE>" [--from <SENDER>] [--priority <1-5>] [--response | --no-response]
```

Target formats (in priority order):
- Full ID: `synapse-claude-8100` (always works)
- Type-port: `claude-8100` (when multiple agents of same type exist)
- Agent type: `claude` (only when single instance exists)

Parameters:
- `--from, -f`: Your agent type (e.g., `gemini`) - **always include this**
- `--priority, -p`: 1-4 normal, 5 = emergency interrupt (sends SIGINT first)
- `--response`: Roundtrip mode - sender waits, **receiver MUST reply** using `synapse reply`
- `--no-response`: Oneway mode - fire and forget, no reply expected (default)

CHOOSING --response vs --no-response:
- Use `--response` when you NEED a reply (questions, requests for analysis, status checks)
- Use `--no-response` when you DON'T need a reply (notifications, fire-and-forget tasks)

**Rule: If your message asks for a reply, use --response**
Examples that NEED --response:
- "What is the status?" → needs reply → use `--response`
- "Please review this code" → needs reply → use `--response`
- "Can you analyze this?" → needs reply → use `--response`

Examples that DON'T need --response:
- "FYI: The build completed" → notification → use `--no-response`
- "Run the tests and commit if passed" → delegated task → use `--no-response`

IMPORTANT: Always use `--from` to identify yourself.

Examples:
```bash
# Question - needs reply
synapse send claude "What is the best practice for error handling?" --response --from gemini

# Delegation - no reply needed
synapse send codex "Run the test suite and commit if all tests pass" --from gemini

# Parallel delegation - no reply needed
synapse send claude "Research React best practices" --from gemini
synapse send codex "Refactor the auth module" --from gemini

# Emergency interrupt
synapse send codex "STOP" --priority 5 --from gemini

# Status check - needs reply
synapse send codex "What is your current status?" --response --from gemini
```

AVAILABLE AGENTS: claude, gemini, codex, opencode, copilot
LIST COMMAND: synapse list

================================================================================
SKILLS
================================================================================

Gemini has access to skills in `.gemini/skills/`. Available skills:
- **synapse-a2a**: Inter-agent communication guidance
- **delegation**: Task delegation configuration

Skills are automatically loaded when relevant tasks are detected.

For advanced features (history, file-safety, delegation), refer to synapse documentation or use the relevant skill.
