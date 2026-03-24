#!/bin/sh
# Aggregate team status.
# Usage: check_team_status.sh
set -e

if ! command -v synapse >/dev/null 2>&1; then
  echo "synapse CLI not found in PATH." >&2
  exit 1
fi

echo "=== Agent Status ==="
if list_output=$(synapse list --plain 2>&1); then
  if printf '%s\n' "$list_output" | grep -q "No agents running."; then
    echo "No agents are currently running."
  else
    printf '%s\n' "$list_output"
  fi
else
  list_status=$?
  echo "synapse list --plain failed: $list_output" >&2
  exit "$list_status"
fi
