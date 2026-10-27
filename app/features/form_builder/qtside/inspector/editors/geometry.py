
from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.engine.ui4.values import RectValue, SizePolicyValue, SizeValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.qt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

_POLICIES = (
    "Fixed",
    "Minimum",
    "Maximum",
    "Preferred",
    "Expanding",
    "MinimumExpanding",
    "Ignored",
)

class SizeEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        row, self._width, self._height = _pair(self._root, ("W", "H"), self._commit)
        layout.addWidget(row)
        self._shown = ("", "")

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._root, value)
        size = _size(value)
        _set_pair(self._width, self._height, 0 if size is None else size.width, 0 if size is None else size.height)
        self._shown = _texts(self._width, self._height)

    def is_dirty(self) -> bool:
        """Digits typed but not committed. Esc reverts them by re-showing the value."""
        return _texts(self._width, self._height) != self._shown

    def _commit(self, _number: int) -> None:
        self._host.commit(SizeValue(self._width.value(), self._height.value()))

class RectEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        origin, self._x, self._y = _pair(self._root, ("X", "Y"), self._commit)
        size, self._width, self._height = _pair(self._root, ("W", "H"), self._commit)
        layout.addWidget(origin)
        layout.addWidget(size)
        self._shown = ("", "", "", "")

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._root, value)
        rect = _rect(value)
        _set_pair(self._x, self._y, 0 if rect is None else rect.x, 0 if rect is None else rect.y)
        _set_pair(
            self._width,
            self._height,
            0 if rect is None else rect.width,
            0 if rect is None else rect.height,
        )
        self._shown = _texts(self._x, self._y, self._width, self._height)

    def is_dirty(self) -> bool:
        """Digits typed but not committed. Esc reverts them by re-showing the value."""
        return _texts(self._x, self._y, self._width, self._height) != self._shown

    def _commit(self, _number: int) -> None:
        self._host.commit(RectValue(self._x.value(), self._y.value(), self._width.value(), self._height.value()))

class SizePolicyEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        policies = QWidget(self._root)
        row = QHBoxLayout(policies)
        row.setContentsMargins(0, 0, 0, 0)
        self._horizontal = _policy_combo(policies)
        self._vertical = _policy_combo(policies)
        row.addWidget(self._horizontal)
        row.addWidget(self._vertical)
        layout.addWidget(policies)
        stretch, self._horstretch, self._verstretch = _pair(self._root, ("H stretch", "V stretch"), self._commit)
        layout.addWidget(stretch)
        self._shown = ("", "")
        self._horizontal.currentIndexChanged.connect(self._commit)
        self._vertical.currentIndexChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._root, value)
        policy = _policy(value)
        horizontal = "Preferred" if policy is None else policy.hsizetype
        vertical = "Preferred" if policy is None else policy.vsizetype
        _select(self._horizontal, horizontal)
        _select(self._vertical, vertical)
        _set_pair(
            self._horstretch,
            self._verstretch,
            0 if policy is None else policy.horstretch,
            0 if policy is None else policy.verstretch,
        )
        self._shown = _texts(self._horstretch, self._verstretch)

    def is_dirty(self) -> bool:
        """Digits typed but not committed. Esc reverts them by re-showing the value."""
        return _texts(self._horstretch, self._verstretch) != self._shown

    def _commit(self, _value: object) -> None:
        self._host.commit(
            SizePolicyValue(
                self._horizontal.currentText() or "Preferred",
                self._vertical.currentText() or "Preferred",
                self._horstretch.value(),
                self._verstretch.value(),
            )
        )

def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(SizeValue.ELEMENT), SizeEditor, baseline=True)
    registrar.editor(EditorKey(RectValue.ELEMENT), RectEditor, baseline=True)
    registrar.editor(EditorKey(SizePolicyValue.ELEMENT), SizePolicyEditor, baseline=True)

def _pair(
    parent: QWidget, captions: Tuple[str, str], on_change: object
) -> Tuple[QWidget, QSpinBox, QSpinBox]:
    """One spin per line. A horizontal pair clips a 4-digit value at 236 px."""
    row = QWidget(parent)
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    boxes: List[QSpinBox] = []
    for caption in captions:
        line = QWidget(row)
        line_layout = QHBoxLayout(line)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(4)
        label = QLabel(caption, line)
        label.setMinimumWidth(0)
        box = QSpinBox(line)
        box.setRange(-1000000, 1000000)
        # Commit on Enter, focus-out or a step, not on every typed digit.
        box.setKeyboardTracking(False)
        box.setMinimumWidth(0)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        box.valueChanged.connect(on_change)
        _show_four_digits(box)
        line_layout.addWidget(label)
        line_layout.addWidget(box, 1)
        layout.addWidget(line)
        boxes.append(box)
    return row, boxes[0], boxes[1]


def _show_four_digits(box: QSpinBox) -> None:
    # Measure on the spin. lineEdit() during construction can hand back a
    # layout item, and that item has no font metrics.
    metrics = box.fontMetrics()
    text_width = int(metrics.horizontalAdvance("0000"))
    current = int(metrics.horizontalAdvance(box.text() or "0"))
    chrome = max(0, int(box.sizeHint().width()) - current)
    box.setMinimumWidth(text_width + chrome + 6)

def _texts(*boxes: QSpinBox) -> Tuple[str, ...]:
    return tuple(box.text() for box in boxes)

def _set_pair(first: QSpinBox, second: QSpinBox, left: int, right: int) -> None:
    first.blockSignals(True)
    second.blockSignals(True)
    first.setValue(int(left))
    second.setValue(int(right))
    first.blockSignals(False)
    second.blockSignals(False)

def _policy_combo(parent: QWidget) -> QComboBox:
    combo = QComboBox(parent)
    combo.addItems(_POLICIES)
    return combo

def _select(combo: QComboBox, name: str) -> None:
    combo.blockSignals(True)
    index = combo.findText(name)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)

def _size(value: RowValue) -> Optional[SizeValue]:
    found = _payload(value)
    return found if isinstance(found, SizeValue) else None

def _rect(value: RowValue) -> Optional[RectValue]:
    found = _payload(value)
    return found if isinstance(found, RectValue) else None

def _policy(value: RowValue) -> Optional[SizePolicyValue]:
    found = _payload(value)
    return found if isinstance(found, SizePolicyValue) else None

def _payload(value: RowValue) -> object:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset):
        return value.default
    return None
