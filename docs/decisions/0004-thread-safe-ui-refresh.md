# 0004 — Thread-safe UI refresh via `threading.Event` + poll loop

- **Status:** Accepted (2026-10)
- **Context:** The MCP server runs on a dedicated thread with its own asyncio
  loop while Flet's GUI runs on its own event loop. The original code called
  `refresh_ui()` (which calls `page.update()`) directly from hub listeners —
  i.e. from the server thread. Flet 1.0 serializes updates with
  `asyncio.Queue.put_nowait`, which is **not thread-safe**, and control trees
  must not be mutated concurrently with Flet's own event handlers.

## Decision

Hub listeners registered by the GUI only set `main.ui_dirty`, a
`threading.Event` (thread-safe). Inside `main()`, an async loop started with
`page.run_task(ui_poll_loop)` checks the flag every ~350 ms **on Flet's event
loop** and calls `refresh_ui()` there. Manual sends call `refresh_ui()`
directly (same thread) for instant feedback.

## Alternatives considered

- `asyncio.run_coroutine_threadsafe` from the server thread into Flet's loop —
  workable but couples the server to a specific loop reference and still needs
  a queue; more moving parts for the same result.
- Polling the hub state unconditionally on a timer (no flag) — simpler but
  rebuilds the UI ~3×/s even when idle; rejected for a "snappy, no wasted
  motion" UI.
- Direct cross-thread `page.update()` (the old behaviour) — unsafe, rejected.

## Consequences

- UI refresh latency is bounded by the 350 ms poll (visually instant enough;
  manual sends bypass it).
- New hub-driven UI features must follow the same pattern: mutate state in
  the server thread, render only on the Flet loop.
- Covered by `tests/unit/test_gui_build.py::test_ui_poll_loop_task_is_scheduled`.
