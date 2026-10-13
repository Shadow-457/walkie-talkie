# 2026-10-13 — cline — startup-skill baseline (process, fixes, tests, docs)

## Task

Apply the Startup Development Skill to the walkie-talkie repository: inspect
first, fix real defects, establish tests/documentation/work-history
infrastructure, verify everything by running it, and leave the repo easier
for the next developer or agent to work on — without discarding existing work
or moving files for cosmetics.

## Findings

1. **The desktop GUI could not run at all.** `main.py` was written against
   Flet 0.x while `flet>=0.25.0` resolves to Flet 1.0.3. Removed APIs in use:
   `ft.app(target=…)` (dead placeholder), `ft.ElevatedButton`,
   `ft.border.only/all`, `ft.ImageFit`, `ft.padding.symmetric`,
   `page.set_clipboard`, `page.open(...)`. Additionally
   `TextField.border_color/border_radius` are deprecated (removed in 1.3.0,
   inside the `<2.0.0` pin).
2. **Broken logo references** after the (pre-existing, uncommitted) logo move
   to `assets/img/`: `README.md` pointed at root `logo.png`; `main.py` used
   `src="logo.png"` (Flet resolves UI `src` relative to `assets_dir`, so the
   correct value is `img/logo.png`).
3. **Cross-thread UI race:** hub listeners called `page.update()` from the
   MCP server thread; Flet 1.0 serializes updates via non-thread-safe
   `asyncio.Queue.put_nowait`.
4. **Dead "Copy URL" button** on the landing page — `data-copy` had no JS
   handler.
5. **Documented-but-unimplemented server contract:** `priority` (docs/api.html,
   README) was ignored; `wt_check_inbox.clear` always dequeued; the SSE
   `endpoint` event dropped `?agent_id=`, so the documented per-agent identity
   never reached tool POSTs (all callers collapsed into `agent-mesh`).
6. **Input-validation gaps:** non-dict `params`/`arguments` crashed with 500;
   `wt_send` accepted empty/whitespace/non-string messages; unknown-method
   errors consumed the caller's piggybacked inbox.
7. **Missing skill deliverables:** no tests, no engineering docs, no
   `agents/` history/memory, no `.env.example`, thin `.gitignore`, README
   said `pip install flet mcp` (wrong deps), TRANSMIT crashed on empty input.

## Changes

- **`main.py`** — migrated to Flet 1.0 (`ft.run`, `ft.Button`,
  `ft.Border.*`, `ft.Padding.*`, `ft.BoxFit`, `page.show_dialog`,
  `ft.CopyToClipboard` action, `OutlineInputBorder`); logo → `img/logo.png`;
  `WT_HOST`/`WT_PORT` env config validated at startup with one `MCP_URL`
  constant; thread-safe refresh via `ui_dirty` Event + `page.run_task` poll
  loop (0.35 s); None-safe manual send; server-start guard.
- **`mcp_server.py`** — implemented `priority` (validated, ordered inbox
  enqueue, exposed in schema + envelope), `wt_check_inbox.clear` (peek vs
  drain), identity-carrying SSE `endpoint` event + re-heartbeat, identity
  precedence (header → params → argument → query → `agent-mesh`),
  `-32602/-32600` validation (no more 500s on malformed input), notifications
  answered with 204, piggyback drained only on successful tool calls,
  `bound_port` for port-0 tests, root endpoint uses bound port.
- **`assets/js/main.js`** — working `data-copy` clipboard handler with
  `execCommand` fallback and instant "Copied" feedback (no animation).
- **`README.md`** — fixed logo/install, added config, development commands,
  repository layout, honest tool reference incl. identity note.
- **`.gitignore`** — venvs, `.env*` (with `!.env.example`), caches, build/dist,
  editor state, logs. **`.env.example`** — `WT_HOST`/`WT_PORT` documented
  (read from process environment; no dotenv dependency).
- **`requirements.txt`** — `flet>=1.0.0,<2.0.0`, `aiohttp>=3.9.0`.
- **Tests (49)** — `conftest.py`; `tests/unit/test_mesh_hub.py` (routing,
  drain/peek, priority, listeners); `tests/unit/test_gui_build.py` (full GUI
  constructed against a stub page + context, URL display, clipboard action,
  logo asset existence, None-safe send, poll-loop scheduling);
  `tests/unit/test_flet_api_surface.py` (pins every Flet API the GUI uses);
  `tests/integration/test_mcp_server.py` (live HTTP on ephemeral port: protocol
  methods, schemas, error codes, roundtrip, piggyback, identity, priority,
  validation, SSE endpoint advertisement).
- **`tools/check_site_links.py`** — internal href/src checker for the site.
- **Docs** — `docs/README.md` (index distinguishing public HTML docs from
  engineering Markdown), `docs/architecture/`, `docs/development/`,
  `docs/protocols/` (full wire contract), `docs/testing/`,
  `docs/release/` (honest: no packaging exists yet), `docs/decisions/` with
  four ADRs (0001 hand-rolled MCP on aiohttp, 0002 site at repo root,
  0003 in-memory store, 0004 thread-safe UI refresh).
- **`agents/`** — README, `memory/stable-facts.md`, this report.

Files NOT touched: `AGENTS.md`, `LICENSE`, `Copyright`, `assets/css/style.css`,
`index.html`, `download.html`, `docs/*.html`, the pre-existing uncommitted
logo/css/index changes (user work preserved).

## Verification (actual results)

- `python3 -m py_compile main.py mcp_server.py tools/check_site_links.py` → OK.
- `pytest -q` → **49 passed** (~11 s, unit + integration, no plugins beyond pytest).
- `python3 tools/check_site_links.py` → **172 internal references, all resolve**.
- **Live launch (twice, DISPLAY=:0)**: GUI window opened; `curl /health` →
  `{"status": "healthy", …}`; `/` metadata correct. Second run (after the
  OutlineInputBorder fix): log **empty — zero warnings/errors**.
- `grep` for stale Flet 0.x APIs in source → none (only negative assertions
  in the guard test).
- `git status` reviewed before/after: only intended files added/modified;
  user's pre-existing uncommitted changes intact.

## Remaining issues / limitations

- Not verified: Windows/macOS builds (no packaging exists — `docs/release/`
  documents this; website download buttons currently link to GitHub Releases).
- No automated rendered-GUI test (headless CI); GUI verified by stub-page
  construction tests + two manual live launches.
- No end-to-end test with a real MCP SDK client (wire-level SSE/JSON-RPC is
  covered instead).
- History/inbox are unbounded and in-memory (deliberate; ADR 0003).
- MCP endpoint has no auth/TLS; local-only binding is the security boundary.
- Nothing was committed (not requested); working tree holds this work plus
  the user's earlier uncommitted website/logo changes.

## Handoff

- Read `agents/memory/stable-facts.md` first; protocol contract lives in
  `docs/protocols/README.md` and is enforced by the integration tests —
  change them together.
- GUI is Flet **1.0-only**; `tests/unit/test_flet_api_surface.py` fails
  precisely if a Flet upgrade removes an API the GUI uses.
- `WT_PORT` env var changes the GUI URL; `main.MCP_URL` is the single source.
- Website design rules are strict (flat, monochrome, zero radius, no
  animation) — enforced globally in `assets/css/style.css`.

