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
from aiohttp import web

logger = logging.getLogger("walkie_talkie.mcp")

class Message:
    def __init__(self, sender: str, recipient: str, text: str, timestamp: str = None):
        self.sender = sender
        self.recipient = recipient
        self.text = text
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.sender,
            "to": self.recipient,
            "message": self.text,
            "timestamp": self.timestamp,
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

    def send_message(self, sender: str, recipient: str, text: str) -> bool:
        self.register_or_heartbeat(sender)
        msg = Message(sender=sender, recipient=recipient, text=text)
        self.history.append(msg)

        if recipient in ("*", "all"):
            # Broadcast to everyone else
            for target_id, data in self.agents.items():
                if target_id != sender and data["status"] == "ONLINE":
                    data["inbox"].append(msg)
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
            self.agents[recipient]["inbox"].append(msg)

        self._notify()
        return True

    def drain_inbox(self, agent_id: str) -> List[Dict[str, Any]]:
        self.register_or_heartbeat(agent_id)
        if agent_id in self.agents:
            inbox = self.agents[agent_id]["inbox"]
            messages = [m.to_dict() for m in inbox]
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
            "mcp_endpoint": f"http://{self.host}:{self.port}/mcp",
            "copyright": "Copyright (C) 2026 Hamza Shahbaz — GPL-3.0"
        })

    async def handle_health(self, request):
        return web.json_response({
            "status": "healthy",
            "agents_connected": len([a for a in self.hub.agents.values() if a["status"] == "ONLINE"]),
            "total_messages": len(self.hub.history)
        })

    async def handle_sse(self, request):
        agent_id = request.query.get("agent_id", "anonymous-agent")
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
        await response.write(b"event: endpoint\ndata: /mcp\n\n")

        try:
            while True:
                await asyncio.sleep(5)
                # Keep-alive heartbeat
                await response.write(b": keepalive\n\n")
        except (asyncio.CancelledError, ConnectionResetError):
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

        msg_id = body.get("id")
        method = body.get("method")
        params = body.get("params", {})

        agent_id = (
            request.headers.get("X-Agent-ID") or 
            params.get("agent_id") or 
            params.get("arguments", {}).get("agent_id") or 
            request.query.get("agent_id") or 
            "agent-mesh"
        )
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
                        "properties": {}
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
                            }
                        }
                    }
                }
            ]
            return web.json_response({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}})

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})

            # 1. Piggyback: Always check if the calling agent has incoming unread messages!
            piggybacked_msgs = self.hub.drain_inbox(agent_id)

            if tool_name == "wt_send":
                recipient = args.get("to", "*")
                text = args.get("message", "")
                self.hub.send_message(sender=agent_id, recipient=recipient, text=text)
                
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

            elif tool_name == "wt_list_agents":
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

            elif tool_name == "wt_check_inbox":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(piggybacked_msgs, indent=2)}],
                        "messages": piggybacked_msgs
                    }
                })

            else:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method/Tool '{tool_name}' not found"}
                })

        elif method == "notifications/initialized":
            return web.Response(status=204)

        return web.json_response({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method '{method}' not implemented"}
        })

    async def start(self):
        if self.is_running:
            return
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        self.is_running = True
        logger.info(f"Walkie-Talkie MCP Server listening on http://{self.host}:{self.port}/mcp")

    async def stop(self):
        if not self.is_running:
            return
        if self.runner:
            await self.runner.cleanup()
        self.is_running = False
        logger.info("Walkie-Talkie MCP Server stopped.")
