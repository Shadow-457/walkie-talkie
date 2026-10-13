"""Integration tests: a real MCPServer on an ephemeral port, real HTTP calls.

The server runs on a background thread with its own event loop (the same
pattern the GUI uses in main.py). Requests are made with the stdlib
urllib client so no extra test dependencies are needed.
"""

import asyncio
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from mcp_server import MCPServer, MeshHub


@pytest.fixture
def server():
    hub = MeshHub()
    mcp = MCPServer(hub=hub, host="127.0.0.1", port=0)  # port 0 = OS-assigned
    loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(mcp.start())
        loop.run_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    deadline = time.time() + 5
    while not mcp.is_running:
        if time.time() > deadline:
            raise RuntimeError("MCP server did not start within 5s")
        time.sleep(0.02)
    assert mcp.is_running

    base_url = f"http://127.0.0.1:{mcp.bound_port}"
    yield base_url, hub, mcp

    async def shutdown():
        await mcp.stop()

    try:
        # The SSE keep-alive handler only notices a dropped client on its
        # next 5s tick, so cleanup can legitimately take a little longer.
        asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout=10)
    except Exception:
        # Best-effort shutdown: the loop is stopped and the thread is a
        # daemon either way; a wedged SSE handler must not fail the test.
        pass
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)


def _rpc(base_url, payload, agent_id=None, path="/mcp"):
    """POST a JSON-RPC payload; returns (http_status, parsed_json_or_str)."""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if agent_id:
        headers["X-Agent-ID"] = agent_id
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            # 204 responses legitimately carry no body.
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a JSON body
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def _get(base_url, path):
    with urllib.request.urlopen(base_url + path, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _sse_read_first_event(base_url, path, timeout=5):
    """Read the raw SSE response up to the first event via a plain socket.

    http.client's read(amt) on a chunked response blocks until it has amt
    bytes (or EOF), which never happens for an SSE stream that only sends
    one small event up front — so read the wire directly instead.
    """
    import socket as socket_mod

    host, _, port = base_url.partition("//")[2].partition(":")
    sock = socket_mod.create_connection((host, int(port)), timeout=timeout)
    try:
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Accept: text/event-stream\r\n\r\n"
        ).encode("utf-8")
        sock.sendall(request)
        sock.settimeout(timeout)
        blob = b""
        while b"\r\n\r\n" not in blob or b"\n\n" not in blob.partition(b"\r\n\r\n")[2]:
            try:
                data = sock.recv(4096)
            except OSError:
                break
            if not data:
                break
            blob += data
        return blob
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# Metadata endpoints
# ---------------------------------------------------------------------------

def test_root_endpoint_advertises_mcp_url(server):
    base_url, _hub, mcp = server
    status, data = _get(base_url, "/")
    assert status == 200
    assert data["name"] == "Walkie-Talkie MCP Server"
    assert data["status"] == "RUNNING"
    assert data["mcp_endpoint"].endswith("/mcp")
    assert str(mcp.bound_port) in data["mcp_endpoint"]


def test_health_endpoint_counts_messages(server):
    base_url, _hub, _mcp = server
    status, data = _get(base_url, "/health")
    assert status == 200
    assert data["status"] == "healthy"
    assert data["total_messages"] == 0

    _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send", "arguments": {"to": "*", "message": "ping"}},
    }, agent_id="health-agent")

    status, data = _get(base_url, "/health")
    assert data["total_messages"] == 1


# ---------------------------------------------------------------------------
# MCP protocol methods
# ---------------------------------------------------------------------------

def test_initialize_returns_protocol_info(server):
    base_url, _hub, _mcp = server
    status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
    }, agent_id="init-agent")
    assert status == 200
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["result"]["protocolVersion"] == "2024-11-05"
    assert data["result"]["serverInfo"]["name"] == "Walkie-Talkie Mesh"
    assert "tools" in data["result"]["capabilities"]


def test_tools_list_exposes_three_wt_tools_with_schemas(server):
    base_url, _hub, _mcp = server
    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
    }, agent_id="list-agent")

    tools = {t["name"]: t for t in data["result"]["tools"]}
    assert set(tools) == {"wt_send", "wt_list_agents", "wt_check_inbox"}

    send_schema = tools["wt_send"]["inputSchema"]
    assert send_schema["required"] == ["to", "message"]
    assert send_schema["properties"]["priority"]["enum"] == ["low", "normal", "high"]
    assert "agent_id" in send_schema["properties"]

    inbox_schema = tools["wt_check_inbox"]["inputSchema"]
    assert inbox_schema["properties"]["clear"]["type"] == "boolean"


