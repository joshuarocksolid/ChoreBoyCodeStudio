"""Shared words and Qt enum lookups for the scalar editors."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.values import Value
from app.features.form_builder.qtside.inspector.api import EditorHost, Mixed, RowValue, Unset, Written
from app.qt.QtCore import QEvent, Qt
from app.qt.QtGui import QColor
from app.qt.QtWidgets import QLabel, QLineEdit, QWidget

MINUS = "\u2212"

# UX spec fb.warning swatches: light, dark, high-contrast light, high-contrast dark.
_WARNING = ((217, 119, 6), (229, 161, 0), (122, 69, 0), (255, 215, 0))


def change_label(label: str) -> str:
    """Undo name for one property session: "Change echo mode"."""
    if not label:
        return "Change value"
    return "Change " + label[0].lower() + label[1:]


def payload(value: RowValue) -> Optional[Value]:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset):
        return value.default
    return None


def can_reset(value: RowValue, previous: bool) -> bool:
    """Clearing deletes a written property, or an unset one that has a class default."""
    if isinstance(value, Written):
        return True
    if isinstance(value, Unset):
        return value.default is not None
    return previous


def part_name(host: EditorHost, part: str) -> str:
    label = host.label.strip() if host.label else "Value"
    return "%s: %s" % (label, part)


def name_part(widget: QWidget, host: EditorHost, part: str) -> None:
    widget.setAccessibleName(part_name(host, part))


def warning_color(chrome: object) -> str:
    dark = bool(getattr(chrome, "is_dark", False))
    contrast = bool(getattr(chrome, "is_high_contrast", False))
    if contrast:
        red, green, blue = _WARNING[3] if dark else _WARNING[2]
    else:
        red, green, blue = _WARNING[1] if dark else _WARNING[0]
    return QColor(red, green, blue).name()


def qt_names_visible(host: EditorHost) -> bool:
    label = host.row_widget.findChild(QLabel, "formBuilder.rowQtName")
    return isinstance(label, QLabel) and label.isVisible() and bool(label.text())


def owner_name(host: EditorHost) -> str:
    widget: Optional[QWidget] = host.row_widget
    while widget is not None and widget.objectName() != "formBuilder.inspector":
        widget = widget.parentWidget()
    if widget is None:
        return ""
    name = widget.findChild(QLineEdit, "formBuilder.inspectorName")
    if not isinstance(name, QLineEdit):
        return ""
    return str(name.text())


def qt_key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def qt_mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def qt_align(name: str) -> object:
    return getattr(getattr(Qt, "AlignmentFlag", Qt), name)


def qt_focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def event_type(name: str) -> object:
    return getattr(getattr(QEvent, "Type", QEvent), name)


def is_mixed(value: RowValue) -> bool:
    return isinstance(value, Mixed)
