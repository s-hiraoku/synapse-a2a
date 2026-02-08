# OpenCode Tools Reference

## File Operations

### read

Read file contents from your codebase.

**Capabilities:**
- Read entire files
- Read specific line ranges
- Support for various file types

**Usage by agents:**
```
Read the contents of src/main.ts
Read lines 50-100 of config.json
```

### write

Create new files or overwrite existing ones.

**Capabilities:**
- Create files with specified content
- Overwrite existing files completely
- Create parent directories as needed

**Usage by agents:**
```
Create a new file src/utils.ts with the helper functions
```

### edit

Modify existing files using exact string replacements.

**Capabilities:**
- Find and replace exact strings
- Multiple replacements in single operation
- Preserves file structure

**Usage by agents:**
```
Replace the old function implementation with the new one
```

### patch

Apply patch files to your codebase.

**Capabilities:**
- Apply unified diff patches
- Multi-file patches
- Conflict detection

## Search & Discovery

### grep

Search file contents using regular expressions.

**Capabilities:**
- Full regex support
- Case-insensitive search
- Context lines
- File type filtering

**Usage by agents:**
```
Search for all usages of "authenticate" function
Find TODO comments in the codebase
```

### glob

Find files by pattern matching.

**Capabilities:**
- Standard glob patterns (`**/*.js`)
- Multiple patterns
- Exclusion patterns

**Usage by agents:**
```
Find all TypeScript files in src/
List all test files
```

### list

List files and directories in a given path.

**Capabilities:**
- Directory listing
- Glob filtering
- Recursive listing

**Usage by agents:**
```
List the contents of the src directory
Show all files in the project root
```

## Execution

### bash

Execute shell commands in your project environment.

**Capabilities:**
- Run any shell command
- Environment variable access
- Working directory context

**Permission modes:**
- `allow` - Execute without confirmation
- `ask` - Require user approval (Plan agent default)
- `deny` - Block execution

**Usage by agents:**
```
Run npm install
Execute the test suite
Build the project
```

## Code Intelligence

### lsp (Experimental)

Interact with Language Server Protocol servers.

**Capabilities:**
- Go to definition
- Find references
- Hover information
- Call hierarchy

**Note:** Requires LSP server to be configured and running.

## Task Management

### todowrite

Create and update task lists during coding sessions.

**Capabilities:**
- Create structured task lists
- Update task status
- Track progress

**Usage by agents:**
```
Create a todo list for the refactoring tasks
Mark the authentication task as complete
```

### todoread

Read current todo list state.

**Capabilities:**
- View all tasks
- Filter by status
- Get task details

## Utilities

### skill

Load skill files into conversations.

**Capabilities:**
- Load project skills
- Load global skills
- Access skill references

**Usage by agents:**
```
Load the database-schema skill
Use the api-docs skill for reference
```

### webfetch

Fetch and read web pages.

**Capabilities:**
- Fetch URL content
- Parse HTML to text
- Follow redirects

**Usage by agents:**
```
Fetch the API documentation from the URL
Read the README from GitHub
```

### question

Ask users clarifying questions during execution.

**Capabilities:**
- Prompt for user input
- Multiple choice questions
- Free-form text input

**Usage by agents:**
```
Ask user which database to use
Confirm the deployment target
```

## Tool Permissions

Tools can be configured with three permission levels:

| Level | Behavior |
|-------|----------|
| `allow` | Execute without confirmation |
| `ask` | Require user approval each time |
| `deny` | Block tool usage |

### Default Permissions by Agent

**Build Agent:**
- All tools: `allow`

**Plan Agent:**
- read, grep, glob, list: `allow`
- write, edit, bash: `ask`
- Others: `allow`

### Configuring Permissions

In `opencode.json`:

```json
{
  "agents": {
    "build": {
      "tools": {
        "bash": "ask",
        "write": "allow"
      }
    }
  }
}
```

## MCP Integration

OpenCode supports Model Context Protocol (MCP) for external tools.

### Adding MCP Servers

```bash
opencode mcp add <server-name>
```

### MCP Tool Access

MCP tools are available alongside built-in tools with configurable permissions.

## Custom Tools

Define custom tools in `opencode.json`:

```json
{
  "tools": {
    "my-tool": {
      "description": "Custom tool description",
      "command": "my-script.sh",
      "args": ["$input"]
    }
  }
}
```
