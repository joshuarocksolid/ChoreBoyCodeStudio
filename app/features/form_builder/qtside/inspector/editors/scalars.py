
from __future__ import annotations

from typing import Dict, Optional, Tuple, Type, Union

from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    CStringValue,
    DoubleValue,
    FloatValue,
    LongLongValue,
    NumberValue,
    StringValue,
    UIntValue,
    ULongLongValue,
    Value,
)
from app.features.form_builder.qtside.inspector.api import (
    KEY_SEQUENCE,
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
from app.qt.QtGui import QKeySequence
from app.qt.QtWidgets import QCheckBox, QDoubleSpinBox, QKeySequenceEdit, QLineEdit, QSpinBox, QWidget

_INT_CLASS: Dict[str, Type[Value]] = {
    NumberValue.ELEMENT: NumberValue,
    UIntValue.ELEMENT: UIntValue,
    LongLongValue.ELEMENT: LongLongValue,
    ULongLongValue.ELEMENT: ULongLongValue,
}
_INT_RANGE: Dict[str, Tuple[int, int]] = {
    NumberValue.ELEMENT: (-2147483648, 2147483647),
    UIntValue.ELEMENT: (0, 2147483647),
    LongLongValue.ELEMENT: (-2147483648, 2147483647),
    ULongLongValue.ELEMENT: (0, 2147483647),
}
class TextEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._shown = ""
        self._edit = QLineEdit(parent)
        self._edit.editingFinished.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._edit

    def show(self, value: RowValue) -> None:
        mark(self._edit, value)
        self._shown = _text_of(value)
        self._edit.blockSignals(True)
        self._edit.setText(self._shown)
        if not self._edit.hasFocus():
            # setText leaves the cursor at the end, which scrolls a long
            # value to its tail ("ame@example.com").
            self._edit.setCursorPosition(0)
        self._edit.setPlaceholderText(_placeholder(value))
        self._edit.blockSignals(False)

    def is_dirty(self) -> bool:
        return self._edit.text() != self._shown

    def _commit(self) -> None:
        text = self._edit.text()
        if text == self._shown:
            return
        if self._spec.element == CStringValue.ELEMENT:
            self._host.commit(CStringValue(text))
            return
        self._host.commit(StringValue(text))

class BoolEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._box = QCheckBox(parent)
        self._box.clicked.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._box

    def show(self, value: RowValue) -> None:
        mark(self._box, value)
        self._box.blockSignals(True)
        flag = _written_bool(value)
        if isinstance(value, Mixed):
            self._box.setTristate(True)
            self._box.setCheckState(Qt.PartiallyChecked)
        else:
            self._box.setTristate(False)
            self._box.setChecked(bool(flag))
        self._box.blockSignals(False)

    def _commit(self, checked: bool) -> None:
        self._box.setTristate(False)
        self._host.commit(BoolValue(bool(checked)))

class IntEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._cls = _INT_CLASS[spec.element]
        low, high = _INT_RANGE[spec.element]
        self._spin = QSpinBox(parent)
        self._shown_text = ""
        self._spin.setRange(low, high)
        # Commit on Enter, focus-out or a step, not on every typed digit.
        self._spin.setKeyboardTracking(False)
        self._spin.valueChanged.connect(self._commit)
        _name_spin(self._spin, spec.element or "Number")

    @property
    def widget(self) -> QWidget:
        return self._spin

    def show(self, value: RowValue) -> None:
        mark(self._spin, value)
        self._spin.blockSignals(True)
        number = _number_of(value)
        if isinstance(value, Mixed) or number is None:
            self._spin.setSpecialValueText(MIXED_TEXT if isinstance(value, Mixed) else NOT_SET_TEXT)
            self._spin.setValue(self._spin.minimum())
        else:
            self._spin.setSpecialValueText("")
            self._spin.setValue(_clamp(number, self._spin.minimum(), self._spin.maximum()))
        self._spin.blockSignals(False)
        self._shown_text = self._spin.text()
        _name_spin(self._spin, self._spin.accessibleName() or self._spec.element or "Number")

    def is_dirty(self) -> bool:
        """Digits typed but not committed. Esc reverts them by re-showing the value."""
        return self._spin.text() != self._shown_text

    def _commit(self, number: int) -> None:
        self._host.commit(self._cls(int(number)))

class DoubleEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._cls: Type[Union[DoubleValue, FloatValue]] = (
            FloatValue if spec.element == FloatValue.ELEMENT else DoubleValue
        )
        self._spin = QDoubleSpinBox(parent)
        self._shown_text = ""
        self._spin.setDecimals(6)
        self._spin.setRange(-1e12, 1e12)
        # Commit on Enter, focus-out or a step, not on every typed digit.
        self._spin.setKeyboardTracking(False)
        self._spin.valueChanged.connect(self._commit)
        _name_spin(self._spin, spec.element or "Number")

    @property
    def widget(self) -> QWidget:
        return self._spin

    def show(self, value: RowValue) -> None:
        mark(self._spin, value)
        self._spin.blockSignals(True)
        number = _number_of(value)
        if isinstance(value, Mixed) or number is None:
            self._spin.setSpecialValueText(MIXED_TEXT if isinstance(value, Mixed) else NOT_SET_TEXT)
            self._spin.setValue(self._spin.minimum())
        else:
            self._spin.setSpecialValueText("")
            self._spin.setValue(float(number))
        self._spin.blockSignals(False)
        self._shown_text = self._spin.text()
        _name_spin(self._spin, self._spin.accessibleName() or self._spec.element or "Number")

    def is_dirty(self) -> bool:
        """Digits typed but not committed. Esc reverts them by re-showing the value."""
        return self._spin.text() != self._shown_text

    def _commit(self, number: float) -> None:
        self._host.commit(self._cls(float(number)))

class KeySequenceEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._edit = QKeySequenceEdit(parent)
        self._edit.keySequenceChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._edit

    def show(self, value: RowValue) -> None:
        mark(self._edit, value)
        self._edit.blockSignals(True)
        self._edit.setKeySequence(QKeySequence(_text_of(value)))
        self._edit.blockSignals(False)

    def _commit(self, sequence: QKeySequence) -> None:
        text = sequence.toString(QKeySequence.PortableText)
        if self._spec.element == CStringValue.ELEMENT:
            self._host.commit(CStringValue(text))
            return
        self._host.commit(StringValue(text))

def register(registrar: Registrar) -> None:
    for element in (StringValue.ELEMENT, CStringValue.ELEMENT):
        registrar.editor(EditorKey(element), TextEditor, baseline=True)
    registrar.editor(EditorKey(BoolValue.ELEMENT), BoolEditor, baseline=True)
    for element in _INT_CLASS:
        registrar.editor(EditorKey(element), IntEditor, baseline=True)
    for element in (DoubleValue.ELEMENT, FloatValue.ELEMENT):
        registrar.editor(EditorKey(element), DoubleEditor, baseline=True)
    registrar.editor(KEY_SEQUENCE, KeySequenceEditor, baseline=True)

def _text_of(value: RowValue) -> str:
    found = _written(value)
    if isinstance(found, (StringValue, CStringValue)):
        return found.text
    return ""

def _placeholder(value: RowValue) -> str:
    if isinstance(value, Mixed):
        return MIXED_TEXT
    if isinstance(value, Unset):
        if isinstance(value.default, (StringValue, CStringValue)) and value.default.text:
            return value.default.text
        return NOT_SET_TEXT
    return ""

def _written(value: RowValue) -> Optional[Value]:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset):
        return value.default
    return None

def _written_bool(value: RowValue) -> Optional[bool]:
    found = _written(value)
    if isinstance(found, BoolValue):
        return found.value
    return None

def _number_of(value: RowValue) -> Optional[float]:
    found = _written(value)
    if isinstance(found, (NumberValue, UIntValue, LongLongValue, ULongLongValue, DoubleValue, FloatValue)):
        return float(found.value)
    return None

def _name_spin(box: QWidget, name: str) -> None:
    box.setAccessibleName(name)
    line = getattr(box, "lineEdit", None)
    edit = line() if callable(line) else None
    if edit is not None:
        edit.setAccessibleName(name)


def _clamp(number: float, low: int, high: int) -> int:
    value = int(number)
    return max(low, min(high, value))

