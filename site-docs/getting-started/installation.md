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
    scoop bucket add synapse-a2a https://github.com/s-hiraoku/synapse-a2a
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

You should see the version number (e.g., `0.8.3`).

## Initialize Configuration

```bash
# Interactive setup — creates .synapse/ directory
synapse init

# Or specify scope directly
synapse init --scope user      # ~/.synapse/settings.json
synapse init --scope project   # ./.synapse/settings.json
```

This creates the configuration directory with default settings and instruction templates.

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
- [Architecture](../concepts/architecture.md) — Understand how Synapse A2A works
