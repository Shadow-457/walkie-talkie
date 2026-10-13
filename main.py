"""
Walkie-Talkie — Desktop GUI & MCP Controller
Copyright (C) 2026 Hamza Shahbaz — GNU GPL v3.0

UI Style:
- Strict Monochrome (Black, White, Zinc) with Royal Blue accent punchline
- Flat 0px sharp buttons, no rounded corners, no bloated animations
- Built with Flet
"""

import asyncio
import threading
import flet as ft
from mcp_server import MeshHub, MCPServer

# Theme colors (Eye-comfort Zinc/Obsidian palette)
COLOR_BG = "#0c0d11"
COLOR_SURFACE = "#15161f"
COLOR_CARD = "#191a24"
COLOR_BORDER = "#27272a"
COLOR_TEXT = "#e4e4e7"
COLOR_MUTED = "#a1a1aa"
COLOR_ACCENT = "#3b82f6"       # Electric Royal Blue
COLOR_ONLINE = "#22c55e"       # Active Green

hub = MeshHub()
server = MCPServer(hub=hub, host="127.0.0.1", port=8765)

# Async background worker loop for MCP Server
server_loop = None
server_thread = None

def run_server_loop():
    global server_loop
    server_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(server_loop)
    server_loop.run_until_complete(server.start())
    server_loop.run_forever()

def start_server_background():
    global server_thread
    server_thread = threading.Thread(target=run_server_loop, daemon=True)
    server_thread.start()

