"""The ▸ panel under one combo or list row (UX-ITEM-003)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional, Tuple

from app.features.form_builder.engine.ui4.values import EnumValue, SetValue, StringValue, Value
from app.features.form_builder.qtside.items.model import Item
from app.qt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLineEdit, QTableWidget, QToolButton, QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.items.editor import ItemEditor

_MORE_CLOSED = "More properties \u25b8"
_MORE_OPEN = "More properties \u25be"

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


def item_details(
    editor: "ItemEditor",
    kind: str,
    current: Callable[[], Item],
    on_value: Callable[[str, Optional[Value]], None],
    parent: QWidget,
) -> QWidget:
    """The UX-ITEM-003 details, including More properties. One panel for every caller."""

    def on_more(host: QWidget) -> None:
        from app.features.form_builder.qtside.items.more import show_more

        show_more(host, editor, current, on_value, lambda: _set_more_open(host, False, focus_row=True))

    def icon_row(host: QWidget) -> QWidget:
        from app.features.form_builder.qtside.items.icon_row import build_icon_row

        return build_icon_row(editor, current, on_value, host)

    return build_details(kind, current, on_value, on_more, parent, icon_row)


def build_details(
    kind: str,
    current: Callable[[], Item],
    on_value: Callable[[str, Optional[Value]], None],
    on_more: Callable[[QWidget], None],
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
    more.setText(_MORE_CLOSED)
    more.setObjectName("formBuilder.itemMore")
    more.clicked.connect(lambda: _toggle_more(panel, more, on_more))
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
            starts = _check_state(form, item, on_value, parent)
            starts.setEnabled(box.isChecked())
            box.toggled.connect(lambda checked, combo=starts: combo.setEnabled(bool(checked)))


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


def _check_state(form: QFormLayout, item: Item, on_value: Callable[[str, Optional[Value]], None], parent: QWidget) -> QComboBox:
    combo = QComboBox(parent)
    combo.setObjectName("formBuilder.itemCheckState")
    combo.addItems(_CHECK)
    current = _enum(item, "checkState")
    for index, label in enumerate(_CHECK):
        if _CHECK_QT[label] == current:
            combo.setCurrentIndex(index)
    combo.currentTextChanged.connect(lambda text: on_value("checkState", EnumValue(_CHECK_QT.get(text, text))))
    form.addRow("Starts", combo)
    return combo


def _toggle_more(panel: QWidget, button: QToolButton, on_more: Callable[[QWidget], None]) -> None:
    existing = panel.findChild(QWidget, "formBuilder.itemMorePanel")
    if existing is None:
        on_more(panel)
        _set_more_open(panel, True, focus_row=False)
        return
    _set_more_open(panel, not existing.isVisible(), focus_row=False)


def _set_more_open(details: QWidget, open_: bool, *, focus_row: bool) -> None:
    panel = details.findChild(QWidget, "formBuilder.itemMorePanel")
    if panel is not None:
        panel.setVisible(open_)
    button = details.findChild(QToolButton, "formBuilder.itemMore")
    if button is not None:
        button.setText(_MORE_OPEN if open_ else _MORE_CLOSED)
    _refit(details)
    if not open_ and focus_row:
        _return_focus(details)


def _refit(widget: QWidget) -> None:
    """The list editor positions details by size hint, so it has to measure again."""
    current: Optional[QWidget] = widget
    while current is not None:
        layout = current.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        current.updateGeometry()
        refit = getattr(current, "refit_details", None)
        if callable(refit):
            refit()
            return
        grow = getattr(current, "make_room", None)
        if callable(grow):
            grow(max(current.height(), widget.sizeHint().height() + 220))
            return
        current = current.parentWidget()


def _return_focus(details: QWidget) -> None:
    current: Optional[QWidget] = details.parentWidget()
    while current is not None:
        focus_row = getattr(current, "focus_row", None)
        focused = getattr(current, "focused_index", None)
        if callable(focus_row) and callable(focused):
            focus_row(focused())
            return
        current = current.parentWidget()
    window = details.window()
    grid = window.findChild(QTableWidget, "formBuilder.itemCells") if window is not None else None
    if grid is not None:
        grid.setFocus()


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
