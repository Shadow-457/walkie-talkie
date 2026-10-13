# 2026-10-13 — cline — web redesign: calm green palette + new SVG logo

## Task

Make the website look better, replace the logo with a new one created as
SVG, and use a calm muted green color palette across the product.

## Findings

- The old design was Swiss/brutalist zinc (blue accent), all-IBM-Plex-Mono
  — functional but flat and generic.
- **Unstyled classes** made the site look unfinished: `.skip-link` (visible
  above the nav), `.btn-lg`, `.hero-meta`, `.hero-terminal`, `.quick-grid`,
  `.quick-copy`, `.cta-title`, `.cta-copy`, `.cta-actions`, `.mini-head`.
- The dark-mode nav logo relied on `filter: invert(1)` — incompatible with a
  colored logo (replaced with `brightness(1.5) saturate(1.05)`).
- Copy still referenced "monochrome with one blue accent" in the GUI mockup.

## Changes

**Design decision (stated per the design skill):** Minimalism/Swiss retained
(flat, sharp, snappy — mandated by `AGENTS.md`) with the single accent
swapped to calm muted green; IBM Plex Sans for prose + IBM Plex Mono for
labels/code/UI chrome; zero new motion.

- **`assets/img/logo.svg`** (new): geometric mesh mark — sharp square channel
  node + symmetric signal arcs, single muted green `#3e7a5c`, tuned (uniform
  2.5 strokes, 7×7 node) for 16px favicon legibility. Verified visually at
  512/48/16px. **`assets/img/logo.png`** regenerated (512px raster from the
  SVG) so `og:image` keeps a shareable format with the new art.
- **`assets/css/style.css`**: new green palette (light sage canvas /
  dark forest charcoal; `--accent`, `--accent-strong`, `--accent-soft`,
  `--on-accent`), accent-based buttons/hover states, green section labels,
  status tag, terminal title, feed routes, active tabs/agents/docs-cards,
  styled the 10 previously unstyled classes, `::selection`/`:focus-visible`
  accents, mono font groups, 96px section rhythm, skip-link a11y fix,
  responsive `.quick-grid`.
- **10 HTML files** (index, download, 8 docs): font link adds IBM Plex Sans;
  favicon + nav logo → `logo.svg`; theme-color meta + mockup copy updated.
- **`main.py`**: logo → `img/logo.svg`; palette → calm muted green on forest
  charcoal (`COLOR_ACCENT #5f9e7f`, `COLOR_ONLINE #7ec29a`, green-tinted
  neutrals).
- **Tests**: `test_gui_build.py` logo assertion → `img/logo.svg`.
- **Docs**: `docs/release/README.md` (SVG canonical, PNG is og render),
  `agents/memory/stable-facts.md` (logo fact + website design rules updated).

## Verification (actual results)

- `pytest -q` → **49 passed**.
- `python3 tools/check_site_links.py` → **172 internal references, all
  resolve**.
- **Firefox headless screenshots viewed** (the actual rendered pages): light
  + dark landing (full page), download, docs — all confirmed: green identity,
  Plex Sans prose, styled quick/CTA/mockup, dark-mode sage accents.
- **Live GUI launch** (`DISPLAY=:0`): window opens, `/health` healthy, log
  empty (0 warnings). Window captured via xdotool+import: **SVG logo renders
  in Flet**, calm green palette applied end-to-end.
- `git status` reviewed; no stray temp files (`.tmp_dark_index.html` removed).

## Remaining issues

- Google Fonts (Plex Sans/Mono) is an external dependency — offline visitors
  get system fallbacks (layout degrades gracefully).
- Logo is a single green tone; no alternate-mark variant for extreme
  small sizes (favicon tuned instead — verified at 16px).
- GitHub README dark mode shows the green logo fine (green reads on both
  backgrounds — by design).

## Handoff

- Palette lives entirely in CSS custom properties at the top of
  `assets/css/style.css`; both themes derive from `--accent`/`--accent-soft`/
  `--on-accent` — retint by editing those 3-4 values per theme.
- Logo source of truth is `assets/img/logo.svg`; regenerate the PNG with
  `rsvg-convert -w 512 -h 512 assets/img/logo.svg -o assets/img/logo.png`
  after any logo change.
- GUI colors are the `COLOR_*` constants at the top of `main.py`.
