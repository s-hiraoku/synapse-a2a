# A2A Local Transport: UDS Fallback Design

## Summary
Codex-like environments can block localhost TCP access, which breaks `a2a.py send` and other A2A client calls even when agents are running. This design adds a local Unix Domain Socket (UDS) transport that is preferred when available, while preserving the existing HTTP/TCP behavior as a fallback. The goal is zero user configuration: local sends succeed in restricted environments without asking users to alter sandbox settings.

## Goals
- Make local A2A sends work in restricted sandboxes without user configuration.
- Preserve existing HTTP/TCP behavior for compatibility.
- Keep changes scoped and opt-in via auto-detection (UDS if present).

## Non-Goals
- Replace HTTP/TCP transport entirely.
- Add remote/secure transport beyond current HTTP interface.
- Implement a full IPC bus or message queue system.

## Proposed Design

## Transport Strategy
- Run the same FastAPI app in two Uvicorn servers: one TCP listener and one UDS listener.
- Avoid single-process multi-listen internals; keep it as two server instances for stability.
- UDS listener start should delete stale socket file immediately before bind.
- If UDS listener crashes, it should be restarted alongside the TCP listener.

## UDS Path Resolution
- Preferred: $XDG_RUNTIME_DIR/synapse-a2a/<agent_id>.sock (if set).
- Fallback: ~/.a2a/uds/<agent_id>.sock.
- This keeps runtime sockets in a temporary area when available, while remaining backward compatible.

## Local Target Definition
- A target is considered local if the registry entry provides `uds_path`.
- If `uds_path` is missing, treat as non-local and do not assume sandbox-safe connectivity.

## Local Fallback Behavior
- For local targets: prefer UDS, and retry a few short times (e.g., 50/100/200ms) if connect fails.
- If UDS still fails, do not fall back to TCP for local targets; return failure.
- For external targets (explicit URL / external registry): keep TCP behavior as-is.

## UDS Availability Check
- Do not rely on exists() alone; attempt a request and treat ECONNREFUSED as transient with retry.

## Security Notes
- Create the UDS directory with mode 0700 (and ensure ~/.a2a is 0700 if needed).
- Socket permissions are secondary to the directory permissions.

### 1) Server: Dual Listener (HTTP + UDS)
- When a local agent starts, it will expose the A2A HTTP endpoints as today.
- Additionally, it will create a UDS socket and serve the same HTTP endpoints over UDS.
- The UDS path is resolved by `resolve_uds_path(agent_id)` (XDG_RUNTIME_DIR preferred, fallback to ~/.a2a/uds).
- The path is registered in the agent registry (`uds_path` field).

Implementation sketch:
- Create a shared helper to compute `uds_path` (in `synapse/registry.py` or new util).
- When the A2A server starts, create the UDS directory and remove any stale socket file.
- Start Uvicorn with `uds=<path>` in parallel to the TCP listener.

### 2) Registry: `uds_path` Field
- `AgentRegistry.register()` will include `uds_path` in the registry JSON.
- Existing readers ignore unknown fields, so this is backward compatible.

### 3) Client: Prefer UDS When Available
- `A2AClient.send_to_local()` will accept an optional `uds_path`.
- If `uds_path` exists on disk, use `httpx.Client(transport=httpx.HTTPTransport(uds=...))` to POST to the same endpoints.
- For local targets: retry UDS a few short times; if it still fails, return failure (no TCP fallback).
- For external/explicit URL targets: keep TCP behavior as-is.

### 4) Tooling: `synapse/tools/a2a.py`
- `cmd_send` will read `uds_path` from the target agent registry entry.
- It will skip the TCP preflight check when UDS is available.
- It will call `A2AClient.send_to_local(..., uds_path=...)`.

### 5) Input Router
- `InputRouter.route_to_agent` will skip `is_port_open` if `uds_path` exists.
- It will pass `uds_path` to `A2AClient.send_to_local`.

## Registry Registration Timing
- Prefer: start and bind the UDS listener, then register `uds_path` in the registry.
- This avoids initial connection failures before UDS is ready.

## Error Handling
- Local target: UDS failures are retried briefly; if still failing, return failure (no TCP fallback).
- External/explicit URL target: use TCP and retain current error handling.

## Compatibility
- No breaking changes to existing HTTP endpoints.
- Registry JSON gains a new field only; existing tooling remains compatible.
- External agents are unaffected; external A2A continues to use HTTP URLs and does not use UDS.

## Security Considerations
- UDS path is within the user home directory. Permission defaults should restrict access to the same user.
- If needed, set socket file permissions to user-only after creation.

## Testing Plan (First)
1) Registry writes `uds_path` on registration.
2) `A2AClient.send_to_local` uses UDS when path exists (no HTTP POST called).
3) `A2AClient.send_to_local` local target: UDS missing/unavailable => failure after retry.
4) External/explicit URL target: TCP behavior unchanged.
5) Input router skips TCP port check when `uds_path` exists and still sends.
6) `a2a.py send` uses UDS when available and does not fail due to TCP precheck.

## Rollout
- Ship in minor version bump; no config changes required.
- Document in `docs/` and optionally mention in release notes.
