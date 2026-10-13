# AI Agent Work Records

This directory holds durable, focused records for AI agents (and humans)
working on this repository. It has three parts:

```text
agents/
├── README.md      # this file
├── history/       # one report per substantial task
└── memory/        # stable facts future agents must not rediscover
```

## History reports

Create one file per substantial task:

```text
agents/history/YYYY-MM-DD_<agent>_<task-slug>.md
```

Example: `agents/history/2026-10-13_cline_startup-skill-baseline.md`

Every report contains:

- **Task** — what was requested.
- **Findings** — problems discovered during inspection.
- **Changes** — files touched and why.
- **Verification** — commands run and their *actual* results.
- **Remaining issues** — known failures, limitations, unverified behaviour.
- **Handoff** — what the next agent needs to know.

Rules:

- Keep reports short and factual. No conversation dumps.
- Never store secrets, tokens, or credentials here or in `memory/`.
- Do not rewrite existing reports; add a new one for follow-up work.

## Memory

`memory/stable-facts.md` stores only facts that stay true across tasks:
architecture constraints, compatibility requirements, recurring pitfalls, and
commands that are known to work. Update it when a stable fact changes — and
delete facts that stop being true rather than contradicting them.
