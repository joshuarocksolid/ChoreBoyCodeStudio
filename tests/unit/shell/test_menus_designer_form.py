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
        ),
    )
    preview = registry.action("designer.form.preview")
    compat = registry.action("designer.form.check_compat")
    assert preview is not None
    assert compat is not None
    assert preview.shortcut().toString() == "Ctrl+R"
    assert compat.shortcut().toString() == "Ctrl+Shift+R"

    preview.trigger()
    compat.trigger()
    assert calls == ["preview", "compat"]
