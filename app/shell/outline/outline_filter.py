"""Inline filter row for the outline panel."""

from __future__ import annotations

from typing import Any, Optional

from PySide2.QtCore import QEvent, Qt, Signal
from PySide2.QtGui import QKeyEvent
from PySide2.QtWidgets import QHBoxLayout, QLineEdit, QWidget


class _OutlineFilterRow(QWidget):
    """Inline search box that filters the outline tree by symbol name."""

    text_changed: Any = Signal(str)
    closed: Any = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.outlinePanel.filterRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self._line_edit = QLineEdit(self)
        self._line_edit.setObjectName("shell.outlinePanel.filter")
        self._line_edit.setPlaceholderText("Filter symbols")
        self._line_edit.setClearButtonEnabled(True)
        self._line_edit.textChanged.connect(self.text_changed)
        self._line_edit.installEventFilter(self)
        layout.addWidget(self._line_edit, 1)

    def line_edit(self) -> QLineEdit:
        return self._line_edit

    def focus(self) -> None:
        self._line_edit.setFocus(Qt.ShortcutFocusReason)
        self._line_edit.selectAll()

    def text(self) -> str:
        return self._line_edit.text()

    def set_text(self, text: str) -> None:
        if self._line_edit.text() == text:
            return
        self._line_edit.setText(text)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self._line_edit and event.type() == QEvent.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() == Qt.Key_Escape:
                if self._line_edit.text():
                    self._line_edit.clear()
                else:
                    self.closed.emit()
                return True
        return super().eventFilter(watched, event)
