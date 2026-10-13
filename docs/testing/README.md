# Testing

## Commands

```bash
pytest                       # everything (49 tests, ~11 s)
pytest tests/unit            # fast, no sockets except… none
pytest tests/integration     # live HTTP against an ephemeral-port server
python3 tools/check_site_links.py   # website link/asset integrity
```

Requires only `pytest` (no pytest-asyncio, no HTTP test plugins): integration
tests run the server on a background thread and use the stdlib `urllib`
client.

## Test categories

| File | What it proves |
|---|---|
| `tests/unit/test_mesh_hub.py` | Registry/presence, targeted + broadcast routing, inbox drain/peek, priority ordering, history order, listener isolation (a broken listener cannot break notifications). |
| `tests/unit/test_gui_build.py` | The full GUI constructs against a stub page: every Flet control, the displayed MCP URL, the `CopyToClipboard` action, the logo asset path, None-safe manual send, and that the UI poll loop is scheduled. Catches Flet API drift without a display. |
| `tests/unit/test_flet_api_surface.py` | A pinned list of the exact Flet 1.0 APIs `main.py` uses still exist (`ft.run`, `ft.Button`, `ft.Border.*`, `ft.Padding.*`, `ft.BoxFit`, `page.show_dialog`, `ft.CopyToClipboard`, window/layout properties). |
| `tests/integration/test_mcp_server.py` | Real server on an OS-assigned port: metadata endpoints, `initialize`, `tools/list` schemas, notification `204`, error codes (`-32700/-32600/-32601/-32602`), send→drain roundtrip, `clear=false` peek, piggyback delivery, failed sends not consuming the inbox, argument validation, priority ordering, identity via header/argument/query, unread counts, SSE endpoint advertisement. |

## Coverage boundaries / known limitations

- **No rendered GUI test**: the GUI test builds controls against a stub page;
  actual window rendering, theming, and clipboard clicks are verified manually
  (below). The environment used for CI-style runs is headless.
- **No real MCP-client end-to-end test**: nothing here drives the official
  `mcp` SDK client or Claude Desktop against the server. The SSE/JSON-RPC
  exchange is asserted at the wire level instead.
- **SSE keep-alive timing** (5 s ticks) is not waited out; tests assert the
  first endpoint event only. Server shutdown tolerates the resulting lag.
- **No load/stress testing**; the in-memory hub is single-process and
  unbounded.

## Manual verification (before a release)

1. `python main.py` — window opens, logo shows, status bar reads
   `SERVER RUNNING • http://localhost:8765/mcp`.
2. Click **COPY URL** — snackbar confirms; paste shows the URL.
3. `curl http://127.0.0.1:8765/health` — `{"status": "healthy", …}`.
4. Connect one MCP-capable client with `?agent_id=test-1`; the GUI lists it
   as ONLINE. Connect a second client; send `wt_send` between them and watch
   the log pane update within ~350 ms.
5. Website: `cd site && python3 -m http.server 8080`, open `index.html`, toggle theme, click **Copy URL** in the mockup,
   open Download and confirm the T&C dialog gates each download button, and
   dismiss the cookie notice (persists via localStorage).

## Adding tests

- Unit: pure functions/classes, no sockets, deterministic.
- Integration: use the `server` fixture (ephemeral port); never hardcode 8765.
- Bug fix ⇒ add a regression test that fails before the fix.
- Do not weaken assertions to get green; fix the code or update the contract
  deliberately (protocol changes also require `docs/protocols/README.md`).
