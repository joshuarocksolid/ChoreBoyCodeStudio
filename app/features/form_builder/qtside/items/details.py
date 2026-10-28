"""The ▸ panel under one combo or list row (UX-ITEM-003)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from app.features.form_builder.engine.ui4.values import EnumValue, SetValue, StringValue, Value
from app.features.form_builder.qtside.items.model import Item
from app.qt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLineEdit, QToolButton, QWidget

_CHECK = ("Unchecked", "Checked", "Partly")
_CHECK_QT = {"Unchecked": "Unchecked", "Checked": "Checked", "Partly": "PartiallyChecked"}
# UX-ITEM-003 order: "User can check it" with "Starts", then Enabled,
# Selectable, Editable.
_FLAG_BITS = (
    ("ItemIsUserCheckable", "User can check it"),
    ("ItemIsEnabled", "Enabled"),
    ("ItemIsSelectable", "Selectable"),
    ("ItemIsEditable", "Editable"),
)


def build_details(
    kind: str,
    current: Callable[[], Item],
    on_value: Callable[[str, Optional[Value]], None],
    on_more: Callable[[], None],
    parent: QWidget,
    icon_row: Optional[Callable[[QWidget], QWidget]] = None,
) -> QWidget:
    item = current()
    panel = QWidget(parent)
    panel.setObjectName("formBuilder.itemDetails")
    form = QFormLayout(panel)
    form.setContentsMargins(8, 4, 8, 4)
    if icon_row is not None:
        # The inspector's icon editor (UX-PED-102), writing into this session.
        form.addRow("Icon", icon_row(panel))
    if kind == "list":
        _flags(form, current, on_value, panel)
    tip = QLineEdit(panel)
    tip.setObjectName("formBuilder.itemTooltip")
    tip.setText(_string(item, "toolTip"))
    tip.editingFinished.connect(lambda: on_value("toolTip", StringValue(tip.text()) if tip.text() else None))
    form.addRow("Tooltip", tip)
    more = QToolButton(panel)
    more.setText("More properties \u25b8")
    more.setObjectName("formBuilder.itemMore")
    more.clicked.connect(on_more)
    form.addRow("", more)
    panel.setMinimumHeight(panel.sizeHint().height())
    return panel


# QListWidgetItem's own default: enabled, selectable, checkable, draggable.
_DEFAULT_FLAGS = ("ItemIsSelectable", "ItemIsUserCheckable", "ItemIsEnabled", "ItemIsDragEnabled")


def _flags(form: QFormLayout, current: Callable[[], Item], on_value: Callable[[str, Optional[Value]], None], parent: QWidget) -> None:
    item = current()
    stored = _flag_names(item)
    for bit, label in _FLAG_BITS:
        box = QCheckBox(label, parent)
        box.setObjectName("formBuilder.itemFlag." + bit)
        box.setChecked(bit in stored)
        box.toggled.connect(lambda _checked=False, bit=bit, box=box: _toggle_flag(current(), bit, box.isChecked(), on_value))
        form.addRow("", box)
        if bit == "ItemIsUserCheckable":
            _check_state(form, item, on_value, parent)


def _toggle_flag(item: Item, bit: str, on: bool, on_value: Callable[[str, Optional[Value]], None]) -> None:
    """Flip one bit. Every other bit, and its spelling in the file, stays."""
    entry = _prop(item, "flags")
    value = getattr(entry, "value", None)
    if isinstance(value, SetValue) and value.text.strip():
        pieces = [piece.strip() for piece in value.text.split("|") if piece.strip()]
    else:
        pieces = list(_DEFAULT_FLAGS)
    kept = [piece for piece in pieces if bit not in (name for _scope, name in SetValue(piece).keys())]
    if on:
        kept.append(bit)
    if entry is None and sorted(kept) == sorted(_DEFAULT_FLAGS):
        return
    on_value("flags", SetValue("|".join(kept)) if kept else None)


def _flag_names(item: Item) -> Tuple[str, ...]:
    entry = _prop(item, "flags")
    value = getattr(entry, "value", None)
    if isinstance(value, SetValue) and value.text.strip():
        return tuple(name for _scope, name in value.keys())
    return _DEFAULT_FLAGS


def _check_state(form: QFormLayout, item: Item, on_value: Callable[[str, Optional[Value]], None], parent: QWidget) -> None:
    combo = QComboBox(parent)
    combo.setObjectName("formBuilder.itemCheckState")
    combo.addItems(_CHECK)
    current = _enum(item, "checkState")
    for index, label in enumerate(_CHECK):
        if _CHECK_QT[label] == current:
            combo.setCurrentIndex(index)
    combo.currentTextChanged.connect(lambda text: on_value("checkState", EnumValue(_CHECK_QT.get(text, text))))
    form.addRow("Starts", combo)


def _prop(item: Item, name: str) -> Optional[object]:
    if item.base is None:
        return None
    for entry in item.base.properties:
        if entry.name == name:
            return entry
    return None


def _string(item: Item, name: str) -> str:
    entry = _prop(item, name)
    value = getattr(entry, "value", None)
    if isinstance(value, StringValue):
        return value.text
    return ""


def _enum(item: Item, name: str) -> str:
    entry = _prop(item, name)
    value = getattr(entry, "value", None)
    if isinstance(value, EnumValue):
        return value.key()[1]
    return ""
