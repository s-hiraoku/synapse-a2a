---
name: parallel-docs-simplify-sync
description: >-
  Runs synapse-docs, code-simplifier, sync-plugin-skills, and github-pages-sync
  in parallel for synapse-a2a development workflows. Use when you need doc
  updates, code simplification, plugin skill sync, and site-docs sync at the
  same time.
commands:
  - /parallel-docs-simplify-sync
---

# Parallel Docs Simplify Sync

Coordinate four independent skills in parallel using the **Task tool**:

- `synapse-docs` — documentation updates
- `code-simplifier` — targeted refactors for readability
- `sync-plugin-skills` — plugin skill synchronization
- `github-pages-sync` — GitHub Pages site synchronization

> **Dev-only skill.** Lives in `.agents/skills/` (not deployed to `plugins/`).
> This is a development orchestration tool, not a user-facing plugin skill.

## When To Use

- Code and documentation were changed in the same task.
- Simplification or refactor cleanup is needed while keeping docs in sync.
- Plugin-skill synchronization should happen in the same run.
- GitHub Pages site (`site-docs/`) needs to reflect code or doc changes.

## Parallel Execution Workflow

### Step 1: Split into four independent sub-tasks

Define one clear objective and divide it:

| Track | Skill | Typical Scope |
|-------|-------|---------------|
| Docs | `synapse-docs` | README.md, guides/, CLAUDE.md |
| Simplify | `code-simplifier` | Recently changed `.py` files |
| Sync | `sync-plugin-skills` | plugins/synapse-a2a/skills/ |
| Pages | `github-pages-sync` | site-docs/ |

### Step 2: Launch four Task tool calls in a single message

Use the **Task tool** with four parallel invocations in one response.
Each Task call should use the prompt template below.

```
# Example: four parallel Task tool calls
Task(subagent_type="general-purpose", prompt="[synapse-docs prompt]")
Task(subagent_type="code-simplifier:code-simplifier", prompt="[simplify prompt]")
Task(subagent_type="general-purpose", prompt="[sync-plugin-skills prompt]")
Task(subagent_type="general-purpose", prompt="[github-pages-sync prompt]")
```

### Step 3: Wait for all four outputs

All four tasks return independently. Collect results before merging.

### Step 4: Merge and resolve conflicts

Apply changes from each track. If conflicts arise, follow the
**Conflict Resolution Rules** below. Run tests after merging.

### Step 5: Retry failed tracks only

If any track fails, rerun only that track — do not re-execute all four.

## Task Prompt Template

Use this for each parallel track:

```text
Goal: <shared task goal>
Track: <synapse-docs | code-simplifier | sync-plugin-skills | github-pages-sync>
Scope: <files/areas>
Constraints:
- Keep behavior unchanged unless explicitly requested
- Keep style consistent with repository conventions
- Do NOT touch files outside your track's scope
Deliverable:
- Concise change summary and touched files
```

## Conflict Resolution Rules

`synapse-docs` and `sync-plugin-skills` can both modify files under
`plugins/synapse-a2a/skills/`. When this happens:

1. **sync-plugin-skills wins** for skill SKILL.md content (it reads the
   latest implementation and generates accurate skill instructions).
2. **synapse-docs wins** for README.md, guides/, and non-skill documentation.
3. If both modified the same SKILL.md, take `sync-plugin-skills` output and
   verify it against the doc changes from `synapse-docs`. Manually reconcile
   if descriptions diverge.
4. `code-simplifier` should never conflict — it only touches `.py` files.
5. `github-pages-sync` only modifies files under `site-docs/` and `mkdocs.yml`,
   so it does not conflict with `synapse-docs` or `sync-plugin-skills` which
   target different directories. If both `synapse-docs` and `github-pages-sync`
   modify `mkdocs.yml`, `github-pages-sync` takes priority since it owns the
   site build configuration.

## Completion Checklist

- [ ] All four tracks completed: `synapse-docs`, `code-simplifier`, `sync-plugin-skills`, `github-pages-sync`
- [ ] Conflicts resolved per rules above
- [ ] `pytest` passes
- [ ] `uv run mkdocs build --strict` passes (if Pages track ran)
- [ ] Final diff is coherent and reviewable
