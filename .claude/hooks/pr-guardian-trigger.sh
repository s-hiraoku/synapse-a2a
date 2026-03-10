#!/usr/bin/env bash
# pr-guardian-trigger.sh — PostToolUse hook
# Detects git push / gh pr create and emits a systemMessage prompting
# Claude to invoke /pr-guardian automatically.

set -euo pipefail

PAYLOAD="$(cat)"

# Parse tool_name and command from the JSON payload.
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

  # Verify a PR actually exists for the current branch.
  if ! gh pr view --json number -q '.number' >/dev/null 2>&1; then
    exit 0
  fi

  PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null || echo "")
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

  # State file prevents re-triggering if pr-guardian is already running.
  STATE_FILE="/tmp/.synapse-ci/pr-guardian-${PR_NUM}"
  if [[ -f "$STATE_FILE" ]]; then
    # Already triggered for this PR — don't spam.
    exit 0
  fi

  mkdir -p /tmp/.synapse-ci
  echo "$(date +%s)" > "$STATE_FILE"

  # Emit systemMessage to prompt Claude to start pr-guardian.
  MSG="[PR Guardian] Push detected on PR #${PR_NUM} (${BRANCH}). Invoke /pr-guardian to start automatic monitoring — it will poll CI status, check for merge conflicts and CodeRabbit reviews, and fix issues until all checks pass."

  ESCAPED=$(printf '%s' "$MSG" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
  echo "{\"systemMessage\": ${ESCAPED}}"
fi

exit 0
