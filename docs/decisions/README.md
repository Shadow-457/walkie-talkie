# Decision Records

Short, honest records of technical decisions: context, what we chose, what we
rejected, and consequences. Newest last. A decision is reversed by adding a
new record — never by editing history silently.

| # | Decision | Status |
|---|---|---|
| [0001](0001-hand-rolled-mcp-server-on-aiohttp.md) | Hand-rolled MCP JSON-RPC on aiohttp instead of the official MCP SDK | Accepted |
| [0002](0002-static-site-at-repo-root.md) | Marketing site stays at repository root; engineering docs live in Markdown subfolders of `docs/` | Accepted |
| [0003](0003-in-memory-message-store.md) | In-memory message store, no persistence | Accepted |
| [0004](0004-thread-safe-ui-refresh.md) | Cross-thread UI refresh via `threading.Event` + poll loop on Flet's event loop | Accepted |
