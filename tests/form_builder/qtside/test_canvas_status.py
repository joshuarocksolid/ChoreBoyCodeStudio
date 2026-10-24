"""Hover text and a gesture sentence share one status line."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import QEvent, QPoint, Qt
from app.qt.QtGui import QMouseEvent
from app.qt.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem, QWidget
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import Stroke
from app.shell.theme_tokens import tokens_from_palette
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


def test_canvas_and_outline_hover_follow_each_other(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    parent.resize(1100, 720)
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    surface.resize(1100, 720)
    parent.show()
    surface.show()
    _flush()
    try:
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")
        assert isinstance(canvas, FormCanvas)
        assert tree is not None
        button = surface._session.document.by_name("okButton")[0]  # type: ignore[attr-defined]  # noqa: SLF001
        root = surface._session.document.root.id  # type: ignore[attr-defined]  # noqa: SLF001
        _move(canvas, "okButton")
        fill = tokens_from_palette(qapp.palette(), force_mode="light").tree_hover_bg.lower()
        assert _row_color(tree, button) == fill
        assert _row_color(tree, root) != fill
        _move_row(tree, root)
        assert surface.editor_status_sentence().startswith("Form ·")
        strokes = [item for item in canvas.overlay().items if isinstance(item, Stroke) and item.role == "hover"]
        assert strokes
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


def _move_row(tree: QTreeWidget, node: object) -> None:
    item = _item(tree, node)
    rect = tree.visualItemRect(item)
    local = rect.center()
    viewport = tree.viewport()
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


def _row_color(tree: QTreeWidget, node: object) -> str:
    return _item(tree, node).background(0).color().name().lower()


def _item(tree: QTreeWidget, node: object) -> QTreeWidgetItem:
    role = getattr(Qt, "UserRole")
    found = _find(tree, role, int(node))  # type: ignore[arg-type]
    assert found is not None
    return found


def _find(tree: QTreeWidget, role: int, node: int) -> QTreeWidgetItem | None:
    def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
        raw = item.data(0, role)
        if raw is not None and int(raw) == node:
            return item
        for index in range(item.childCount()):
            child = item.child(index)
            if child is None:
                continue
            found = walk(child)
            if found is not None:
                return found
        return None

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is None:
            continue
        found = walk(top)
        if found is not None:
            return found
    return None


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()


def _button(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)
