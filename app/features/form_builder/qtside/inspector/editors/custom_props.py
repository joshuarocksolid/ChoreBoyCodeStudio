"""Custom (dynamic) properties (UX-PED-060 … UX-PED-062).

A custom property is a ``property`` with ``stdset="0"``. Names that start
with ``cbcs`` are hidden and refused. Add, rename, remove and change-type
are each one undo step. The fifteen types are the value elements the file
can store. Editors for a type come from the catalog. An unregistered element
stays "Kept as is".
"""

from __future__ import annotations

import datetime
from typing import Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetProperty, SetPropertyMany
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node, WidgetNode
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    ColorValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    FontValue,
    NumberValue,
    PointValue,
    RectValue,
    SizeValue,
    StringListValue,
    StringValue,
    TimeValue,
    UrlValue,
    Value,
)
from app.qt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import exec_qt

_IDENTIFIER = "Names use letters, digits and _, and can't start with a digit."
_CLASS = "%s already has a property called %s. Pick another name."
_DUPLICATE = "This widget already has a custom property called %s."
_CBCS = "Names starting with cbcs are kept for Code Studio."
_CLEAR = "%s can't be turned into %s. Its value will be cleared."

# The drop-down, in spec order. Shortcut is stored as a string. The key editor
# is selected by property name, so a custom shortcut uses the text editor
# after the file is reopened.
TYPES: Tuple[Tuple[str, str], ...] = (
    ("Text", StringValue.ELEMENT),
    ("Number", NumberValue.ELEMENT),
    ("Decimal number", DoubleValue.ELEMENT),
    ("True or false", BoolValue.ELEMENT),
    ("Date", DateValue.ELEMENT),
    ("Time", TimeValue.ELEMENT),
    ("Date and time", DateTimeValue.ELEMENT),
    ("Colour", ColorValue.ELEMENT),
    ("Font", FontValue.ELEMENT),
    ("Size", SizeValue.ELEMENT),
    ("Point", PointValue.ELEMENT),
    ("Rectangle", RectValue.ELEMENT),
    ("List of text", StringListValue.ELEMENT),
    ("Address (URL)", UrlValue.ELEMENT),
    ("Shortcut", "shortcut"),
)


def type_label(element: str) -> str:
    for label, kind in TYPES:
        if kind == element:
            return label
    return element


def empty_value(kind: str) -> Value:
    """The value written when a custom property is added."""
    today = datetime.date.today()
    if kind == StringValue.ELEMENT or kind == "shortcut":
        return StringValue("")
    if kind == NumberValue.ELEMENT:
        return NumberValue(0)
    if kind == DoubleValue.ELEMENT:
        return DoubleValue(0.0)
    if kind == BoolValue.ELEMENT:
        return BoolValue(False)
    if kind == DateValue.ELEMENT:
        return DateValue(today.year, today.month, today.day)
    if kind == TimeValue.ELEMENT:
        return TimeValue(0, 0, 0)
    if kind == DateTimeValue.ELEMENT:
        return DateTimeValue(0, 0, 0, today.year, today.month, today.day)
    if kind == ColorValue.ELEMENT:
        return ColorValue(0, 0, 0)
    if kind == FontValue.ELEMENT:
        return FontValue()
    if kind == SizeValue.ELEMENT:
        return SizeValue(0, 0)
    if kind == PointValue.ELEMENT:
        return PointValue(0, 0)
    if kind == RectValue.ELEMENT:
        return RectValue(0, 0, 0, 0)
    if kind == StringListValue.ELEMENT:
        return StringListValue(())
    if kind == UrlValue.ELEMENT:
        return UrlValue(StringValue(""))
    return StringValue("")


def explain_name(document: UiDocument, owners: Sequence[NodeId], name: str) -> Optional[str]:
    """The refusal sentence, or None when the name can be added."""
    if not _identifier(name):
        return _IDENTIFIER
    if name.startswith("cbcs"):
        return _CBCS
    for owner in owners:
        node = document.node(owner)
        sentence = _taken(node, name)
        if sentence is not None:
            return sentence
    return None


def add_commands(owners: Sequence[NodeId], name: str, value: Value) -> Tuple[Command, ...]:
    if len(owners) == 1:
        return (SetProperty(owners[0], name, value, stdset="0"),)
    return (SetPropertyMany(tuple(owners), name, value, stdset="0"),)


def rename_commands(owner: NodeId, old: str, new: str, value: Value) -> Tuple[Command, ...]:
    return (
        SetProperty(owner, old, None),
        SetProperty(owner, new, value, stdset="0"),
    )


def remove_commands(owners: Sequence[NodeId], name: str) -> Tuple[Command, ...]:
    return tuple(SetProperty(owner, name, None) for owner in owners)


