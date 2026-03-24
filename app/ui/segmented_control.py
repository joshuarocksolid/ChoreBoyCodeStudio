"""Reusable segmented control (pill toggle) widget."""

from __future__ import annotations

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QHBoxLayout, QPushButton, QStyle, QWidget


class SegmentedControl(QWidget):
    """Horizontal pill-style toggle with mutually exclusive segments.

    Each segment holds a user-defined *data* string.  Only one segment
    can be active at a time.  Disabled segments are visible but cannot
    be selected.
    """

    selection_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._buttons: dict[str, QPushButton] = {}
        self._order: list[str] = []
        self._selected: str = ""

    # -- public API ----------------------------------------------------------

    def add_segment(self, label: str, data: str) -> None:
        """Append a new segment with *label* text and *data* identifier."""
        btn = QPushButton(label, self)
        btn.setCheckable(True)
        btn.setAutoExclusive(False)
        btn.setProperty("segmentActive", False)
        btn.clicked.connect(lambda _checked=False, d=data: self._on_segment_clicked(d))
        self._buttons[data] = btn
        self._order.append(data)
        self._layout.addWidget(btn)
        self._refresh_position_properties()
        if len(self._order) == 1:
            self._apply_selection(data, emit=False)

    def set_selected(self, data: str) -> None:
        """Programmatically select the segment identified by *data*."""
        if data not in self._buttons:
            return
        btn = self._buttons[data]
        if not btn.isEnabled():
            return
        self._apply_selection(data, emit=False)

    def selected_data(self) -> str:
        """Return the *data* string of the currently active segment."""
        return self._selected

    def set_segment_enabled(self, data: str, enabled: bool) -> None:
        """Enable or disable a segment without removing it."""
        btn = self._buttons.get(data)
        if btn is None:
            return
        btn.setEnabled(enabled)

    def set_segment_tooltip(self, data: str, tooltip: str) -> None:
        """Set the tooltip on a specific segment."""
        btn = self._buttons.get(data)
        if btn is None:
            return
        btn.setToolTip(tooltip)

    # -- internals -----------------------------------------------------------

    def _on_segment_clicked(self, data: str) -> None:
        btn = self._buttons.get(data)
        if btn is None:
            return
        if not btn.isEnabled():
            btn.setChecked(False)
            return
        if data == self._selected:
            btn.setChecked(True)
            return
        self._apply_selection(data, emit=True)

    def _apply_selection(self, data: str, *, emit: bool) -> None:
        self._selected = data
        for d, btn in self._buttons.items():
            is_active = d == data
            btn.setChecked(is_active)
            btn.setProperty("segmentActive", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if emit:
            self.selection_changed.emit(data)

    def _refresh_position_properties(self) -> None:
        for i, data in enumerate(self._order):
            btn = self._buttons[data]
            if len(self._order) == 1:
                pos = "only"
            elif i == 0:
                pos = "first"
            elif i == len(self._order) - 1:
                pos = "last"
            else:
                pos = "middle"
            btn.setProperty("segmentPosition", pos)
