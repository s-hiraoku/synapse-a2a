# Synapse A2A Skills

Skills for [Synapse A2A](https://github.com/s-hiraoku/synapse-a2a) - a multi-agent communication framework.

## Installation

```bash
# Install via skills.sh (https://skills.sh/)
npx skills add s-hiraoku/synapse-a2a
```

## Skills Included

### synapse-a2a

Comprehensive guidance for inter-agent communication:

- Send messages to other agents (`@agent` pattern)
- Priority levels (1-5, with 5 being emergency interrupt)
- Task history management (search, export, cleanup)
- File Safety (locking, modification tracking)
- Settings management (`synapse init`, `settings.json`)
- Agent monitoring (`synapse list --watch`)

### anthropic-skill-creator

Design, review, and improve skills based on Anthropic's methodology:

- Use-case definition and trigger phrase design
- SKILL.md frontmatter and workflow authoring
- Test protocol (triggering, functional, performance)
- Iteration based on under-trigger/over-trigger signals

## Usage

Once installed, Claude will automatically use these skills when relevant tasks are detected:

- Sending messages to other agents
- Managing file locks in multi-agent environments
- Viewing task history

## Requirements

- [Synapse A2A](https://github.com/s-hiraoku/synapse-a2a) installed and running
- Claude Code with plugin support

## Links

- [Synapse A2A Documentation](https://github.com/s-hiraoku/synapse-a2a)
- [File Safety Guide](https://github.com/s-hiraoku/synapse-a2a/blob/main/docs/file-safety.md)
