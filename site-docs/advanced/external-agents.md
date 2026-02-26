# External Agents

## Overview

Synapse can communicate with external A2A agents — services running outside your local machine that implement the A2A protocol.

## Registering External Agents

```bash
synapse external add https://agent.example.com --alias my-remote-agent
```

This fetches the Agent Card from `/.well-known/agent.json` and stores it in `~/.a2a/external/`.

## Listing External Agents

```bash
synapse external list
```

## Sending Messages

```bash
synapse external send my-remote-agent "Analyze this dataset" --wait
```

## Removing Agents

```bash
synapse external remove my-remote-agent
```

## Agent Details

```bash
synapse external info my-remote-agent
```

## API Endpoints

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/external/discover` | Register external agent by URL |
| GET | `/external/agents` | List all external agents |
| GET | `/external/agents/{alias}` | Get agent details |
| DELETE | `/external/agents/{alias}` | Remove external agent |
| POST | `/external/agents/{alias}/send` | Send message |

## Use Cases

### SaaS Integration
Connect to external services that expose A2A endpoints (e.g., specialized AI models, data analysis services).

### Cross-Project Coordination
Link agents across different projects or machines.

### Specialized AI Models
Delegate specialized tasks to purpose-built external agents (medical AI, legal AI, code review services).

## Future Vision

As the A2A ecosystem matures, external agent connectivity enables:

- **Agent Marketplace**: Discover and connect to professional specialist agents
- **B2B Collaboration**: Secure inter-company agent communication via mTLS
- **IoT Integration**: Connect to edge devices and automation systems
- **Gateway Role**: Synapse as a hub between local CLI agents and external A2A services

## Current Limitations

- Authentication and authorization are basic (API key only)
- No mTLS support yet
- Push notifications not implemented
- SSE streaming not available for external connections
