"""Unit tests for Designer New Form menu action wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui  # noqa: E402
import PySide2.QtWidgets as qt_widgets  # noqa: E402
from PySide2.QtWidgets import QMainWindow  # noqa: E402

from app.shell.menus import MenuCallbacks, build_menu_stubs  # noqa: E402

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


def test_designer_new_form_action_is_registered_with_shortcut(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()
    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(on_new_form=lambda: calls.append("triggered")),
    )
    action = registry.action("designer.file.new_form")
    assert action is not None
    assert action.text() == "New Form..."
    assert action.shortcut().toString() == "Ctrl+Shift+N"

    action.trigger()
    assert calls == ["triggered"]
