---
name: fix-review
description: Automatically address CodeRabbit review comments on the current PR. Fetches inline comments from coderabbitai[bot], classifies them by severity (bug/style/suggestion), applies fixes for actionable issues, verifies locally, and pushes. Use when CodeRabbit posts review comments.
---

# Fix CodeRabbit Review Comments

This skill automatically addresses CodeRabbit review comments by fetching inline comments, classifying their severity, **verifying each finding against the current code**, applying targeted fixes, and pushing the result.

## Usage

```
/fix-review           # Auto-fix actionable CodeRabbit comments
/fix-review --dry-run # Show what would be fixed without applying
/fix-review --all     # Also attempt to fix suggestions and nitpicks (not just bugs/style)
```

## Workflow

### Step 1: Fetch PR and Review Data

Get the current PR details:

```bash
gh pr view --json number,url,headRefName
```

If no PR exists, report "No PR found for the current branch." and stop.

Get the repo identifier:

```bash
gh repo view --json nameWithOwner -q '.nameWithOwner'
```

### Step 2: Fetch CodeRabbit Reviews and Comments

Fetch all reviews from CodeRabbit:

```bash
gh api "repos/<owner>/<repo>/pulls/<pr_number>/reviews" \
  --jq '[.[] | select(.user.login == "coderabbitai[bot]")]'
```

Fetch inline comments (including outside-diff and nitpick comments):

```bash
gh api "repos/<owner>/<repo>/pulls/<pr_number>/comments" \
  --jq '[.[] | select(.user.login == "coderabbitai[bot]") | {id, path, line, original_line, diff_hunk, body, created_at, subject_type}]'
```

Also fetch PR-level review body comments (CodeRabbit often posts a summary review with actionable items in the review body itself):

```bash
gh api "repos/<owner>/<repo>/pulls/<pr_number>/reviews" \
  --jq '[.[] | select(.user.login == "coderabbitai[bot]" and .body != "") | {id, body, state}]'
```

If no CodeRabbit reviews or comments exist, report "No CodeRabbit review comments found on this PR." and stop.

### Step 3: Parse Comment Sections

CodeRabbit structures its review body into distinct sections. Parse each section:

- **Inline comments** (`In \`@file\`:` blocks): These reference specific files and line ranges
- **Outside diff comments**: Comments about code not in the current diff but affected by changes
- **Nitpick comments**: Low-priority style/improvement suggestions
- **Duplicate comments**: Comments that repeat across review rounds (may already be fixed)

For each comment, extract:
- **File path** (from `@file` reference or inline comment path)
- **Line range** (approximate — verify against current code)
- **Referenced symbols** (function names, class names, CSS selectors mentioned)
- **The specific ask** (what change is requested)

### Step 4: Verify Each Finding Against Current Code

**CRITICAL STEP — Do not skip this.** For each comment:

1. **Read the referenced file** at the specified path
2. **Locate the exact code** referenced by the comment using:
   - Line numbers (may have shifted — use symbol names as anchors)
   - Function/class/variable names mentioned in the comment
   - Code snippets quoted in the comment body
3. **Confirm the issue still exists** in the current code:
   - If the code has already been fixed (e.g., by a previous commit), mark as "already resolved" and skip
   - If the referenced code no longer exists (refactored away), mark as "no longer applicable" and skip
   - If the issue exists as described, proceed to classification
4. **Check for consistency with implementation** — when a comment says "option X should be Y", verify by reading the actual argparse/CLI definition, not just the referenced doc line. Cross-reference:
   - CLI option names: check `synapse/cli.py` argparse definitions
   - Function signatures: check the actual function definition
   - API endpoints: check the server route definitions
   - CSS classes: check both `.css` and `.js` files that reference them

### Step 5: Classify Comments

For each **verified** comment, classify into categories:

