#!/usr/bin/env python3
"""
Walkie-Talkie Buddy Agent
Copyright (C) 2026 Hamza Shahbaz — GNU GPL v3.0

A tiny terminal agent that joins the Walkie-Talkie mesh as a second peer,
so you can watch two agents coordinate without a second MCP client.

It follows the mesh protocol exactly like a big agent would:
  1. announce itself on join (wt_send broadcast)
  2. park on wt_wait_for_messages — it gets pinged the moment anyone
     messages it (direct, broadcast, or @mention)
  3. reply to direct messages and mentions, never to plain broadcasts it
     merely overhears
  4. Ctrl+C to leave

Stdlib only — no dependencies beyond Python 3.10.

Usage:
    python3 examples/buddy_agent.py
    BUDDY_ID=researcher WT_URL=http://localhost:8765/mcp python3 examples/buddy_agent.py
"""

import json
import os
import sys
import time
import urllib.request

WT_URL = os.environ.get("WT_URL", "http://127.0.0.1:8765/mcp")
BUDDY_ID = os.environ.get("BUDDY_ID", "terminal-buddy")
COLOR = "\033[92m"   # green
DIM = "\033[2m"
RESET = "\033[0m"


def rpc(tool: str, args: dict) -> dict:
    """One MCP tools/call over Streamable HTTP, as this agent's identity."""
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 1_000_000,
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }
    req = urllib.request.Request(
        WT_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Agent-ID": BUDDY_ID},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def say(text: str):
    print(f"{COLOR}[{BUDDY_ID}]{RESET} {text}", flush=True)


def note(text: str):
    print(f"{DIM}  {text}{RESET}", flush=True)


def reply_text(msg: dict) -> str | None:
    """Decide whether (and what) to answer. Returns None to stay silent."""
    sender = msg.get("from", "")
    text = msg.get("message", "")
    if not text or sender in ("", "system"):
        return None

    mentioned = f"@{BUDDY_ID.lower()}" in text.lower()
    direct = msg.get("to") == BUDDY_ID
    if not (direct or mentioned):
        return None  # overhearing a broadcast is not a summons

    lower = text.lower()
    if "hello" in lower or "hi " in lower or lower.startswith("hi"):
        return f"Hey {sender}! Buddy online — tell me what you need."
    if "?" in text:
        return (
            f"Good question, {sender}. I'm a simple terminal buddy, but I'm "
            f"listening: say it again in a direct message and I'll ack."
        )
    if "ping" in lower:
        return "pong"
    return (
        f"Ack from {BUDDY_ID}: got your message"
        f"{' (mention, high priority)' if mentioned else ''} — '{text[:60]}'."
    )


def main():
    say(f"joining mesh at {WT_URL} …")
    agents = rpc("wt_list_agents", {})
    peers = [
        a["id"] for a in agents.get("result", {}).get("agents", [])
        if a["id"] != BUDDY_ID
    ]
    say(f"online. peers in the mesh: {', '.join(peers) if peers else '(none yet)'}")
    rpc("wt_send", {"to": "*", "message": f"{BUDDY_ID} has joined the mesh."})
    note("announced myself — waiting for pings (Ctrl+C to leave)")

    while True:
        try:
            data = rpc("wt_wait_for_messages", {"timeout": 55})
        except KeyboardInterrupt:
            break
        except urllib.error.URLError as err:
            # A 55s hold can brush against proxy/client limits; just re-park.
            note(f"re-parking after transport hiccup ({err.reason})")
            continue
        messages = data.get("result", {}).get("messages", [])
        for msg in messages:
            frm = msg.get("from", "?")
            note(f"ping from {frm}: {msg.get('message', '')[:70]}")
            answer = reply_text(msg)
            if answer:
                say(f"→ replying to {frm}")
                rpc("wt_send", {"to": frm, "message": answer})

    say("leaving the mesh. o7")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
    except ConnectionRefusedError:
        print("Walkie-Talkie is not reachable. Start the desktop app first.",
              file=sys.stderr)
        sys.exit(1)
