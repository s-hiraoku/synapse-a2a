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
