"""
Walkie-Talkie — Desktop GUI & MCP Controller
Copyright (C) 2026 Hamza Shahbaz — GNU GPL v3.0

UI Style:
- Strict Calm Minimalism (Sage/Forest greens, flat surfaces) with muted green accent
- Flat 0px sharp buttons, no rounded corners, no bloated animations
- Built with Flet 1.0

The GUI is a READ-ONLY mission control: it shows connected agents, their
per-agent conversations, code-line statistics (+/−), and the connection log.
The human operator can never send messages into the mesh — only connected
AI agents can communicate, through their MCP tools.

Configuration (read from the environment, see .env.example):
- WT_HOST: MCP bind address (default 127.0.0.1 — local-only by design)
- WT_PORT: MCP port (default 8765)
"""

import asyncio
import os
import threading

import flet as ft

from mcp_server import MCPServer, MeshHub


def _load_config():
    """Read and validate WT_HOST / WT_PORT from the environment."""
    host = os.environ.get("WT_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port_raw = str(os.environ.get("WT_PORT", "8765")).strip() or "8765"
    try:
        port = int(port_raw)
    except ValueError:
        raise SystemExit(f"WT_PORT must be an integer, got {port_raw!r}")
    if not 1 <= port <= 65535:
        raise SystemExit(f"WT_PORT must be between 1 and 65535, got {port}")
    return host, port


HOST, PORT = _load_config()
DISPLAY_HOST = "localhost" if HOST in ("127.0.0.1", "::1") else HOST
MCP_URL = f"http://{DISPLAY_HOST}:{PORT}/mcp"

# Theme colors (cream + deep forest, matching the walkie-talkie logo)
COLOR_BG = "#101710"          # deep forest charcoal
COLOR_SURFACE = "#16211a"     # elevated surface
COLOR_CARD = "#1c2b21"        # logo-green card layer
COLOR_BORDER = "#2c3b2f"      # soft green border
COLOR_TEXT = "#eceadf"        # warm cream white
COLOR_MUTED = "#9db09d"       # muted sage
COLOR_ACCENT = "#5f9e7f"      # calm forest green accent
COLOR_ONLINE = "#8fbf9d"      # soft sage status
COLOR_ADDED = "#8fbf9d"       # lines added (soft sage green)
COLOR_REMOVED = "#c99484"     # lines removed (muted clay)
COLOR_ACCENT_SOFT = "#1e2c23"  # tinted green chip wash

POLL_SECONDS = 0.4  # UI refresh cadence; cheap because sections diff first

# App zoom (Ctrl + / Ctrl - / Ctrl 0, or the top-bar zoom controls)
ZOOM_MIN = 0.5
ZOOM_MAX = 2.0
ZOOM_STEP = 0.1


def _clamp_zoom(value: float) -> float:
    """Keep the zoom factor inside [ZOOM_MIN, ZOOM_MAX], snapped to steps."""
    value = round(value, 2)
    return max(ZOOM_MIN, min(ZOOM_MAX, value))

hub = MeshHub()
server = MCPServer(hub=hub, host=HOST, port=PORT)

# Async background worker loop for MCP Server
server_loop = None
server_thread = None

# Hub listeners fire on the MCP server thread; Flet controls may only be
# touched on Flet's event loop, so listeners only raise this thread-safe
# flag and a poll loop inside main() drains it on the UI thread.
ui_dirty = threading.Event()
hub.add_listener(ui_dirty.set)

# Set by main(): the UI refresh entry point, so tests can trigger a render
# without the async poll loop running.
_ui_refresh = None


def run_server_loop():
    global server_loop
    server_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(server_loop)
    server_loop.run_until_complete(server.start())
    server_loop.run_forever()


def start_server_background():
    global server_thread
    if server_thread is not None and server_thread.is_alive():
        return
    server_thread = threading.Thread(target=run_server_loop, daemon=True)
    server_thread.start()


def _section_header(icon, label, trailing=None):
    return ft.Row([
        ft.Icon(icon, size=14, color=COLOR_ACCENT),
        ft.Text(label, size=10, weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                color=COLOR_MUTED),
        ft.Container(expand=True),
        *( [trailing] if trailing is not None else [] ),
    ], spacing=8)


def _empty_state(icon, title, subtitle=""):
    return ft.Container(
        padding=28,
        alignment=ft.Alignment.CENTER,
        content=ft.Column([
            ft.Icon(icon, size=36, color=COLOR_BORDER),
            ft.Container(height=10),
            ft.Text(title, size=11, weight=ft.FontWeight.BOLD,
                    font_family="Outfit Bold", color=COLOR_MUTED,
                    text_align=ft.TextAlign.CENTER),
            *([ft.Text(subtitle, size=10, color=COLOR_MUTED,
                       text_align=ft.TextAlign.CENTER)] if subtitle else []),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
    )


def main(page: ft.Page):
    page.title = "Walkie-Talkie — Agent Mesh Controller"
    page.window.width = 1240
    page.window.height = 760
    page.window.min_width = 980
    page.window.min_height = 620
    page.bgcolor = COLOR_BG
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.DARK

    # Self-hosted Outfit (downloaded to assets/fonts/); bold texts use the
    # separate "Outfit Bold" family (see font_family assignments below).
    page.fonts = {
        "Outfit": "fonts/Outfit-Regular.ttf",
        "Outfit Bold": "fonts/Outfit-Bold.ttf",
    }
    page.theme = ft.Theme(font_family="Outfit")

    # Start MCP server automatically
    start_server_background()

    # ------------------------------------------------------------------ state
    state = {
        "selected_agent": None,      # agent id shown in the center chat panel
        "agents_fp": None,           # fingerprint of last rendered agent list
        "chat_fp": None,             # fingerprint of last rendered chat
        "log_fp": None,              # fingerprint of last rendered connection log
    }

    # ---------------------------------------------------------------- top bar
    status_chip = ft.Container(
        bgcolor=COLOR_ACCENT_SOFT,
        border=ft.Border.all(1, COLOR_ACCENT),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        content=ft.Row([
            ft.Container(width=8, height=8, bgcolor=COLOR_ONLINE),
            ft.Text("SERVER RUNNING", size=10, weight=ft.FontWeight.BOLD,
                    font_family="Outfit Bold", color=COLOR_ONLINE),
        ], spacing=8)
    )

    url_text = ft.TextField(
        value=MCP_URL,
        read_only=True,
        text_size=12,
        height=38,
        width=300,
        border=ft.OutlineInputBorder(
            side=ft.BorderSide(1, COLOR_BORDER),
            border_radius=0,
        ),
        bgcolor=COLOR_SURFACE,
        color=COLOR_TEXT,
    )

    def copy_url(e):
        page.show_dialog(ft.SnackBar(
            ft.Text("Copied MCP URL to clipboard!", color=COLOR_TEXT,
                    weight=ft.FontWeight.BOLD, font_family="Outfit Bold"),
            bgcolor=COLOR_SURFACE,
            duration=2000,
        ))

    copy_btn = ft.Button(
        content=ft.Row([
            ft.Icon(ft.Icons.CONTENT_COPY, size=15, color=COLOR_BG),
            ft.Text("COPY URL", size=12, weight=ft.FontWeight.BOLD,
                    font_family="Outfit Bold", color=COLOR_BG),
        ], spacing=8),
        action=ft.CopyToClipboard(MCP_URL),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_ACCENT,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        ),
        on_click=copy_url,
    )

    # --- Zoom controls (Ctrl + / Ctrl - / Ctrl 0 also work) ---------------
    zoom_state = {"z": 1.0}
    zoom_label = ft.Container(
        ink=True,
        on_click=lambda e: apply_zoom(1.0),  # click the % to reset
        tooltip="Reset zoom (Ctrl+0)",
        padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        content=ft.Text("100%", size=11, weight=ft.FontWeight.BOLD,
                        font_family="Outfit Bold", color=COLOR_MUTED),
    )
    zoom_out_btn = ft.Button(
        content=ft.Icon(ft.Icons.ZOOM_OUT, size=15, color=COLOR_TEXT),
        tooltip="Zoom out (Ctrl+-)",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_SURFACE,
            side=ft.BorderSide(1, COLOR_BORDER),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        ),
        on_click=lambda e: apply_zoom(zoom_state["z"] - ZOOM_STEP),
    )
    zoom_in_btn = ft.Button(
        content=ft.Icon(ft.Icons.ZOOM_IN, size=15, color=COLOR_TEXT),
        tooltip="Zoom in (Ctrl+=)",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_SURFACE,
            side=ft.BorderSide(1, COLOR_BORDER),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        ),
        on_click=lambda e: apply_zoom(zoom_state["z"] + ZOOM_STEP),
    )

    def apply_zoom(value: float):
        zoom_state["z"] = _clamp_zoom(value)
        zoom_root.scale = ft.Scale(
            scale=zoom_state["z"], origin=ft.Alignment.TOP_LEFT,
        )
        zoom_label.content.value = f"{int(round(zoom_state['z'] * 100))}%"
        page.update()

    def on_keyboard(e):
        if not (getattr(e, "ctrl", False) or getattr(e, "meta", False)):
            return
        key = (getattr(e, "key", "") or "").lower()
        if key in ("=", "+"):
            apply_zoom(zoom_state["z"] + ZOOM_STEP)
        elif key in ("-", "_"):
            apply_zoom(zoom_state["z"] - ZOOM_STEP)
        elif key == "0":
            apply_zoom(1.0)

    top_bar = ft.Container(
        bgcolor=COLOR_SURFACE,
        border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        padding=ft.Padding.symmetric(horizontal=20, vertical=12),
        content=ft.Row([
            ft.Row([
                ft.Image(src="img/logo-icon.png", width=26, height=26,
                         fit=ft.BoxFit.CONTAIN),
                ft.Text("WALKIE-TALKIE", weight=ft.FontWeight.BOLD,
                        font_family="Outfit Bold", size=13, color=COLOR_TEXT),
            ], spacing=10),
            ft.VerticalDivider(width=16, color=COLOR_BORDER),
            status_chip,
            ft.Container(expand=True),
            url_text,
            ft.Container(width=10),
            copy_btn,
            ft.Container(width=10),
            zoom_out_btn,
            zoom_label,
            zoom_in_btn,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )

    # ------------------------------------------------------- left: agents list
    agents_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=6)
    agents_header_text = ft.Text("0 online", size=10, color=COLOR_MUTED)
    code_stats_column = ft.Column(spacing=6)

    def select_agent(agent_id):
        state["selected_agent"] = agent_id
        state["chat_fp"] = None  # force chat re-render
        render_chat()

    def _agent_row(agent):
        is_on = agent["status"] == "ONLINE"
        selected = state["selected_agent"] == agent["id"]
        return ft.Container(
            bgcolor=COLOR_ACCENT_SOFT if selected else (COLOR_CARD if is_on else COLOR_SURFACE),
            border=ft.Border.all(
                1, COLOR_ACCENT if selected else (COLOR_ONLINE if is_on else COLOR_BORDER)
            ),
            ink=True,
            on_click=lambda e, aid=agent["id"]: select_agent(aid),
            padding=10,
            content=ft.Row([
                ft.Container(width=8, height=8,
                             bgcolor=COLOR_ONLINE if is_on else COLOR_MUTED),
                ft.Column([
                    ft.Row([
                        ft.Text(agent["id"], weight=ft.FontWeight.BOLD,
                                font_family="Outfit Bold", size=12,
                                color=COLOR_TEXT, expand=True,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Container(
                            bgcolor=COLOR_ACCENT if is_on else COLOR_BORDER,
                            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                            content=ft.Text(
                                agent["status"], size=9,
                                weight=ft.FontWeight.BOLD,
                                font_family="Outfit Bold",
                                color=COLOR_BG if is_on else COLOR_MUTED,
                            ),
                        ),
                    ], spacing=6),
                    ft.Text(
                        f"seen {agent['last_seen']} · "
                        f"+{agent['lines_added']} −{agent['lines_removed']}"
                        + (f" · {agent['unread_count']} unread"
                           if agent["unread_count"] else ""),
                        size=9, color=COLOR_MUTED,
                    ),
                ], spacing=2, expand=True),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def render_agents():
        agents_data = hub.get_connected_agents()
        fp = tuple(
            (a["id"], a["status"], a["last_seen"], a["unread_count"],
             a["lines_added"], a["lines_removed"])
            for a in agents_data
        )
        if fp == state["agents_fp"]:
            return
        state["agents_fp"] = fp

        online = sum(1 for a in agents_data if a["status"] == "ONLINE")
        agents_header_text.value = f"{online} / {len(agents_data)} online"

        agents_column.controls.clear()
        if not agents_data:
            agents_column.controls.append(_empty_state(
                ft.Icons.HUB,
                "No agents connected yet",
                f"Plug {MCP_URL} into Cursor, Claude Desktop, or your agent script. "
                "Agents appear here under the exact ID they declare.",
            ))
        else:
            # Keep the selected agent pinned in view order; others by name.
            ordered = sorted(
                agents_data,
                key=lambda a: (a["id"] != state["selected_agent"], a["id"]),
            )
            for agent in ordered:
                agents_column.controls.append(_agent_row(agent))

        render_code_stats(agents_data)
        page.update()

    def render_code_stats(agents_data):
        stats = hub.get_code_stats()
        by_id = {a["id"]: a for a in agents_data}
        rows = [
            a for a in stats["agents"]
            if a["lines_added"] or a["lines_removed"] or a["files_changed"]
        ]
        rows.sort(key=lambda a: -(a["lines_added"] - a["lines_removed"]))

        code_stats_column.controls.clear()
        code_stats_column.controls.append(
            ft.Container(
                bgcolor=COLOR_SURFACE,
                border=ft.Border.all(1, COLOR_BORDER),
                padding=10,
                content=ft.Row([
                    ft.Text("MESH TOTAL", size=9, weight=ft.FontWeight.BOLD,
                            font_family="Outfit Bold", color=COLOR_MUTED,
                            expand=True),
                    ft.Text(f"+{stats['total']['lines_added']}", size=11,
                            weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                            color=COLOR_ADDED),
                    ft.Text(f"−{stats['total']['lines_removed']}", size=11,
                            weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                            color=COLOR_REMOVED),
                ], spacing=10),
            )
        )
        if not rows:
            code_stats_column.controls.append(ft.Container(
                padding=8,
                content=ft.Text(
                    "No code reports yet. Agents call wt_report_code after "
                    "editing files.",
                    size=9, color=COLOR_MUTED,
                ),
            ))
        for a in rows:
            is_on = by_id.get(a["id"], {}).get("status") == "ONLINE"
            code_stats_column.controls.append(ft.Container(
                bgcolor=COLOR_SURFACE,
                border=ft.Border.all(1, COLOR_BORDER),
                padding=10,
                content=ft.Column([
                    ft.Row([
                        ft.Container(width=6, height=6,
                                     bgcolor=COLOR_ONLINE if is_on else COLOR_BORDER),
                        ft.Text(a["id"], size=11, weight=ft.FontWeight.BOLD,
                                font_family="Outfit Bold", color=COLOR_TEXT,
                                expand=True, max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS),
                    ], spacing=6),
                    ft.Row([
                        ft.Text(f"+{a['lines_added']}", size=11, color=COLOR_ADDED,
                                weight=ft.FontWeight.BOLD, font_family="Outfit Bold"),
                        ft.Text(f"−{a['lines_removed']}", size=11, color=COLOR_REMOVED,
                                weight=ft.FontWeight.BOLD, font_family="Outfit Bold"),
                        ft.Container(expand=True),
                        ft.Text(f"{a['files_changed']} file(s)", size=9,
                                color=COLOR_MUTED),
                    ], spacing=8),
                ], spacing=4),
            ))

    # ------------------------------------------------------ center: agent chat
    chat_header_name = ft.Text(
        "Select an agent", size=12, weight=ft.FontWeight.BOLD,
        font_family="Outfit Bold", color=COLOR_MUTED,
    )
    chat_header_meta = ft.Text("", size=10, color=COLOR_MUTED)
    chat_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=6)

    def _chat_row(msg):
        is_code = msg.get("message", "").startswith("code report:")
        return ft.Container(
            bgcolor=COLOR_SURFACE,
            border=ft.Border.all(1, COLOR_BORDER),
            padding=10,
            content=ft.Row([
                ft.Icon(ft.Icons.CODE if is_code else (
                    ft.Icons.CAMPAIGN if msg["to"] in ("*", "all")
                    else ft.Icons.ARROW_FORWARD
                ), size=13, color=COLOR_MUTED if is_code else COLOR_ACCENT),
                ft.Text(msg["timestamp"], size=9, color=COLOR_MUTED, width=52),
                ft.Text(f"{msg['from']} → {msg['to']}", size=10,
                        weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                        color=COLOR_ACCENT if not is_code else COLOR_MUTED,
                        width=170, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(msg["message"], size=11,
                        color=COLOR_MUTED if is_code else COLOR_TEXT,
                        expand=True, selectable=True),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def render_chat():
        agent_id = state["selected_agent"]
        if agent_id is None:
            chat_header_name.value = "Select an agent"
            chat_header_name.color = COLOR_MUTED
            chat_header_meta.value = ""
            chat_column.controls.clear()
            chat_column.controls.append(_empty_state(
                ft.Icons.FORUM,
                "Click an agent on the left to read its conversation",
                "Every message the agent sends, receives, or hears as a "
                "broadcast shows up here.",
            ))
            page.update()
            return

        history = hub.get_agent_history(agent_id)
        fp = tuple(
            (m["timestamp"], m["from"], m["to"], m["message"]) for m in history
        )
        if fp == state["chat_fp"]:
            return
        state["chat_fp"] = fp

        agent = next(
            (a for a in hub.get_connected_agents() if a["id"] == agent_id), None
        )
        chat_header_name.value = agent_id
        chat_header_name.color = COLOR_TEXT
        if agent:
            chat_header_meta.value = (
                f"{agent['status']} · connected {agent['connected_at']} · "
                f"last seen {agent['last_seen']} · "
                f"+{agent['lines_added']} −{agent['lines_removed']} lines"
            )
        chat_column.controls.clear()
        if not history:
            chat_column.controls.append(_empty_state(
                ft.Icons.FORUM,
                f"No messages involving {agent_id} yet",
            ))
        else:
            for m in history:
                chat_column.controls.append(_chat_row(m))
        page.update()

    # ------------------------------------------------- right: connection log
    log_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4)

    _EVENT_COLORS = {
        "connect": COLOR_ONLINE,
        "reconnect": COLOR_ACCENT,
        "disconnect": COLOR_MUTED,
        "code": COLOR_ADDED,
    }
    _EVENT_ICONS = {
        "connect": ft.Icons.LOGIN,
        "reconnect": ft.Icons.REFRESH,
        "disconnect": ft.Icons.LOGOUT,
        "code": ft.Icons.CODE,
    }

    def _log_row(entry):
        color = _EVENT_COLORS.get(entry["event"], COLOR_MUTED)
        return ft.Container(
            padding=8,
            bgcolor=COLOR_SURFACE,
            border=ft.Border.all(1, COLOR_BORDER),
            content=ft.Row([
                ft.Icon(_EVENT_ICONS.get(entry["event"], ft.Icons.CIRCLE),
                        size=12, color=color),
                ft.Text(entry["timestamp"], size=9, color=COLOR_MUTED, width=118),
                ft.Text(entry["event"].upper(), size=9,
                        weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                        color=color, width=76),
                ft.Column([
                    ft.Text(entry["agent"], size=10, weight=ft.FontWeight.BOLD,
                            font_family="Outfit Bold", color=COLOR_TEXT,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    *([ft.Text(entry["detail"], size=9, color=COLOR_MUTED)]
                      if entry.get("detail") else []),
                ], spacing=1, expand=True),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def render_log():
        entries = hub.get_connection_log(limit=120)
        fp = tuple(
            (e["timestamp"], e["event"], e["agent"], e.get("detail", ""))
            for e in entries
        )
        if fp == state["log_fp"]:
            return
        state["log_fp"] = fp

        log_column.controls.clear()
        if not entries:
            log_column.controls.append(_empty_state(
                ft.Icons.HISTORY,
                "No AI has connected yet",
                "Connection events appear here the moment an agent "
                "handshakes with the MCP server.",
            ))
        else:
            for entry in entries:
                log_column.controls.append(_log_row(entry))
        page.update()

    # ------------------------------------------------------------- refresh loop
    def refresh_ui():
        render_agents()
        render_chat()
        render_log()

    # Drain cross-thread hub notifications on Flet's event loop; the MCP
    # server thread only ever raises ui_dirty and never touches controls.
    async def ui_poll_loop():
        while True:
            await asyncio.sleep(POLL_SECONDS)
            if ui_dirty.is_set():
                ui_dirty.clear()
                refresh_ui()

    # Initial Render
    refresh_ui()
    globals()["_ui_refresh"] = refresh_ui
    page.run_task(ui_poll_loop)

    # ------------------------------------------------------------- layout
    left_panel = ft.Container(
        width=320,
        bgcolor=COLOR_SURFACE,
        border=ft.Border.only(right=ft.BorderSide(1, COLOR_BORDER)),
        padding=14,
        content=ft.Column([
            _section_header(ft.Icons.HUB, "CONNECTED AGENTS", agents_header_text),
            ft.Divider(height=8, color=COLOR_BORDER),
            agents_column,
            ft.Divider(height=8, color=COLOR_BORDER),
            _section_header(ft.Icons.CODE, "CODE STATS"),
            ft.Container(height=6),
            ft.Column([code_stats_column], scroll=ft.ScrollMode.AUTO, expand=True),
        ], expand=True, spacing=4),
    )

    center_panel = ft.Container(
        bgcolor=COLOR_BG,
        padding=14,
        expand=True,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.FORUM, size=14, color=COLOR_ACCENT),
                chat_header_name,
                ft.Container(expand=True),
                chat_header_meta,
            ], spacing=8),
            ft.Divider(height=8, color=COLOR_BORDER),
            chat_column,
            ft.Divider(height=8, color=COLOR_BORDER),
            ft.Row([
                ft.Icon(ft.Icons.VISIBILITY, size=12, color=COLOR_MUTED),
                ft.Text("READ-ONLY — agents talk over MCP; the operator "
                        "cannot send messages", size=9, color=COLOR_MUTED),
                ft.Container(expand=True),
                ft.Icon(ft.Icons.BOLT, size=12, color=COLOR_ACCENT),
                ft.Text("Piggyback zero-interrupt delivery", size=9,
                        color=COLOR_ACCENT),
            ], spacing=6),
        ], expand=True, spacing=4),
    )

    right_panel = ft.Container(
        width=340,
        bgcolor=COLOR_SURFACE,
        border=ft.Border.only(left=ft.BorderSide(1, COLOR_BORDER)),
        padding=14,
        content=ft.Column([
            _section_header(ft.Icons.HISTORY, "CONNECTION LOG"),
            ft.Divider(height=8, color=COLOR_BORDER),
            log_column,
        ], expand=True, spacing=4),
    )

    # Root wrapper carries the app-wide zoom transform; top-left origin
    # keeps the top bar pinned while content scales right/down.
    zoom_root = ft.Container(
        scale=ft.Scale(scale=1.0, origin=ft.Alignment.TOP_LEFT),
        content=ft.Column([
            top_bar,
            ft.Row([left_panel, center_panel, right_panel], expand=True, spacing=0),
        ], spacing=0, expand=True),
        expand=True,
    )
    page.on_keyboard_event = on_keyboard
    page.add(zoom_root)


if __name__ == "__main__":
    ft.run(main)