def convert_value(value: Value, kind: str) -> Optional[Value]:
    """A converted value, or None when the type change must clear it."""
    if kind == "shortcut":
        kind = StringValue.ELEMENT
    if getattr(value, "ELEMENT", "") == kind:
        return value
    if kind == StringValue.ELEMENT:
        return StringValue(_as_text(value))
    if kind == NumberValue.ELEMENT and isinstance(value, StringValue):
        try:
            return NumberValue(int(value.text.strip()))
        except ValueError:
            return None
    if kind == DoubleValue.ELEMENT and isinstance(value, StringValue):
        try:
            return DoubleValue(float(value.text.strip()))
        except ValueError:
            return None
    if kind == NumberValue.ELEMENT and isinstance(value, DoubleValue):
        return NumberValue(int(value.value))
    if kind == DoubleValue.ELEMENT and isinstance(value, NumberValue):
        return DoubleValue(float(value.value))
    return None


def hidden_custom(name: str) -> bool:
    return name.startswith("cbcs")


class CustomPropertyAdder(QWidget):
    """The "+ Add custom property" button and its inline form."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.customProperties")
        self.setMinimumWidth(0)
        self._run: Optional[Callable[[str, Sequence[Command]], object]] = None
        self._names: Optional[Callable[[str], Optional[str]]] = None
        self._owners: Tuple[NodeId, ...] = ()
        self._focus: Optional[Callable[[str], None]] = None
        self._heading = QLabel("Custom properties", self)
        self._heading.setObjectName("formBuilder.customHeading")
        self._add = QPushButton("+ Add custom property", self)
        self._add.setObjectName("formBuilder.addCustomProperty")
        self._add.setAccessibleName("Add custom property")
        self._add.setFlat(True)
        self._form = QWidget(self)
        self._name = QLineEdit(self._form)
        self._name.setAccessibleName("Custom property name")
        self._name.setPlaceholderText("Name")
        self._type = QComboBox(self._form)
        self._type.setAccessibleName("Custom property type")
        for label, _kind in TYPES:
            self._type.addItem(label)
        self._ok = QPushButton("Add", self._form)
        self._cancel = QPushButton("Cancel", self._form)
        self._error = QLabel(self._form)
        self._error.setObjectName("formBuilder.rowError")
        self._error.setWordWrap(True)
        self._error.hide()
        form = QVBoxLayout(self._form)
        form.setContentsMargins(0, 0, 0, 0)
        form.addWidget(self._name)
        form.addWidget(self._type)
        buttons = QHBoxLayout()
        buttons.addWidget(self._ok)
        buttons.addWidget(self._cancel)
        form.addLayout(buttons)
        form.addWidget(self._error)
        self._form.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._heading)
        layout.addWidget(self._add)
        layout.addWidget(self._form)
        self._add.clicked.connect(self.open_form)
        self._ok.clicked.connect(self.submit)
        self._cancel.clicked.connect(self.close_form)
        self._name.returnPressed.connect(self.submit)

    def set_handlers(
        self,
        run: Callable[[str, Sequence[Command]], object],
        names: Callable[[str], Optional[str]],
        focus: Callable[[str], None],
    ) -> None:
        self._run = run
        self._names = names
        self._focus = focus

    def set_owners(self, owners: Sequence[NodeId]) -> None:
        self._owners = tuple(owners)

    def set_heading(self, shown: bool) -> None:
        self._heading.setVisible(shown)

    def open_form(self) -> None:
        self._error.hide()
        self._name.clear()
        self._form.show()
        self._name.setFocus()

    def close_form(self) -> None:
        self._form.hide()
        self._error.hide()

    def submit(self) -> None:
        name = self._name.text().strip()
        check = self._names
        sentence = check(name) if check is not None else None
        if sentence is not None:
            self._error.setText(sentence)
            self._error.show()
            return
        kind = TYPES[self._type.currentIndex()][1]
        value = empty_value(kind)
        runner = self._run
        if runner is None or not self._owners:
            return
        runner("Add custom property %s" % name, add_commands(self._owners, name, value))
        self.close_form()
        focus = self._focus
        if focus is not None:
            focus(name)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        from app.qt.QtCore import Qt

        key = getattr(event, "key", lambda: None)()
        if key == getattr(getattr(Qt, "Key", Qt), "Key_Escape") and self._form.isVisible():
            self.close_form()
            getattr(event, "accept", lambda: None)()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


def confirm_clear(parent: QWidget, name: str, type_name: str) -> bool:
    box = QMessageBox(parent)
    box.setText(_CLEAR % (name, type_name))
    change = box.addButton("Change type", QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    exec_qt(box)
    return box.clickedButton() is change


def _identifier(name: str) -> bool:
    if not name or name[0].isdigit():
        return False
    return all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in name)


def _taken(node: Node, name: str) -> Optional[str]:
    existing = node.prop(name)
    if existing is not None and existing.is_dynamic:
        return _DUPLICATE % name
    class_name = node.class_name if isinstance(node, WidgetNode) else node.kind
    if existing is not None:
        return _CLASS % (class_name, name)
    if isinstance(node, WidgetNode):
        info = QtClassTable.shared().property_info(node.class_name, name)
        if info is not None:
            return _CLASS % (node.class_name, name)
    return None


def _as_text(value: Value) -> str:
    if isinstance(value, StringValue):
        return value.text
    if isinstance(value, NumberValue):
        return str(value.value)
    if isinstance(value, DoubleValue):
        return str(value.value)
    if isinstance(value, BoolValue):
        return "true" if value.value else "false"
    return ""
