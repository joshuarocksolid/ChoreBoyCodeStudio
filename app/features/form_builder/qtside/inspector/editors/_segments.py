"""SegmentedControl with a quiet paint path.

Size and alignment paint a selection without writing it. A second click on
the same segment still tells the caller, so a class default can be chosen.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import SEGMENT_CELL
from app.features.form_builder.qtside.theme.segmented import SegmentedControl
from app.qt.QtCore import QSize
from app.qt.QtGui import QIcon
from app.qt.QtWidgets import QToolButton


class ChoiceSegments(SegmentedControl):
    """One segmented row. ``show_index(-1)`` clears the selection."""

    def __init__(self, parent: Optional[object] = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._quiet = False
        self._icons: List[QIcon] = []

    def buttons(self) -> List[QToolButton]:
        return list(self._buttons)

    def show_index(self, index: int) -> None:
        self._quiet = True
        self.blockSignals(True)
        try:
            if index < 0:
                self._index = -1
                for button in self._buttons:
                    button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(False)
                self._paint()
                return
            super().set_current_index(index)
        finally:
            self.blockSignals(False)
            self._quiet = False

    def set_current_index(self, index: int) -> None:
        if self._quiet:
            super().set_current_index(index)
            return
        before = self._index
        super().set_current_index(index)
        if index == before:
            self.current_changed.emit(index)

    def name_buttons(self, names: Sequence[str]) -> None:
        """Object names tests and the pane's segment rules already use."""
        for button, name in zip(self._buttons, names):
            button.setObjectName(name)
            button.setProperty("fbSegment", "true")

    def set_icons(self, icons: Sequence[QIcon]) -> None:
        self._icons = [icon for icon in icons]
        self._apply_icons()

    def apply_chrome(self, chrome: FormChrome) -> None:
        super().apply_chrome(chrome)
        for button in self._buttons:
            if button.objectName() != "formBuilder.segment":
                button.setProperty("fbSegment", "true")
        if self._icons:
            self._apply_icons()

    def _apply_icons(self) -> None:
        for button, icon in zip(self._buttons, self._icons):
            button.setIcon(icon)
            button.setIconSize(QSize(SEGMENT_CELL, SEGMENT_CELL))
            if not button.text():
                button.setFixedWidth(SEGMENT_CELL)
