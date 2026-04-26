---
name: dev-issue
license: MIT
description: >-
  Bootstrap a new GitHub issue implementation in one command: fetch the issue
  body, gather cross-references and code hotspots, infer a branch prefix and
  slug, generate a structured task brief, create a fresh branch from latest
  main, and (by default) spawn a codex agent to implement it. Triggered by
  /dev-issue <number>. Use this skill when starting work on a new issue that
  follows the standard issue → codex spawn → review → PR pipeline.
---

# /dev-issue — Bootstrap an issue implementation

Compresses the manual `gh issue view` → grep → handwritten brief → branch →
`synapse spawn` ritual into a single slash command. The skill is a procedural
guide for Claude to execute, not an automation script — Claude reads the
issue, reasons about scope, and constructs the brief.

## Usage

```
/dev-issue <number>            # default: spawn codex with the brief
/dev-issue <number> --solo     # don't spawn; parent (you) implements
/dev-issue <number> --dry-run  # generate brief only; no branch, no spawn
```

`<number>` accepts:
- bare integer: `467`
- hash form: `#467`
- full URL: `https://github.com/s-hiraoku/synapse-a2a/issues/467`

## Steps Claude must follow

### 1. Validate input and parse the issue number

Accept `123`, `#123`, or a full GitHub issue URL. Extract the integer. If the
input does not match any of these forms, abort with:

```
/dev-issue: cannot parse '<input>'. Expected: <num>, #<num>, or full issue URL.
```

### 2. Fetch state in parallel

Run these three calls **in parallel** (one Bash batch with `&` or three
separate parallel tool calls):

```bash
gh issue view <num> --json number,title,body,labels,state,comments
gh issue list --state closed --search "#<num> in:body" --limit 5
git fetch origin main && git rev-parse origin/main
```

Parse the JSON outputs. Save the issue body, label names, state, and the SHA
of `origin/main` for later steps.

### 3. Issue triage

- If `state == "CLOSED"`: abort. Print the closure date and the closer's
  comment. Do not create a branch.
- If labels contain `architecture` or `discussion`: warn the user that this
  issue typically needs design discussion before implementation, and **ask**
  whether to proceed. Do not auto-continue.
- If the issue body is empty: abort with a request for the user to add
  context to the issue first.

### 4. Discover related code (hotspots)

Heuristically grep the repo for:

- File paths mentioned in the issue body. Regex: `synapse/[a-z_/]+\.py`,
  `tests/[a-z_/]+\.py`, etc. (extend per repo layout).
- Symbols enclosed in backticks in the issue body (function names, env vars,
  constants).

For each unique file or symbol match:

```bash
git log --oneline -5 -- <file>
```

Build a "Code hotspots" section listing each file with its 1-2 most recent
relevant commits (subject + SHA). Cap at the top 6 hotspots to keep the
brief readable.

### 5. Discover related closed PRs

```bash
gh pr list --state merged --search "<num>" --json number,title,mergedAt --limit 5
```

These are usually implementation precedents (e.g., "PROCESSING wait" for a
"READY delay" issue). Include them in the brief's `前提:` section so the
implementing agent treats them as the symmetric reference.

### 6. Determine branch prefix

Infer from issue labels (first match wins):

| Label                 | Prefix       |
|-----------------------|--------------|
| `bug`                 | `fix/`       |
| `enhancement`         | `feat/`      |
| `feature`             | `feat/`      |
| `chore`               | `chore/`     |
| `refactor`            | `refactor/`  |
| `docs` / `documentation` | `docs/`   |
| (no match)            | `feat/`      |

### 7. Generate slug from title

Goal: a short, lowercased, hyphenated slug derived from the issue title.

- If the title contains ASCII words: take the first 4-6 meaningful tokens
  (skip articles like "a/the/of"), lowercase, hyphenate. Example:
  `"Delay send to READY agents"` → `delay-send-to-ready`.
- If the title is fully Japanese or otherwise non-ASCII: fall back to a
  short English summary derived from labels + the first sentence of the
  body. If even that is unclear, use the prefix-only form `<prefix>/<num>`
  and let the user rename later.

Final branch name: `<prefix>/<slug>-<num>`. Example: `feat/delay-send-to-ready-467`.

### 8. Construct the task brief

Write to `/tmp/issue<num>-task.md` using the **Brief Template** below
(literal embed). Fill placeholders with the data gathered in steps 2-7.
The template uses Japanese for consistency with the existing handwritten
briefs in the repo (`/tmp/issue467-task.md` etc.) — switch to English if
the user has indicated English-language briefs.

### 9. Create the branch

Only execute this step in **default** mode and `--solo` mode (skip in
`--dry-run`):

```bash
git fetch origin main
git checkout main
git pull --ff-only origin main
git checkout -b <prefix>/<slug>-<num>
```

**Idempotency**: before creating, run `git rev-parse --verify <branch>
2>/dev/null`. If the branch already exists locally, abort with:

```
/dev-issue: branch '<branch>' already exists. Delete it (git branch -D),
or re-run with --resume (not yet implemented) to continue prior work.
```

Do **not** delete the branch automatically — that is a destructive action
the user must perform.

### 10. Spawn or skip

Depending on the flag:

- **default**:
  ```bash
  synapse spawn codex --task-file /tmp/issue<num>-task.md --notify
  ```
  Capture the spawned agent's name/ID from the output for the summary.

