"""
Walkie-Talkie — Desktop GUI & MCP Controller
Copyright (C) 2026 Hamza Shahbaz — GNU GPL v3.0

UI Style:
- Strict Calm Minimalism (Sage/Forest greens, flat surfaces) with muted green accent
- Flat 0px sharp buttons, no rounded corners, no bloated animations
- Built with Flet 1.0

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
COLOR_ACCENT_SOFT = "#1e2c23"  # tinted green chip wash

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

def main(page: ft.Page):
    page.title = "Walkie-Talkie — Agent Mesh Controller"
    page.window.width = 1080
    page.window.height = 720
    page.window.min_width = 860
    page.window.min_height = 600
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

    # --- Top bar -----------------------------------------------------------
    status_chip = ft.Container(
        bgcolor=COLOR_ACCENT_SOFT,
        border=ft.Border.all(1, COLOR_ACCENT),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        content=ft.Row([
            ft.Container(width=8, height=8, bgcolor=COLOR_ONLINE),
            ft.Text("SERVER RUNNING", size=10, weight=ft.FontWeight.BOLD, font_family="Outfit Bold", color=COLOR_ONLINE),
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
        # The clipboard write itself runs client-side inside the click
        # gesture via the CopyToClipboard action; this only confirms it.
        page.show_dialog(ft.SnackBar(
            ft.Text("Copied MCP URL to clipboard!", color=COLOR_TEXT, weight=ft.FontWeight.BOLD, font_family="Outfit Bold"),
            bgcolor=COLOR_SURFACE,
            duration=2000
        ))

    copy_btn = ft.Button(
        content=ft.Row([
            ft.Icon(ft.Icons.CONTENT_COPY, size=15, color=COLOR_BG),
            ft.Text("COPY URL", size=12, weight=ft.FontWeight.BOLD, font_family="Outfit Bold", color=COLOR_BG),
        ], spacing=8),
        action=ft.CopyToClipboard(MCP_URL),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_ACCENT,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10)
        ),
        on_click=copy_url
    )

    def disconnect_all(e):
        for a in hub.agents.values():
            a["status"] = "OFFLINE"
        refresh_ui()

    stop_btn = ft.Button(
        content=ft.Row([
            ft.Icon(ft.Icons.LOGOUT, size=15, color=COLOR_TEXT),
            ft.Text("DISCONNECT ALL", size=12, weight=ft.FontWeight.BOLD, font_family="Outfit Bold", color=COLOR_TEXT),
        ], spacing=8),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_BG,
            side=ft.BorderSide(1, COLOR_BORDER),
            padding=ft.Padding.symmetric(horizontal=14, vertical=10)
        ),
        on_click=disconnect_all
    )

    # Top Status Bar
    top_bar = ft.Container(
        bgcolor=COLOR_SURFACE,
        border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        padding=ft.Padding.symmetric(horizontal=20, vertical=14),
        content=ft.Row([
            ft.Row([
                ft.Image(src="img/logo-icon.png", width=26, height=26, fit=ft.BoxFit.CONTAIN),
                ft.Text("WALKIE-TALKIE", weight=ft.FontWeight.BOLD, font_family="Outfit Bold", size=13, color=COLOR_TEXT),
            ], spacing=10),
            ft.VerticalDivider(width=20, color=COLOR_BORDER),
            status_chip,
            ft.Container(expand=True),
            url_text,
            ft.Container(width=10),
            copy_btn,
            ft.Container(width=10),
            stop_btn,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    )

    # Agents List Container
    agents_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=6)

    # Message Log Container
    logs_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4)

    agents_header_text = ft.Text("0 online", size=10, color=COLOR_MUTED)

    # Quick test sender inputs
    sender_input = ft.TextField(
        label="From Agent",
        value="human-operator",
        text_size=11,
        height=42,
        prefix=ft.Icon(ft.Icons.PERSON, size=16, color=COLOR_MUTED),
        bgcolor=COLOR_SURFACE,
        border=ft.OutlineInputBorder(
            side=ft.BorderSide(1, COLOR_BORDER),
            border_radius=0,
        ),
        width=170
    )
    target_input = ft.TextField(
        label="To (* for all)",
        value="*",
        text_size=11,
        height=42,
        prefix=ft.Icon(ft.Icons.ALTERNATE_EMAIL, size=16, color=COLOR_MUTED),
        bgcolor=COLOR_SURFACE,
        border=ft.OutlineInputBorder(
            side=ft.BorderSide(1, COLOR_BORDER),
            border_radius=0,
        ),
        width=140
    )
    msg_input = ft.TextField(
        label="Broadcast / Send Message to Swarm",
        hint_text="e.g. Pause task, critical update on branch...",
        text_size=11,
        height=42,
        prefix=ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=16, color=COLOR_MUTED),
        bgcolor=COLOR_SURFACE,
        border=ft.OutlineInputBorder(
            side=ft.BorderSide(1, COLOR_BORDER),
            border_radius=0,
        ),
        expand=True
    )

    def send_manual_msg(e):
        txt = (msg_input.value or "").strip()
        if not txt:
            return
        hub.send_message(
            sender=(sender_input.value or "").strip() or "human-operator",
            recipient=(target_input.value or "").strip() or "*",
            text=txt
        )
        msg_input.value = ""
        refresh_ui()

    send_btn = ft.Button(
        content=ft.Row([
            ft.Icon(ft.Icons.SEND, size=15, color=COLOR_BG),
            ft.Text("TRANSMIT", size=12, weight=ft.FontWeight.BOLD, font_family="Outfit Bold", color=COLOR_BG),
        ], spacing=8),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_ACCENT,
            padding=ft.Padding.symmetric(horizontal=18, vertical=10)
        ),
        on_click=send_manual_msg
    )

    def refresh_ui():
        # 1. Update Agents
        agents_data = hub.get_connected_agents()
        agents_column.controls.clear()
        online = sum(1 for a in agents_data if a["status"] == "ONLINE")
        agents_header_text.value = f"{online} / {len(agents_data)} online"

        if not agents_data:
            agents_column.controls.append(
                ft.Container(
                    padding=32,
                    content=ft.Column([
                        ft.Icon(ft.Icons.HUB, size=44, color=COLOR_BORDER),
                        ft.Container(height=14),
                        ft.Text(
                            "No agents connected yet",
                            size=12,
                            weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                            color=COLOR_MUTED,
                            text_align=ft.TextAlign.CENTER
                        ),
                        ft.Container(height=6),
                        ft.Text(
                            "Plug the MCP URL into Cursor, Claude Desktop, or your agent script.",
                            size=10,
                            color=COLOR_MUTED,
                            text_align=ft.TextAlign.CENTER
                        ),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                )
            )
        else:
            for a in agents_data:
                is_on = (a["status"] == "ONLINE")
                agents_column.controls.append(
                    ft.Container(
                        bgcolor=COLOR_CARD if is_on else COLOR_SURFACE,
                        border=ft.Border.all(1, COLOR_ACCENT if is_on else COLOR_BORDER),
                        border_radius=0,
                        padding=12,
                        content=ft.Row([
                            ft.Container(
                                width=8,
                                height=8,
                                bgcolor=COLOR_ONLINE if is_on else COLOR_MUTED,
                                border_radius=0
                            ),
                            ft.Column([
                                ft.Text(a["id"], weight=ft.FontWeight.BOLD, font_family="Outfit Bold", size=12, color=COLOR_TEXT),
                                ft.Text(f"Seen: {a['last_seen']} • Unread: {a['unread_count']}", size=10, color=COLOR_MUTED),
                            ], spacing=2, expand=True),
                            ft.Container(
                                bgcolor=COLOR_ACCENT if is_on else COLOR_BORDER,
                                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                border_radius=0,
                                content=ft.Text(
                                    a["status"],
                                    size=9,
                                    weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                                    color=COLOR_BG if is_on else COLOR_MUTED
                                )
                            )
                        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                    )
                )

        # 2. Update Logs
        logs_column.controls.clear()
        if not hub.history:
            logs_column.controls.append(
                ft.Container(
                    padding=32,
                    content=ft.Column([
                        ft.Icon(ft.Icons.FORUM, size=44, color=COLOR_BORDER),
                        ft.Container(height=14),
                        ft.Text(
                            "Awaiting transmissions between agents...",
                            size=12,
                            color=COLOR_MUTED,
                            text_align=ft.TextAlign.CENTER
                        ),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                )
            )
        else:
            for m in reversed(hub.history):
                is_broadcast = m.recipient in ("*", "all")
                logs_column.controls.append(
                    ft.Container(
                        bgcolor=COLOR_SURFACE,
                        border=ft.Border.all(1, COLOR_BORDER),
                        border_radius=0,
                        padding=10,
                        content=ft.Row([
                            ft.Text(m.timestamp, size=10, color=COLOR_MUTED, width=60),
                            ft.Icon(
                                ft.Icons.CAMPAIGN if is_broadcast else ft.Icons.ARROW_FORWARD,
                                size=14,
                                color=COLOR_ACCENT if is_broadcast else COLOR_MUTED
                            ),
                            ft.Text(
                                f"{m.sender} → {m.recipient}:",
                                size=11,
                                weight=ft.FontWeight.BOLD, font_family="Outfit Bold",
                                color=COLOR_ACCENT,
                                width=170
                            ),
                            ft.Text(m.text, size=11, color=COLOR_TEXT, expand=True),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                    )
                )

        page.update()

    # Drain cross-thread hub notifications on Flet's event loop; the MCP
    # server thread only ever raises ui_dirty and never touches controls.
    async def ui_poll_loop():
        while True:
            await asyncio.sleep(0.35)
            if ui_dirty.is_set():
                ui_dirty.clear()
                refresh_ui()

    # Initial Render
    refresh_ui()
    page.run_task(ui_poll_loop)

    # Main Body Layout
    left_panel = ft.Container(
        width=340,
        bgcolor=COLOR_SURFACE,
        border=ft.Border.only(right=ft.BorderSide(1, COLOR_BORDER)),
        padding=16,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.HUB, size=15, color=COLOR_ACCENT),
                ft.Text("CONNECTED AGENTS", size=11, weight=ft.FontWeight.BOLD, font_family="Outfit Bold", color=COLOR_MUTED),
                ft.Container(expand=True),
                agents_header_text,
            ], spacing=8),
            ft.Divider(height=10, color=COLOR_BORDER),
            agents_column,
            ft.Divider(height=10, color=COLOR_BORDER),
            ft.Row([
                ft.Icon(ft.Icons.SENSORS, size=13, color=COLOR_MUTED),
                ft.Text("local-only", size=10, color=COLOR_MUTED),
                ft.Container(expand=True),
                ft.Icon(ft.Icons.SHIELD, size=13, color=COLOR_MUTED),
                ft.Text("GPL-3.0", size=10, color=COLOR_MUTED),
            ], spacing=6),
        ], expand=True)
    )

    right_panel = ft.Container(
        bgcolor=COLOR_BG,
        padding=16,
        expand=True,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.FORUM, size=15, color=COLOR_ACCENT),
                ft.Text("REAL-TIME MESH LOG", size=11, weight=ft.FontWeight.BOLD, font_family="Outfit Bold", color=COLOR_MUTED),
                ft.Container(expand=True),
                ft.Icon(ft.Icons.BOLT, size=13, color=COLOR_ACCENT),
                ft.Text("Piggyback Zero-Interrupt Active", size=10, color=COLOR_ACCENT),
            ], spacing=8),
            ft.Divider(height=10, color=COLOR_BORDER),
            logs_column,
            ft.Divider(height=10, color=COLOR_BORDER),
            ft.Row([sender_input, target_input, msg_input, send_btn], spacing=8),
        ], expand=True)
    )

    page.add(
        top_bar,
        ft.Row([left_panel, right_panel], expand=True, spacing=0)
    )

if __name__ == "__main__":
    ft.run(main)
