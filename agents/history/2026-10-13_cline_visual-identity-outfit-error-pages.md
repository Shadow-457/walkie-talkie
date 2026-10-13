# 2026-10-13 — cline — visual identity with user logo + Outfit font, error pages

## Task

From the user's `todo.md` (dropped into the repo): create a full visual
identity of walkie-talkie using **their logo** (two agent heads exchanging
speech bubbles, cream-on-forest) and the **Outfit** font from Google
("first donwload it"). Follow-up requests: custom **error pages**
(404 + common ones) and **remove the "Free & open source" badge** from the
hero; also remove the hero logo image when it looked wrong.

## Changes

- **Fonts downloaded and self-hosted** (`assets/fonts/`): Outfit 400–900 as
  latin + latin-ext woff2 (web) and Regular/Bold TTF (desktop GUI),
  registered via `assets/css/fonts.css` (`@import` from style.css). Google
  Fonts link in HTML now loads Plex Mono only (code/labels).
- **Logo integration**: processed the user's art into
  `assets/img/logo-icon.png` (256px nav/GUI tile), `favicon.png` (64px),
  `logo-full.png` (lockup, README), `logo.png` (512px og:image). Nav,
  favicons, README, and GUI all switched to these; the interim handset
  `logo.svg` was removed. Palette retinted from sage to the identity's
  **cream `#f5f3ec` / forest `#2f5d40` / deep `#121b15`** in both themes.
- **GUI (main.py)**: `page.fonts` registers Outfit + Outfit Bold, theme
  font set to Outfit, all bold texts use the `Outfit Bold` family (Flutter
  does not synthesize bold for custom fonts); logo tile, forest palette.
- **Error pages**: `403.html`, `404.html` (GitHub Pages default),
  `500.html`, `503.html` — shared template with logo, big mono status code
  in accent, message, and back/download/docs actions; `.error-*` styles in
  style.css.
- **Badge removed**: "Free & open source" status tag dropped from the hero.
- Docs/memory updated (release checklist, stable facts).

## Verification (actual results)

- `pytest -q` → **51 passed**; `tools/check_site_links.py` → **240 internal
  references, all resolve** (up from 172 — error pages included).
- **Firefox headless screenshots viewed**: index light, index dark, 404 —
  identity renders correctly in both themes; logo tile integrates in nav.
- **Live GUI launch** (`DISPLAY=:0`): `/health` healthy; window captured
  and viewed — Outfit typography, logo tile, cream-on-forest palette all
  correct. (Only a benign OpenGL frame-size warning, same as prior runs.)
- `py_compile` OK.

## Remaining issues

- The user's source PNGs (`Walkie Talkie Agent Connection Icon.png`,
  `logoonly.png`) and `todo.md` remain untracked in the repo root — the
  user's own drop-ins, not part of the committed assets.
- GUI bold text uses a second family name ("Outfit Bold") because Flet
  maps one file per family; fine but slightly unconventional.

## Handoff

- Identity facts live in `agents/memory/stable-facts.md` (palette, font
  files, logo file roles, error pages).
- New bold UI text: add `font_family="Outfit Bold"` alongside
  `weight=ft.FontWeight.BOLD` in main.py.
