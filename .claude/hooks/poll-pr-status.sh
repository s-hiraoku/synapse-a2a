#!/usr/bin/env bash
# poll-pr-status.sh — Monitor PR mergeable status and CodeRabbit reviews
#
# Launched by check-ci-trigger.sh after git push / gh pr create.
# Reports merge conflicts and CodeRabbit review comments via systemMessage.

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
CODERABBIT_INITIAL_WAIT=90   # seconds before first CodeRabbit check
CODERABBIT_POLL_INTERVAL=30  # seconds between CodeRabbit polls
CODERABBIT_MAX_WAIT=300      # max wait for CodeRabbit review (5 minutes)
MERGEABLE_RETRY_WAIT=30      # seconds to wait when mergeable=null (GitHub computing)
MERGEABLE_MAX_RETRIES=3      # max retries for mergeable=null state
STATE_DIR="/tmp/.synapse-ci"
# ───────────────────────────────────────────────────────────────

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
SAFE_BRANCH="$(echo "$BRANCH" | tr '/' '-')"

CONFLICT_REPORTED_FILE="${STATE_DIR}/conflict-reported-${SAFE_BRANCH}"
REVIEW_REPORTED_PREFIX="${STATE_DIR}/review-reported-${SAFE_BRANCH}"

mkdir -p "$STATE_DIR"

# ── Helper: output systemMessage JSON ─────────────────────────
emit_message() {
  local msg="$1"
  local escaped
  escaped="$(printf '%s' "$msg" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')"
  echo "{\"systemMessage\": ${escaped}}"
}

# ── Helper: check if conflict was already reported ────────────
was_conflict_reported() {
  [[ -f "$CONFLICT_REPORTED_FILE" ]]
}

mark_conflict_reported() {
  echo "$(date +%s)" > "$CONFLICT_REPORTED_FILE"
}

# ── Helper: check if review was already reported ──────────────
was_review_reported() {
  local review_id="$1"
  [[ -f "${REVIEW_REPORTED_PREFIX}-${review_id}" ]]
}

mark_review_reported() {
  local review_id="$1"
  echo "$(date +%s)" > "${REVIEW_REPORTED_PREFIX}-${review_id}"
}

# ── Preflight: verify gh CLI ──────────────────────────────────
if ! command -v gh &>/dev/null; then
  exit 0
fi

if ! gh auth status &>/dev/null 2>&1; then
  exit 0
fi

# ── Step 1: Check if PR exists ────────────────────────────────
PR_JSON="$(gh pr view --json number,url,headRefName 2>/dev/null || echo "")"
if [[ -z "$PR_JSON" || "$PR_JSON" == "" ]]; then
  # No PR for this branch — nothing to monitor
  exit 0
fi

PR_NUM="$(echo "$PR_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('number', ''))
" 2>/dev/null || echo "")"

PR_URL="$(echo "$PR_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('url', ''))
" 2>/dev/null || echo "")"

if [[ -z "$PR_NUM" ]]; then
  exit 0
fi

# ── Step 2: Conflict check (mergeable state) ─────────────────
check_conflict() {
  local retries=0

  while [[ "$retries" -lt "$MERGEABLE_MAX_RETRIES" ]]; do
    local merge_json
    merge_json="$(gh pr view --json mergeable,mergeStateStatus 2>/dev/null || echo "{}")"

    local mergeable merge_state
    mergeable="$(echo "$merge_json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
m = d.get('mergeable', '')
# gh CLI returns 'MERGEABLE', 'CONFLICTING', or 'UNKNOWN'
print(str(m))
" 2>/dev/null || echo "")"

    merge_state="$(echo "$merge_json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('mergeStateStatus', ''))
" 2>/dev/null || echo "")"

    # GitHub still computing — wait and retry
    if [[ "$mergeable" == "UNKNOWN" || -z "$mergeable" ]]; then
      retries=$((retries + 1))
      sleep "$MERGEABLE_RETRY_WAIT"
      continue
    fi

    # Conflict detected
    if [[ "$mergeable" == "CONFLICTING" || "$merge_state" == "DIRTY" ]]; then
      if ! was_conflict_reported; then
        mark_conflict_reported
        emit_message "[PR Monitor] Merge conflict detected on PR #${PR_NUM} (${BRANCH}).

The PR has merge conflicts with the base branch. This must be resolved before CI can pass.

Please run /fix-conflict to attempt automatic conflict resolution."
      fi
      return 0
    fi

    # Clean — no conflict
    # Clear old conflict report if it existed (conflict was resolved)
    rm -f "$CONFLICT_REPORTED_FILE" 2>/dev/null || true
    return 0
  done

  # Timed out waiting for GitHub to compute mergeable state — silently skip
  return 0
}

