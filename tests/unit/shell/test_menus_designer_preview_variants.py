"""Unit tests for Designer preview variant menu wiring."""

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


def test_designer_preview_variant_actions_are_registered(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()
    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(
            on_designer_preview_default=lambda: calls.append("default"),
            on_designer_preview_fusion=lambda: calls.append("fusion"),
            on_designer_preview_phone_portrait=lambda: calls.append("phone"),
            on_designer_preview_tablet_portrait=lambda: calls.append("tablet"),
        ),
    )

    default_preview = registry.action("designer.form.preview.default")
    fusion_preview = registry.action("designer.form.preview.fusion")
    phone_preview = registry.action("designer.form.preview.phone_portrait")
    tablet_preview = registry.action("designer.form.preview.tablet_portrait")
    assert default_preview is not None
    assert fusion_preview is not None
    assert phone_preview is not None
    assert tablet_preview is not None
    assert default_preview.shortcut().toString() == ""
    assert fusion_preview.shortcut().toString() == ""
    assert phone_preview.shortcut().toString() == ""
    assert tablet_preview.shortcut().toString() == ""

    default_preview.trigger()
    fusion_preview.trigger()
    phone_preview.trigger()
    tablet_preview.trigger()
    assert calls == ["default", "fusion", "phone", "tablet"]
