"""Selection state synchronization for designer surfaces."""

from __future__ import annotations

from PySide2.QtCore import QObject, Signal


class SelectionController(QObject):
    """Single-selection state coordinator across canvas/inspector views."""

    selection_changed = Signal(str)
    selection_set_changed = Signal(list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._selected_object_name: str | None = None
        self._selected_object_names: list[str] = []

    @property
    def selected_object_name(self) -> str | None:
        return self._selected_object_name

    @property
    def selected_object_names(self) -> list[str]:
        return list(self._selected_object_names)

    def set_selected_object_name(self, object_name: str | None) -> None:
        self.set_selected_object_names([] if object_name is None else [object_name])

    def set_selected_object_names(self, object_names: list[str]) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for object_name in object_names:
            if not object_name or object_name in seen:
                continue
            seen.add(object_name)
            normalized.append(object_name)
        first = normalized[0] if normalized else None
        if first == self._selected_object_name and normalized == self._selected_object_names:
            return
        self._selected_object_name = first
        self._selected_object_names = normalized
        self.selection_changed.emit(first or "")
        self.selection_set_changed.emit(list(normalized))