def test_notifications_receive_204_and_no_body(server):
    base_url, _hub, _mcp = server
    status, _data = _rpc(base_url, {
        "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
    }, agent_id="notif-agent")
    assert status == 204


def test_unknown_method_returns_method_not_found(server):
    base_url, _hub, _mcp = server
    status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 9, "method": "resources/list", "params": {},
    })
    assert status == 200
    assert data["error"]["code"] == -32601


def test_unknown_tool_returns_method_not_found(server):
    base_url, _hub, _mcp = server
    status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 10, "method": "tools/call",
        "params": {"name": "wt_nope", "arguments": {}},
    })
    assert status == 200
    assert data["error"]["code"] == -32601


def test_invalid_json_returns_parse_error(server):
    base_url, _hub, _mcp = server
    req = urllib.request.Request(
        base_url + "/mcp", data=b"{not json",
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read()
    assert status == 400
    assert json.loads(body)["error"]["code"] == -32700


def test_non_object_body_returns_invalid_request(server):
    base_url, _hub, _mcp = server
    status, data = _rpc(base_url, [1, 2, 3])
    assert status == 400
    assert data["error"]["code"] == -32600


# ---------------------------------------------------------------------------
# Messaging flow: identity, piggyback, priority, clear
# ---------------------------------------------------------------------------

def test_send_then_check_inbox_roundtrip(server):
    base_url, _hub, _mcp = server

    status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send",
                   "arguments": {"to": "receiver", "message": "hello there"}},
    }, agent_id="sender-1")
    assert status == 200
    assert data["result"]["_walkie_talkie_inbox"] == []
    assert "Message successfully transmitted" in data["result"]["content"][0]["text"]

    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "wt_check_inbox", "arguments": {}},
    }, agent_id="receiver")
    messages = data["result"]["messages"]
    assert len(messages) == 1
    assert messages[0]["from"] == "sender-1"
    assert messages[0]["message"] == "hello there"

    # Second check is empty: the inbox was drained.
    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "wt_check_inbox", "arguments": {}},
    }, agent_id="receiver")
    assert data["result"]["messages"] == []


def test_check_inbox_clear_false_does_not_dequeue(server):
    base_url, _hub, _mcp = server
    _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send", "arguments": {"to": "peeker", "message": "x"}},
    }, agent_id="sender")

    for _ in range(2):
        _status, data = _rpc(base_url, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "wt_check_inbox", "arguments": {"clear": False}},
        }, agent_id="peeker")
        assert len(data["result"]["messages"]) == 1

    # Explicit clear dequeues.
    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "wt_check_inbox", "arguments": {"clear": True}},
    }, agent_id="peeker")
    assert len(data["result"]["messages"]) == 1
    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "wt_check_inbox", "arguments": {}},
    }, agent_id="peeker")
    assert data["result"]["messages"] == []


def test_check_inbox_rejects_non_boolean_clear(server):
    base_url, _hub, _mcp = server
    status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_check_inbox", "arguments": {"clear": "yes"}},
    })
    assert status == 200
    assert data["error"]["code"] == -32602


def test_pending_messages_piggyback_on_next_tool_result(server):
    base_url, _hub, _mcp = server
    _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send",
                   "arguments": {"to": "busy-agent", "message": "review this"}},
    }, agent_id="peer")

    # busy-agent asks for the peer list; the pending message rides along.
    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "wt_list_agents", "arguments": {}},
    }, agent_id="busy-agent")

    inbox = data["result"]["_walkie_talkie_inbox"]
    assert len(inbox) == 1
    assert inbox[0]["from"] == "peer"
    assert "[WALKIE-TALKIE INCOMING PEER MSGS]" in data["result"]["content"][0]["text"]

    # Drained: the next call has an empty inbox.
    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "wt_list_agents", "arguments": {}},
    }, agent_id="busy-agent")
    assert data["result"]["_walkie_talkie_inbox"] == []


