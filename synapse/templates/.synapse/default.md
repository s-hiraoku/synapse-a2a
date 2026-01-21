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

HOW TO RECEIVE AND REPLY TO A2A MESSAGES:
Input format:
  [A2A:<task_id>:<sender_id>:R] <message>  ← Response required (:R flag present)
  [A2A:<task_id>:<sender_id>] <message>    ← No response required

WHEN TO USE --reply-to:
- **:R flag present** → MUST use `--reply-to <task_id>` to reply
- **:R flag absent** → Do NOT use `--reply-to`
  - If you need to communicate back, send a new message (without `--reply-to`)

```bash
# :R flag present → use --reply-to
synapse send <sender_type> "<your reply>" --reply-to <task_id> --from <your_agent_type>

# :R flag absent → do the task, no --reply-to needed
# (send a new message only if you have questions or need to report completion)
```

Example - Response required (:R flag):
  [A2A:abc12345:synapse-claude-8100:R] What is the project structure?
Reply with:
  synapse send claude "The project has src/, tests/, docs/ directories..." --reply-to abc12345 --from codex

Example - No response required (no :R flag):
  [A2A:xyz67890:synapse-claude-8100] Run the tests and fix any failures
Action: Just do the task. No reply needed unless you have questions.

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
synapse send gemini "What is the best practice for error handling?" --response --from claude

# Delegation - no reply needed
synapse send codex "Run the test suite and commit if all tests pass" --from claude

# Parallel delegation - no reply needed
synapse send gemini "Research React best practices" --from claude
synapse send codex "Refactor the auth module" --from claude

# Emergency interrupt
synapse send codex "STOP" --priority 5 --from claude

# Status check - needs reply
synapse send codex "What is your current status?" --response --from claude
```

AVAILABLE AGENTS: claude, gemini, codex, opencode
LIST COMMAND: synapse list

For advanced features (history, file-safety, delegation), use synapse-a2a skill.
