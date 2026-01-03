# Task Completion Checklist

When completing a task, ensure:

## Development Flow
- [ ] Write tests first for new functionality
- [ ] Present tests to user for specification confirmation
- [ ] Implement according to confirmed specification
- [ ] All tests pass

## Code Quality
- [ ] Type checking passes: `mypy synapse/`
- [ ] Linting passes: `ruff check synapse/`
- [ ] Code is formatted: `ruff format synapse/`
- [ ] Tests pass: `pytest`

## A2A Protocol Compliance
- [ ] If dealing with inter-agent communication, ensure A2A protocol compliance
- [ ] Use Message/Part + Task format
- [ ] Use standard endpoints or x-prefixed extensions

## Testing
- [ ] All existing tests still pass
- [ ] New tests are added for new functionality
- [ ] Tests are comprehensive and follow async patterns if needed

## Documentation
- [ ] Update relevant documentation if needed
- [ ] Add docstrings to new functions/classes
- [ ] Update CLAUDE.md if significant changes were made

## Git
- [ ] Changes are committed with clear commit messages
- [ ] No uncommitted changes left unless intentional
