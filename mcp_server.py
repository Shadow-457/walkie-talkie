"""
Walkie-Talkie MCP Server & Mesh Hub
Copyright (C) 2026 Hamza Shahbaz — GNU GPL v3.0

Provides:
- In-memory agent registry and presence tracking
- Non-blocking priority inbox per agent
- Piggybacked inbox attachment for responses (zero-interruption delivery)
- MCP JSON-RPC 2.0 over two transports:
    * Streamable HTTP: POST /mcp (JSON responses, Mcp-Session-Id sessions)
    * Classic SSE:     GET /mcp/sse (endpoint event) + POST /mcp/messages
      (202 accepted; JSON-RPC responses delivered as `event: message`
      frames on the SSE stream — the wire behaviour real MCP clients,
      e.g. Cline / Claude Desktop in SSE mode, expect)
- Per-agent message history, connection log, and code-line statistics

Identity policy:
- An agent is EXACTLY the ID it presents: X-Agent-ID header, ?agent_id=
  query, per-call agent_id argument, or the clientInfo.name its client
  declared during `initialize` (bound to the connection session).
- The server never invents, merges, renames, or assigns identities/roles.
  Mesh actions (tools/call) without any identity are rejected with
  error -32000.
"""

import asyncio
import json
import logging
import threading
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

from aiohttp import web

logger = logging.getLogger("walkie_talkie.mcp")

# Delivery order inside an agent's inbox: lower rank is delivered first.
PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}

HISTORY_LIMIT = 2000   # global mesh message ring
LOG_LIMIT = 500        # connection-event ring

DEFAULT_PROTOCOL_VERSION = "2024-11-05"


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Message:
    def __init__(
        self,
        sender: str,
        recipient: str,
        text: str,
        timestamp: str = None,
        priority: str = "normal",
        session: str = "chat",
    ):
        self.sender = sender
        self.recipient = recipient
        self.text = text
        self.timestamp = timestamp or _now()
        self.priority = priority if priority in PRIORITY_RANK else "normal"
        # "chat" for peer messages, "code" for code reports.
        self.session = session

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.sender,
            "to": self.recipient,
            "message": self.text,
            "timestamp": self.timestamp,
            "priority": self.priority,
        }


