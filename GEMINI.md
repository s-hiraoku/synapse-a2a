# GEMINI.md

This file provides Gemini-specific guidance. For repository-wide policies, see [AGENTS.md](./AGENTS.md).

## Skills

Gemini has access to skills in `.gemini/skills/`. Use these skills for specialized tasks:

- **synapse-a2a**: Inter-agent communication using Synapse A2A framework

Skills are automatically loaded when relevant tasks are detected.

## Gemini-Specific Branch Management

- Follow all branch rules in AGENTS.md (no direct commits to `main`, always use PRs)
- **When creating a new branch for a new task**: Gemini may create the branch without asking for confirmation, as long as it follows the naming conventions
- **When switching to an existing branch**: Always ask the user for confirmation first
- Before switching branches, ensure all changes are committed or stashed
- When sending tasks to other agents, they must work on the same branch

For complete command reference, see [AGENTS.md](./AGENTS.md).
