"""Preview window helpers for designer form rendering."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QStyleFactory, QWidget


def configure_preview_widget(
    widget: QWidget,
    *,
    window_title: str,
    style_name: Optional[str] = None,
    viewport_size: Optional[Tuple[int, int]] = None,
) -> QWidget:
    """Apply common preview window options and return widget."""
    widget.setAttribute(Qt.WA_DeleteOnClose, True)
    widget.setWindowTitle(window_title)
    if style_name:
        style = QStyleFactory.create(style_name)
        if style is not None:
            widget.setStyle(style)
    if viewport_size is not None:
        width, height = viewport_size
        widget.resize(int(width), int(height))
    return widget
