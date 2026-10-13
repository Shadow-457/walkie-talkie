"""
Walkie-Talkie MCP Server & Mesh Hub
Copyright (C) 2026 Hamza Shahbaz — GNU GPL v3.0

Provides:
- In-memory agent registry and presence tracking
- Non-blocking queue per agent
- Piggybacked inbox attachment for responses
- Native MCP JSON-RPC 2.0 endpoints over HTTP/SSE
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from urllib.parse import urlencode

from aiohttp import web

logger = logging.getLogger("walkie_talkie.mcp")

# Delivery order inside an agent's inbox: lower rank is delivered first.
PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


class Message:
    def __init__(
        self,
        sender: str,
        recipient: str,
        text: str,
        timestamp: str = None,
        priority: str = "normal",
    ):
        self.sender = sender
        self.recipient = recipient
        self.text = text
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")
        self.priority = priority if priority in PRIORITY_RANK else "normal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.sender,
            "to": self.recipient,
            "message": self.text,
            "timestamp": self.timestamp,
            "priority": self.priority,
        }

class MeshHub:
    """Core message router and presence registry for Walkie-Talkie."""
    def __init__(self):
        # agent_id -> { "last_seen": timestamp, "status": "ONLINE", "inbox": [Message] }
        self.agents: Dict[str, Dict[str, Any]] = {}
        # global log of messages
        self.history: List[Message] = []
        # listeners (e.g. GUI updates)
        self.on_change_callbacks: List[Callable[[], None]] = []

    def add_listener(self, cb: Callable[[], None]):
        self.on_change_callbacks.append(cb)

    def _notify(self):
        for cb in self.on_change_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Error in notify callback: {e}")

    def register_or_heartbeat(self, agent_id: str):
        if not agent_id:
            return
        now_str = datetime.now().strftime("%H:%M:%S")
        if agent_id not in self.agents:
            self.agents[agent_id] = {
                "connected_at": now_str,
                "last_seen": now_str,
                "status": "ONLINE",
                "inbox": []
            }
        else:
            self.agents[agent_id]["last_seen"] = now_str
            self.agents[agent_id]["status"] = "ONLINE"
        self._notify()

    def disconnect_agent(self, agent_id: str):
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = "OFFLINE"
            self._notify()

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
        self.register_or_heartbeat(sender)
        msg = Message(
            sender=sender, recipient=recipient, text=text, priority=priority
        )
        self.history.append(msg)

        if recipient in ("*", "all"):
            # Broadcast to everyone else
            for target_id, data in self.agents.items():
                if target_id != sender and data["status"] == "ONLINE":
                    self._enqueue(data["inbox"], msg)
        else:
            # Targeted send
            if recipient not in self.agents:
                # auto-create recipient placeholder
                self.agents[recipient] = {
                    "connected_at": "-",
                    "last_seen": "-",
                    "status": "IDLE",
                    "inbox": []
                }
            self._enqueue(self.agents[recipient]["inbox"], msg)

        self._notify()
        return True

    def drain_inbox(self, agent_id: str, clear: bool = True) -> List[Dict[str, Any]]:
        self.register_or_heartbeat(agent_id)
        if agent_id in self.agents:
            inbox = self.agents[agent_id]["inbox"]
            messages = [m.to_dict() for m in inbox]
            if clear:
                self.agents[agent_id]["inbox"] = []
                self._notify()
            return messages
        return []

    def get_connected_agents(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": aid,
                "status": data["status"],
                "connected_at": data["connected_at"],
                "last_seen": data["last_seen"],
                "unread_count": len(data["inbox"])
            }
            for aid, data in self.agents.items()
        ]


class MCPServer:
    """Lightweight aiohttp server implementing MCP JSON-RPC 2.0 endpoints."""
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

        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_post("/mcp", self.handle_mcp)
        self.app.router.add_post("/mcp/messages", self.handle_mcp)
        self.app.router.add_get("/mcp/sse", self.handle_sse)

    async def handle_root(self, request):
        return web.json_response({
            "name": "Walkie-Talkie MCP Server",
            "version": "1.0.0",
            "status": "RUNNING",
            "mcp_endpoint": f"http://{self.host}:{self.bound_port}/mcp",
            "copyright": "Copyright (C) 2026 Hamza Shahbaz — GPL-3.0"
        })

    async def handle_health(self, request):
        return web.json_response({
            "status": "healthy",
            "agents_connected": len([a for a in self.hub.agents.values() if a["status"] == "ONLINE"]),
            "total_messages": len(self.hub.history)
        })

    async def handle_sse(self, request):
        # Identity is carried on the SSE URL (?agent_id=...) and echoed back
        # in the endpoint event so every subsequent POST keeps it. Without an
        # explicit id, presence is only tracked from actual tool calls.
        agent_id = (request.query.get("agent_id") or "").strip()
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
        endpoint = "/mcp"
        if agent_id:
            endpoint = "/mcp?" + urlencode({"agent_id": agent_id})
        await response.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())

        try:
            while True:
                await asyncio.sleep(5)
                if agent_id:
                    self.hub.register_or_heartbeat(agent_id)
                # Keep-alive heartbeat
                await response.write(b": keepalive\n\n")
        except (asyncio.CancelledError, ConnectionResetError):
            if agent_id:
                self.hub.disconnect_agent(agent_id)
        return response

    async def handle_mcp(self, request):
        """MCP JSON-RPC 2.0 processor."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }, status=400)

        msg_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(body, dict):
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}
            }, status=400)

        method = body.get("method")
        params = body.get("params", {})
        if not isinstance(params, dict):
            params = {}
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        # Identity precedence: explicit header > params > per-call argument >
        # query string (kept alive by the SSE endpoint event) > shared default.
        agent_id = (
            request.headers.get("X-Agent-ID")
            or params.get("agent_id")
            or arguments.get("agent_id")
            or request.query.get("agent_id")
            or "agent-mesh"
        )
        if not isinstance(agent_id, str):
            agent_id = str(agent_id)
        agent_id = agent_id.strip() or "agent-mesh"
        self.hub.register_or_heartbeat(agent_id)

        # Handle MCP Methods
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True}
                },
                "serverInfo": {
                    "name": "Walkie-Talkie Mesh",
                    "version": "1.0.0"
                }
            }
            return web.json_response({"jsonrpc": "2.0", "id": msg_id, "result": result})

        elif method == "tools/list":
            tools = [
                {
                    "name": "wt_send",
                    "description": "Send a message or data fragment to another agent in the Walkie-Talkie mesh.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Target agent ID (e.g. 'coder-agent') or '*' to broadcast."
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
                    "description": "List all active peer agents currently connected to the Walkie-Talkie mesh.",
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
                }
            ]
            return web.json_response({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}})

        elif method == "tools/call":
            tool_name = params.get("name")
            args = arguments

            # wt_check_inbox handles its own inbox access because `clear`
            # controls whether messages are dequeued or only peeked at.
            if tool_name == "wt_check_inbox":
                clear = args.get("clear", True)
                if not isinstance(clear, bool):
                    return self._rpc_error(msg_id, -32602, "'clear' must be a boolean")
                messages = self.hub.drain_inbox(agent_id, clear=clear)
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(messages, indent=2)}],
                        "messages": messages
                    }
                })

            if tool_name == "wt_send":
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

                # Piggyback pending peer messages alongside the send result.
                piggybacked_msgs = self.hub.drain_inbox(agent_id)
                self.hub.send_message(
                    sender=agent_id,
                    recipient=recipient,
                    text=text,
                    priority=priority,
                )

                content_text = f"Message successfully transmitted to '{recipient}'."
                if piggybacked_msgs:
                    content_text += f"\n\n[WALKIE-TALKIE INCOMING PEER MSGS]:\n{json.dumps(piggybacked_msgs, indent=2)}"

                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": content_text}],
                        "_walkie_talkie_inbox": piggybacked_msgs
                    }
                })

            if tool_name == "wt_list_agents":
                # Piggyback: incoming peer messages ride along any tool result.
                piggybacked_msgs = self.hub.drain_inbox(agent_id)
                agents = self.hub.get_connected_agents()
                content_text = f"Active Agents in Mesh:\n{json.dumps(agents, indent=2)}"
                if piggybacked_msgs:
                    content_text += f"\n\n[WALKIE-TALKIE INCOMING PEER MSGS]:\n{json.dumps(piggybacked_msgs, indent=2)}"

                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": content_text}],
                        "agents": agents,
                        "_walkie_talkie_inbox": piggybacked_msgs
                    }
                })

            return self._rpc_error(
                msg_id, -32601, f"Method/Tool '{tool_name}' not found"
            )

        elif isinstance(method, str) and method.startswith("notifications/"):
            # JSON-RPC notifications never receive a response (204 = accepted).
            return web.Response(status=204)

        return self._rpc_error(
            msg_id, -32601, f"Method '{method}' not implemented"
        )

    @staticmethod
    def _rpc_error(msg_id, code: int, message: str):
        return web.json_response({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message}
        })

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
