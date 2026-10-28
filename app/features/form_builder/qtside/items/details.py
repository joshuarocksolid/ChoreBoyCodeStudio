"""The ▸ panel under one combo or list row (UX-ITEM-003)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from app.features.form_builder.engine.ui4.values import EnumValue, SetValue, StringValue, Value
from app.features.form_builder.qtside.items.model import Item
from app.qt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QToolButton, QWidget

_CHECK = ("Unchecked", "Checked", "Partly")
_CHECK_QT = {"Unchecked": "Unchecked", "Checked": "Checked", "Partly": "PartiallyChecked"}
_FLAG_BITS = (
    ("ItemIsSelectable", "Selectable"),
    ("ItemIsEnabled", "Enabled"),
    ("ItemIsEditable", "Editable"),
    ("ItemIsUserCheckable", "User can check it"),
)


def build_details(
    kind: str,
    current: Callable[[], Item],
    on_value: Callable[[str, Optional[Value]], None],
    on_more: Callable[[], None],
    parent: QWidget,
) -> QWidget:
    item = current()
    panel = QWidget(parent)
    panel.setObjectName("formBuilder.itemDetails")
    form = QFormLayout(panel)
    form.setContentsMargins(8, 4, 8, 4)
    icon = QLabel("Icon")
    icon.setObjectName("formBuilder.itemIcon")
    icon.setEnabled(False)
    form.addRow("Icon", icon)
    if kind == "list":
        _flags(form, current, on_value, panel)
        _check_state(form, item, on_value, panel)
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


def _flags(form: QFormLayout, current: Callable[[], Item], on_value: Callable[[str, Optional[Value]], None], parent: QWidget) -> None:
    item = current()
    stored = _flags_of(item)
    written = _prop(item, "flags") is not None
    for bit, label in _FLAG_BITS:
        box = QCheckBox(label, parent)
        box.setObjectName("formBuilder.itemFlag." + bit)
        default_on = bit in ("ItemIsSelectable", "ItemIsEnabled")
        box.setChecked(bit in stored if written else default_on)
        box.toggled.connect(lambda _checked=False, bit=bit, box=box: _toggle_flag(current(), bit, box.isChecked(), on_value))
        form.addRow("", box)


def _toggle_flag(item: Item, bit: str, on: bool, on_value: Callable[[str, Optional[Value]], None]) -> None:
    bits = set(_flags_of(item) or ("ItemIsSelectable", "ItemIsEnabled"))
    if on:
        bits.add(bit)
    else:
        bits.discard(bit)
    order = [name for name, _label in _FLAG_BITS if name in bits]
    on_value("flags", SetValue("|".join(order)) if order else None)


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
        return value.name
    return ""


def _flags_of(item: Item) -> Tuple[str, ...]:
    entry = _prop(item, "flags")
    value = getattr(entry, "value", None)
    if isinstance(value, SetValue) and value.text:
        return tuple(part.strip() for part in value.text.split("|") if part.strip())
    return ()
