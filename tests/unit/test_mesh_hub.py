"""Unit tests for MeshHub — the in-memory agent registry and message router."""

from mcp_server import MeshHub


def test_register_creates_online_agent():
    hub = MeshHub()
    hub.register_or_heartbeat("coder")

    agents = hub.get_connected_agents()
    assert len(agents) == 1
    assert agents[0]["id"] == "coder"
    assert agents[0]["status"] == "ONLINE"
    assert agents[0]["unread_count"] == 0
    assert agents[0]["connected_at"]


def test_empty_agent_id_is_ignored():
    hub = MeshHub()
    hub.register_or_heartbeat("")
    assert hub.get_connected_agents() == []


def test_heartbeat_updates_presence_without_duplicating():
    hub = MeshHub()
    hub.register_or_heartbeat("a")
    hub.register_or_heartbeat("a")
    agents = hub.get_connected_agents()
    assert len(agents) == 1
    assert agents[0]["status"] == "ONLINE"


def test_targeted_send_queues_only_for_recipient():
    hub = MeshHub()
    hub.register_or_heartbeat("sender")
    hub.register_or_heartbeat("receiver")

    assert hub.send_message("sender", "receiver", "hello") is True

    by_id = {a["id"]: a for a in hub.get_connected_agents()}
    assert by_id["receiver"]["unread_count"] == 1
    assert by_id["sender"]["unread_count"] == 0


def test_drain_inbox_returns_messages_and_clears():
    hub = MeshHub()
    hub.send_message("a", "b", "first")

    messages = hub.drain_inbox("b")
    assert len(messages) == 1
    assert messages[0]["from"] == "a"
    assert messages[0]["to"] == "b"
    assert messages[0]["message"] == "first"
    assert messages[0]["priority"] == "normal"
    assert "timestamp" in messages[0]

    assert hub.drain_inbox("b") == []
    assert {a["id"]: a for a in hub.get_connected_agents()}["b"]["unread_count"] == 0


def test_drain_inbox_without_clear_peeks_only():
    hub = MeshHub()
    hub.send_message("a", "b", "still here")

    first = hub.drain_inbox("b", clear=False)
    second = hub.drain_inbox("b", clear=False)
    assert len(first) == 1
    assert first == second  # peeking must not dequeue

    hub.drain_inbox("b", clear=True)
    assert hub.drain_inbox("b") == []


def test_broadcast_reaches_all_other_online_agents():
    hub = MeshHub()
    for name in ("a", "b", "c"):
        hub.register_or_heartbeat(name)

    hub.send_message("a", "*", "alert")

    by_id = {a["id"]: a for a in hub.get_connected_agents()}
    assert by_id["b"]["unread_count"] == 1
    assert by_id["c"]["unread_count"] == 1
    assert by_id["a"]["unread_count"] == 0


def test_broadcast_skips_offline_agents():
    hub = MeshHub()
    hub.register_or_heartbeat("a")
    hub.register_or_heartbeat("b")
    hub.disconnect_agent("b")

    hub.send_message("a", "*", "alert")

    by_id = {a["id"]: a for a in hub.get_connected_agents()}
    assert by_id["b"]["status"] == "OFFLINE"
    assert by_id["b"]["unread_count"] == 0


def test_send_to_unknown_recipient_creates_placeholder():
    hub = MeshHub()
    hub.send_message("a", "mystery", "hi")

    by_id = {a["id"]: a for a in hub.get_connected_agents()}
    assert by_id["mystery"]["status"] == "IDLE"
    assert by_id["mystery"]["unread_count"] == 1


def test_send_registers_unknown_sender_as_online():
    hub = MeshHub()
    hub.send_message("fresh-agent", "x", "hello")

    by_id = {a["id"]: a for a in hub.get_connected_agents()}
    assert by_id["fresh-agent"]["status"] == "ONLINE"


def test_high_priority_is_delivered_before_earlier_normal_messages():
    hub = MeshHub()
    hub.register_or_heartbeat("receiver")

    hub.send_message("a", "receiver", "first normal")
    hub.send_message("a", "receiver", "later normal")
    hub.send_message("a", "receiver", "urgent!", priority="high")
    hub.send_message("a", "receiver", "chore", priority="low")

    inbox = hub.drain_inbox("receiver")
    assert [m["message"] for m in inbox] == [
        "urgent!",
        "first normal",
        "later normal",
        "chore",
    ]
    assert [m["priority"] for m in inbox] == ["high", "normal", "normal", "low"]


def test_history_keeps_chronological_order_regardless_of_priority():
    hub = MeshHub()
    hub.send_message("a", "b", "normal one")
    hub.send_message("a", "b", "urgent", priority="high")

    assert [m.text for m in hub.history] == ["normal one", "urgent"]


def test_listeners_are_notified_on_changes():
    hub = MeshHub()
    calls = []
    hub.add_listener(lambda: calls.append(1))

    hub.register_or_heartbeat("a")
    hub.send_message("a", "b", "x")
    assert len(calls) >= 2


def test_broken_listener_does_not_break_notification():
    hub = MeshHub()
    good = []

    def broken():
        raise RuntimeError("boom")

    hub.add_listener(broken)
    hub.add_listener(lambda: good.append(1))

    hub.register_or_heartbeat("a")  # must not raise
    assert good == [1]
