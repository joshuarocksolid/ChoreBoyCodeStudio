"""Number fields: int, uint, long, float and double."""

from __future__ import annotations

from typing import Optional, Tuple, Type, Union

from app.features.form_builder.engine.ui4.values import (
    DoubleValue,
    FloatValue,
    LongLongValue,
    NumberValue,
    UIntValue,
    ULongLongValue,
    Value,
)
from app.features.form_builder.qtside.inspector.api import (
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
from app.features.form_builder.qtside.inspector.editors._editor_kit import can_reset, name_part
from app.features.form_builder.qtside.inspector.editors._number_box import (
    IntBox,
    RealBox,
    WideIntBox,
    _SpinHooks,
)
from app.qt.QtWidgets import QHBoxLayout, QLabel, QWidget
from app.qt.QtCore import Qt

_INT_CLASS = {
    NumberValue.ELEMENT: NumberValue,
    UIntValue.ELEMENT: UIntValue,
    LongLongValue.ELEMENT: LongLongValue,
    ULongLongValue.ELEMENT: ULongLongValue,
}
_TYPE_RANGE = {
    NumberValue.ELEMENT: (-2147483648, 2147483647),
    UIntValue.ELEMENT: (0, 4294967295),
    LongLongValue.ELEMENT: (-9223372036854775808, 9223372036854775807),
    ULongLongValue.ELEMENT: (0, 18446744073709551615),
}
# Curated rows name a tighter range than the Qt type.
_CURATED = {
    "maxLength": (0, 32767),
}
_UNITS = {
    "spacing": "px",
    "horizontalSpacing": "px",
    "verticalSpacing": "px",
    "leftMargin": "px",
    "topMargin": "px",
    "rightMargin": "px",
    "bottomMargin": "px",
    "margin": "px",
    "minimumWidth": "px",
    "maximumWidth": "px",
    "minimumHeight": "px",
    "maximumHeight": "px",
}
_INT32 = (-2147483648, 2147483647)


def _range_for(element: str, qt_name: str) -> Tuple[int, int]:
    curated = _CURATED.get(qt_name)
    if curated is not None and element == NumberValue.ELEMENT:
        return curated
    return _TYPE_RANGE[element]


def _fits_spin(low: int, high: int) -> bool:
    return low >= _INT32[0] and high <= _INT32[1]


class NumberEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._can_reset = True
        self._hooks = _SpinHooks(self._commit, self._host.invalid, self._reset, lambda: None)
        element = spec.element
        box: Union[IntBox, RealBox, WideIntBox]
        if element in (DoubleValue.ELEMENT, FloatValue.ELEMENT):
            box = RealBox(parent, self._hooks, places=6, strip=True)
            self._cls: Optional[Type[Value]] = FloatValue if element == FloatValue.ELEMENT else DoubleValue
        else:
            low, high = _range_for(element, host.qt_name)
            self._cls = _INT_CLASS[element]
            if _fits_spin(low, high):
                box = IntBox(low, high, parent, self._hooks)
            else:
                box = WideIntBox(low, high, parent, self._hooks)
        self._box = box
        unit = _UNITS.get(host.qt_name, "")
        if unit:
            self._root = QWidget(parent)
            layout = QHBoxLayout(self._root)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(box, 1)
            label = QLabel(unit, self._root)
            label.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus"))  # type: ignore[arg-type]
            layout.addWidget(label, 0)
        else:
            self._root = box

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._box, value)
        self._can_reset = can_reset(value, self._can_reset)
        name_part(self._box, self._host, "value")
        if isinstance(value, Mixed):
            self._box.show_blank(MIXED_TEXT, can_reset=self._can_reset)
            return
        number = _number_of(value)
        if number is None:
            self._box.show_blank(NOT_SET_TEXT, can_reset=False)
            return
        self._box.show_number(number, can_reset=self._can_reset)

    def is_dirty(self) -> bool:
        return bool(self._box.is_dirty())

    def _commit(self, number: Union[int, float]) -> None:
        cls = self._cls
        if cls is None:
            return
        if cls in (FloatValue, DoubleValue):
            self._host.commit(cls(float(number)))  # type: ignore[arg-type]
            return
        self._host.commit(cls(int(number)))  # type: ignore[arg-type]

    def _reset(self) -> None:
        self._host.reset()


def register(registrar: Registrar) -> None:
    for element in _INT_CLASS:
        registrar.editor(EditorKey(element), NumberEditor)
    for element in (DoubleValue.ELEMENT, FloatValue.ELEMENT):
        registrar.editor(EditorKey(element), NumberEditor)


def _number_of(value: RowValue) -> Optional[float]:
    if isinstance(value, Written):
        found: Optional[Value] = value.value
    elif isinstance(value, Unset):
        found = value.default
    else:
        return None
    if isinstance(found, (NumberValue, UIntValue, LongLongValue, ULongLongValue, DoubleValue, FloatValue)):
        return float(found.value)
    return None
