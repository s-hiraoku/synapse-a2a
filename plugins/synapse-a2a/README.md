# Synapse A2A Plugin

Claude Code plugin for [Synapse A2A](https://github.com/s-hiraoku/synapse-a2a) - a multi-agent communication framework.

## Installation

```bash
# Add the marketplace
/plugin marketplace add s-hiraoku/synapse-a2a

# Install the plugin
/plugin install synapse-a2a@synapse-a2a
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

### delegation

Configure automatic task delegation between agents:

- **Orchestrator mode**: Claude analyzes, delegates, integrates results
- **Passthrough mode**: Direct forwarding without processing
- Pre-delegation checklist (agent status, file locks)
- File Safety integration
- Error handling and recovery

## Usage

Once installed, Claude will automatically use these skills when relevant tasks are detected:

- Sending messages to other agents
- Configuring task delegation
- Managing file locks in multi-agent environments
- Viewing task history

## Requirements

- [Synapse A2A](https://github.com/s-hiraoku/synapse-a2a) installed and running
- Claude Code with plugin support

## Links

- [Synapse A2A Documentation](https://github.com/s-hiraoku/synapse-a2a)
- [File Safety Guide](https://github.com/s-hiraoku/synapse-a2a/blob/main/docs/file-safety.md)
- [Delegation Guide](https://github.com/s-hiraoku/synapse-a2a/blob/main/guides/delegation.md)
