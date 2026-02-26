# Authentication

## Overview

Synapse supports API key authentication for securing agent communication endpoints.

## Setup

```bash
synapse auth setup
```

This generates API keys and shows setup instructions.

## Generate Keys

```bash
# Generate a single key
synapse auth generate-key

# Generate multiple keys
synapse auth generate-key -n 3

# Export format (easy to copy)
synapse auth generate-key -n 3 -e
```

## Enable Authentication

Set environment variables:

```bash
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS="key1,key2,key3"
export SYNAPSE_ADMIN_KEY="admin-key-here"
```

Or in `.synapse/settings.json`:

```json
{
  "env": {
    "SYNAPSE_AUTH_ENABLED": "true",
    "SYNAPSE_API_KEYS": "key1,key2,key3"
  }
}
```

## Localhost Bypass

By default, localhost requests skip authentication:

```bash
export SYNAPSE_ALLOW_LOCALHOST=true    # Default
export SYNAPSE_ALLOW_LOCALHOST=false   # Require auth even for localhost
```

## Protected Endpoints

When authentication is enabled, all API endpoints require an API key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer <api-key>" \
  http://localhost:8100/tasks/send \
  -d '...'
```

## Key Features

- **SHA-256 hashing**: Keys are stored as hashes, not plaintext
- **Key scoping**: Read/write/admin permission levels
- **Rate limiting**: 1000 requests/hour per key (default)
- **Key expiration**: Optional TTL per key

## Security Best Practices

- Rotate API keys regularly
- Use separate keys for each agent or service
- Enable `SYNAPSE_ALLOW_LOCALHOST=false` in production environments
- Store keys in environment variables, not in config files
- Use the admin key only for management operations
