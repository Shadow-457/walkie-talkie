# 0001 — Hand-rolled MCP JSON-RPC server on aiohttp

- **Status:** Accepted (2026-10)
- **Context:** The product needs MCP clients (Claude Desktop, Cursor, custom
  scripts) to connect, list tools, and — crucially — receive peer messages
  *piggybacked inside ordinary tool results* (`_walkie_talkie_inbox`), plus a
  custom SSE `endpoint` event that carries agent identity. The official
  `mcp` Python SDK is available but ties us to its server abstractions,
  response shapes, and release cadence.

## Decision

Implement the MCP wire protocol directly in `mcp_server.py` using **aiohttp**,
covering exactly: `initialize`, `tools/list`, `tools/call`, `notifications/*`,
and an SSE transport endpoint. `requirements.txt` therefore contains only
`flet` and `aiohttp`.

## Alternatives considered

- **Official MCP Python SDK (`FastMCP`)** — faster to a compliant server, but
  piggybacking inside arbitrary tool results and the identity-carrying
  endpoint event would have required fighting its abstractions; adds a heavy
  dependency to a small desktop app.
- **`mcp` SDK client + custom server**: rejected for the same reasons on the
  server side.

## Consequences

- We own protocol conformance: `protocolVersion` pinned to `2024-11-05`, and
  `tests/integration/test_mcp_server.py` must be updated with any protocol
  change (`docs/protocols/README.md` is the contract).
- Input validation is our responsibility (implemented: `-32602` on bad tool
  arguments, `-32600/-32700` on bad bodies).
- If MCP drifts or we need resources/prompts transports, revisit — a migration
  to the official SDK remains open.
