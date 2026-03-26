"""Unit tests for Designer Form menu action wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QMainWindow

from app.shell.menus import MenuCallbacks, build_menu_stubs

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    return app


def test_designer_form_actions_registered_with_shortcuts(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()
    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(
            on_designer_preview=lambda: calls.append("preview"),
            on_designer_check_compat=lambda: calls.append("compat"),
            on_designer_add_resource=lambda: calls.append("resource"),
            on_designer_promote_widget=lambda: calls.append("promote"),
            on_designer_format_ui_xml=lambda: calls.append("format"),
            on_designer_save_component=lambda: calls.append("save_component"),
            on_designer_insert_component=lambda: calls.append("insert_component"),
            on_designer_duplicate_selection=lambda: calls.append("duplicate"),
        ),
    )
    preview = registry.action("designer.form.preview")
    compat = registry.action("designer.form.check_compat")
    resource = registry.action("designer.form.add_resource")
    promote = registry.action("designer.form.promote_widget")
    format_ui = registry.action("designer.form.format_ui_xml")
    save_component = registry.action("designer.form.save_component")
    insert_component = registry.action("designer.form.insert_component")
    duplicate = registry.action("designer.form.duplicate_selection")
    assert preview is not None
    assert compat is not None
    assert resource is not None
    assert promote is not None
    assert format_ui is not None
    assert save_component is not None
    assert insert_component is not None
    assert duplicate is not None
    assert preview.shortcut().toString() == "Ctrl+R"
    assert compat.shortcut().toString() == "Ctrl+Shift+R"
    assert resource.shortcut().toString() == ""
    assert promote.shortcut().toString() == ""
    assert format_ui.shortcut().toString() == "Ctrl+Alt+Shift+F"
    assert save_component.shortcut().toString() == ""
    assert insert_component.shortcut().toString() == ""
    assert duplicate.shortcut().toString() == "Ctrl+D"

    preview.trigger()
    compat.trigger()
    resource.trigger()
    promote.trigger()
    format_ui.trigger()
    save_component.trigger()
    insert_component.trigger()
    duplicate.trigger()
    assert calls == [
        "preview",
        "compat",
        "resource",
        "promote",
        "format",
        "save_component",
        "insert_component",
        "duplicate",
    ]


def test_designer_form_actions_include_edit_clipboard_shortcuts(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window, callbacks=MenuCallbacks())

    cut_action = registry.action("shell.action.edit.cut")
    copy_action = registry.action("shell.action.edit.copy")
    paste_action = registry.action("shell.action.edit.paste")

    assert cut_action is not None
    assert copy_action is not None
    assert paste_action is not None
    assert cut_action.shortcut().toString() == "Ctrl+X"
    assert copy_action.shortcut().toString() == "Ctrl+C"
    assert paste_action.shortcut().toString() == "Ctrl+V"
