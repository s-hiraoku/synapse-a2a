#!/bin/sh
# Aggregate team status: agents + task board.
# Usage: check_team_status.sh
set -e

echo "=== Agent Status ==="
if ! synapse list 2>/dev/null; then
  echo "(synapse list not available or no agents running)"
fi

echo ""
echo "=== Task Board ==="
if ! synapse tasks list 2>/dev/null; then
  echo "(task board not available)"
fi
