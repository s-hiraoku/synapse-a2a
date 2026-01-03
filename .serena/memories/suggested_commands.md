# Suggested Commands for Development

## Setup & Installation
```bash
# Install dependencies
uv sync
```

## Testing
```bash
pytest                                    # All tests
pytest tests/test_a2a_compat.py -v        # Specific file
pytest -k "test_identity" -v              # Pattern match
```

## Running Agents (Interactive)
```bash
synapse claude
synapse codex
synapse gemini
```

## Listing Agents
```bash
synapse list                              # Show all running agents
synapse list --watch                      # Watch mode (refresh every 2s)
synapse list -w -i 1                      # Watch mode with 1s interval
```

## Low-level A2A Tool
```bash
python3 synapse/tools/a2a.py list                                           # List running agents
python3 synapse/tools/a2a.py send --target claude --priority 1 "message"    # Send message to agent
```

## Code Quality
```bash
mypy synapse/                             # Type checking
ruff check synapse/                       # Linting
ruff format synapse/                      # Code formatting
```

## Git
```bash
git status                                # Check status
git diff                                  # View changes
git add <file>                            # Stage changes
git commit -m "message"                   # Create commit
git push                                  # Push to remote
```