class MeshHub:
    """Core message router, presence registry, and stats keeper.

    All state is guarded by a re-entrant lock because the MCP server runs on
    its own thread while the GUI polls snapshots from the Flet thread.
    """

    def __init__(self):
        # agent_id -> presence/inbox/code record
        self.agents: Dict[str, Dict[str, Any]] = {}
        # global chronological log of chat + code-report messages
        self.history: List[Message] = []
        # connection lifecycle events (connect / disconnect / reconnect)
        self.connection_log: Deque[Dict[str, Any]] = deque(maxlen=LOG_LIMIT)
        # listeners (e.g. GUI updates)
        self.on_change_callbacks: List[Callable[[], None]] = []
        self._lock = threading.RLock()

    # -- listeners ----------------------------------------------------------

    def add_listener(self, cb: Callable[[], None]):
        self.on_change_callbacks.append(cb)

    def _notify(self):
        for cb in self.on_change_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Error in notify callback: {e}")

    # -- connection log -----------------------------------------------------

    def _log_event(self, event: str, agent_id: str, detail: str = "") -> Dict[str, Any]:
        entry = {
            "timestamp": _stamp(),
            "event": event,          # connect | disconnect | reconnect | code
            "agent": agent_id,
            "detail": detail,
        }
        self.connection_log.append(entry)
        return entry

    def get_connection_log(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Newest first."""
        with self._lock:
            entries = list(self.connection_log)
        return list(reversed(entries[-limit:]))

    # -- presence -----------------------------------------------------------

    def register_or_heartbeat(self, agent_id: str):
        if not isinstance(agent_id, str) or not agent_id.strip():
            return
        agent_id = agent_id.strip()
        now = _now()
        with self._lock:
            if agent_id not in self.agents:
                self.agents[agent_id] = {
                    "connected_at": now,
                    "last_seen": now,
                    "status": "ONLINE",
                    "inbox": [],
                    "code": {"added": 0, "removed": 0, "files": 0},
                }
                self._log_event("connect", agent_id)
            else:
                record = self.agents[agent_id]
                was_offline = record["status"] == "OFFLINE"
                record["last_seen"] = now
                record["status"] = "ONLINE"
                if was_offline:
                    self._log_event("reconnect", agent_id)
        self._notify()

    def disconnect_agent(self, agent_id: str):
        with self._lock:
            record = self.agents.get(agent_id)
            if record and record["status"] == "ONLINE":
                record["status"] = "OFFLINE"
                self._log_event("disconnect", agent_id)
        self._notify()

    # -- messaging ----------------------------------------------------------

    @staticmethod
    def _enqueue(inbox: List["Message"], msg: "Message") -> None:
        """Append a message and keep the inbox ordered by priority.

        Python's sort is stable, so messages of equal priority keep their
        original FIFO order.
        """
        inbox.append(msg)
        inbox.sort(key=lambda m: PRIORITY_RANK[m.priority])

    def send_message(
        self, sender: str, recipient: str, text: str, priority: str = "normal"
    ) -> bool:
        """Route a message. Returns False for unknown recipients — the hub
        never fabricates placeholder agents."""
        if not isinstance(sender, str) or not sender.strip():
            return False
        sender = sender.strip()
        self.register_or_heartbeat(sender)

        with self._lock:
            if recipient in ("*", "all"):
                targets = [
                    aid for aid, data in self.agents.items()
                    if aid != sender and data["status"] == "ONLINE"
                ]
            else:
                # Strict delivery: the recipient must have connected before.
                if recipient not in self.agents:
                    logger.warning(
                        "Rejected send to unknown recipient %r (no such agent)",
                        recipient,
                    )
                    return False
                targets = [recipient]

            msg = Message(
                sender=sender, recipient=recipient, text=text, priority=priority
            )
            self.history.append(msg)
            if len(self.history) > HISTORY_LIMIT:
                del self.history[: len(self.history) - HISTORY_LIMIT]

            for target_id in targets:
                self._enqueue(self.agents[target_id]["inbox"], msg)
        self._notify()
        return True

    def drain_inbox(self, agent_id: str, clear: bool = True) -> List[Dict[str, Any]]:
        if not isinstance(agent_id, str) or not agent_id.strip():
            return []
        agent_id = agent_id.strip()
        self.register_or_heartbeat(agent_id)
        with self._lock:
            record = self.agents.get(agent_id)
            if not record:
                return []
            messages = [m.to_dict() for m in record["inbox"]]
            if clear:
                record["inbox"] = []
        if clear:
            self._notify()
        return messages

    # -- code statistics ------------------------------------------------------

    def report_code(
        self,
        agent_id: str,
        lines_added: int,
        lines_removed: int,
        files_changed: int = 0,
        summary: str = "",
    ) -> Dict[str, Any]:
        """Accumulate a code report into the agent's running totals."""
        agent_id = agent_id.strip()
        self.register_or_heartbeat(agent_id)
        with self._lock:
            stats = self.agents[agent_id]["code"]
            stats["added"] += lines_added
            stats["removed"] += lines_removed
            stats["files"] += files_changed
            totals = dict(stats)

        self.history.append(Message(
            sender="system",
            recipient=agent_id,
            text=f"code report: +{lines_added} −{lines_removed}"
                 + (f" across {files_changed} file(s)" if files_changed else "")
                 + (f" — {summary}" if summary else ""),
            session="code",
        ))
        if len(self.history) > HISTORY_LIMIT:
            del self.history[: len(self.history) - HISTORY_LIMIT]
        self._log_event("code", agent_id, f"+{lines_added} −{lines_removed}")
        self._notify()
        return totals

    def get_code_stats(self) -> Dict[str, Any]:
        with self._lock:
            per_agent = [
                {
                    "id": aid,
                    "lines_added": data["code"]["added"],
                    "lines_removed": data["code"]["removed"],
                    "files_changed": data["code"]["files"],
                }
                for aid, data in self.agents.items()
            ]
            total = {
                "lines_added": sum(a["lines_added"] for a in per_agent),
                "lines_removed": sum(a["lines_removed"] for a in per_agent),
                "files_changed": sum(a["files_changed"] for a in per_agent),
            }
        return {"agents": per_agent, "total": total}

    # -- read models for the GUI ---------------------------------------------

    def get_connected_agents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "id": aid,
                    "status": data["status"],
                    "connected_at": data["connected_at"],
                    "last_seen": data["last_seen"],
                    "unread_count": len(data["inbox"]),
                    "lines_added": data["code"]["added"],
                    "lines_removed": data["code"]["removed"],
                }
                for aid, data in self.agents.items()
            ]

    def get_agent_history(self, agent_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Every message where the agent is the sender or a recipient, plus
        broadcasts sent by others (visible to the whole mesh) and code
        reports addressed to it. Oldest first."""
        with self._lock:
            rows = [
                m for m in self.history
                if m.sender == agent_id
                or m.recipient == agent_id
                or (m.recipient in ("*", "all") and m.sender != agent_id)
            ]
            rows = rows[-limit:]
            return [m.to_dict() for m in rows]


class MCPServer:
    """aiohttp server implementing MCP JSON-RPC 2.0 over Streamable HTTP
    and classic SSE transports."""

    IDENTITY_ERROR_CODE = -32000

    def __init__(self, hub: MeshHub, host: str = "127.0.0.1", port: int = 8765):
        self.hub = hub
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.is_running = False
        # Actual bound port (equals `port`, unless port=0 asked the OS for a
        # free one — used by tests).
        self.bound_port: int = port

        # Classic SSE transport sessions:
        #   session_id -> {"queue": asyncio.Queue, "agent_id": str | None}
        # JSON-RPC responses for POSTs to /mcp/messages are pushed onto the
        # queue and written to the SSE stream by handle_sse.
        self.sse_sessions: Dict[str, Dict[str, Any]] = {}
        # Streamable HTTP sessions: session_id -> {"agent_id": str | None}
        self.http_sessions: Dict[str, Dict[str, Any]] = {}

        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        # Streamable HTTP transport
        self.app.router.add_post("/mcp", self.handle_mcp)
        self.app.router.add_get("/mcp", self.handle_mcp_get)
        self.app.router.add_delete("/mcp", self.handle_mcp_delete)
        # Classic SSE transport
        self.app.router.add_get("/mcp/sse", self.handle_sse)
        self.app.router.add_post("/mcp/messages", self.handle_mcp_messages)

    # ------------------------------------------------------------------
    # Metadata endpoints
    # ------------------------------------------------------------------

    async def handle_root(self, request):
        return web.json_response({
            "name": "Walkie-Talkie MCP Server",
            "version": "2.1.0",
            "status": "RUNNING",
            "mcp_endpoint": f"http://{self.host}:{self.bound_port}/mcp",
            "sse_endpoint": f"http://{self.host}:{self.bound_port}/mcp/sse",
            "transports": ["streamable-http", "sse"],
            "copyright": "Copyright (C) 2026 Hamza Shahbaz — GPL-3.0"
        })

    async def handle_health(self, request):
        return web.json_response({
            "status": "healthy",
            "agents_connected": len([
                a for a in self.hub.agents.values() if a["status"] == "ONLINE"
            ]),
            "total_messages": len(self.hub.history)
        })

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_agent_id(identities: Dict[str, Any]) -> str:
        """Identity precedence: header > params > per-call argument > query >
        connection-session binding (query or clientInfo.name bound at
        initialize). Returns "" when the client presents no identity at all —
        the server never guesses or invents one."""
        for candidate in (
            identities.get("header"),
            identities.get("params"),
            identities.get("args"),
            identities.get("query"),
            identities.get("session"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                return str(candidate)
        return ""

    def _identity_error(self, msg_id) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": self.IDENTITY_ERROR_CODE,
                "message": (
                    "Unidentified agent: pass your agent identity via the "
                    "X-Agent-ID header, a ?agent_id= query parameter on the "
                    "server URL, or an agent_id tool argument. Walkie-Talkie "
                    "does not assign identities or roles automatically."
                ),
            },
        }

    # ------------------------------------------------------------------
    # Core JSON-RPC processor (transport-independent)
    # ------------------------------------------------------------------

    def _process_jsonrpc(
        self, body: Dict[str, Any], identities: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Process one JSON-RPC message. Returns (payload, client_name).

        payload is None for notifications (no response is sent).
        client_name is the clientInfo.name from `initialize` ("" otherwise);
        transports use it to bind a connection-level identity.
        """
        msg_id = body.get("id")
        method = body.get("method")
        params = body.get("params", {})
        if not isinstance(params, dict):
            params = {}
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        # JSON-RPC notifications never receive a response.
        if isinstance(method, str) and method.startswith("notifications/"):
            return None, ""

        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}, ""

        if method == "initialize":
            requested = params.get("protocolVersion")
            version = (
                requested
                if isinstance(requested, str) and requested.strip()
                else DEFAULT_PROTOCOL_VERSION
            )
            client_name = ""
            client_info = params.get("clientInfo")
            if isinstance(client_info, dict) and isinstance(client_info.get("name"), str):
                client_name = client_info["name"].strip()
            result = {
                "protocolVersion": version,
                "capabilities": {
                    "tools": {"listChanged": True}
                },
                "serverInfo": {
                    "name": "Walkie-Talkie Mesh",
                    "version": "2.1.0"
                }
            }
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}, client_name

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": self._tool_schemas()}}, ""

        if method == "tools/call":
            # Mesh actions require the caller to present an identity.
            agent_id = self._resolve_agent_id(identities)
            if not agent_id:
                return self._identity_error(msg_id), ""
            self.hub.register_or_heartbeat(agent_id)

            tool_name = params.get("name")
            args = arguments

            if tool_name == "wt_check_inbox":
                clear = args.get("clear", True)
                if not isinstance(clear, bool):
                    return self._rpc_error(msg_id, -32602, "'clear' must be a boolean"), ""
                messages = self.hub.drain_inbox(agent_id, clear=clear)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(messages, indent=2)}],
                        "messages": messages
                    }
                }, ""

            if tool_name == "wt_report_code":
                return self._handle_report_code(msg_id, agent_id, args), ""

            if tool_name == "wt_send":
                return self._handle_send(msg_id, agent_id, args), ""

            if tool_name == "wt_list_agents":
                # Piggyback: incoming peer messages ride along any tool result.
                piggybacked_msgs = self.hub.drain_inbox(agent_id)
                agents = self.hub.get_connected_agents()
                stats = self.hub.get_code_stats()
                content_text = f"Active Agents in Mesh:\n{json.dumps(agents, indent=2)}"
                content_text += (
                    f"\n\nCode totals:\n{json.dumps(stats['total'], indent=2)}"
                )
                if piggybacked_msgs:
                    content_text += f"\n\n[WALKIE-TALKIE INCOMING PEER MSGS]:\n{json.dumps(piggybacked_msgs, indent=2)}"

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": content_text}],
                        "agents": agents,
                        "code_stats": stats,
                        "_walkie_talkie_inbox": piggybacked_msgs
                    }
                }, ""

            return self._rpc_error(
                msg_id, -32601, f"Method/Tool '{tool_name}' not found"
            ), ""

        return self._rpc_error(
            msg_id, -32601, f"Method '{method}' not implemented"
        ), ""

    def _tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "wt_send",
                "description": "Send a message or data fragment to another agent in the Walkie-Talkie mesh. The recipient must already be connected (its ID appears in wt_list_agents).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "Target agent ID (exactly as shown by wt_list_agents) or '*' to broadcast to all other online agents."
                        },
                        "message": {
                            "type": "string",
                            "description": "The message or information to transmit."
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Delivery priority (default: 'normal'). High-priority messages are delivered before normal and low ones."
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Sender identity for this call; overrides connection-level identity (X-Agent-ID header or ?agent_id= query)."
                        }
                    },
                    "required": ["to", "message"]
                }
            },
            {
                "name": "wt_list_agents",
                "description": "List all peer agents currently known to the Walkie-Talkie mesh, including their status, unread counts, and code-line totals.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Caller identity for this call; overrides connection-level identity (X-Agent-ID header or ?agent_id= query)."
                        }
                    }
                }
            },
            {
                "name": "wt_check_inbox",
                "description": "Retrieve any unread messages from other agents in the Walkie-Talkie mesh.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "clear": {
                            "type": "boolean",
                            "description": "Whether to mark fetched messages as read (default: true)."
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Caller identity for this call; overrides connection-level identity (X-Agent-ID header or ?agent_id= query)."
                        }
                    }
                }
            },
            {
                "name": "wt_report_code",
                "description": "Report code changes made during this work session so the mesh tracks each agent's contribution. Call after editing files.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "lines_added": {
                            "type": "integer",
                            "minimum": 0,
                            "description": "Number of lines added."
                        },
                        "lines_removed": {
                            "type": "integer",
                            "minimum": 0,
                            "description": "Number of lines removed."
                        },
                        "files_changed": {
                            "type": "integer",
                            "minimum": 0,
                            "description": "Optional number of files touched."
                        },
                        "summary": {
                            "type": "string",
                            "description": "Optional one-line summary of the change."
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Caller identity for this call; overrides connection-level identity (X-Agent-ID header or ?agent_id= query)."
                        }
                    },
                    "required": ["lines_added", "lines_removed"]
                }
            },
        ]

    def _handle_send(self, msg_id, agent_id: str, args: dict) -> Dict[str, Any]:
        recipient = args.get("to", "*")
        text = args.get("message", "")
        priority = args.get("priority", "normal")

        if recipient is None:
            recipient = "*"
        if not isinstance(recipient, str) or not recipient.strip():
            return self._rpc_error(
                msg_id, -32602,
                "'to' must be a non-empty string (or '*' to broadcast)"
            )
        if not isinstance(text, str) or not text.strip():
            return self._rpc_error(
                msg_id, -32602, "'message' must be a non-empty string"
            )
        if priority is None:
            priority = "normal"
        if not isinstance(priority, str) or priority not in PRIORITY_RANK:
            return self._rpc_error(
                msg_id, -32602, "'priority' must be one of: low, normal, high"
            )
        recipient = recipient.strip()

        # Strict routing: no placeholder agents are fabricated for typos.
        if recipient not in ("*", "all") and recipient not in self.hub.agents:
            known = ", ".join(sorted(self.hub.agents.keys())) or "(none yet)"
            return self._rpc_error(
                msg_id, -32602,
                f"Unknown recipient '{recipient}'. That agent has never "
                f"connected to this mesh. Known agents: {known}. Use "
                f"wt_list_agents to see current peers."
            )

        # Piggyback pending peer messages alongside the send result.
        piggybacked_msgs = self.hub.drain_inbox(agent_id)
        delivered = self.hub.send_message(
            sender=agent_id,
            recipient=recipient,
            text=text,
            priority=priority,
        )
        if not delivered:
            return self._rpc_error(
                msg_id, -32602, f"Message could not be delivered to '{recipient}'."
            )

        content_text = f"Message successfully transmitted to '{recipient}'."
        if piggybacked_msgs:
            content_text += (
                f"\n\n[WALKIE-TALKIE INCOMING PEER MSGS]:\n"
                f"{json.dumps(piggybacked_msgs, indent=2)}"
            )

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": content_text}],
                "_walkie_talkie_inbox": piggybacked_msgs
            }
        }

    def _handle_report_code(self, msg_id, agent_id: str, args: dict) -> Dict[str, Any]:
        def _count(name: str, required: bool = False) -> Any:
            if name not in args:
                return None if required else 0
            value = args[name]
            if value is None:
                return None if required else 0
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return None
            return value

        # Schema-required fields must be present and valid.
        lines_added = _count("lines_added", required=True)
        lines_removed = _count("lines_removed", required=True)
        files_changed = _count("files_changed")
        summary = args.get("summary", "")

        if lines_added is None or lines_removed is None:
            return self._rpc_error(
                msg_id, -32602,
                "'lines_added' and 'lines_removed' must be integers >= 0"
            )
        if files_changed is None:
            return self._rpc_error(
                msg_id, -32602, "'files_changed' must be an integer >= 0"
            )
        if summary is None:
            summary = ""
        if not isinstance(summary, str):
            return self._rpc_error(msg_id, -32602, "'summary' must be a string")
        summary = summary.strip()[:300]

        totals = self.hub.report_code(
            agent_id=agent_id,
            lines_added=lines_added,
            lines_removed=lines_removed,
            files_changed=files_changed,
            summary=summary,
        )
        text = (
            f"Code report recorded: +{lines_added} −{lines_removed}"
            + (f" across {files_changed} file(s)" if files_changed else "")
            + f". Session totals for '{agent_id}': "
            + f"+{totals['added']} −{totals['removed']}."
        )
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "code_totals": totals,
            }
        }

    @staticmethod
    def _rpc_error(msg_id, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message}
        }

    # ------------------------------------------------------------------
    # Transport 1: Streamable HTTP  (POST /mcp, JSON responses)
    # ------------------------------------------------------------------

    async def handle_mcp(self, request):
        """Streamable HTTP transport. Requests get JSON responses directly;
        sessions are tracked with the Mcp-Session-Id header."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }, status=400)

        if not isinstance(body, dict):
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}
            }, status=400)

        params = body.get("params")
        if not isinstance(params, dict):
            params = {}
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        incoming_sid = request.headers.get("Mcp-Session-Id")
        session_agent = None
        if incoming_sid:
            session = self.http_sessions.get(incoming_sid)
            if session:
                session_agent = session.get("agent_id")

        identities = {
            "header": request.headers.get("X-Agent-ID"),
            "params": params,
            "args": arguments,
            "query": request.query.get("agent_id"),
            "session": session_agent,
        }
        payload, client_name = self._process_jsonrpc(body, identities)

        # Bind connection-level identity at initialize: explicit query wins,
        # otherwise the client's own declared clientInfo.name. The agent
        # becomes visible in the mesh the moment it handshakes.
        if body.get("method") == "initialize":
            bound = None
            for candidate in (request.query.get("agent_id"), client_name):
                if isinstance(candidate, str) and candidate.strip():
                    bound = candidate.strip()
                    break
            new_sid = uuid.uuid4().hex
            self.http_sessions[new_sid] = {"agent_id": bound}
            if bound:
                self.hub.register_or_heartbeat(bound)
            return web.json_response(payload, headers={"Mcp-Session-Id": new_sid})

        if incoming_sid and client_name:
            session = self.http_sessions.get(incoming_sid)
            if session and not session.get("agent_id"):
                session["agent_id"] = client_name

        # Notifications never receive a body.
        if payload is None:
            return web.Response(status=204)
        return web.json_response(payload)

    async def handle_mcp_get(self, request):
        """Streamable HTTP GET (server-initiated stream) is not offered."""
        return web.json_response({
            "error": "GET /mcp is not supported. POST JSON-RPC to /mcp, or "
                     "use the classic SSE transport at /mcp/sse."
        }, status=405, headers={"Allow": "POST, DELETE"})

    async def handle_mcp_delete(self, request):
        """Streamable HTTP session termination: drop the session and mark the
        agent offline once no connection (HTTP or SSE) still holds it."""
        sid = request.headers.get("Mcp-Session-Id") or ""
        record = self.http_sessions.pop(sid, None)
        if record and record.get("agent_id"):
            agent_id = record["agent_id"]
            still_connected = any(
                s.get("agent_id") == agent_id
                for s in self.http_sessions.values()
            ) or any(
                s.get("agent_id") == agent_id
                for s in self.sse_sessions.values()
            )
            if not still_connected:
                self.hub.disconnect_agent(agent_id)
        return web.Response(status=204)

    # ------------------------------------------------------------------
    # Transport 2: classic SSE  (GET /mcp/sse + POST /mcp/messages)
    # ------------------------------------------------------------------

    async def handle_sse(self, request):
        """Classic SSE transport. The endpoint event advertises the POST
        target; JSON-RPC responses are delivered as `event: message` frames
        on this stream (as real MCP clients expect)."""
        agent_id = (request.query.get("agent_id") or "").strip()
        sid = uuid.uuid4().hex
        queue: asyncio.Queue = asyncio.Queue()
        self.sse_sessions[sid] = {"queue": queue, "agent_id": agent_id or None}
        if agent_id:
            self.hub.register_or_heartbeat(agent_id)

        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            }
        )
        await response.prepare(request)

        base = f"{request.scheme}://{request.host}"
        endpoint = f"{base}/mcp/messages?sessionId={sid}"
        if agent_id:
            endpoint += "&agent_id=" + quote(agent_id)
        await response.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())

        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=5.0)
                    await response.write(
                        f"event: message\ndata: {payload}\n\n".encode()
                    )
                except asyncio.TimeoutError:
                    bound = self.sse_sessions.get(sid, {}).get("agent_id")
                    if bound:
                        self.hub.register_or_heartbeat(bound)
                    # Keep-alive heartbeat
                    await response.write(b": keepalive\n\n")
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            record = self.sse_sessions.pop(sid, None)
            bound = (record or {}).get("agent_id") or agent_id
            if bound:
                self.hub.disconnect_agent(bound)
        return response

    async def handle_mcp_messages(self, request):
        """Classic SSE transport POST target. Requests return 202 Accepted;
        the JSON-RPC response is written to the client's SSE stream."""
        sid = request.query.get("sessionId") or ""
        record = self.sse_sessions.get(sid)
        if record is None:
            return web.json_response({
                "error": "Unknown or expired SSE session. Reconnect to "
                         "/mcp/sse to obtain a fresh endpoint."
            }, status=404)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }, status=400)

        if not isinstance(body, dict):
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}
            }, status=400)

        params = body.get("params")
        if not isinstance(params, dict):
            params = {}
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        identities = {
            "header": request.headers.get("X-Agent-ID"),
            "params": params,
            "args": arguments,
            "query": request.query.get("agent_id"),
            "session": record.get("agent_id"),
        }
        payload, client_name = self._process_jsonrpc(body, identities)

        # A client that declared its name at initialize (and had no explicit
        # ?agent_id) keeps that name as its connection identity.
        if client_name and not record.get("agent_id"):
            record["agent_id"] = client_name
            self.hub.register_or_heartbeat(client_name)

        if payload is not None:
            record["queue"].put_nowait(json.dumps(payload))
        return web.Response(status=202)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        if self.is_running:
            return
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        server = getattr(self.site, "_server", None)
        if server is not None and server.sockets:
            self.bound_port = server.sockets[0].getsockname()[1]
        self.is_running = True
        logger.info(
            f"Walkie-Talkie MCP Server listening on http://{self.host}:{self.bound_port}/mcp"
        )

    async def stop(self):
        if not self.is_running:
            return
        if self.runner:
            await self.runner.cleanup()
        self.is_running = False
        logger.info("Walkie-Talkie MCP Server stopped.")
