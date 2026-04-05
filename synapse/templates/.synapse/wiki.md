LLM Wiki rules:

- Write or update wiki content only when the user explicitly asks.
- Suggest wiki updates after meaningful design decisions, non-obvious bug fixes, new module understanding, option comparisons, or contradictions with existing pages.
- Do not suggest wiki updates for typo fixes, one-off debugging, or information already present.
- Use `wiki/sources/` for ingested source files and `wiki/pages/` for structured knowledge pages.
- Page filenames should follow `{type}-{kebab-case-title}.md`.
- Cross-reference pages with `[[wikilink]]`.
- Keep `wiki/index.md` updated with page summaries.
- Append operations to `wiki/log.md` with timestamp, operation, and details.
