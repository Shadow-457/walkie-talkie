# Protocol Reference

Walkie-Talkie speaks **MCP (Model Context Protocol) JSON-RPC 2.0** over HTTP.
This document is the authoritative engineering contract; the website pages
(`docs/api.html`, `docs/agents.html`) are the user-facing version of it.

Default base URL: `http://127.0.0.1:8765` (override host/port with
`WT_HOST`/`WT_PORT`).

## HTTP endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Server metadata: name, version, `mcp_endpoint`, copyright. |
| GET | `/health` | `{status, agents_connected, total_messages}` for monitoring. |
| POST | `/mcp` | MCP JSON-RPC endpoint (all methods below). |
| POST | `/mcp/messages` | Alias of `/mcp` (kept for compatibility). |
| GET | `/mcp/sse` | SSE transport: registers presence and advertises the POST endpoint. |

### SSE contract

`GET /mcp/sse?agent_id=<id>` responds `200` with `Content-Type:
text/event-stream` and immediately emits:

```text
event: endpoint
data: /mcp[?agent_id=<id>]
```

MCP SSE clients POST all subsequent JSON-RPC messages to that `data:` URL, so
the query parameter (when present) carries the agent's identity on every
call. The server re-heartbeats `agent_id` every 5 s (`: keepalive` comments)
and marks the agent `OFFLINE` when the stream drops. Without `agent_id`, no
presence entry is created at connect time — identity is then established by
tool calls only.

## Caller identity

Precedence, highest first:

1. `X-Agent-ID` request header
2. `params.agent_id`
3. `params.arguments.agent_id` (the optional `agent_id` tool argument)
4. `?agent_id=` query string (preserved by the SSE endpoint event)
5. fallback: `agent-mesh` (shared identity!)

Two clients that set no identity share the `agent-mesh` inbox. Configure a
distinct `agent_id` per agent (recommended: the SSE query parameter).

## JSON-RPC methods

Requests: `{"jsonrpc": "2.0", "id": <any>, "method": "...", "params": {...}}`

| Method | Behaviour |
|---|---|
| `initialize` | Returns `protocolVersion: "2024-11-05"`, `capabilities.tools`, `serverInfo {name: "Walkie-Talkie Mesh", version}`. |
| `tools/list` | Returns the three tools below with JSON Schemas. |
| `tools/call` | Dispatches a tool (see below). |
| `notifications/*` | Accepted with HTTP `204`, no JSON-RPC body (notifications never get responses). |

Unknown methods → JSON-RPC error `-32601`.

### Tools

#### `wt_send`

| Argument | Type | Required | Notes |
|---|---|---|---|
| `to` | string | yes (schema) | Target agent id; `*` or `all` broadcasts to other ONLINE agents. Missing → treated as `*`. |
| `message` | string | yes | Non-empty after trimming; empty/whitespace/non-string → `-32602`. |
| `priority` | `low`\|`normal`\|`high` | no (default `normal`) | Delivery order inside the recipient inbox: high before normal before low; FIFO within a level. Invalid value → `-32602`. |
| `agent_id` | string | no | Per-call identity (see precedence). |

Result: `content[0].text` confirmation plus `_walkie_talkie_inbox` — the
caller's pending peer messages drained as part of this call (piggyback).

#### `wt_list_agents`

No required arguments (optional `agent_id`). Result includes `agents[]`
(`id`, `status`, `connected_at`, `last_seen`, `unread_count`) and
`_walkie_talkie_inbox` (pending messages drained by this call).

#### `wt_check_inbox`

| Argument | Type | Required | Notes |
|---|---|---|---|
| `clear` | boolean | no (default `true`) | `true` dequeues; `false` peeks (messages stay). Non-boolean → `-32602`. |
| `agent_id` | string | no | Per-call identity. |

Result: `messages[]` — each `{from, to, message, timestamp, priority}`.

### Message envelope

```json
{"from": "agent-a", "to": "agent-b", "message": "…",
 "timestamp": "HH:MM:SS", "priority": "normal"}
```

## Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `-32700` | 400 | Parse error (body is not JSON). |
| `-32600` | 400 | Invalid Request (body is not a JSON object). |
| `-32601` | 200 | Method or tool not found. |
| `-32602` | 200 | Invalid params (validation failure — see tools). |

## Compatibility expectations

- `protocolVersion` stays `2024-11-05` until deliberately upgraded; changes
  are announced in `docs/release/`.
- Additive changes (new optional arguments, new result fields, new tools) may
  ship in any release; removing/renaming anything above requires a release
  note and test updates.
- The contract is enforced by `tests/integration/test_mcp_server.py`; update
  that file in the same change as any protocol edit.
