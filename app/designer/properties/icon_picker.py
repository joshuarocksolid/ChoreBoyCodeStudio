"""Icon path picker widget for designer property editing."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class IconPickerField(QWidget):
    """Line-edit + browse button control for icon paths."""

    path_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._line_edit = QLineEdit(self)
        self._line_edit.editingFinished.connect(self._emit_path)
        self._browse_button = QPushButton("Browse…", self)
        self._browse_button.clicked.connect(self._browse_for_icon)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._line_edit, 1)
        layout.addWidget(self._browse_button, 0)

    def set_path(self, path: str) -> None:
        self._line_edit.setText(path)

    def path(self) -> str:
        return self._line_edit.text().strip()

    def _emit_path(self) -> None:
        self.path_changed.emit(self.path())

    def _browse_for_icon(self) -> None:
        selected_file, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            str(Path.cwd()),
            "Icons (*.png *.jpg *.jpeg *.bmp *.svg *.ico *.qrc);;All Files (*)",
        )
        if not selected_file:
            return
        self.set_path(selected_file)
        self._emit_path()
