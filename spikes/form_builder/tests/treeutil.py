"""Compare a realized Qt widget tree without depending on our canvas."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


_KEYS = (
    "windowTitle",
    "text",
    "plainText",
    "placeholderText",
    "toolTip",
    "title",
    "checked",
    "enabled",
    "value",
    "minimum",
    "maximum",
    "currentIndex",
    "readOnly",
    "editable",
)


def _norm(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, int):
        return int(value)
    text = str(value)
    if text.startswith("<") and ":" in text:
        return text
    return text


def _direct(widget: QWidget):
    return widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly)


def signature(widget: QWidget):
    cls = widget.metaObject().className()
    name = widget.objectName()
    lay = widget.layout()
    lay_name = ""
    lay_count = 0
    if lay is not None:
        lay_name = lay.metaObject().className()
        lay_count = lay.count()
    props = []
    meta = widget.metaObject()
    for key in _KEYS:
        if meta.indexOfProperty(key) >= 0:
            props.append((key, _norm(widget.property(key))))
    extra = ()
    if meta.indexOfProperty("count") >= 0 and cls in {"QComboBox", "QListWidget"}:
        count = widget.count() if hasattr(widget, "count") else 0
        if cls == "QComboBox":
            extra = tuple(widget.itemText(i) for i in range(count))
    kids = []
    for child in _direct(widget):
        object_name = child.objectName()
        if not object_name or object_name.startswith("qt_"):
            for grand in _direct(child):
                kids.extend(_flatten(grand))
            continue
        kids.append(signature(child))
    return (cls, name, lay_name, lay_count, tuple(props), extra, tuple(kids))


def _flatten(widget: QWidget):
    object_name = widget.objectName()
    if not object_name or object_name.startswith("qt_"):
        found = []
        for child in _direct(widget):
            found.extend(_flatten(child))
        return found
    return [signature(widget)]
