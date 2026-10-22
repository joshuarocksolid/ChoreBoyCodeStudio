"""Raw PySide6 build and repaint, the ChoreBoy overhead baseline.

This module imports PySide6 directly. The number it measures is the cost of
Qt itself, not the form builder and not ``app.qt``.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Callable, Dict, Optional, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import PySide6
import PySide6.QtWidgets as QtWidgets
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QWidget

_ACTIONS: Dict[str, QAction] = {}
# Layouts do not own a widget until the layout is installed on a parent.
# Dropping the Python wrapper before that deletes the C++ object.
_KEEP: list = []


def qt_version() -> str:
    return PySide6.__version__


def _invoke(widget: QWidget, method_name: str, *args: object) -> None:
    method = cast(Optional[Callable[..., None]], getattr(widget, method_name, None))
    if method is not None:
        method(*args)


def application() -> QApplication:
    current = QApplication.instance()
    if isinstance(current, QApplication):
        return current
    return QApplication([])


def build_and_show(xml: str) -> QWidget:
    """Construct the widget tree described by ``xml`` and show it."""
    _ACTIONS.clear()
    _KEEP.clear()
    app = application()
    root = ET.fromstring(xml)
    window_el = root.find("widget")
    if window_el is None:
        raise ValueError("reference form has no root widget")
    window = _build_widget(window_el, None)
    window.resize(960, 640)
    window.show()
    app.processEvents()
    return window


def release(widget: QWidget) -> None:
    """Hide the window and drop our wrappers.

    ``deleteLater`` plus ``processEvents`` crashes the offscreen platform
    plugin on the way out. The process exits with ``os._exit`` so the leaked
    widgets are not destroyed by the interpreter shutdown either.
    """
    widget.hide()
    _KEEP.clear()
    _ACTIONS.clear()


def raw_edit(widget: QWidget) -> None:
    """One property write plus a repaint of that widget."""
    widget.setToolTip("raw-edit")
    widget.repaint()
    application().processEvents()


def find_named(window: QWidget, name: str) -> QWidget:
    found = window.findChild(QWidget, name)
    if found is None:
        raise ValueError("raw tree has no widget named %s" % name)
    return found


def _build_widget(el: ET.Element, parent: Optional[QWidget]) -> QWidget:
    class_name = el.attrib.get("class", "QWidget")
    cls = getattr(QtWidgets, class_name, QtWidgets.QWidget)
    widget = cls()
    _KEEP.append(widget)
    if parent is not None:
        widget.setParent(parent)
    widget.setObjectName(el.attrib.get("name", ""))
    _apply_properties(widget, el)
    if isinstance(widget, QtWidgets.QMainWindow):
        _populate_main_window(widget, el)
        return widget
    if isinstance(widget, QtWidgets.QTabWidget):
        for child in el.findall("widget"):
            page = _build_widget(child, None)
            widget.addTab(page, page.objectName())
        return widget
    if isinstance(widget, QtWidgets.QSplitter):
        for child in el.findall("widget"):
            widget.addWidget(_build_widget(child, None))
        return widget
    if isinstance(widget, QtWidgets.QMenuBar):
        for child in list(el):
            if child.tag != "widget":
                continue
            menu = _build_widget(child, widget)
            if isinstance(menu, QtWidgets.QMenu):
                widget.addMenu(menu)
        return widget
    if isinstance(widget, QtWidgets.QMenu):
        for child in list(el):
            if child.tag == "addaction":
                _apply_addaction(widget, child)
        return widget
    if isinstance(widget, QtWidgets.QToolBar):
        for child in list(el):
            if child.tag == "addaction":
                _apply_addaction(widget, child)
        return widget
    layout_el = el.find("layout")
    if layout_el is not None:
        widget.setLayout(_build_layout(layout_el))
    else:
        for child in el.findall("widget"):
            _build_widget(child, widget)
    return widget


def _populate_main_window(window: QtWidgets.QMainWindow, el: ET.Element) -> None:
    central_set = False
    for child in list(el):
        if child.tag == "widget":
            class_name = child.attrib.get("class", "")
            if class_name == "QMenuBar":
                bar = _build_widget(child, None)
                if isinstance(bar, QtWidgets.QMenuBar):
                    window.setMenuBar(bar)
                continue
            if class_name == "QToolBar":
                bar = _build_widget(child, None)
                if isinstance(bar, QtWidgets.QToolBar):
                    window.addToolBar(bar)
                continue
            if class_name == "QStatusBar":
                bar = _build_widget(child, None)
                if isinstance(bar, QtWidgets.QStatusBar):
                    window.setStatusBar(bar)
                continue
            built = _build_widget(child, None)
            if not central_set:
                window.setCentralWidget(built)
                central_set = True
            continue
        if child.tag == "addaction":
            _apply_addaction(window, child)


def _build_layout(el: ET.Element) -> QtWidgets.QLayout:
    class_name = el.attrib.get("class", "QVBoxLayout")
    cls = getattr(QtWidgets, class_name, QtWidgets.QVBoxLayout)
    layout = cls()
    for item in el.findall("item"):
        row = int(item.attrib["row"]) if "row" in item.attrib else None
        column = int(item.attrib["column"]) if "column" in item.attrib else None
        nested = item.find("layout")
        child = item.find("widget")
        if nested is not None:
            _place_layout(layout, _build_layout(nested), row, column)
        elif child is not None:
            _place_widget(layout, _build_widget(child, None), row, column)
    return layout


def _place_widget(
    layout: QtWidgets.QLayout,
    widget: QWidget,
    row: Optional[int],
    column: Optional[int],
) -> None:
    if isinstance(layout, QtWidgets.QFormLayout) and row is not None and column is not None:
        role = (
            QtWidgets.QFormLayout.ItemRole.LabelRole
            if column == 0
            else QtWidgets.QFormLayout.ItemRole.FieldRole
        )
        layout.setWidget(row, role, widget)
        return
    if isinstance(layout, QtWidgets.QGridLayout) and row is not None and column is not None:
        layout.addWidget(widget, row, column)
        return
    layout.addWidget(widget)


def _place_layout(
    layout: QtWidgets.QLayout,
    nested: QtWidgets.QLayout,
    row: Optional[int],
    column: Optional[int],
) -> None:
    if isinstance(layout, QtWidgets.QGridLayout) and row is not None and column is not None:
        layout.addLayout(nested, row, column)
        return
    if isinstance(layout, QtWidgets.QBoxLayout):
        layout.addLayout(nested)
        return
    raise RuntimeError("no place for a nested layout in %s" % type(layout).__name__)


def _apply_properties(widget: QWidget, el: ET.Element) -> None:
    for prop in el.findall("property"):
        name = prop.attrib.get("name", "")
        string_el = prop.find("string")
        text = "" if string_el is None or string_el.text is None else string_el.text
        if string_el is None:
            continue
        if name == "text":
            _invoke(widget, "setText", text)
        elif name == "windowTitle":
            widget.setWindowTitle(text)
        elif name == "toolTip":
            widget.setToolTip(text)
        elif name == "title":
            _invoke(widget, "setTitle", text)


def _apply_addaction(owner: QWidget, el: ET.Element) -> None:
    name = el.attrib.get("name", "")
    if name == "separator":
        _invoke(owner, "addSeparator")
        return
    if name.startswith("menu"):
        menu = owner.findChild(QtWidgets.QMenu, name)
        if menu is not None:
            _invoke(owner, "addMenu", menu)
            return
    action = _ACTIONS.get(name)
    if action is None:
        action = QAction(owner)
        action.setObjectName(name)
        action.setText(name)
        _ACTIONS[name] = action
    if hasattr(owner, "addAction"):
        owner.addAction(action)
