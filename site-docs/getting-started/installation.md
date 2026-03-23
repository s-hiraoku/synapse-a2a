# Installation

## Prerequisites

- **OS**: macOS, Linux, or WSL2 on Windows
- **Python**: 3.10 or higher
- **CLI Agents**: At least one of the following installed and configured:
    - [Claude Code](https://docs.anthropic.com/en/docs/build-with-claude/claude-code) (`claude`)
    - [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`gemini`)
    - [Codex CLI](https://github.com/openai/codex) (`codex`)
    - [OpenCode](https://github.com/opencode-ai/opencode) (`opencode`)
    - [GitHub Copilot CLI](https://docs.github.com/en/copilot/github-copilot-in-the-cli) (`copilot`)

!!! info "System Requirements & Constraints"
    - **OS**: macOS, Linux (WSL2 included). Native Windows is not supported.
    - **Python**: 3.10+ required. `pipx` recommended for isolated install.
    - **Storage**: `~/.synapse/`, `~/.a2a/` (user-level), `.synapse/` (project-local)
    - **Network**: Local only (UDS preferred, TCP fallback). See [External Agents](../advanced/external-agents.md) for remote connections.
    - **PTY Note**: Synapse wraps CLI tools via PTY. UI updates to underlying tools (e.g., Claude Code) may require profile adjustments.
    - **Terminal**: tmux, iTerm2, Terminal.app, Ghostty, or Zellij required for `team start` / `spawn`.

## Install Synapse A2A

=== "pipx (Recommended)"

    ```bash
    pipx install synapse-a2a
    ```

    !!! tip
        `pipx` installs in an isolated environment, preventing dependency conflicts.
        Install pipx: `pip install pipx && pipx ensurepath`

=== "pip"

    ```bash
    pip install synapse-a2a
    ```

=== "Scoop (Windows)"

    ```powershell
    scoop bucket add synapse-a2a https://github.com/s-hiraoku/scoop-synapse-a2a
    scoop install synapse-a2a
    ```

=== "From Source"

    ```bash
    git clone https://github.com/s-hiraoku/synapse-a2a.git
    cd synapse-a2a
    uv sync
    ```

## Verify Installation

```bash
synapse --version
```

You should see the version number (e.g., `0.17.3`).

## Initialize Configuration

```bash
# Interactive setup — creates .synapse/ directory
synapse init

# Or specify scope directly
synapse init --scope user      # ~/.synapse/settings.json
synapse init --scope project   # ./.synapse/settings.json
```

This creates the configuration directory with default settings and instruction templates.

!!! info "Safe to re-run"
    `synapse init` uses a **merge strategy** — only template files (`settings.json`, `default.md`, `gemini.md`, `file-safety.md`, `learning.md`, `shared-memory.md`) are written. User-generated data such as saved agent definitions (`agents/`), databases (`*.db`), sessions, workflows, and worktrees are **preserved**. You can safely re-run `synapse init` to pick up new template files after upgrading.

## Install Skills

Skills teach agents how to use Synapse features — messaging, file safety, task delegation, and more. The `synapse-a2a` skill package is **essential** for multi-agent communication.

```bash
npx skills add s-hiraoku/synapse-a2a
```

This installs all core skills into your project:

| Skill | Description |
|-------|-------------|
| **synapse-a2a** | Core A2A communication — commands, API, file safety, task board |
| **synapse-manager** | Multi-agent orchestration (7-step workflow) |
| **synapse-reinst** | Re-inject instructions after `/clear` or context reset |

!!! tip "Why This Matters"
    Without `synapse-a2a`, agents won't automatically discover peers or use `synapse send`/`synapse reply`. Install it in every project where you use Synapse.

Verify installation:

```bash
synapse skills list --scope project
```

## Configure MCP Server (Recommended)

Synapse provides an MCP (Model Context Protocol) server that distributes bootstrap instructions to MCP-capable agents. Agents that use the MCP bootstrap require a one-time configuration to connect to the Synapse MCP server.

Once this Synapse MCP configuration is present, Synapse skips PTY startup instruction injection automatically for Claude Code, Codex, Gemini CLI, OpenCode, and GitHub Copilot.

=== "Claude Code"

    Add to your MCP configuration file. Use project-local `.mcp.json` for repo-specific settings, or user-global `~/.claude.json` for machine-wide defaults. If both exist, `.mcp.json` takes precedence:

    ```json
    {
      "mcpServers": {
        "synapse": {
          "type": "stdio",
          "command": "/path/to/uv",
          "args": [
            "run", "--directory", "/path/to/synapse-a2a",
            "python", "-m", "synapse.mcp"
          ]
        }
      }
    }
    ```

    Or via CLI: `claude mcp add --scope user synapse /path/to/uv run --directory /path/to/synapse-a2a python -m synapse.mcp`

=== "Gemini CLI"

    Add to `~/.gemini/settings.json`:

    ```json
    {
      "mcpServers": {
        "synapse": {
          "command": "/path/to/uv",
          "args": [
            "run", "--directory", "/path/to/synapse-a2a",
            "python", "-m", "synapse.mcp"
          ],
          "timeout": 5000,
          "trust": true
        }
      }
    }
    ```

=== "Codex CLI"

    Add to `~/.codex/config.toml`:

    ```toml
    [mcp_servers.synapse]
    command = "/path/to/uv"
    args = [
      "run", "--directory", "/path/to/synapse-a2a",
      "python", "-m", "synapse.mcp",
    ]
    ```

=== "OpenCode"

    Add to `~/.config/opencode/opencode.json`:

    ```json
    {
      "mcp": {
        "synapse": {
          "type": "local",
          "command": [
            "/path/to/uv",
            "run", "--directory", "/path/to/synapse-a2a",
            "python", "-m", "synapse.mcp"
          ],
          "enabled": true,
          "timeout": 5000
        }
      }
    }
    ```

    !!! note
        OpenCode uses `"mcp"` (not `"mcpServers"`) and `command` is an **array**.

=== "GitHub Copilot"

    Add to `~/.copilot/mcp-config.json`:

    ```json
    {
      "mcpServers": {
        "synapse": {
          "command": "/path/to/uv",
          "args": [
            "run", "--directory", "/path/to/synapse-a2a",
            "python", "-m", "synapse.mcp"
          ]
        }
      }
    }
    ```

    !!! note
        Copilot's coding agent supports MCP **tools only** and cannot consume MCP resources/prompts. Copilot uses the `bootstrap_agent` and `analyze_task` tools to retrieve runtime context and task suggestions.

!!! tip "Path Replacement"
    The examples above assume a **source checkout** with `uv`. Replace `/path/to/uv` with the output of `which uv`, and `/path/to/synapse-a2a` with your actual checkout path.

    If you installed via **pipx**, use the `synapse` entrypoint (pipx isolates the virtualenv, so `python -m` won't find the package):

    ```json
    "command": "synapse",
    "args": ["mcp", "serve"]
    ```

    If you installed via **pip** (system or venv), you can use either the entrypoint or the module directly:

    ```json
    "command": "python",
    "args": ["-m", "synapse.mcp"]
    ```

For detailed configuration, troubleshooting, and verification steps, see [MCP Bootstrap Setup](../guide/mcp-setup.md).

## Terminal Requirements

For multi-agent features like `synapse team start` and `synapse spawn`, you need a supported terminal multiplexer or application:

| Terminal | `synapse list` Jump | `synapse spawn` | `synapse team start` |
|----------|:---:|:---:|:---:|
| **tmux** | :material-check: | :material-check: | :material-check: |
| **iTerm2** | :material-check: | :material-check: | :material-check: |
| **Terminal.app** | :material-check: | :material-check: | :material-check: |
| **Ghostty** | :material-check: | :material-check: | :material-check: |
| **VS Code Terminal** | :material-check: | — | — |
| **Zellij** | :material-check: | :material-check: | :material-check: |

!!! info "Ghostty Focus Limitation"
    Ghostty uses AppleScript to target the **currently focused window/tab**. If you switch tabs while a `spawn` or `team start` command is running, the agent may be created in the unintended tab. Wait for the command to complete before switching tabs.

## Next Steps

- [Quick Start](quickstart.md) — Launch your first agent and send a message
- [Interactive Setup](setup.md) — Configure agent names, roles, and skill sets
- [MCP Bootstrap Setup](../guide/mcp-setup.md) — Detailed MCP server configuration and troubleshooting
- [Skills](../guide/skills.md) — Manage skills, skill sets, and deployment
- [Architecture](../concepts/architecture.md) — Understand how Synapse A2A works
