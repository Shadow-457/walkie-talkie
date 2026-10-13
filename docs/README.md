# Developer Documentation

This directory serves two audiences:

| Content | Audience | Location |
|---|---|---|
| End-user documentation (Getting Started, MCP Server, Agents, API, Legal) | Website visitors | `docs/*.html` — published with the site |
| Engineering documentation (this Markdown tree) | Contributors & AI agents | `docs/<section>/README.md` |

The HTML pages are the public product docs and are linked from the site
navigation; the Markdown tree is the internal engineering record. Both are
intentionally kept here so contributors find everything in one place. Neither
contains secrets — everything under `docs/` may be published.

## Engineering sections

- **[architecture/](architecture/README.md)** — components, data flows, threading, storage, networking, and the trust model.
- **[development/](development/README.md)** — environment setup, common commands, conventions, debugging.
- **[protocols/](protocols/README.md)** — HTTP endpoints and the MCP JSON-RPC contract (tools, identity, errors, compatibility).
- **[testing/](testing/README.md)** — test categories, commands, coverage boundaries, manual checks.
- **[decisions/](decisions/README.md)** — decision records: what we chose, alternatives, and why.
- **[release/](release/README.md)** — current packaging status, release checklist, known gaps.

## Related top-level files

- [`README.md`](../../README.md) — product overview, quickstart, tool reference.
- [`AGENTS.md`](../../AGENTS.md) — human-written product brief and design rules.
- [`Copyright`](../../Copyright) / [`LICENSE`](../../LICENSE) — GPL-3.0 notices.
