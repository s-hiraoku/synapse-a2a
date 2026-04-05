# LLM Wiki Schema

## Structure

- Directory layout:
  - `wiki/sources/` stores ingested source material.
  - `wiki/pages/` stores normalized wiki pages.
  - `wiki/index.md` lists pages with one-line summaries.
  - `wiki/log.md` records append-only operations.
  - `wiki/schema.md` documents these conventions.
- File naming: `{type}-{kebab-case-title}.md`
- Cross references use `[[wikilink]]` syntax and should point at page filenames without `.md`.

## Page Types

- `entity`
- `concept`
- `decision`
- `comparison`
- `synthesis`
- `learning`

## Frontmatter

Every page must include YAML frontmatter with:

- `type`
- `title`
- `created`
- `updated`
- `sources`
- `links`
- `confidence`
- `author`
- `source_files` (optional) — list of source code paths this page documents
- `source_commit` (optional) — git commit SHA when source_files were last reviewed

## Accumulation Rules

### Step 1

Only write or update wiki pages when the user explicitly asks.

### Step 2

Suggest wiki updates in these situations:

- Made a design decision: suggest a decision page.
- Fixed a non-obvious bug: suggest a concept page.
- Understood a new module structure: suggest an entity page.
- Compared two or more options: suggest a comparison page.
- Found a contradiction with an existing page: suggest an update.

Do not suggest wiki updates for typo fixes, one-off debugging, or information already captured in the wiki.

Suggestion format:

`Wiki suggestion: ... [y/n]`

## Index And Log Rules

- Add a new entry to `index.md` whenever a new page is created.
- Append to `log.md` with timestamp, operation, and details for each ingest or page update.
