# GEMINI.md

This file provides Gemini-specific guidance. For repository-wide policies, see [AGENTS.md](./AGENTS.md).

## Gemini-Specific Branch Management

- Follow all branch rules in AGENTS.md (no direct commits to `main`, always use PRs)
- **When creating a new branch for a new task**: Gemini may create the branch without asking for confirmation, as long as it follows the naming conventions
- **When switching to an existing branch**: Always ask the user for confirmation first
- Before switching branches, ensure all changes are committed or stashed
- When delegating to other agents, they must work on the same branch

## Gemini Strengths & Recommended Tasks

Gemini excels at:

- **Research & Analysis**: Exploring codebases, understanding architecture, answering questions
- **Documentation**: Writing and reviewing docs, README improvements
- **Test Writing**: Creating test cases, especially for specification confirmation
- **Code Review**: Reviewing PRs, suggesting improvements
- **Multi-file Refactoring**: Coordinated changes across multiple files

## Gemini Development Workflow

### Tests-First Approach

1. Receive a feature request or modification
2. Write tests first to define the expected behavior
3. Present tests to the user for specification confirmation
4. Implement only after tests are approved
5. Iterate until all tests pass

### Testing Commands

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_a2a_compat.py -v

# Run tests matching a pattern
pytest -k "test_identity" -v

# Run with verbose output
pytest -v --tb=short
```

### Integration with Repo Flow

1. Check current branch: `git branch --show-current`
2. Create feature branch if needed: `git checkout -b feat/description`
3. Write tests, get confirmation, implement
4. Run full test suite: `pytest`
5. Commit with conventional format: `git commit -m "feat: description"`
6. Push and create PR

## Commands Quick Reference

```bash
# Install dependencies
uv sync

# Run Gemini agent
synapse gemini

# List running agents
synapse list
synapse list --watch

# Task history
synapse history list
synapse history list --agent gemini
```

For complete command reference, see [AGENTS.md](./AGENTS.md).
