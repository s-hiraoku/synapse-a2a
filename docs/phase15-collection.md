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
synapse waiting-debug collect --timeout 10
```

The collector warns on stderr when one agent cannot be reached and continues
collecting the remaining agents.

Each agent's `/debug/waiting` request uses a **5-second HTTP timeout by
default** (raised from 3 s in v0.28.2). On slow or heavily loaded hosts where
the agent's controller cannot assemble the snapshot within 5 s you will see
repeat `Warning: failed to collect waiting debug for <agent-id>: timed out`
entries on stderr. Pass `--timeout 10` (or higher) to relax the budget, and
add the same flag to the cron/launchd invocation so the schedule picks it up.
An explicit `--timeout 0` is preserved as-is (passed to `urllib`) rather than
falling back to the default. Note that `urllib.request.urlopen(..., timeout=0)`
puts the underlying socket into non-blocking mode and will fail almost
immediately (typically `BlockingIOError`/`URLError`), so `--timeout 0` is a
deliberate "fail fast, never wait" mode — it is **not** the same as "no
timeout". To get the standard 5-second budget, simply omit `--timeout`.
Negative values are rejected by argparse before reaching the collector.

The default JSONL path (`~/.synapse/waiting_debug.jsonl`) is resolved at call
time, so test harnesses or alternate profiles that override `HOME` see the
expected `<HOME>/.synapse/waiting_debug.jsonl` location — no module-level
constant is captured at import time (v0.28.2).

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

Capture the JSON report into a file (stdout stays empty, so this is safe for
cron / scripted pipelines that redirect stdout to a log):

```bash
synapse waiting-debug report --out /tmp/waiting_debug_report.json
```

`--out` takes precedence over `--json`: when both are set, nothing is written
to stdout and the JSON report is written to the given file instead (v0.28.2).
Parent directories are created on demand. The write is **atomic** — the
report is staged in a sibling `.report.json.<random>.tmp` file and
`os.replace`d into place, so a cron-driven dashboard that reads the report
file in parallel will never see a half-written document.

The report includes profile, `pattern_source`, `path_used`, and `confidence`
distributions, plus idle-gate drop counts and the ratio of agents whose
snapshot reported `renderer_available=false`.

When a JSONL record has a `collected_at` field that cannot be parsed as
ISO-8601, `report` no longer silently drops it. It prints
`Warning: record at line N has unparseable collected_at: 'value' (reason)` to
stderr and skips only that row (v0.28.2). This helps catch JSONL files that
got mixed with cron stdout or hand-edited with a broken timestamp.

## Run Every Five Minutes

There is no `synapse schedule` CLI in this version. Use cron or launchd to run
collection every five minutes.

Cron example:

```cron
*/5 * * * * /usr/bin/env synapse waiting-debug collect >> ~/.synapse/waiting_debug_collect.log 2>&1
```

On hosts where 5 seconds is not enough for every agent's snapshot, pin a
longer timeout explicitly:

```cron
*/5 * * * * /usr/bin/env synapse waiting-debug collect --timeout 10 >> ~/.synapse/waiting_debug_collect.log 2>&1
```

If you also want a daily aggregate JSON written somewhere predictable without
polluting the collector log, drive `report` from cron with `--out`:

```cron
0 * * * * /usr/bin/env synapse waiting-debug report --out ~/.synapse/waiting_debug_report.json 2>> ~/.synapse/waiting_debug_report.err
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
  unusual session contexts. From v0.28.2 the collector resolves the default
  JSONL path lazily, so overriding `HOME` for a sandboxed run actually routes
  output to `<HOME>/.synapse/waiting_debug.jsonl` as expected.
- `--timeout` — if your agents' controllers regularly take longer than 5 s to
  respond to `/debug/waiting`, append `--timeout` and a value to
  `ProgramArguments` (e.g. add `<string>--timeout</string><string>10</string>`
  after `<string>collect</string>`).

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
