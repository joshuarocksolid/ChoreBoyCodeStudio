
from __future__ import annotations

from typing import List, Tuple

from app.features.form_builder.engine.ui4.values import (
    CursorShapeValue,
    CursorValue,
    EnumValue,
    SetValue,
)
from app.features.form_builder.qtside.inspector.api import (
    ALIGNMENT,
    MIXED_TEXT,
    NOT_SET_TEXT,
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

_HORIZONTAL = ("AlignLeft", "AlignHCenter", "AlignRight", "AlignJustify")
_VERTICAL = ("AlignTop", "AlignVCenter", "AlignBottom")
_ALIGN_ALIASES = {"AlignLeading": "AlignLeft", "AlignTrailing": "AlignRight"}
_SHORT_ALIGN = {
    "AlignHCenter": "Center",
    "AlignVCenter": "Center",
}
_ALIGN_TAILS = {
    "AlignLeft": "Left",
    "AlignHCenter": "Horizontal center",
    "AlignRight": "Right",
    "AlignJustify": "Justify",
    "AlignTop": "Top",
    "AlignVCenter": "Vertical center",
    "AlignBottom": "Bottom",
}


def _row_label(host: EditorHost) -> str:
    label = getattr(host, "row_label", "")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return "Alignment"
# Layout policies are long Qt enumerator names. The combo shows a short label.
# Item data stays the enumerator, which is what the document stores.
_PLAIN_ENUM = {
    "SetDefaultConstraint": "Default",
    "SetNoConstraint": "None",
    "SetMinimumSize": "Minimum",
    "SetFixedSize": "Fixed",
    "SetMaximumSize": "Maximum",
    "SetMinAndMaxSize": "Min and max",
    "FieldsStayAtSizeHint": "Stay at hint",
    "ExpandingFieldsGrow": "Expanding",
    "AllNonFixedFieldsGrow": "All but fixed",
    "DontWrapRows": "Don't wrap",
    "WrapLongRows": "Long rows",
    "WrapAllRows": "All rows",
}


def _fill_enum(combo: QComboBox, names: Tuple[str, ...]) -> None:
    for name in names:
        label = _PLAIN_ENUM.get(name, name)
        combo.addItem(label)
        index = combo.count() - 1
        combo.setItemData(index, name)
        if label != name:
            combo.setItemData(index, name, Qt.ToolTipRole)


_CURSORS = (
    "ArrowCursor",
    "UpArrowCursor",
    "CrossCursor",
    "WaitCursor",
    "IBeamCursor",
    "SizeVerCursor",
    "SizeHorCursor",
    "SizeBDiagCursor",
    "SizeFDiagCursor",
    "SizeAllCursor",
    "BlankCursor",
    "SplitVCursor",
    "SplitHCursor",
    "PointingHandCursor",
    "ForbiddenCursor",
    "WhatsThisCursor",
    "BusyCursor",
    "OpenHandCursor",
    "ClosedHandCursor",
)

class EnumEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._enum = spec.enum
        if spec.enum is None:
            self._box: QWidget = QLabel(parent)
            return
        combo = QComboBox(parent)
        _fill_enum(combo, spec.enum.names)
        combo.currentIndexChanged.connect(self._commit)
        self._box = combo

    @property
    def widget(self) -> QWidget:
        return self._box

    def show(self, value: RowValue) -> None:
        text = _enum_text(value)
        if self._enum is None:
            label = self._box
            assert isinstance(label, QLabel)
            mark(label, value)
            if isinstance(value, Mixed):
                label.setText(MIXED_TEXT)
            elif text:
                label.setText(text)
            else:
                label.setText(NOT_SET_TEXT)
            return
        combo = self._box
        assert isinstance(combo, QComboBox)
        mark(combo, value)
        combo.blockSignals(True)
        names = self._enum.names
        tail = text.split("::")[-1] if text else ""
        index = names.index(tail) if tail in names else -1
        combo.setCurrentIndex(index)
        if index < 0:
            if isinstance(value, Mixed):
                placeholder = MIXED_TEXT
            elif text:
                placeholder = text
            else:
                placeholder = NOT_SET_TEXT
            combo.setPlaceholderText(placeholder)
        else:
            combo.setPlaceholderText("")
        combo.blockSignals(False)

    def _commit(self, index: int) -> None:
        if self._enum is None or index < 0:
            return
        self._host.commit(self._host.enum_value(self._enum, (self._enum.names[index],)))

class SetEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._host = host
        self._enum = spec.enum
        self._list = QListWidget(parent)
        if spec.enum is not None:
            for name in spec.enum.names:
                item = QListWidgetItem(name, self._list)
                item.setFlags(item.flags() | _item_checkable())
        self._list.itemChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._list

    def show(self, value: RowValue) -> None:
        mark(self._list, value)
        chosen = set(_flag_tails(_set_text(value)))
        self._list.blockSignals(True)
        for index in range(self._list.count()):
            item = self._list.item(index)
            item.setCheckState(_checked() if item.text() in chosen else _unchecked())
        self._list.blockSignals(False)

    def _commit(self, _item: QListWidgetItem) -> None:
        enum = self._enum
        if enum is None:
            return
        names = [
            self._list.item(index).text()
            for index in range(self._list.count())
            if enum_value(self._list.item(index).checkState()) == enum_value(_checked())
        ]
        self._host.commit(self._host.enum_value(enum, names))

class AlignmentEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        self._buttons: List[Tuple[str, QToolButton]] = []
        layout.addWidget(self._row(_HORIZONTAL))
        layout.addWidget(self._row(_VERTICAL))

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._root, value)
        # Qt names 1 AlignLeading and 2 AlignTrailing when it turns a value
        # into keys, so a live default reads Leading, not Left.
        chosen = {_ALIGN_ALIASES.get(name, name) for name in _flag_tails(_set_text(value))}
        for name, button in self._buttons:
            button.blockSignals(True)
            button.setChecked(name in chosen)
            button.blockSignals(False)

    def _row(self, names: Tuple[str, ...]) -> QWidget:
        row = QWidget(self._root)
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(2)
        layout.setVerticalSpacing(2)
        group = QButtonGroup(row)
        group.setExclusive(True)
        for index, name in enumerate(names):
            button = QToolButton(row)
            button.setText(_SHORT_ALIGN.get(name, name.replace("Align", "")))
            button.setAccessibleName("%s: %s" % (_row_label(self._host), _ALIGN_TAILS.get(name, button.text())))
            button.setToolTip(name)
            button.setCheckable(True)
            button.setProperty("fbSegment", "true")
            button.setSizePolicy(_size_policy("Expanding"), _size_policy("Fixed"))
            # clicked, not toggled: the exclusive group also untoggles the old
            # segment, which would commit a half-made value first.
            button.clicked.connect(self._commit)
            group.addButton(button)
            layout.addWidget(button, index // 2, index % 2)
            self._buttons.append((name, button))
        return row

    def _commit(self, _checked: bool) -> None:
        names = ["Qt::" + name for name, button in self._buttons if button.isChecked()]
        self._host.commit(SetValue("|".join(names)))

class CursorEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._combo = QComboBox(parent)
        self._combo.addItems(_CURSORS)
        self._combo.currentIndexChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._combo

    def show(self, value: RowValue) -> None:
        mark(self._combo, value)
        name = _cursor_name(value)
        self._combo.blockSignals(True)
        index = self._combo.findText(name)
        if index < 0 and name:
            self._combo.addItem(name)
            index = self._combo.findText(name)
        self._combo.setCurrentIndex(index)
        self._combo.blockSignals(False)

    def _commit(self, index: int) -> None:
        if index < 0:
            return
        name = self._combo.itemText(index)
        if self._spec.element == CursorValue.ELEMENT:
            shape = getattr(Qt, name, 0)
            self._host.commit(CursorValue(enum_value(shape)))
            return
        self._host.commit(CursorShapeValue(name))

def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(EnumValue.ELEMENT), EnumEditor, baseline=True)
    registrar.editor(EditorKey(SetValue.ELEMENT), SetEditor, baseline=True)
    registrar.editor(ALIGNMENT, AlignmentEditor, baseline=True)
    for element in (CursorShapeValue.ELEMENT, CursorValue.ELEMENT):
        registrar.editor(EditorKey(element), CursorEditor, baseline=True)

