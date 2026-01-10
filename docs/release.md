# Release Guide

This document describes how to release a new version of synapse-a2a to PyPI.

## Overview

Releases are automated via GitHub Actions. When you push a tag starting with `v` (e.g., `v0.2.0`), the `publish.yml` workflow automatically builds and publishes the package to PyPI using Trusted Publisher.

## Release Steps

### 1. Update Version in pyproject.toml

Update the version number in `pyproject.toml`:

```toml
[project]
name = "synapse-a2a"
version = "0.3.0"  # Update this
```

### 2. Create a Pull Request

Create a PR with the version bump:

```bash
git checkout -b chore/bump-version-0.3.0
# Edit pyproject.toml
git add pyproject.toml
git commit -m "chore: bump version to 0.3.0"
git push origin chore/bump-version-0.3.0
gh pr create --title "chore: bump version to 0.3.0" --body "Update version for release"
```

### 3. Merge the PR

After CI passes and review is complete, merge the PR to main.

### 4. Create and Push Tag

```bash
git checkout main
git pull origin main
git tag v0.3.0
git push origin v0.3.0
```

### 5. Verify Release

1. Check GitHub Actions: https://github.com/s-hiraoku/synapse-a2a/actions/workflows/publish.yml
2. Verify on PyPI: https://pypi.org/project/synapse-a2a/

### 6. Create GitHub Release (Optional)

```bash
gh release create v0.3.0 --title "v0.3.0" --notes "Release notes here"
```

Or create via GitHub UI at https://github.com/s-hiraoku/synapse-a2a/releases/new

## Important Notes

- **Version must match**: The version in `pyproject.toml` must be updated BEFORE creating the tag. Otherwise, the publish workflow will try to upload an existing version and fail.
- **Trusted Publisher**: No API tokens needed. The workflow uses PyPI Trusted Publisher (OIDC).
- **Semantic Versioning**: Follow [semver](https://semver.org/):
  - MAJOR: Breaking changes
  - MINOR: New features (backward compatible)
  - PATCH: Bug fixes (backward compatible)

## Troubleshooting

### "File already exists" Error

This means the tag was created before updating `pyproject.toml`. Fix:

```bash
# Delete the tag
git tag -d v0.3.0
git push origin :refs/tags/v0.3.0

# Ensure pyproject.toml has correct version, then recreate
git tag v0.3.0
git push origin v0.3.0
```

### Workflow Not Triggered

Ensure the tag starts with `v` (e.g., `v0.3.0`, not `0.3.0`).
