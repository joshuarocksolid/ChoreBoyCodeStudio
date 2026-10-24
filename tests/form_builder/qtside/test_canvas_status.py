"""Hover text and a gesture sentence share one status line."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import QEvent, QPoint, Qt
from app.qt.QtGui import QMouseEvent
from app.qt.QtWidgets import QApplication, QWidget
from app.features.form_builder.integration.canvas import FormCanvas
from tests.unit.features.form_builder.test_workbench import _FORM, _open

pytestmark = pytest.mark.usefixtures("qapp")


def test_hover_sets_the_status_sentence_until_a_gesture_speaks(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(960, 720)
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    parent.show()
    _flush()
    try:
        assert "okButton" not in surface.editor_status_sentence()
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        assert isinstance(canvas, FormCanvas)
        _move(canvas, "okButton")
        hovered = surface.editor_status_sentence()
        assert hovered == "okButton · Push button · double-click to edit text"
        button = surface._session.document.by_name("okButton")[0]  # type: ignore[attr-defined]  # noqa: SLF001
        assert surface._workbench.outline.hover_node() == button  # type: ignore[attr-defined]  # noqa: SLF001
        surface.narrate("Widgets in a layout move by drag in a later release.")
        assert surface.editor_status_sentence().startswith("Widgets in a layout")
    finally:
        surface.release()
        parent.deleteLater()
        _flush()


def _move(canvas: FormCanvas, name: str) -> None:
    local = _center(canvas, name)
    viewport = canvas.viewport()
    kind = getattr(getattr(QEvent, "Type", QEvent), "MouseMove")
    event = QMouseEvent(
        kind,
        local,
        viewport.mapToGlobal(local),
        _button("NoButton"),
        _button("NoButton"),
        _mods("NoModifier"),
    )
    QApplication.sendEvent(viewport, event)
    _flush()


def _center(canvas: FormCanvas, name: str) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(widget.mapTo(root, widget.rect().center())))


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()


def _button(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)