def _enum_text(value: RowValue) -> str:
    found = _payload(value)
    if isinstance(found, EnumValue):
        return found.text
    if isinstance(found, SetValue):
        return found.text
    return ""

def _set_text(value: RowValue) -> str:
    found = _payload(value)
    if isinstance(found, SetValue):
        return found.text
    return ""

def _size_policy(name: str) -> QSizePolicy.Policy:
    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), name)

def _payload(value: RowValue) -> object:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset) and value.default is not None:
        return value.default
    return None

def _flag_tails(text: str) -> Tuple[str, ...]:
    tails = []
    for piece in text.split("|"):
        name = piece.strip().split("::")[-1]
        if name and name != "0":
            tails.append(name)
    return tuple(tails)

def _cursor_name(value: RowValue) -> str:
    found = _payload(value)
    if isinstance(found, CursorShapeValue):
        return found.name
    if isinstance(found, CursorValue):
        return str(found.value)
    if isinstance(value, Mixed):
        return ""
    return ""

def _item_checkable() -> object:
    item_flag = getattr(Qt, "ItemIsUserCheckable")
    enabled = getattr(Qt, "ItemIsEnabled")
    return item_flag | enabled

def _checked() -> object:
    return getattr(Qt, "Checked")

def _unchecked() -> object:
    return getattr(Qt, "Unchecked")
