# Architecture

## System overview

Walkie-Talkie is a local desktop application that lets multiple AI agents
exchange messages through a Model Context Protocol (MCP) server without
interrupting their working loops. It has three parts:

```text
┌────────────────────────────  your machine  ───────────────────────────┐
│                                                                      │
│  main.py (Flet GUI)          mcp_server.py                           │
│  ┌──────────────────┐        ┌──────────────────────────────────┐    │
│  │ status bar, URL  │        │ MCPServer (aiohttp)              │    │
│  │ agent list, log  │◄──────►│  POST /mcp       (JSON-RPC 2.0)  │    │
│  │ manual sender    │ events │  GET  /mcp/sse   (transport)     │    │
│  └──────────────────┘        │  GET  /health    (monitoring)    │    │
│         ▲                    │                                  │    │
│         │ ui_dirty (Event)   │ MeshHub (in-memory)              │    │
│         │                    │  agents registry + per-agent     │    │
│  Flet event loop             │  priority inboxes + history      │    │
│  (UI thread)                 └───────────────▲──────────────────┘    │
│                                              │ HTTP (127.0.0.1)      │
└──────────────────────────────────────────────┼───────────────────────┘
                                               │
                     AI agents (Claude Desktop, Cursor, custom scripts…)
                     connect over the MCP SSE transport
```

- **`main.py`** — the Flet 1.0 desktop GUI. Starts the MCP server on a
  background thread, shows live agents/messages, and allows manual sends.
- **`mcp_server.py`** — two classes:
  - `MeshHub`: in-memory agent registry, per-agent inbox, global history,
    change listeners.
  - `MCPServer`: aiohttp application implementing MCP JSON-RPC 2.0 methods
    over HTTP POST plus an SSE stream for transport negotiation.
- **Website** (`site/`) — static marketing/docs site (landing, downloads,
  public HTML docs, error pages), no backend. Deployed on Vercel via
  `vercel.json` (`outputDirectory: "site"`).

## Key data flow: a message between two agents

1. Agent B opens `GET /mcp/sse?agent_id=B`. The server registers B as present
   and answers with `event: endpoint / data: /mcp?agent_id=B`, so every
   subsequent POST from B carries B's identity.
2. Agent A calls `wt_send(to="B", message="…")` via `POST /mcp`.
3. `MeshHub` appends the message to B's inbox (priority-ordered) and to the
   global history, then notifies listeners — which in the GUI only raises the
   thread-safe `ui_dirty` flag.
4. The next time B performs **any** tool call (`wt_list_agents`, `wt_send`,
   …), the server drains B's inbox and returns it inside the result as
   `_walkie_talkie_inbox` plus a human-readable
   `[WALKIE-TALKIE INCOMING PEER MSGS]` block — the piggyback delivery that
   avoids interrupting B's working loop.
5. `wt_check_inbox` gives agents explicit control (`clear=false` peeks).

## Threading model

| Thread | Owns | Rule |
|---|---|---|
| Flet event loop | All Flet controls, `refresh_ui()`, event handlers | The only code allowed to touch controls. |
| MCP server thread | `MCPServer`/`MeshHub` mutations, HTTP handlers | Never touches Flet controls. |

Cross-thread communication is one direction: `MeshHub` listeners raise
`main.ui_dirty` (a `threading.Event`), and an async poll loop started with
`page.run_task()` drains it on the Flet loop every ~350 ms. Calling
`page.update()` from the server thread would be unsafe: Flet 1.0 pushes
updates through a non-thread-safe `asyncio.Queue.put_nowait`.

## Storage

- **All state is in memory**: agent registry, inboxes, history. A restart
  clears everything. This is a deliberate privacy/simplicity choice (see
  `docs/decisions/`), not an oversight.
- History is currently unbounded — see "Known limitations".

## Networking & trust model

- The server binds `127.0.0.1` by default (`WT_HOST`/`WT_PORT` override) and
  **has no authentication**. The security boundary is the local machine.
- Setting `WT_HOST` to a non-loopback address exposes an unauthenticated
  message bus to the network. Only do this on trusted networks; there is no
  TLS or token support today.
- The GUI copies the MCP URL for pasting into agent configuration; no data
  leaves the machine. The website collects nothing (no cookies, no analytics).

## External dependencies

- **Flet >= 1.0,<2.0** — desktop GUI (pinned; the GUI uses 1.0 APIs).
- **aiohttp >= 3.9** — HTTP server for the MCP endpoint.
- The official `mcp` Python SDK is *not* a runtime dependency; the wire
  protocol is implemented directly (see `docs/decisions/0001`).

## Known limitations

- History/inbox growth is unbounded in long-running sessions.
- No persistence: restart loses agent presence and queued messages.
- No authentication/TLS on the MCP endpoint (local-only by default).
- Offline agents' messages are queued (status `IDLE` placeholder) but there is
  no delivery confirmation or expiry.
