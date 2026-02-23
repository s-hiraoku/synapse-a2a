#!/usr/bin/env bash
# poll-ci.sh — Poll GitHub Actions CI and report results via systemMessage
#
# Usage: poll-ci.sh [<commit-sha>]
#   If no SHA given, uses HEAD.
#
# Outputs JSON with "systemMessage" key on completion.
# Manages fix counters in /tmp/.synapse-ci/ per branch.

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
INITIAL_WAIT=30        # seconds before first poll (let GitHub register the run)
POLL_INTERVAL=30       # seconds between polls
MAX_WAIT=600           # total max wait (10 minutes)
STATE_DIR="/tmp/.synapse-ci"
# ───────────────────────────────────────────────────────────────

COMMIT_SHA="${1:-$(git rev-parse HEAD 2>/dev/null || echo "")}"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"

# Sanitize branch name for filename
SAFE_BRANCH="$(echo "$BRANCH" | tr '/' '-')"
FIX_COUNT_FILE="${STATE_DIR}/fix-count-${SAFE_BRANCH}"
LAST_REPORTED_FILE="${STATE_DIR}/last-reported-${SAFE_BRANCH}"

mkdir -p "$STATE_DIR"

# ── Helper: read fix counter ──────────────────────────────────
get_fix_count() {
  if [[ -f "$FIX_COUNT_FILE" ]]; then
    cat "$FIX_COUNT_FILE"
  else
    echo "0"
  fi
}

increment_fix_count() {
  local count
  count="$(get_fix_count)"
  echo $((count + 1)) > "$FIX_COUNT_FILE"
}

reset_fix_count() {
  echo "0" > "$FIX_COUNT_FILE"
}

# ── Helper: check if run was already reported ─────────────────
was_reported() {
  local run_id="$1"
  if [[ -f "$LAST_REPORTED_FILE" ]] && grep -qF "$run_id" "$LAST_REPORTED_FILE"; then
    return 0
  fi
  return 1
}

mark_reported() {
  local run_id="$1"
  echo "$run_id" > "$LAST_REPORTED_FILE"
}

# ── Helper: decide message based on fix count ─────────────────
# TODO(human): Implement the fix-count decision logic
# Based on $fix_count, construct the appropriate systemMessage:
#   - If fix_count < 2: increment counter, suggest /fix-ci
#   - If fix_count >= 2: suggest manual intervention
# Consider: should the message include the failed log excerpt?
#           should priority escalate with each retry?
#           what info does the developer need to decide next steps?
decide_message() {
  local fix_count="$1" branch="$2" sha="$3" run_name="$4" run_id="$5" failed_log="$6"

  if [[ "$fix_count" -lt 2 ]]; then
    increment_fix_count
    emit_message "[CI Monitor] CI FAILED on ${branch} (${sha}). Workflow: ${run_name}. Attempt $((fix_count + 1))/2.

Failed log (excerpt):
${failed_log}

Please run /fix-ci to diagnose and fix the failure."
  else
    emit_message "[CI Monitor] CI FAILED on ${branch} (${sha}). Workflow: ${run_name}. Auto-fix attempted ${fix_count} times without success.

Failed log (excerpt):
${failed_log}

Manual intervention required. Run 'gh run view ${run_id} --log-failed' for full details."
  fi
}

# ── Helper: output systemMessage JSON ─────────────────────────
emit_message() {
  local msg="$1"
  # Escape for JSON (newlines, quotes, backslashes)
  local escaped
  escaped="$(printf '%s' "$msg" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')"
  echo "{\"systemMessage\": ${escaped}}"
}

# ── Preflight: verify gh CLI is available and authenticated ───
if ! command -v gh &>/dev/null; then
  emit_message "[CI Monitor] gh CLI not found. Install it to enable CI monitoring."
  exit 0
fi

if ! gh auth status &>/dev/null 2>&1; then
  emit_message "[CI Monitor] gh CLI not authenticated. Run 'gh auth login' to enable CI monitoring."
  exit 0
fi

# ── Initial wait ──────────────────────────────────────────────
sleep "$INITIAL_WAIT"

# ── Polling loop ──────────────────────────────────────────────
elapsed="$INITIAL_WAIT"

while [[ "$elapsed" -lt "$MAX_WAIT" ]]; do
  # Get the latest run for this commit (or branch if no commit match)
  run_json="$(gh run list \
    --branch "$BRANCH" \
    --limit 1 \
    --json databaseId,status,conclusion,headSha,name,updatedAt \
    2>/dev/null || echo "[]")"

  # Parse run info
  run_id="$(echo "$run_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[0]['databaseId'] if data else '')
" 2>/dev/null || echo "")"

  run_status="$(echo "$run_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[0]['status'] if data else '')
" 2>/dev/null || echo "")"

  run_conclusion="$(echo "$run_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[0].get('conclusion') or '' if data else '')
" 2>/dev/null || echo "")"

  run_name="$(echo "$run_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[0].get('name', '') if data else '')
" 2>/dev/null || echo "")"

  run_sha="$(echo "$run_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[0].get('headSha', '')[:8] if data else '')
" 2>/dev/null || echo "")"

  # No run found yet — keep waiting
  if [[ -z "$run_id" ]]; then
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
    continue
  fi

  # Skip if already reported
  if was_reported "$run_id"; then
    exit 0
  fi

  # Run still in progress — keep polling
  if [[ "$run_status" == "in_progress" || "$run_status" == "queued" || "$run_status" == "waiting" ]]; then
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
    continue
  fi

  # ── Run completed — build the report ──────────────────────
  mark_reported "$run_id"

  case "$run_conclusion" in
    success)
      reset_fix_count
      emit_message "[CI Monitor] CI PASSED on ${BRANCH} (${run_sha}). Workflow: ${run_name}. All checks green."
      exit 0
      ;;
    cancelled)
      emit_message "[CI Monitor] CI CANCELLED on ${BRANCH} (${run_sha}). Workflow: ${run_name}. The run was cancelled."
      exit 0
      ;;
    failure)
      # Fetch failed job logs (truncate to avoid huge output)
      failed_log="$(gh run view "$run_id" --log-failed 2>/dev/null | head -80 || echo "(could not retrieve logs)")"

      fix_count="$(get_fix_count)"
      decide_message "$fix_count" "$BRANCH" "$run_sha" "$run_name" "$run_id" "$failed_log"
      exit 0
      ;;
    *)
      emit_message "[CI Monitor] CI finished with unexpected conclusion '${run_conclusion}' on ${BRANCH} (${run_sha}). Check manually: gh run view ${run_id}"
      exit 0
      ;;
  esac
done

# ── Timeout ───────────────────────────────────────────────────
emit_message "[CI Monitor] Timed out waiting for CI on ${BRANCH} after ${MAX_WAIT}s. Check manually: gh run list --branch ${BRANCH}"
exit 0
