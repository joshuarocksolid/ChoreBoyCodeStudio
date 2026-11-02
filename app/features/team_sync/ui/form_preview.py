"""Read-only .ui preview. Falls back to a property table when the loader is missing."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from app.qt.QtCore import QByteArray, QBuffer, QIODevice
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def form_properties(xml_text: str) -> dict[str, dict[str, str]]:
    """Widget name to property name to value. Used when the form cannot be loaded."""
    found: dict[str, dict[str, str]] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return found
    for widget in root.iter("widget"):
        name = widget.attrib.get("name") or widget.attrib.get("class") or "widget"
        props: dict[str, str] = {}
        for prop in widget.findall("property"):
            key = prop.attrib.get("name", "")
            child = next(iter(prop), None)
            if child is not None and child.text:
                props[key] = child.text
        if props:
            found[name] = props
    return found


def property_changes(before: str, after: str) -> list[tuple[str, str, str, str]]:
    left = form_properties(before)
    right = form_properties(after)
    rows: list[tuple[str, str, str, str]] = []
    names = list(dict.fromkeys(list(left) + list(right)))
    for name in names:
        keys = list(dict.fromkeys(list(left.get(name, {})) + list(right.get(name, {}))))
        for key in keys:
            old = left.get(name, {}).get(key, "")
            new = right.get(name, {}).get(key, "")
            if old != new:
                rows.append((name, key, old, new))
    return rows


def load_form_widget(xml_text: str, parent: QWidget) -> Optional[QWidget]:
    try:
        from app.qt.QtUiTools import QUiLoader
    except ImportError:
        return None
    data = QByteArray(xml_text.encode("utf-8"))
    buffer = QBuffer()
    buffer.setData(data)
    if not buffer.open(QIODevice.ReadOnly):
        return None
    loader = QUiLoader()
    widget = loader.load(buffer, parent)
    buffer.close()
    return widget


class FormCompare(QWidget):
    """Before and after form, with changed widgets outlined and a property table."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.formCompare")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        panes = QHBoxLayout()
        self._before_host = QFrame(self)
        self._after_host = QFrame(self)
        self._before_layout = QVBoxLayout(self._before_host)
        self._after_layout = QVBoxLayout(self._after_host)
        panes.addWidget(self._before_host, 1)
        panes.addWidget(self._after_host, 1)
        layout.addLayout(panes, 1)
        self._table = QTableWidget(0, 4, self)
        self._table.setObjectName("shell.teamSync.formProperties")
        self._table.setHorizontalHeaderLabels(["Widget", "Property", "Before", "After"])
        layout.addWidget(self._table)

    def set_forms(self, before: str, after: str) -> None:
        self._mount(self._before_host, self._before_layout, before)
        self._mount(self._after_host, self._after_layout, after)
        rows = property_changes(before, after)
        self._table.setRowCount(len(rows))
        changed = {name for name, _key, _old, _new in rows}
        self._outline(self._before_host, changed)
        self._outline(self._after_host, changed)
        for index, (name, key, old, new) in enumerate(rows):
            for column, text in enumerate((name, key, old, new)):
                self._table.setItem(index, column, QTableWidgetItem(text))

    def _mount(self, host: QFrame, layout: QVBoxLayout, xml_text: str) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        loaded = load_form_widget(xml_text, host)
        if loaded is None:
            layout.addWidget(QLabel("Property changes", host))
            return
        loaded.setEnabled(False)
        layout.addWidget(loaded)

    def _outline(self, host: QWidget, names: set[str]) -> None:
        for name in names:
            widget = host.findChild(QWidget, name)
            if widget is not None:
                widget.setStyleSheet("border: 2px solid #B45309;")


__all__ = ["FormCompare", "form_properties", "load_form_widget", "property_changes"]
