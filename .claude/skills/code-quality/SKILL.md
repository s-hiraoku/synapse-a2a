---
name: code-quality
description: Run code quality checks (ruff, mypy) and optionally simplify code. This skill should be used when the user wants to check code quality, run linters, or simplify recently modified code. Triggered by /lint, /check, or /code-quality commands.
---

# Code Quality Check

This skill runs code quality tools and optionally simplifies code.

## Usage

```
/code-quality [options]
```

### Options

- `--all` or `-a`: Run on all synapse/ files (default: recently modified files only)
- `--simplify` or `-s`: Also run code-simplifier agent after checks pass
- `--fix` or `-f`: Auto-fix ruff issues with `--fix` flag

## Workflow

### Step 1: Identify Target Files

If `--all` flag is provided:
- Target all files in `synapse/` directory

Otherwise:
- Run `git diff --name-only HEAD~1` to get recently modified files
- Filter to only `.py` files in `synapse/` or `tests/`

### Step 2: Run Ruff Linter

```bash
ruff check [files]
```

If `--fix` flag is provided:
```bash
ruff check --fix [files]
```

Report any errors found.

### Step 3: Run Mypy Type Checker

```bash
uv run mypy [files]
```

Report any type errors found.

### Step 4: Run Code Simplifier (Optional)

If `--simplify` flag is provided AND ruff/mypy passed:

Use the `code-simplifier:code-simplifier` agent to simplify the recently modified code:

```
Task tool with subagent_type: code-simplifier:code-simplifier
Prompt: Simplify and refine the recently modified code in [files].
Look for opportunities to reduce duplication, simplify conditionals,
and improve readability while maintaining all functionality.
```

### Step 5: Report Results

Summarize:
- Number of files checked
- Ruff status (pass/fail, errors fixed if --fix)
- Mypy status (pass/fail)
- Code simplifier status (if run)

## Examples

### Basic check on recent changes
```
/code-quality
```

### Check all files with auto-fix
```
/code-quality --all --fix
```

### Full quality check with simplification
```
/code-quality --simplify
```

### Shorthand
```
/lint          # Same as /code-quality
/check         # Same as /code-quality
/lint -s       # With simplification
/lint -a -f    # All files with auto-fix
```
