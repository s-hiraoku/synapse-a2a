# Golden Path

Run this from the repository after `uv sync`. The `claude` and `codex` CLIs
must already be installed, authenticated, and available on `PATH`.

```bash
uv run synapse start claude --port 8108
uv run synapse start codex --port 8122
uv run synapse list --plain
uv run synapse send synapse-codex-8122 "Reply with exactly: SYNAPSE_GOLDEN_PATH_OK" --from synapse-claude-8108 --wait
```

Before the final command, wait or answer prompts until `list --plain` shows both
agents as `READY`.

Success means the final command prints a Codex reply containing:

```text
SYNAPSE_GOLDEN_PATH_OK
```

Cleanup:

```bash
uv run synapse kill claude-8108 -f
uv run synapse kill codex-8122 -f
```
