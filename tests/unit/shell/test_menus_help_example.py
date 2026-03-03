"""Unit tests for Help menu example-project action wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtWidgets as qt_widgets  # noqa: E402
import PySide2.QtGui as qt_gui  # noqa: E402
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


def test_load_example_project_action_is_registered_with_callback(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()

    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(on_help_load_example_project=lambda: calls.append("triggered")),
    )
    action = registry.action("shell.action.help.loadExampleProject")

    assert action is not None
    assert action.text() == "Load Example Project..."
    assert action.isEnabled()

    action.trigger()
    assert calls == ["triggered"]


def test_load_example_project_action_appears_in_help_menu(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    _ = build_menu_stubs(window, callbacks=MenuCallbacks())

    help_menu = window.findChild(qt_widgets.QMenu, "shell.menu.help")
    assert help_menu is not None

    action_texts = [a.text() for a in help_menu.actions() if not a.isSeparator()]
    assert "Load Example Project..." in action_texts

    example_idx = action_texts.index("Load Example Project...")
    getting_started_idx = action_texts.index("Getting Started")
    assert example_idx < getting_started_idx
