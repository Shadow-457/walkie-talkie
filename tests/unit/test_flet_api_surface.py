"""Guard: every Flet API main.py depends on must exist in the installed Flet.

The GUI was originally written against Flet 0.x and silently broke when the
dependency resolved to Flet 1.x. If a future Flet upgrade removes or renames
one of these APIs, this test fails with a precise name instead of the app
crashing at launch.
"""

import flet as ft


def test_entrypoint_api():
    assert callable(ft.run)
    app_attr = getattr(ft, "app", None)
    # ft.app was removed in Flet 1.0 (a dead placeholder may remain).
    assert app_attr is None or not callable(app_attr), \
        "ft.app is not a usable entrypoint in Flet 1.0; use ft.run"


def test_button_apis():
    assert hasattr(ft, "Button")
    assert not hasattr(ft, "ElevatedButton"), "renamed to ft.Button in Flet 1.0"
    fields = ft.Button.__dataclass_fields__
    assert "action" in fields  # CopyToClipboard client action
    assert "style" in fields
    style_fields = ft.ButtonStyle.__dataclass_fields__
    for name in ("bgcolor", "color", "padding", "shape"):
        assert name in style_fields


def test_border_apis():
    assert callable(ft.Border.all)
    assert callable(ft.Border.only)
    assert hasattr(ft, "BorderSide")
    assert not hasattr(ft.border, "only"), "moved to ft.Border.only in Flet 1.0"


def test_box_fit_replaces_image_fit():
    assert not hasattr(ft, "ImageFit"), "renamed to ft.BoxFit in Flet 1.0"
    assert hasattr(ft, "BoxFit")
    assert hasattr(ft.BoxFit, "CONTAIN")


def test_clipboard_and_dialog_apis():
    assert hasattr(ft, "CopyToClipboard")
    assert callable(ft.CopyToClipboard)
    assert hasattr(ft.Page, "show_dialog"), "replaces page.open(...) in Flet 1.0"
    assert not hasattr(ft.Page, "open")
    assert not hasattr(ft.Page, "set_clipboard"), "use CopyToClipboard action"
    assert hasattr(ft, "SnackBar")
    assert "duration" in ft.SnackBar.__dataclass_fields__


def test_page_layout_properties():
    for name in ("bgcolor", "padding", "spacing", "theme_mode", "title"):
        assert hasattr(ft.Page, name), name
    assert callable(ft.Page.update)
    assert callable(ft.Page.add)
    assert callable(ft.Page.run_task)


def test_window_properties():
    window_fields = ft.Window.__dataclass_fields__
    for name in ("width", "height", "min_width", "min_height"):
        assert name in window_fields, name


def test_misc_controls_used_by_gui():
    assert hasattr(ft, "Container")
    assert hasattr(ft, "TextField")
    assert hasattr(ft, "VerticalDivider")
    assert hasattr(ft, "Divider")
    assert hasattr(ft, "TextAlign")
    assert hasattr(ft, "ScrollMode")
    assert hasattr(ft.Padding, "symmetric")
    assert not callable(getattr(ft.padding, "symmetric", None)), \
        "helpers moved from ft.padding.* to ft.Padding.* in Flet 1.0"
    assert hasattr(ft, "RoundedRectangleBorder")
    assert hasattr(ft, "OutlineInputBorder"), \
        "TextField.border_color/border_radius are deprecated; use OutlineInputBorder"
