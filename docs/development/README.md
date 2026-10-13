# Development Guide

## Prerequisites

- Python **3.10+** (verified on 3.14.6)
- `pip install -r requirements.txt` (Flet 1.x, aiohttp)
- `pytest` for the test suite

No `.env` loader or other tooling is required.

## Setup

```bash
git clone https://github.com/Shadow-457/walkie-talkie.git
cd walkie-talkie
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt pytest
```

## Common commands

| Task | Command |
|---|---|
| Run the desktop app | `python main.py` |
| Run all tests | `pytest` |
| Unit tests only | `pytest tests/unit` |
| Integration tests only | `pytest tests/integration` |
| Check website links | `python3 tools/check_site_links.py` |
| Syntax check | `python3 -m py_compile main.py mcp_server.py` |

## Configuration

Read from the process environment (validated at startup, see `.env.example`):

- `WT_HOST` — bind address, default `127.0.0.1`.
- `WT_PORT` — port, default `8765`; must be an integer in 1–65535 or the app
  exits with a clear error.

Example: `WT_PORT=9000 python main.py`.

There is intentionally no `.env` file loader (no extra dependency for two
variables). Export them in your shell or launcher.

## Project conventions

- **License headers**: new source files carry the GPL-3.0 copyright line used
  in `main.py` / `mcp_server.py`.
- **UI style** (from `AGENTS.md`): flat, monochrome, sharp 0px corners, no
  decorative animations, snappy. Buttons are `ft.Button` with
  `RoundedRectangleBorder(radius=0)`.
- **Website style**: same rules in CSS — `assets/css/style.css` forces
  `border-radius: 0` and `transition: none` globally. Keep it that way.
- **Flet API**: write against Flet **1.0** (`ft.run`, `ft.Button`,
  `ft.Border.*`, `ft.Padding.*`, `ft.BoxFit`, `page.show_dialog`,
  `ft.CopyToClipboard`). `tests/unit/test_flet_api_surface.py` guards these
  names — do not weaken it; update `main.py` and the test together when Flet
  changes.
- **Threading**: never call Flet control APIs from the MCP server thread; use
  `main.ui_dirty` (see `docs/architecture/README.md`).
- **Tests**: unit tests are pure/deterministic; integration tests bind
  ephemeral ports (`port=0`) and must never require network access beyond
  `127.0.0.1`.

## Debugging

- Server logs: logger `walkie_talkie.mcp` (enable with
  `python -c "import logging; logging.basicConfig(level=logging.DEBUG)"`-style
  configuration if needed).
- Health check while the app runs: `curl http://127.0.0.1:8765/health`.
- Port conflict: the GUI and server share `WT_PORT`; change it rather than
  killing processes.
- Website: open `index.html` directly, or serve the repo root with
  `python3 -m http.server` and browse to `/index.html`.

## Local workflow

1. Inspect (`git status`, read affected files).
2. Small, focused changes; follow the conventions above.
3. Run `pytest` + `tools/check_site_links.py` for anything relevant.
4. Update the docs whose behaviour you changed.
5. Record substantial work in `agents/history/` (see `agents/README.md`).