**Priority rule**: If a comment contains a ` ```suggestion ` code block, it is always auto-fixable regardless of category — apply the suggestion directly. Classification then only affects reporting priority.

**Bug/Security** (auto-fix):
- CodeRabbit header markers: `⚠️ Potential issue`, `🐛 Bug`, `🔒 Security`
- Keywords in body (case-insensitive): `bug`, `error`, `security`, `vulnerability`, `incorrect`, `wrong`, `crash`, `leak`, `null`, `undefined`, `race condition`, `injection`, `xss`, `overflow`, `missing check`, `unhandled`, `exception`, `type error`, `not defined`
- Pattern: comment describes *what is broken*, not what could be improved
- Edge case: if body contains both a bug keyword AND `consider`/`might want to`, classify as Bug (err on side of safety)

**Inconsistency** (auto-fix):
- Comments about documentation/code mismatch (e.g., docs say `--id` but CLI uses `--card-id`)
- Comments about DOM structure inconsistency (e.g., meta inside `<pre>` in one renderer but outside in another)
- Comments about naming differences between files
- **Always verify both sides**: read both the doc AND the implementation to determine which is correct

**Style** (auto-fix):
- CodeRabbit header markers: `🧹 Nitpick`, `📝 Style`
- Keywords in body: `style`, `format`, `naming`, `convention`, `readability`, `import`, `unused`, `lint`, `whitespace`, `indentation`, `nit:`, `nit `, `typo`, `spelling`, `consistent`, `redundant`
- Delegation: if the issue is about Python formatting/linting (import order, unused imports, line length), delegate to `ruff check --fix` and `ruff format` rather than manual editing
- Edge case: `nit:` prefix always means Style regardless of other keywords

**Suggestion** (report only, unless `--all` flag):
- CodeRabbit header markers: `🛠️ Refactor suggestion`, `💡 Suggestion`, `📖 Note`
- Keywords in body: `consider`, `might want to`, `could be`, `alternative`, `refactor`, `performance`, `optimization`, `simplify`, `extract`, `pattern`, `architecture`
- Default: any comment that does not match Bug/Security or Style patterns falls here
- Edge case: `suggest` alone is NOT a Style keyword — it goes to Suggestion unless a `suggestion` code block is present (which makes it auto-fixable)

### Step 6: Apply Fixes

For each actionable comment (Bug/Security, Inconsistency, and Style categories):

1. Read the file at the specified path
2. Locate the exact code using symbol names (not just line numbers, which shift)
3. Analyze the comment body for:
   - **Code suggestion blocks** (` ```suggestion ` markers): Apply the suggested code directly
   - **Descriptive feedback**: Understand the issue and implement an appropriate fix
4. Apply the fix to the file
5. **After each fix, verify the change is correct** — re-read the modified code to confirm it matches the intent

For Style issues that ruff can handle:

```bash
ruff check --fix synapse/ tests/
ruff format synapse/ tests/
```

If `--dry-run` flag is provided: show each comment with its classification and proposed fix, but do NOT modify files, commit, or push.

### Step 7: Local Verification

After applying all fixes:

```bash
ruff check synapse/ tests/
```

```bash
ruff format synapse/ tests/ --check
```

```bash
pytest
```

If any check fails after fixing:
- Attempt one targeted correction
- If it still fails, revert the problematic fix and report it as unresolvable

### Step 8: Commit and Push

Stage and commit the changes:

```bash
git add -u
```

```bash
git commit -m "fix: address CodeRabbit review comments

Resolved:
- <summary of each fixed comment>

Reported (not auto-fixed):
- <summary of suggestion-only comments>"
```

```bash
git push
```

### Step 9: Report Summary

Report what was done:
- Number of comments addressed (by category: bug, inconsistency, style, suggestion)
- Number of comments verified as already resolved or not applicable
- Files modified
- Comments left as suggestions (not auto-fixed)
- Whether all local checks pass
- Link to the PR for manual review of remaining suggestions

### Error Handling

- **No PR found**: Report and stop
- **No CodeRabbit comments**: Report and stop
- **gh API errors**: Report the error and suggest manual review
- **Fix causes test failure**: Revert that specific fix, report the issue
- **Never force-push**: Always use `git push`
- **Max 1 fix cycle**: One pass of fixes. If issues remain, report for manual handling

## Safety

- Only fixes Bug/Security, Inconsistency, and Style categories by default
- Suggestions are reported but not auto-fixed (unless `--all`)
- **Every finding is verified against current code before fixing**
- Cross-references implementation (argparse, routes, etc.) when fixing doc/code mismatches
- Local verification before pushing
- One retry per failed fix, then revert
- CodeRabbit's `profile: "chill"` means suggestions are advisory, not blocking
