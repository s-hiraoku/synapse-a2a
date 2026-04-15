---
name: release
description: Update version in pyproject.toml, plugin.json, and add changelog entry. This skill should be used when the user wants to bump the version number and update CHANGELOG.md. Triggered by /release or /version commands.
---

# Release Version Update

This skill updates the project version, plugin version, and changelog.

## Usage

```
/release [version-type-or-number] [description]
```

### Version Types

- `patch` - Increment patch version (e.g., 0.2.12 → 0.2.13)
- `minor` - Increment minor version (e.g., 0.2.12 → 0.3.0)
- `major` - Increment major version (e.g., 0.2.12 → 1.0.0)
- `X.Y.Z` - Set specific version (e.g., 1.0.0)

### Version Type is Optional — Auto-detect from Conventional Commits

If the version type is omitted, auto-detect the bump level from commits since the
latest tag using the standard [Semantic Versioning](https://semver.org/) +
[Conventional Commits](https://www.conventionalcommits.org/) mapping:

- **major** — any commit contains `BREAKING CHANGE:` in the body or `!` before the
  colon in the subject (e.g. `feat!:`, `refactor(core)!:`).
- **minor** — otherwise, at least one `feat:` (or `feat(scope):`) commit.
- **patch** — otherwise (fixes, chores, docs, etc.).

Procedure:

1. `git describe --tags --abbrev=0` → latest tag. If this command exits non-zero
   because the repository has no tags yet, fall back to the full history:
   `git log HEAD --pretty=%H%x00%s%x00%b` (initial commit → HEAD) and treat
   every commit as "unreleased".
2. Otherwise `git log <tag>..HEAD --pretty=%H%x00%s%x00%b` → commits to
   classify. (NUL-separated fields keep multi-line bodies parseable.)
3. If the range is empty, abort with `No commits since <tag>; nothing to release`.
4. Print the detected bump type with a one-line commit count summary, then continue
   with the normal bump flow. Do not prompt for confirmation — this keeps
   non-interactive workflows like `post-impl-codex` unblocked.

**Explicit argument always wins.** If the user passes `patch`/`minor`/`major`/`X.Y.Z`,
skip auto-detection entirely.

### Description (Optional)

If provided, use as the changelog entry description. Otherwise, analyze recent commits to generate the changelog.

## Workflow

### Step 1: Read Current Version

Read `pyproject.toml` and extract current version:

```python
# Look for: version = "X.Y.Z"
```

### Step 2: Calculate New Version

Based on the version type:

- **patch**: `major.minor.patch` → `major.minor.(patch+1)`
- **minor**: `major.minor.patch` → `major.(minor+1).0`
- **major**: `major.minor.patch` → `(major+1).0.0`
- **specific**: Use the provided version directly

Validate the new version is greater than current (unless forced).

### Step 3: Update pyproject.toml

Edit `pyproject.toml`:

```toml
version = "NEW_VERSION"
```

### Step 3.5: Update plugin.json

Edit `plugins/synapse-a2a/.claude-plugin/plugin.json`:

```json
"version": "NEW_VERSION",
```

**Important:** Keep plugin version in sync with pyproject.toml version.

### Step 3.6: Update site-docs version references

Update hardcoded version strings in GitHub Pages documentation:

1. `site-docs/getting-started/installation.md` — version example in verification section:
   ```
   You should see the version number (e.g., `NEW_VERSION`).
   ```

2. `site-docs/concepts/a2a-protocol.md` — Agent Card JSON example:
   ```json
   "version": "NEW_VERSION",
   ```

3. `site-docs/changelog.md` — add new version entry at the top of "Recent Highlights" (only if CHANGELOG.md was updated in Step 4-5).

4. `mkdocs.yml` — `repo_name` includes version displayed in GitHub Pages header:
   ```yaml
   repo_name: s-hiraoku/synapse-a2a vNEW_VERSION
   ```

**Important:** Keep site-docs version in sync with pyproject.toml version.

### Step 4: Generate Changelog with git-cliff

Use git-cliff to automatically generate the changelog entry from Conventional Commits:

```bash
# Preview the generated changelog
python scripts/generate_changelog.py --unreleased --tag vNEW_VERSION --dry-run

# Write to CHANGELOG.md
python scripts/generate_changelog.py --unreleased --tag vNEW_VERSION
```

### Step 5: Review and Adjust CHANGELOG.md

Review the generated entry and make manual adjustments if needed:
- Reword entries for clarity
- Add context or PR references if missing
- Remove noise entries that slipped through filters
- Ensure the date is correct: `## [NEW_VERSION] - YYYY-MM-DD`

If no git-cliff is available, or for a manual override, write the entry directly using Keep a Changelog format (see below).

### Step 6: Report Results

Display:
- Old version → New version
- Changelog entry preview
- Files modified

## Examples

### Bump patch version
```
/release patch
```

### Bump minor version with description
```
/release minor "Add new authentication system"
```

### Bump major version
```
/release major
```

### Set specific version
```
/release 1.0.0
```

### Shorthand
```
/version patch    # Same as /release patch
```

## File Locations

- Version: `pyproject.toml` (line with `version = "..."`)
- Plugin Version: `plugins/synapse-a2a/.claude-plugin/plugin.json` (line with `"version": "..."`)
- Site Docs Version: `site-docs/getting-started/installation.md`, `site-docs/concepts/a2a-protocol.md`
- Site Header Version: `mkdocs.yml` (`repo_name` field)
- Changelog: `CHANGELOG.md`
- Site Docs Changelog: `site-docs/changelog.md`

## Changelog Format

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes in existing functionality

### Fixed
- Bug fixes

### Removed
- Removed features

### Documentation
- Documentation updates

### Tests
- Test updates
```

Only include sections that have entries. Order sections as shown above.
