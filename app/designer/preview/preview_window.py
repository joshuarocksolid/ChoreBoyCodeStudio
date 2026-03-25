"""Preview window helpers for designer form rendering."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QWidget


def configure_preview_widget(widget: QWidget, *, window_title: str) -> QWidget:
    """Apply common preview window options and return widget."""
    widget.setAttribute(Qt.WA_DeleteOnClose, True)
    widget.setWindowTitle(window_title)
    return widget
