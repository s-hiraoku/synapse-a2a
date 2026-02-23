#!/usr/bin/env bash
set -euo pipefail

# PostToolUse hook: launches poll-ci.sh when a git push or gh pr create is detected.
# Reads the hook JSON payload from stdin, checks tool_name and tool_input.command.

PAYLOAD="$(cat)"

# Parse tool_name and command from the JSON payload using python3.
read -r TOOL_NAME COMMAND < <(
  python3 -c "
import json, sys
d = json.loads(sys.argv[1])
tn = d.get('tool_name', '')
cmd = d.get('tool_input', {}).get('command', '')
print(tn + ' ' + cmd)
" "$PAYLOAD"
)

# Only act on Bash tool invocations.
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

# Check if the command matches git push or gh pr create.
if [[ "$COMMAND" =~ (^|[;&|[:space:]])git[[:space:]]+push([[:space:]]|$) ]] ||
   [[ "$COMMAND" =~ (^|[;&|[:space:]])gh[[:space:]]+pr[[:space:]]+create([[:space:]]|$) ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  nohup "$SCRIPT_DIR/poll-ci.sh" >/dev/null 2>&1 &
  nohup "$SCRIPT_DIR/poll-pr-status.sh" >/dev/null 2>&1 &
fi

exit 0