def test_failed_wt_send_does_not_consume_inbox(server):
    base_url, _hub, _mcp = server
    _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send", "arguments": {"to": "victim", "message": "keep me"}},
    }, agent_id="peer")

    status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "wt_send", "arguments": {"to": "x", "message": ""}},
    }, agent_id="victim")
    assert status == 200
    assert data["error"]["code"] == -32602

    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "wt_check_inbox", "arguments": {}},
    }, agent_id="victim")
    assert len(data["result"]["messages"]) == 1


def test_wt_send_validates_arguments(server):
    base_url, _hub, _mcp = server

    bad_calls = [
        {"to": "", "message": "x"},                        # empty recipient
        {"to": 42, "message": "x"},                        # non-string recipient
        {"to": "a"},                                       # missing message
        {"to": "a", "message": "   "},                     # whitespace message
        {"to": "a", "message": "x", "priority": "urgent"}, # bad priority
    ]
    for i, arguments in enumerate(bad_calls):
        status, data = _rpc(base_url, {
            "jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": "wt_send", "arguments": arguments},
        })
        assert status == 200
        assert data["error"]["code"] == -32602, arguments


def test_wt_send_rejects_non_object_arguments(server):
    base_url, _hub, _mcp = server
    status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send", "arguments": "not-a-dict"},
    })
    assert status == 200
    # arguments falls back to {} -> missing 'message' -> invalid params
    assert data["error"]["code"] == -32602


def test_priority_orders_delivery_over_http(server):
    base_url, _hub, _mcp = server
    for i, (message, priority) in enumerate([
        ("normal-1", "normal"),
        ("normal-2", "normal"),
        ("high-1", "high"),
        ("low-1", "low"),
    ]):
        _rpc(base_url, {
            "jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": "wt_send",
                       "arguments": {"to": "target", "message": message,
                                     "priority": priority}},
        }, agent_id="sender")

    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 99, "method": "tools/call",
        "params": {"name": "wt_check_inbox", "arguments": {}},
    }, agent_id="target")
    assert [m["message"] for m in data["result"]["messages"]] == [
        "high-1", "normal-1", "normal-2", "low-1",
    ]


def test_identity_via_argument_and_query(server):
    base_url, _hub, _mcp = server

    # Per-call argument identity (documented in the tool schemas).
    _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send",
                   "arguments": {"to": "*", "message": "from-arg",
                                 "agent_id": "arg-identity"}},
    })

    # Query-string identity (kept alive by the SSE endpoint event).
    _rpc(base_url, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "wt_send",
                   "arguments": {"to": "someone", "message": "from-query"}},
    }, agent_id=None, path="/mcp?agent_id=query-identity")

    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "wt_list_agents", "arguments": {}},
    }, agent_id="arg-identity")
    agent_ids = {a["id"] for a in data["result"]["agents"]}
    assert "arg-identity" in agent_ids
    assert "query-identity" in agent_ids
    assert "agent-mesh" not in agent_ids  # neither call fell back


def test_wt_list_agents_reports_unread_counts(server):
    base_url, _hub, _mcp = server
    _rpc(base_url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "wt_send", "arguments": {"to": "b", "message": "1"}},
    }, agent_id="a")

    # Ask from a third, unaffected agent so piggybacking doesn't hide counts.
    _status, data = _rpc(base_url, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "wt_list_agents", "arguments": {}},
    }, agent_id="observer")
    by_id = {a["id"]: a for a in data["result"]["agents"]}
    assert by_id["b"]["unread_count"] == 1
    assert by_id["a"]["status"] == "ONLINE"


def test_sse_stream_advertises_endpoint_with_identity(server):
    base_url, hub, _mcp = server
    blob = _sse_read_first_event(base_url, "/mcp/sse?agent_id=sse-agent")
    head, _, body = blob.partition(b"\r\n\r\n")
    assert b"HTTP/1.1 200" in head
    assert b"text/event-stream" in head
    assert b"event: endpoint" in body
    assert b"data: /mcp?agent_id=sse-agent" in body


def test_sse_without_identity_advertises_plain_endpoint(server):
    base_url, hub, _mcp = server
    blob = _sse_read_first_event(base_url, "/mcp/sse")
    _, _, body = blob.partition(b"\r\n\r\n")
    assert b"event: endpoint" in body
    assert b"data: /mcp\n\n" in body.replace(b"\r", b"")




