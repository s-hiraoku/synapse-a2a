# Release Guide

This document describes how to release a new version of synapse-a2a to PyPI.

## Overview

Releases are fully automated via GitHub Actions. When a `pyproject.toml` version change is merged to `main`, the following chain runs automatically:

1. **`auto-release.yml`** — Detects version bump, creates git tag (`v*`) and GitHub Release with changelog
2. **`publish.yml`** — Triggered by the new tag, builds and publishes to PyPI (Trusted Publisher)
3. **`update-installers.yml`** — Triggered by the new tag, creates PR to update Homebrew formula and Scoop manifest

## Release Steps

### 1. Update Version and Changelog

Generate the changelog entry using git-cliff, then update the version in `pyproject.toml`:

```bash
# Generate changelog for the new version (preview first)
python scripts/generate_changelog.py --unreleased --tag vX.Y.Z --dry-run

# If it looks good, write to CHANGELOG.md
python scripts/generate_changelog.py --unreleased --tag vX.Y.Z

# Review and adjust the generated entry if needed
# (e.g., reword entries, add context, remove noise)
```

Then update the version number in `pyproject.toml`:

```toml
[project]
name = "synapse-a2a"
version = "X.Y.Z"  # Update this
```

### 2. Create a Pull Request

Create a PR with the version bump and changelog:

```bash
git checkout -b chore/bump-version-X.Y.Z
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version to X.Y.Z"
git push origin chore/bump-version-X.Y.Z
gh pr create --title "chore: bump version to X.Y.Z" --body "Update version for release"
```

### 3. Merge the PR

After CI passes and review is complete, merge the PR to main.

### 4. Verify Release (Automatic)

After merging, the automation chain runs. Verify each step:

1. **Tag & Release**: https://github.com/s-hiraoku/synapse-a2a/actions/workflows/auto-release.yml
2. **PyPI publish**: https://github.com/s-hiraoku/synapse-a2a/actions/workflows/publish.yml
3. **Installers PR**: https://github.com/s-hiraoku/synapse-a2a/actions/workflows/update-installers.yml
4. **PyPI package**: https://pypi.org/project/synapse-a2a/

## Important Notes

- **Changelog required**: `auto-release.yml` extracts release notes from `CHANGELOG.md` using `scripts/extract_changelog.py`. The version must have a matching `## [X.Y.Z] - YYYY-MM-DD` section. Use `python scripts/generate_changelog.py --unreleased --tag vX.Y.Z` to generate this section from Conventional Commits.
- **Idempotent**: If the tag already exists (e.g., manual creation), `auto-release.yml` skips. No duplicate tags or releases.
- **Trusted Publisher**: No API tokens needed. The publish workflow uses PyPI Trusted Publisher (OIDC).
- **Semantic Versioning**: Follow [semver](https://semver.org/):
  - MAJOR: Breaking changes
  - MINOR: New features (backward compatible)
  - PATCH: Bug fixes (backward compatible)

## Troubleshooting

### Auto-Release Not Triggered

- Ensure `pyproject.toml` was changed in the merge commit (the workflow checks `paths: [pyproject.toml]`)
- Ensure the `version = ` line actually changed (the workflow diffs `HEAD~1`)

### Changelog Extraction Failed

- Ensure `CHANGELOG.md` has a section matching the exact version: `## [X.Y.Z] - 2026-XX-XX`
- Run locally to verify: `python scripts/extract_changelog.py X.Y.Z`

### "File already exists" Error on PyPI

This means PyPI already has this version. The tag was likely created before. Check releases at https://github.com/s-hiraoku/synapse-a2a/releases.

### Manual Tag/Release (Fallback)

If automation fails, you can still create the tag and release manually:

```bash
git checkout main && git pull origin main
git tag vX.Y.Z
git push origin vX.Y.Z
python scripts/extract_changelog.py X.Y.Z > /tmp/release-notes.md
gh release create vX.Y.Z --title "vX.Y.Z" --notes-file /tmp/release-notes.md
rm /tmp/release-notes.md
```
