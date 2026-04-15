# Multi-Agent Pattern Samples

Annotated, ready-to-run YAML definitions for each of the five built-in
coordination patterns.

## How to use

Copy any sample into your project's pattern directory and run it:

```bash
# Project scope — shared via git
mkdir -p .synapse/patterns
cp examples/patterns/code-review.yaml .synapse/patterns/

# Or user scope — personal, reused across every project
mkdir -p ~/.synapse/patterns
cp examples/patterns/code-review.yaml ~/.synapse/patterns/

# Preview what running the pattern would do (no agents are spawned)
synapse map run code-review --task "Review the auth module" --dry-run

# Actually run it
synapse map run code-review --task "Review the auth module"
```

Once copied, patterns appear in:

- `synapse map list`
- The Canvas **Multi Agent** tab
- `GET /api/multiagent`

## Files

| File | Pattern type | Use case |
|---|---|---|
| `code-review.yaml` | generator-verifier | Iteratively generate and verify a change against textual criteria |
| `research-synthesis.yaml` | orchestrator-subagent | Fan out research aspects to subagents and synthesize the final answer |
| `batch-translate.yaml` | agent-teams | Distribute a list of inline tasks across a parallel worker pool |
| `triage-fanout.yaml` | message-bus | Route an incoming task through a router and fan out to topic handlers |
| `parallel-research.yaml` | shared-state | Multiple agents collaborate by writing findings to the project wiki |

Each sample is documented inline with `#` comments explaining every field.
Edit the `profile:` values to match the agent profiles you actually have
available (`claude`, `codex`, `gemini`, `opencode`, etc.).

See [`guides/multi-agent-patterns.md`](../../guides/multi-agent-patterns.md)
for the full conceptual guide.
