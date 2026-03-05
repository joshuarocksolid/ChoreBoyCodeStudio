"""Selection state synchronization for designer surfaces."""

from __future__ import annotations

from PySide2.QtCore import QObject, Signal


class SelectionController(QObject):
    """Single-selection state coordinator across canvas/inspector views."""

    selection_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._selected_object_name: str | None = None

    @property
    def selected_object_name(self) -> str | None:
        return self._selected_object_name

    def set_selected_object_name(self, object_name: str | None) -> None:
        if object_name == self._selected_object_name:
            return
        self._selected_object_name = object_name
        self.selection_changed.emit(object_name or "")
