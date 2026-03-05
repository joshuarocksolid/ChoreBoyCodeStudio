"""Designer editor surface shell widget (placeholder)."""

from __future__ import annotations

from PySide2.QtWidgets import QWidget


class DesignerEditorSurface(QWidget):
    """Host widget for visual `.ui` designer workflows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