def main(page: ft.Page):
    page.title = "Walkie-Talkie — Agent Mesh Controller"
    page.window.width = 1000
    page.window.height = 680
    page.window.min_width = 800
    page.window.min_height = 550
    page.bgcolor = COLOR_BG
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.DARK

    # Start MCP server automatically
    start_server_background()

    # GUI Components
    status_dot = ft.Container(
        width=8,
        height=8,
        bgcolor=COLOR_ONLINE,
        border_radius=0
    )
    status_text = ft.Text(
        "SERVER RUNNING • 127.0.0.1:8765/mcp",
        size=11,
        weight=ft.FontWeight.BOLD,
        color=COLOR_TEXT
    )

    url_text = ft.TextField(
        value="http://localhost:8765/mcp",
        read_only=True,
        text_size=12,
        height=36,
        border_color=COLOR_BORDER,
        border_radius=0,
        bgcolor=COLOR_SURFACE,
        color=COLOR_TEXT,
        expand=True
    )

    def copy_url(e):
        page.set_clipboard("http://localhost:8765/mcp")
        page.open(ft.SnackBar(
            ft.Text("Copied MCP URL to clipboard!", color=COLOR_TEXT, weight=ft.FontWeight.BOLD),
            bgcolor=COLOR_SURFACE,
            duration=2000
        ))

    copy_btn = ft.ElevatedButton(
        "COPY URL",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_ACCENT,
            color=COLOR_TEXT,
            padding=ft.padding.symmetric(horizontal=16, vertical=10)
        ),
        on_click=copy_url
    )

    # Top Status Bar
    top_bar = ft.Container(
        bgcolor=COLOR_SURFACE,
        border=ft.border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        padding=ft.padding.symmetric(horizontal=20, vertical=12),
        content=ft.Row([
            ft.Row([
                ft.Image(src="logo.png", width=24, height=24, fit=ft.ImageFit.CONTAIN),
                ft.Text("WALKIE-TALKIE", weight=ft.FontWeight.BOLD, size=13, color=COLOR_TEXT),
            ], spacing=10),
            ft.VerticalDivider(width=20, color=COLOR_BORDER),
            ft.Row([status_dot, status_text], spacing=8),
            ft.Container(expand=True),
            ft.Container(width=340, content=url_text),
            copy_btn
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    )

    # Agents List Container
    agents_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=6)

    # Message Log Container
    logs_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4)

    # Quick test sender inputs
    sender_input = ft.TextField(
        label="From Agent",
        value="human-operator",
        text_size=11,
        height=40,
        bgcolor=COLOR_SURFACE,
        border_color=COLOR_BORDER,
        border_radius=0,
        width=140
    )
    target_input = ft.TextField(
        label="To (* for all)",
        value="*",
        text_size=11,
        height=40,
        bgcolor=COLOR_SURFACE,
        border_color=COLOR_BORDER,
        border_radius=0,
        width=120
    )
    msg_input = ft.TextField(
        label="Broadcast / Send Message to Swarm",
        hint_text="e.g. Pause task, critical update on branch...",
        text_size=11,
        height=40,
        bgcolor=COLOR_SURFACE,
        border_color=COLOR_BORDER,
        border_radius=0,
        expand=True
    )

    def send_manual_msg(e):
        txt = msg_input.value.strip()
        if not txt:
            return
        hub.send_message(
            sender=sender_input.value.strip() or "human-operator",
            recipient=target_input.value.strip() or "*",
            text=txt
        )
        msg_input.value = ""
        page.update()

    send_btn = ft.ElevatedButton(
        "TRANSMIT",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=COLOR_TEXT,
            color=COLOR_BG,
            padding=ft.padding.symmetric(horizontal=18, vertical=10)
        ),
        on_click=send_manual_msg
    )

    def refresh_ui():
        # 1. Update Agents
        agents_data = hub.get_connected_agents()
        agents_column.controls.clear()

        if not agents_data:
            agents_column.controls.append(
                ft.Container(
                    padding=20,
                    content=ft.Text(
                        "No agents connected yet.\nPlug MCP URL into Cursor, Claude Desktop, or your agent script.",
                        size=11,
                        color=COLOR_MUTED,
                        text_align=ft.TextAlign.CENTER
                    )
                )
            )
        else:
            for a in agents_data:
                is_on = (a["status"] == "ONLINE")
                agents_column.controls.append(
                    ft.Container(
                        bgcolor=COLOR_CARD if is_on else COLOR_SURFACE,
                        border=ft.border.all(1, COLOR_ACCENT if is_on else COLOR_BORDER),
                        border_radius=0,
                        padding=12,
                        content=ft.Row([
                            ft.Column([
                                ft.Text(a["id"], weight=ft.FontWeight.BOLD, size=12, color=COLOR_TEXT),
                                ft.Text(f"Seen: {a['last_seen']} • Unread: {a['unread_count']}", size=10, color=COLOR_MUTED),
                            ], spacing=2, expand=True),
                            ft.Container(
                                bgcolor=COLOR_ONLINE if is_on else COLOR_MUTED,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                border_radius=0,
                                content=ft.Text(a["status"], size=9, weight=ft.FontWeight.BOLD, color=COLOR_BG)
                            )
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                    )
                )

        # 2. Update Logs
        logs_column.controls.clear()
        if not hub.history:
            logs_column.controls.append(
                ft.Container(
                    padding=20,
                    content=ft.Text(
                        "Awaiting transmissions between agents...",
                        size=11,
                        color=COLOR_MUTED
                    )
                )
            )
        else:
            for m in reversed(hub.history):
                logs_column.controls.append(
                    ft.Container(
                        bgcolor=COLOR_SURFACE,
                        border=ft.border.all(1, COLOR_BORDER),
                        border_radius=0,
                        padding=10,
                        content=ft.Row([
                            ft.Text(m.timestamp, size=10, color=COLOR_MUTED, width=65),
                            ft.Text(f"{m.sender} → {m.recipient}:", size=11, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT, width=170),
                            ft.Text(m.text, size=11, color=COLOR_TEXT, expand=True),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
                    )
                )

        page.update()

    hub.add_listener(refresh_ui)

    # Initial Render
    refresh_ui()

    # Main Body Layout
    left_panel = ft.Container(
        width=320,
        bgcolor=COLOR_SURFACE,
        border=ft.border.only(right=ft.BorderSide(1, COLOR_BORDER)),
        padding=16,
        content=ft.Column([
            ft.Row([
                ft.Text("CONNECTED AGENTS", size=11, weight=ft.FontWeight.BOLD, color=COLOR_MUTED),
            ]),
            ft.Divider(height=10, color=COLOR_BORDER),
            agents_column
        ], expand=True)
    )

    right_panel = ft.Container(
        bgcolor=COLOR_BG,
        padding=16,
        expand=True,
        content=ft.Column([
            ft.Row([
                ft.Text("REAL-TIME MESH LOG", size=11, weight=ft.FontWeight.BOLD, color=COLOR_MUTED),
                ft.Text("Piggyback Zero-Interrupt Active", size=10, color=COLOR_ACCENT)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=10, color=COLOR_BORDER),
            logs_column,
            ft.Divider(height=10, color=COLOR_BORDER),
            ft.Row([sender_input, target_input, msg_input, send_btn], spacing=8)
        ], expand=True)
    )

    page.add(
        top_bar,
        ft.Row([left_panel, right_panel], expand=True, spacing=0)
    )

if __name__ == "__main__":
    ft.app(target=main)
