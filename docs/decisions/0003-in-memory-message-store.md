# 0003 — In-memory message store, no persistence

- **Status:** Accepted (2026-10)
- **Context:** Agent presence, per-agent inboxes, and message history must
  live somewhere. The product pitch is "everything stays on your machine" and
  the target usage is short interactive sessions between local agents.

## Decision

Keep **all state in memory** (`MeshHub.agents`, inboxes, `history`). No
database, no files, no telemetry. Restarting the app clears everything.

## Alternatives considered

- SQLite persistence — survives restarts but writes message content to disk
  (weaker privacy story), adds schema/migration overhead, and no user has
  asked for it.
- Append-only JSON log — same privacy concerns, plus unbounded disk growth.

## Consequences

- Queued messages for agents that disconnect are lost on restart; the GUI and
  docs should not promise durability.
- History is unbounded within a session (known limitation in
  `docs/architecture/README.md`); if long-running sessions become common,
  add a bounded ring buffer and revisit this record.
- Tests are simple and fast: fixtures build a fresh `MeshHub` per test.
