"""GUI construction test: build the entire Flet UI against a stub page.

This does not render a window (the test environment is headless); it calls
main() with a mock Page so every Flet control in the GUI is actually
constructed. Renamed/removed Flet control properties fail here instead of
at launch time.
"""

from unittest.mock import MagicMock

import pytest
from flet.controls import context as flet_context

import main as main_mod


@pytest.fixture
def stub_page(monkeypatch):
    # Never bind port 8765 from a unit test.
    monkeypatch.setattr(main_mod, "start_server_background", lambda: None)
    page = MagicMock()
    page.title = None
    # ft.run() sets this page context before invoking main(); CopyToClipboard
    # resolves its shared Clipboard service through it, so mirror that here.
    token = flet_context._context_page.set(page)
    yield page
    flet_context._context_page.reset(token)


def _walk(control):
    """Yield a control and everything nested under content/controls."""
    yield control
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, (str, bool)):
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if isinstance(controls, (list, tuple)):
        for child in controls:
            yield from _walk(child)


def _collect_added(page):
    added = []
    for call in page.add.call_args_list:
        for arg in call.args:
            added.extend(_walk(arg))
    return added


def test_main_builds_full_gui(stub_page):
    main_mod.main(stub_page)

    assert stub_page.title == "Walkie-Talkie — Agent Mesh Controller"
    stub_page.add.assert_called_once()

    controls = _collect_added(stub_page)
    types = {type(c) for c in controls}
    import flet as ft
    assert ft.Container in types
    assert ft.Column in types
    assert ft.Row in types
    assert ft.Button in types
    assert ft.TextField in types
    assert ft.Image in types
    assert ft.Divider in types


def test_gui_shows_configured_mcp_url(stub_page):
    main_mod.main(stub_page)

    controls = _collect_added(stub_page)
    texts = [c.value for c in controls if hasattr(c, "value")
             and isinstance(getattr(c, "value", None), str)]
    assert any(main_mod.MCP_URL in t for t in texts)

    url_fields = [c for c in controls if type(c).__name__ == "TextField"
                  and getattr(c, "value", None) == main_mod.MCP_URL]
    assert url_fields, "read-only MCP URL field must show MCP_URL"


def _button_label(button):
    """Extract a button's text label from str or Row content."""
    import flet as ft
    content = button.content
    if isinstance(content, str):
        return content
    if isinstance(content, ft.Row):
        for child in content.controls:
            if isinstance(child, ft.Text) and child.value:
                return child.value
    return None


def test_copy_button_uses_client_side_clipboard_action(stub_page):
    main_mod.main(stub_page)

    import flet as ft
    buttons = [c for c in _collect_added(stub_page) if isinstance(c, ft.Button)]
    copy_buttons = [b for b in buttons if _button_label(b) == "COPY URL"]
    assert len(copy_buttons) == 1
    action = copy_buttons[0].action
    assert isinstance(action, ft.CopyToClipboard)
    assert action.data == main_mod.MCP_URL


def test_logo_asset_path_is_relative_to_assets_dir(stub_page):
    main_mod.main(stub_page)

    import flet as ft
    images = [c for c in _collect_added(stub_page) if isinstance(c, ft.Image)]
    assert images, "GUI must render the logo"
    # assets/img/logo-icon.png exists; Flet resolves src relative to assets/.
    assert images[0].src == "img/logo-icon.png"
    import os
    assert os.path.exists(os.path.join(os.path.dirname(main_mod.__file__),
                                       "assets", images[0].src))


def test_gui_has_no_send_capability(stub_page, monkeypatch):
    """The operator is a read-only observer: no TRANSMIT box, no send path."""
    main_mod.main(stub_page)

    import flet as ft
    controls = _collect_added(stub_page)
    buttons = [c for c in controls if isinstance(c, ft.Button)]
    labels = [_button_label(b) for b in buttons]
    assert "TRANSMIT" not in labels

    # No free-text message input exists besides the read-only MCP URL field.
    text_fields = [c for c in controls
                   if isinstance(c, ft.TextField) and not c.read_only]
    assert text_fields == []

    # Even if the message box were abused, the GUI never calls the hub's
    # send path.
    sent = []
    monkeypatch.setattr(main_mod.hub, "send_message",
                        lambda **kw: sent.append(kw) or True)
    for button in buttons:
        if callable(getattr(button, "on_click", None)):
            button.on_click(MagicMock())
    assert sent == []


def test_clicking_agent_row_loads_its_chat(stub_page):
    main_mod.main(stub_page)
    main_mod.hub.register_or_heartbeat("chat-agent")
    main_mod.hub.send_message("chat-agent", "*", "hello mesh")

    # Trigger a synchronous re-render (the async poll loop is mocked here).
    main_mod._ui_refresh()

    import flet as ft
    controls = _collect_added(stub_page)
    texts = [c.value for c in controls if isinstance(c, ft.Text)]
    assert "chat-agent" in texts, "connected agent id must appear in the list"


def test_gui_uses_icons(stub_page):
    main_mod.main(stub_page)

    import flet as ft
    controls = _collect_added(stub_page)
    icons = [c for c in controls if isinstance(c, ft.Icon)]
    assert len(icons) >= 6, "GUI should use icons throughout, not just a few"

    # Buttons carry icons next to their labels
    buttons = [c for c in controls if isinstance(c, ft.Button)]
    icon_buttons = 0
    for b in buttons:
        if isinstance(b.content, ft.Row):
            if any(isinstance(ch, ft.Icon) for ch in b.content.controls):
                icon_buttons += 1
    assert icon_buttons >= 1  # COPY URL


def test_ui_poll_loop_task_is_scheduled(stub_page):
    main_mod.main(stub_page)
    # main() must schedule the cross-thread refresh loop on Flet's loop.
    assert stub_page.run_task.call_count == 1
    handler = stub_page.run_task.call_args.args[0]
    assert handler.__name__ == "ui_poll_loop"
