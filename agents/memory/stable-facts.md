# Stable Project Facts

Concise facts future agents need. Update when reality changes; delete what
stops being true.

## Product

- Walkie-Talkie = Flet desktop GUI + local MCP server letting AI agents
  message each other; piggyback delivery inside normal tool results is the
  core value proposition (never break the agent's working loop).
- License GPL-3.0, Copyright (C) 2026 Hamza Shahbaz (see `Copyright`,
  `LICENSE`). New source files carry the same notice.

## Architecture constraints

- Two Python modules at repo root: `main.py` (GUI entry, `ft.run(main)`),
  `mcp_server.py` (`MeshHub` + `MCPServer`). Tests import them from the repo
  root via `conftest.py`.
- MCP server runs on a **dedicated thread with its own asyncio loop**;
  Flet owns a separate event loop. **Never touch Flet controls from the
  server thread** — signal via `main.ui_dirty` (see
  `docs/decisions/0004-thread-safe-ui-refresh.md`).
- All message state is in memory only; no persistence by decision
  (`docs/decisions/0003`).
- Server binds `127.0.0.1:8765` by default; `WT_HOST`/`WT_PORT` env vars are
  validated at startup (no `.env` loader, no dotenv dependency).

## Compatibility / tooling

- Python verified: **3.14.6**. Dependencies: `flet>=1.0.0,<2.0.0`,
  `aiohttp>=3.9.0`. Test runner: `pytest` (no plugins needed).
- The GUI is written against **Flet 1.0** APIs: `ft.run`, `ft.Button`,
  `ft.Border.all/only`, `ft.Padding.symmetric`, `ft.BoxFit`,
  `page.show_dialog`, `ft.CopyToClipboard`, `page.window.*`,
  `page.run_task`. Flet 0.x names (`ft.app`, `ft.ElevatedButton`,
  `ft.border.*`, `ft.ImageFit`, `page.set_clipboard`, `page.open`) are
  **gone** — `tests/unit/test_flet_api_surface.py` pins this.
- `ft.Image(src=...)` for local files is relative to `assets_dir`
  (default `assets/`): logo → `src="img/logo.svg"` (SVG is canonical; the PNG
  is only the og:image raster render).
- `ft.CopyToClipboard(...)` constructs a service via `ft.context.page`; it
  works inside `main()` under `ft.run` (context set by flet) and in tests only
  if `flet.controls.context._context_page` is set first.

## Recurring pitfalls

- `http.client`/`urllib` `read(amt)` on **chunked** responses blocks until
  `amt` bytes or EOF — never use it to sample the first SSE event; read the
  socket directly (see `_sse_read_first_event` in the integration tests).
- Port 8765 must be free to launch the GUI; tests never use it (ephemeral
  `port=0`).
- The website design rules are strict: flat, `border-radius: 0`,
  `transition: none` (enforced globally in `assets/css/style.css`) — do not
  reintroduce rounded corners or animations. Visual identity = warm cream
  `#f5f3ec` / deep forest `#121b15` with forest-green accent `#2f5d40` /
  sage `#8fbf9d`, built around the user's walkie-talkie logo (two agent
  heads). Type: **Outfit** (self-hosted, `assets/fonts/`, via
  `assets/css/fonts.css` + `@import`) for prose/headings + IBM Plex Mono
  (Google) for labels/code. Retint via the `--accent*` custom properties.
- Logo files: `assets/img/logo-icon.png` (nav/GUI/favicon tile, 256px),
  `assets/img/favicon.png` (64px), `assets/img/logo-full.png` (full lockup
  for README), `assets/img/logo.png` (512px og:image render). Source art
  stays outside the repo; regenerate tiles from it if the logo changes.
- Error pages: `403.html`, `404.html` (GitHub Pages default), `500.html`,
  `503.html` at repo root, sharing `.error-*` classes in style.css.
- `docs/*.html` are public user docs; Markdown subfolders in `docs/` are
  engineering docs (`docs/decisions/0002`).

## Verification commands (known good)

```bash
python3 -m py_compile main.py mcp_server.py
pytest                              # 49 tests
python3 tools/check_site_links.py   # 172 internal references
```
