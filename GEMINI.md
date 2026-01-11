# GEMINI.md

This file provides guidance to the Gemini agent when working with code in this repository.

## Development Flow (Mandatory)

1. When receiving a feature request or modification, write tests first
2. Present the tests to confirm the specification
3. Proceed to implementation only after confirmation
4. Adjust implementation until all tests pass

### Branch Management Rules

- **Do NOT commit directly to the `main` branch.**
- **Always create a separate branch for your changes.**
- **Submit a Pull Request (PR) for all modifications.**
- **If branch change is needed**, always ask the user for confirmation first (unless following the rule to create a branch for a new task)
- Before switching branches, ensure all changes are committed or stashed
- When delegating to other agents, they must work on the same branch

## Project Overview

**Mission: Enable agents to collaborate on tasks without changing their behavior.**

Synapse A2A is a framework that wraps CLI agents (Claude Code, Codex, Gemini) with PTY and enables inter-agent communication via Google A2A Protocol. Each agent runs as an A2A server (P2P architecture, no central server).

### Core Principles

1. **Non-Invasive**: Wrap agents transparently without modifying their behavior
2. **Collaborative**: Enable multiple agents to work together using their strengths
3. **Transparent**: Maintain existing workflows and user experience

## Commands

```bash
# Install
uv sync

# Run tests
pytest                                    # All tests
pytest tests/test_a2a_compat.py -v        # Specific file

# Run agent (interactive)
synapse gemini
synapse claude
synapse codex

# List agents
synapse list                              # Show all running agents
synapse list --watch                      # Watch mode

# Task history
synapse history list                      # Show recent task history
```

## Commit & Pull Request Guidelines

- Commit messages follow Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- PRs should include: a short summary, rationale, and tests run.
