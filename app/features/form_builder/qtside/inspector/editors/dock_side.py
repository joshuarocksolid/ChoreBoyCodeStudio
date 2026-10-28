"""Four-segment Dock side control (UX-CONT-012).

The row writes ``dockWidgetArea`` as the number Qt stores. The inspector
selects this editor when the row's editor key is ``dock_side``.
"""

from __future__ import annotations

from typing import List, Tuple

from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.qtside.inspector.api import EditorHost, EditorKey, Registrar, RowValue, Unset, Written, mark
from app.qt.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget

DOCK_SIDE = EditorKey("dock_side")

_SIDES: Tuple[Tuple[str, int], ...] = (
    ("Left", 1),
    ("Right", 2),
    ("Top", 4),
    ("Bottom", 8),
)


class DockSideEditor:
    """Left, Right, Top, Bottom. One of them is the dock's side."""

    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._buttons: List[Tuple[int, QToolButton]] = []
        group = QButtonGroup(self._root)
        group.setExclusive(True)
        for label, number in _SIDES:
            button = QToolButton(self._root)
            button.setText(label)
            button.setCheckable(True)
            button.setAccessibleName("Dock side: %s" % label)
            button.clicked.connect(self._commit)
            group.addButton(button)
            layout.addWidget(button)
            self._buttons.append((number, button))

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._root, value)
        number = _number(value)
        for side, button in self._buttons:
            button.blockSignals(True)
            button.setChecked(side == number)
            button.blockSignals(False)

    def _commit(self, _checked: bool) -> None:
        for number, button in self._buttons:
            if button.isChecked():
                self._host.commit(NumberValue(number))
                return


def _number(value: RowValue) -> int:
    if isinstance(value, Written) and isinstance(value.value, NumberValue):
        return value.value.value
    if isinstance(value, Unset) and isinstance(value.default, NumberValue):
        return value.default.value
    return 1


def register(registrar: Registrar) -> None:
    registrar.editor(DOCK_SIDE, DockSideEditor)
