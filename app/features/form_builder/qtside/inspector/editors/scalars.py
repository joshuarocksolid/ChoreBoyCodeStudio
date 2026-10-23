"""Text, true or false, whole numbers, decimals, and key sequences."""

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
    """One line. Commits on Enter and when focus leaves. Mixed is an empty field."""

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
        self._shown = _text_of(value)
        self._edit.blockSignals(True)
        self._edit.setText(self._shown)
        self._edit.setPlaceholderText(_placeholder(value))
        self._edit.blockSignals(False)

    def _commit(self) -> None:
        text = self._edit.text()
        if text == self._shown:
            return
        if self._spec.element == CStringValue.ELEMENT:
            self._host.commit(CStringValue(text))
            return
        self._host.commit(StringValue(text))


class BoolEditor:
    """A check box. Mixed is the partially checked state, which a click leaves."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._box = QCheckBox(parent)
        self._box.clicked.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._box

    def show(self, value: RowValue) -> None:
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
    """A spin box. The value class follows spec.element."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._cls = _INT_CLASS[spec.element]
        low, high = _INT_RANGE[spec.element]
        self._spin = QSpinBox(parent)
        self._spin.setRange(low, high)
        self._spin.valueChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._spin

    def show(self, value: RowValue) -> None:
        self._spin.blockSignals(True)
        if isinstance(value, Mixed):
            self._spin.setSpecialValueText(MIXED_TEXT)
            self._spin.setValue(self._spin.minimum())
        else:
            self._spin.setSpecialValueText("")
            self._spin.setValue(_clamp(_number_of(value), self._spin.minimum(), self._spin.maximum()))
        self._spin.blockSignals(False)

    def _commit(self, number: int) -> None:
        self._host.commit(self._cls(int(number)))


class DoubleEditor:
    """A double spin box. The value class follows spec.element."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._cls: Type[Union[DoubleValue, FloatValue]] = (
            FloatValue if spec.element == FloatValue.ELEMENT else DoubleValue
        )
        self._spin = QDoubleSpinBox(parent)
        self._spin.setDecimals(6)
        self._spin.setRange(-1e12, 1e12)
        self._spin.valueChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._spin

    def show(self, value: RowValue) -> None:
        self._spin.blockSignals(True)
        if isinstance(value, Mixed):
            self._spin.setSpecialValueText(MIXED_TEXT)
            self._spin.setValue(self._spin.minimum())
        else:
            self._spin.setSpecialValueText("")
            self._spin.setValue(float(_number_of(value)))
        self._spin.blockSignals(False)

    def _commit(self, number: float) -> None:
        self._host.commit(self._cls(float(number)))


class KeySequenceEditor:
    """Edits a key sequence and commits portable text."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._edit = QKeySequenceEdit(parent)
        self._edit.keySequenceChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._edit

    def show(self, value: RowValue) -> None:
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


def _number_of(value: RowValue) -> float:
    found = _written(value)
    if isinstance(found, (NumberValue, UIntValue, LongLongValue, ULongLongValue, DoubleValue, FloatValue)):
        return float(found.value)
    return 0.0


def _clamp(number: float, low: int, high: int) -> int:
    value = int(number)
    return max(low, min(high, value))

