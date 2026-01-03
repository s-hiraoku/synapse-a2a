# Code Style and Conventions

## Development Flow (Mandatory)
1. When receiving a feature request or modification, write tests first
2. Present the tests to confirm the specification
3. Proceed to implementation only after confirmation
4. Adjust implementation until all tests pass

## Language & Type Hints
- **Language**: Python 3
- **Type Hints**: Full type annotations expected
- **Docstrings**: Include docstrings for modules, classes, and functions
- **Naming Conventions**: 
  - Classes: PascalCase (e.g., `TerminalController`)
  - Functions/methods: snake_case (e.g., `send_message`)
  - Constants: UPPER_SNAKE_CASE

## A2A Protocol Compliance
- All communication must use Message/Part + Task format per Google A2A spec
- Standard endpoints: `/.well-known/agent.json`, `/tasks/send`, `/tasks/{id}`
- Extensions use `x-` prefix (e.g., `x-synapse-context`)
- PTY output format: `[A2A:<task_id>:<sender_id>] <message>`

## Code Quality Tools
- **Type Checking**: mypy
- **Linting**: ruff
- **Testing**: pytest with async support

## Key Design Pattern: A2A Protocol First
All code must follow the A2A protocol specification when dealing with inter-agent communication.
