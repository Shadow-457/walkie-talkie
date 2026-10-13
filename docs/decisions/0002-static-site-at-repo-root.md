# 0002 — Static site at repository root; engineering docs inside `docs/`

- **Status:** Accepted (2026-10)
- **Context:** The repository holds both a Python desktop app and a static
  marketing website (`index.html`, `download.html`, `docs/*.html`,
  `assets/`). The site's pages link to each other with root-relative paths
  (`docs/index.html`, `assets/...`) and are likely to be served by
  GitHub Pages-style hosting from the repository root or `/docs`.

## Decision

- Keep the website exactly where it is (root + `assets/` + `docs/*.html`).
  No file moves, no link rewrites, no deployment risk.
- Put engineering documentation in **Markdown subfolders alongside the public
  HTML pages**: `docs/architecture/`, `docs/development/`, `docs/decisions/`,
  `docs/protocols/`, `docs/testing/`, `docs/release/`, indexed by
  `docs/README.md`.

## Alternatives considered

- Move the site under `web/` and give `docs/` to Markdown only — cleaner on
  paper, but breaks every relative link and any Pages configuration; the
  skill governing this repo explicitly forbids moves that risk deployment for
  cosmetics.
- Put engineering docs in a top-level `dev-docs/` — diverges from the standard
  `docs/` convention used by the project's process documentation.

## Consequences

- If the site is published as-is, Markdown engineering docs are reachable by
  URL. They contain no secrets by policy (never store any under `docs/`).
- Contributors must know `docs/*.html` = user docs, `docs/<section>/` =
  engineering docs; `docs/README.md` explains this.
