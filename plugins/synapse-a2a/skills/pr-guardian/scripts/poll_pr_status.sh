#!/usr/bin/env bash
# poll_pr_status.sh — One-shot PR health check.
# Exits with a JSON blob on stdout describing the current state.
# Exit codes: 0 = produced status, 1 = fatal error (no PR, gh missing, etc.)

set -euo pipefail

PORT="${1:-}"

# --- helpers -----------------------------------------------------------
die() { echo "ERROR: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh CLI not found"
gh auth status >/dev/null 2>&1 || die "gh CLI not authenticated"

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || die "not in a git repo"

PR_JSON=$(gh pr view --json number,url,mergeable,mergeStateStatus 2>/dev/null) \
  || die "no PR found for branch $BRANCH"

PR_NUMBER=$(echo "$PR_JSON" | jq -r '.number')
MERGEABLE=$(echo "$PR_JSON" | jq -r '.mergeable')
MERGE_STATE=$(echo "$PR_JSON" | jq -r '.mergeStateStatus')

# --- CI checks ---------------------------------------------------------
CHECKS_JSON=$(gh pr checks --json name,state,conclusion 2>/dev/null || echo "[]")

TOTAL=$(echo "$CHECKS_JSON" | jq 'length')
PASSED=$(echo "$CHECKS_JSON" | jq '[.[] | select(.conclusion == "SUCCESS" or .conclusion == "NEUTRAL" or .conclusion == "SKIPPED")] | length')
FAILED=$(echo "$CHECKS_JSON" | jq '[.[] | select(.conclusion == "FAILURE" or .conclusion == "CANCELLED" or .conclusion == "TIMED_OUT" or .conclusion == "ACTION_REQUIRED")] | length')
RUNNING=$(echo "$CHECKS_JSON" | jq '[.[] | select(.state == "IN_PROGRESS" or .state == "QUEUED" or .state == "PENDING" or .state == "WAITING")] | length')

# --- Merge conflict state -----------------------------------------------
HAS_CONFLICT=false
if [[ "$MERGEABLE" == "CONFLICTING" ]] || [[ "$MERGE_STATE" == "DIRTY" ]]; then
  HAS_CONFLICT=true
fi

# --- CodeRabbit review ---------------------------------------------------
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null || echo "")
CR_COMMENTS=0
if [[ -n "$REPO" ]]; then
  CR_COMMENTS=$(gh api "repos/$REPO/pulls/$PR_NUMBER/comments" \
    --jq '[.[] | select(.user.login == "coderabbitai[bot]")] | length' 2>/dev/null || echo "0")
fi

# --- Output JSON --------------------------------------------------------
cat <<EOF
{
  "branch": "$BRANCH",
  "pr_number": $PR_NUMBER,
  "checks_total": $TOTAL,
  "checks_passed": $PASSED,
  "checks_failed": $FAILED,
  "checks_running": $RUNNING,
  "has_conflict": $HAS_CONFLICT,
  "coderabbit_comments": $CR_COMMENTS,
  "all_green": $(if [[ "$HAS_CONFLICT" == "false" ]] && [[ "$FAILED" -eq 0 ]] && [[ "$RUNNING" -eq 0 ]] && [[ "$CR_COMMENTS" -eq 0 ]] && [[ "$TOTAL" -gt 0 ]]; then echo "true"; else echo "false"; fi)
}
EOF
