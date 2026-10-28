"""More properties uses the inspector editor registry (UX-ITEM-006)."""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.engine.ui4.values import (
    EnumValue,
    FontValue,
    SetValue,
    StringValue,
    Value,
)
from app.features.form_builder.qtside.inspector.api import (
    ALIGNMENT,
    EditorKey,
    EnumSpec,
    Unset,
    ValueSpec,
    Written,
)
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.items.model import Item
from app.qt.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

_ROWS = (
    ("Text", "text", EditorKey(StringValue.ELEMENT)),
    ("Tooltip", "toolTip", EditorKey(StringValue.ELEMENT)),
    ("Status tip", "statusTip", EditorKey(StringValue.ELEMENT)),
    ("What's this", "whatsThis", EditorKey(StringValue.ELEMENT)),
    ("Font", "font", EditorKey(FontValue.ELEMENT)),
    ("Text alignment", "textAlignment", ALIGNMENT),
    ("Check state", "checkState", EditorKey(EnumValue.ELEMENT)),
    ("Flags", "flags", EditorKey(SetValue.ELEMENT)),
)


def show_more(parent: QWidget, item: Item, on_value: Callable[[str, Optional[Value]], None]) -> QWidget:
    existing = parent.findChild(QWidget, "formBuilder.itemMorePanel")
    if existing is not None:
        existing.show()
        return existing
    panel = QWidget(parent)
    panel.setObjectName("formBuilder.itemMorePanel")
    form = QFormLayout(panel)
    catalog = default_catalog()
    for label, name, key in _ROWS:
        factory = catalog.editor(key)
        if factory is None:
            form.addRow(label, QLabel("No editor"))
            continue
        spec = ValueSpec(str(key))
        if name == "checkState":
            spec = ValueSpec(
                EnumValue.ELEMENT,
                enum=EnumSpec("Qt", "CheckState", ("Unchecked", "PartiallyChecked", "Checked"), False),
            )
        host = _Host(label, name, on_value)
        try:
            editor = factory(spec, host, panel)  # type: ignore[arg-type]
            value = _value(item, name)
            editor.show(Unset(value) if value is None else Written(value))
            form.addRow(label, editor.widget)
        except Exception:
            form.addRow(label, QLabel(label))
    layout = parent.layout()
    if isinstance(layout, QVBoxLayout):
        layout.addWidget(panel)
    else:
        panel.setParent(parent)
        panel.show()
    return panel


class _Host:
    def __init__(self, label: str, name: str, on_value: Callable[[str, Optional[Value]], None]) -> None:
        self.label = label
        self.qt_name = name
        self._name = name
        self._on = on_value
        self.row_widget = None

    def commit(self, value: object, session: object = None) -> None:
        del session
        self._on(self._name, value if isinstance(value, Value) else None)

    def begin_session(self, label: str) -> "_Session":
        del label
        return _Session()

    def document(self) -> None:
        return None

    def owner_ids(self) -> tuple:
        return ()

    def qt_names(self) -> bool:
        return False

    def form_shortcuts(self) -> dict:
        return {}

    def reset(self) -> None:
        self._on(self._name, None)

    def invalid(self, message: str) -> None:
        del message

    def enum_value(self, name: str) -> None:
        del name
        return None


class _Session:
    token = "item-more"
    label = "Edit items"

    def close(self) -> None:
        return None

    def revert(self) -> None:
        return None


def _value(item: Item, name: str) -> Optional[Value]:
    if item.base is None:
        return StringValue("") if name == "text" else None
    if name == "text":
        return StringValue(item.text_at(0))
    for entry in item.base.properties:
        if entry.name == name:
            return entry.value
    return None