# ── Step 3: CodeRabbit review check ──────────────────────────
classify_review_comments() {
  python3 << 'PYTHON_EOF'
import sys, json

data = json.load(sys.stdin)

# CodeRabbit emoji header markers (appear at start of comment body)
bug_headers = {"\u26a0\ufe0f potential issue", "\U0001f41b bug", "\U0001f512 security"}
style_headers = {"\U0001f9f9 nitpick", "\U0001f4dd style"}
suggestion_headers = {"\U0001f6e0\ufe0f refactor suggestion", "\U0001f4a1 suggestion", "\U0001f4d6 note"}

bug_keywords = {"bug", "error", "security", "vulnerability",
                "incorrect", "wrong", "crash", "leak", "null", "undefined",
                "race condition", "injection", "xss", "overflow",
                "missing check", "unhandled", "exception", "type error",
                "not defined"}
style_keywords = {"style", "format", "naming", "convention", "readability",
                  "import", "unused", "lint", "whitespace", "indentation",
                  "nit:", "nit ", "typo", "spelling", "consistent", "redundant"}

bugs, styles, suggestions = [], [], []

for item in data:
    body = item.get("body", "")
    body_lower = body.lower()
    path = item.get("path", "unknown")
    line = item.get("line", "?")
    first_line = body.split("\n")[0][:120]
    entry = f"{path}:{line} - {first_line}"

    # Check CodeRabbit emoji headers first (highest priority)
    if any(h in body_lower for h in bug_headers):
        bugs.append(entry)
    elif any(h in body_lower for h in style_headers):
        styles.append(entry)
    elif any(h in body_lower for h in suggestion_headers):
        suggestions.append(entry)
    # nit: prefix always means Style
    elif body_lower.lstrip().startswith("nit:") or body_lower.lstrip().startswith("nit "):
        styles.append(entry)
    # Bug keywords override suggestion keywords when both present
    elif any(kw in body_lower for kw in bug_keywords):
        bugs.append(entry)
    elif any(kw in body_lower for kw in style_keywords):
        styles.append(entry)
    else:
        suggestions.append(entry)

print(f"BUGS: {len(bugs)}")
print(f"STYLE: {len(styles)}")
print(f"SUGGESTIONS: {len(suggestions)}")
print("---")
for e in bugs:
    print(f"[BUG] {e}")
for e in styles:
    print(f"[STYLE] {e}")
for e in suggestions:
    print(f"[SUGGESTION] {e}")
PYTHON_EOF
}

check_coderabbit_review() {
  # Get repo owner/name
  local repo_full
  repo_full="$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null || echo "")"
  if [[ -z "$repo_full" ]]; then
    return 0
  fi

  # Wait for CodeRabbit to process (it typically takes 60-120s)
  sleep "$CODERABBIT_INITIAL_WAIT"

  local elapsed="$CODERABBIT_INITIAL_WAIT"

  while [[ "$elapsed" -lt "$CODERABBIT_MAX_WAIT" ]]; do
    # Check for CodeRabbit reviews
    local reviews
    reviews="$(gh api "repos/${repo_full}/pulls/${PR_NUM}/reviews" \
      --jq '[.[] | select(.user.login == "coderabbitai[bot]")] | sort_by(.submitted_at) | last' \
      2>/dev/null || echo "")"

    if [[ -z "$reviews" || "$reviews" == "null" ]]; then
      sleep "$CODERABBIT_POLL_INTERVAL"
      elapsed=$((elapsed + CODERABBIT_POLL_INTERVAL))
      continue
    fi

    # Extract review ID and state
    local review_id review_state review_body
    review_id="$(echo "$reviews" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('id', ''))
" 2>/dev/null || echo "")"

    review_state="$(echo "$reviews" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('state', ''))
" 2>/dev/null || echo "")"

    if [[ -z "$review_id" ]]; then
      sleep "$CODERABBIT_POLL_INTERVAL"
      elapsed=$((elapsed + CODERABBIT_POLL_INTERVAL))
      continue
    fi

    # Already reported this review
    if was_review_reported "$review_id"; then
      return 0
    fi

    # Fetch inline comments from CodeRabbit
    local comments
    comments="$(gh api "repos/${repo_full}/pulls/${PR_NUM}/comments" \
      --jq '[.[] | select(.user.login == "coderabbitai[bot]") | {path, line, body}]' \
      2>/dev/null || echo "[]")"

    local comment_count
    comment_count="$(echo "$comments" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(len(data))
" 2>/dev/null || echo "0")"

    mark_review_reported "$review_id"

    if [[ "$comment_count" -eq 0 && "$review_state" == "APPROVED" ]]; then
      emit_message "[PR Monitor] CodeRabbit reviewed PR #${PR_NUM} — approved with no comments."
      return 0
    fi

    if [[ "$comment_count" -eq 0 ]]; then
      # Review exists but no inline comments (summary only)
      emit_message "[PR Monitor] CodeRabbit reviewed PR #${PR_NUM} (${review_state}). No inline code comments."
      return 0
    fi

    # Classify comments
    local classification
    classification="$(echo "$comments" | classify_review_comments)"

    local bug_count style_count suggestion_count
    bug_count="$(echo "$classification" | grep '^BUGS:' | cut -d' ' -f2)"
    style_count="$(echo "$classification" | grep '^STYLE:' | cut -d' ' -f2)"
    suggestion_count="$(echo "$classification" | grep '^SUGGESTIONS:' | cut -d' ' -f2)"
    local details
    details="$(echo "$classification" | sed '1,/^---$/d')"

    # Build message
    local actionable_count=$((bug_count + style_count))
    local msg="[PR Monitor] CodeRabbit review on PR #${PR_NUM} (${BRANCH}):
- Bugs/Security: ${bug_count}
- Code Style: ${style_count}
- Suggestions: ${suggestion_count}

${details}"

    if [[ "$actionable_count" -gt 0 ]]; then
      msg="${msg}

Actionable issues found (${actionable_count} bugs + style). Please run /fix-review to address them."
    else
      msg="${msg}

No critical issues — only suggestions. Review them at your convenience."
    fi

    emit_message "$msg"
    return 0
  done

  # Timed out waiting for CodeRabbit — silent exit
  return 0
}

# ── Main: Run checks ─────────────────────────────────────────
# Run conflict check first (fast), then CodeRabbit (slow)
check_conflict
check_coderabbit_review

exit 0
