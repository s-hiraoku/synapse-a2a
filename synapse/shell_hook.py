#!/usr/bin/env python3
"""Generate shell hook for bash/zsh integration."""

BASH_HOOK = '''
# Synapse A2A Shell Hook
# Add this to your .bashrc or .zshrc

synapse_preexec() {
    local cmd="$1"
    # Check if command starts with @
    if [[ "$cmd" == @* ]]; then
        # Extract agent name and message
        local agent=$(echo "$cmd" | sed 's/^@\\([^ ]*\\).*/\\1/')
        local message=$(echo "$cmd" | sed 's/^@[^ ]* *//')

        # Check for --return flag
        if [[ "$message" == --return* ]]; then
            message=$(echo "$message" | sed 's/^--return *//')
            PYTHONPATH=. python3 -c "
from synapse.shell import SynapseShell
shell = SynapseShell()
shell.send_to_agent('$agent', '$message', wait_response=True)
"
        else
            PYTHONPATH=. python3 synapse/tools/a2a.py send --target "$agent" --priority 1 "$message"
        fi
        return 1  # Prevent original command execution
    fi
    return 0
}

# For Zsh
if [[ -n "$ZSH_VERSION" ]]; then
    autoload -Uz add-zsh-hook

    synapse_zsh_preexec() {
        synapse_preexec "$1"
        if [[ $? -eq 1 ]]; then
            # Cancel the command by clearing the buffer
            zle kill-whole-line 2>/dev/null || true
        fi
    }

    # Note: This hook approach has limitations in zsh
    # Consider using synapse-shell for full functionality
fi

# For Bash
if [[ -n "$BASH_VERSION" ]]; then
    # Bash preexec requires bash-preexec or DEBUG trap
    # This is a simplified version
    synapse_debug_trap() {
        local cmd="$BASH_COMMAND"
        if [[ "$cmd" == @* ]] && [[ "$SYNAPSE_RUNNING" != "1" ]]; then
            SYNAPSE_RUNNING=1
            synapse_preexec "$cmd"
            SYNAPSE_RUNNING=0
            return 1
        fi
    }

    # Uncomment to enable (may have side effects):
    # trap 'synapse_debug_trap' DEBUG
fi

echo "Synapse shell hook loaded. Use @Agent <message> to send messages."
echo "For best experience, use: synapse-shell"
'''

ZSH_HOOK_SIMPLE = '''
# Synapse A2A - Simple Zsh Integration
# Add to your .zshrc

synapse-send() {
    if [[ "$1" == @* ]]; then
        local agent=$(echo "$1" | sed 's/^@\\([^ ]*\\).*/\\1/')
        local message=$(echo "$@" | sed 's/^@[^ ]* *//')
        PYTHONPATH=. python3 synapse/tools/a2a.py send --target "$agent" --priority 1 "$message"
    else
        echo "Usage: synapse-send @Agent message"
    fi
}

alias @='synapse-send @'
'''


def generate_hook(shell_type: str = "bash") -> str:
    """Generate shell hook script."""
    if shell_type == "simple":
        return ZSH_HOOK_SIMPLE
    return BASH_HOOK


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Synapse shell hook")
    parser.add_argument("--type", choices=["bash", "zsh", "simple"], default="bash",
                        help="Shell type (default: bash)")
    args = parser.parse_args()

    print(generate_hook(args.type))


if __name__ == "__main__":
    main()