- **`--solo`**: skip spawn. Print:
  ```
  /dev-issue: branch and brief ready. Begin implementation in this session.
  ```

- **`--dry-run`**: skip branch creation (step 9) and spawn. Print:
  ```
  /dev-issue: dry run. Brief written to /tmp/issue<num>-task.md.
  Review and re-run without --dry-run to create the branch and spawn.
  ```

### 11. Output a summary

Print a concise summary to stdout (not a synapse send — this is for the
human user invoking the slash):

```
✓ /dev-issue <num> ready
  Title:   <issue title>
  Branch:  <prefix>/<slug>-<num>   (created from origin/main @ <sha>)
  Brief:   /tmp/issue<num>-task.md
  Spawned: <codex agent name>      (omit if --solo or --dry-run)
  Next:    Wait for codex plan reply, or begin implementation.
```

## Brief Template

This is the literal template Claude uses in step 8. Replace every `{{...}}`
placeholder with the corresponding value gathered earlier. Sections may be
omitted only if the corresponding data is empty (e.g., no merged precedent
PRs → drop the `前提:` section).

```markdown
# Task: Issue #{{num}} を実装してください — {{short_title}}

あなたは Codex developer agent です。Issue #{{num}}
({{issue_url}}) を実装してください。Claude (parent) が伴走してレビュー /
commit / PR 作成を担当します。

## 作業ブランチ

`{{branch}}` は parent (Claude) 側で **最新 main から作成済み** です。**同じ
ディレクトリ** (`{{repo_path}}`) で作業してください。`git checkout` は **しない**
でください。

## 前提: 関連 merge 済 PR

{{#each related_prs}}
- PR #{{number}} ({{title}}) — {{mergedAt}} — 参照実装 / 対称ケース
{{/each}}

(該当なしならこのセクション削除)

## Issue の核心

{{issue_body_summary}}

## 採用方針

{{recommended_approach}}

(Claude が issue 本文と関連 PR から推論。複数案ある場合は採用案 + 理由 + 不採用案
の理由を併記。)

## 実装スポット

{{#each hotspots}}
- `{{file}}` — {{recent_commit_subject}} ({{sha}})
{{/each}}

(具体的な diff hint があれば code block で例示)

## スコープ制約

{{#each scope_constraints}}
- ✅ {{constraint}}
{{/each}}

## テスト (Test-First)

新規ファイル `tests/test_<feature>_<num>.py` を作成。既存 `tests/test_a2a_*` の
conftest/fixture pattern に合わせてください。

最小ケース ({{推奨3-6個}}):

{{#each test_cases}}
{{index}}. **`{{name}}`**: {{description}}
{{/each}}

## 進め方

1. **まず方針 reply** (200 単語以内) を `synapse reply <incoming-msg-id>` で:
   - 上の方針で OK か
   - 別案 / 懸念があれば
2. parent (Claude) から OK を返したら **Test-First で red phase**
3. 実装 (green)
4. focused 確認: `uv run pytest tests/test_<feature>_<num>.py -q`
5. mypy clean: `uv run mypy synapse/`
6. CHANGELOG `[Unreleased]` に Added/Changed のいずれかで記載
7. 完了 reply で 触ったファイル + テスト結果

## 完了時の報告

- 触ったファイル一覧
- 新規テスト数 + green な focused suite テスト数
- 実装の判断点
- mypy 結果
- CHANGELOG `[Unreleased]` 追記済か

## 参考

{{#each references}}
- {{ref}}
{{/each}}
```

## Notes

- **Idempotency**: re-running `/dev-issue <num>` after the branch exists
  must abort cleanly (step 9). Do not destroy work.
- **Conflict avoidance**: brief generation never modifies tracked files.
  Only `/tmp/issue<num>-task.md` is written. Steps 1-8 are read-only.
- **No auto-memory writes**: this skill produces ephemeral task state.
  It must not call `synapse memory save` or `synapse wiki ingest` —
  those are the implementing agent's decision after the work is done.
- **`gh issue view` JSON**: parse via `jq` in shell or `json.loads` if
  invoked from a Python helper. Skill execution is by Claude, so reading
  the JSON output of a Bash tool call and reasoning about it is fine —
  full automation is not required.
- **No unit tests**: this skill is a procedural document, not code. The
  `--dry-run` flag exists to verify behavior without side effects. Self-
  review by reading the SKILL.md is the correctness check.
- **Branch safety in shared dirs**: if multiple agents share the working
  directory, prefer `git worktree add` over `git checkout` to avoid
  disrupting peers. The skill defaults to `git checkout` because the
  common case is a single-agent invocation; switch to worktree manually
  when collaborating.

## Future work

- `--resume <branch>`: pick up an existing branch instead of aborting.
- `gh skill` migration: once `gh skill` (GitHub CLI v2.90+) becomes the
  canonical skill management tool, replace the 3-mirror layout with a
  single `gh skill install` step. Until then, keep the
  `.agents` ↔ `.claude` symlink + `plugins/` copy structure.
- YAML workflow extraction: once this skill stabilizes, consider
  extracting steps 2-7 into a `synapse workflow` for parts that don't
  need LLM reasoning. Steps 4 (hotspot grep) and 8 (brief construction)
  will likely stay LLM-driven.
