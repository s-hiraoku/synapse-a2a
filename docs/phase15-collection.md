# Phase 1.5 WAITING Debug Collection

Phase 1.5 persists the in-memory WAITING detection debug data exposed by
`GET /debug/waiting`. It does not change WAITING detection logic; it only
collects snapshots for later Phase 2 analysis.

## Collect Snapshots

Run a one-shot collection across registered agents:

```bash
synapse waiting-debug collect
```

By default, records are appended to `~/.synapse/waiting_debug.jsonl`. The file
is user-scoped so data can accumulate across projects. Each JSONL row has this
shape:

```json
{
  "agent_id": "synapse-codex-8123",
  "agent_type": "codex",
  "port": 8123,
  "collected_at": "2026-04-23T01:00:00+00:00",
  "snapshot": {
    "renderer_available": true,
    "attempts": []
  }
}
```

Useful options:

```bash
synapse waiting-debug collect --out /tmp/waiting_debug.jsonl
synapse waiting-debug collect --agent synapse-codex-8123
synapse waiting-debug collect --include-empty
```

The collector warns on stderr when one agent cannot be reached and continues
collecting the remaining agents.

## Report Aggregates

Print a human-readable report:

```bash
synapse waiting-debug report
```

Filter by time or agent:

```bash
synapse waiting-debug report --since 2026-04-23T00:00:00+00:00
synapse waiting-debug report --agent synapse-codex-8123
```

Produce machine-readable JSON for Phase 2 analysis:

```bash
synapse waiting-debug report --json
```

The report includes profile, `pattern_source`, `path_used`, and `confidence`
distributions, plus idle-gate drop counts and the ratio of agents whose
snapshot reported `renderer_available=false`.

## Run Every Five Minutes

There is no `synapse schedule` CLI in this version. Use cron or launchd to run
collection every five minutes.

Cron example:

```cron
*/5 * * * * /usr/bin/env synapse waiting-debug collect >> ~/.synapse/waiting_debug_collect.log 2>&1
```

Launchd example for macOS, saved as
`~/Library/LaunchAgents/dev.synapse.waiting-debug.plist`:
replace `your-user` with the local macOS account name.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>dev.synapse.waiting-debug</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>synapse</string>
    <string>waiting-debug</string>
    <string>collect</string>
  </array>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>StandardOutPath</key>
  <string>/Users/your-user/.synapse/waiting_debug_collect.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/your-user/.synapse/waiting_debug_collect.err</string>
</dict>
</plist>
```

Load it with:

```bash
launchctl load ~/Library/LaunchAgents/dev.synapse.waiting-debug.plist
```

Stop or disable later with:

```bash
launchctl unload ~/Library/LaunchAgents/dev.synapse.waiting-debug.plist
```

Useful additions for the plist that can bite on a fresh macOS account:

- `PATH` in `EnvironmentVariables` — launchd does not inherit the login shell's
  `PATH`, so `synapse` must be reachable via an absolute path in
  `ProgramArguments` (recommended) or the plist must export
  `PATH=/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin`.
- `HOME` — launchd sets `HOME` for user agents automatically, but explicitly
  adding it to `EnvironmentVariables` makes the collector robust against
  unusual session contexts.

## Prerequisite: bump the installed `synapse` CLI

`synapse waiting-debug` only exists in **v0.28.1 and newer**. The 5-minute
cron/launchd schedule will spew `invalid choice: 'waiting-debug'` until the CLI
is upgraded.

If `synapse` was installed with `uv tool install`:

```bash
# Pull the latest release from PyPI once it is published
uv tool upgrade synapse-a2a

# Or install directly from a local checkout (useful before PyPI publish)
uv tool install --reinstall --from /path/to/synapse-a2a synapse-a2a
```

If `synapse` was installed with `pipx`:

```bash
pipx upgrade synapse-a2a
```

Verify with:

```bash
synapse --version                   # expect 0.28.1 or newer
synapse waiting-debug --help        # should list collect/report subcommands
```

## Known Caveat: Legacy Agents Return 404 (or 503 When Capability-Gated)

Agents that were **spawned with an older `synapse` binary (v0.27.x or earlier)
remain running with the old Python runtime** and do not expose
`GET /debug/waiting` — the route is not registered, so the collector sees a
404. When the collector reaches them it logs a one-line warning to stderr:

```text
Warning: failed to collect waiting debug for <agent-id>: HTTP Error 404: Not Found
```

Agents running v0.28.0+ **can also fail with 503** if their controller does
not expose `waiting_debug_snapshot` (for example, a non-PTY runtime where the
capability is gated off). In that case the route exists but returns
`503 Service Unavailable` with detail `waiting debug data not available`:

```text
Warning: failed to collect waiting debug for <agent-id>: HTTP Error 503: Service Unavailable
```

Both 404 (legacy) and 503 (capability gap) are expected and non-fatal — the
collector continues with the next agent and still appends any successful
snapshots to the JSONL. To bring an existing agent into the data set, stop
and respawn it with the upgraded CLI:

```bash
synapse kill <agent-id>
synapse spawn <profile>            # or the appropriate team/spawn invocation
```

Only agents respawned after the CLI upgrade will start contributing rows.
Pre-existing rooms stay invisible to Phase 2 analysis; this trade-off is
intentional — the alternative (rolling restarts of every running agent on
upgrade) is disruptive and not needed for Phase 2 planning.
