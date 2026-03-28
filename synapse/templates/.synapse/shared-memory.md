SHARED MEMORY (Cross-Agent Knowledge Base):

Commands:
  synapse memory save <key> "<content>" [--tags tag1,tag2] [--scope global|project|private]
  synapse memory list [--author <id>] [--scope <scope>]
  synapse memory search <query> [--scope <scope>]
  synapse memory show <key>
  synapse memory delete <key> [--force]
  synapse memory stats

Scopes:
  global   - All agents across all projects (default)
  project  - Agents in the same working directory only
  private  - Only the saving agent can see it

What to save:
  - Patterns or conventions discovered in the codebase
  - Architectural decisions and their rationale
  - Bugs or pitfalls that other agents should avoid
  - Project-specific knowledge (use --scope project)
  - Personal work notes (use --scope private)

What NOT to save:
  - Simple task completion reports (use broadcast or reply instead)
  - Information already in code comments or documentation
  - Temporary debugging state

Key naming: use kebab-case descriptive keys (e.g. "auth-jwt-pattern", "api-error-handling")
Tags: use topic-based tags (e.g. "auth", "testing", "performance")
