"""Put a preview font on a realized tree.

The root always takes a copy of the startup font. A child is touched only
when it already has its own font. This module does not write the document,
geometry, the application font, or the application palette.
"""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import Qt
from app.qt.QtGui import QFont
from app.qt.QtWidgets import QWidget

from app.features.form_builder.engine.preview_state import PreviewState, applied_point_size

_FILE = "_cbcsFileFont"
_APPLIED = "_cbcsAppliedPt"


def apply_preview(root: QWidget, state: PreviewState, startup_font: QFont) -> None:
    """Idempotent. Normal at 100% puts the startup font back on the root."""
    startup_points = font_point_size(startup_font)
    if state.is_plain():
        root.setFont(QFont(startup_font))
        _restore_authored(root)
    else:
        point = applied_point_size(state, startup_points)
        font = QFont(startup_font)
        font.setPointSizeF(point)
        root.setFont(font)
        _scale_authored(root, point)
    layout = root.layout()
    if layout is not None:
        layout.activate()


def font_point_size(font: QFont) -> Optional[float]:
    """None when the font is sized in pixels."""
    size = float(font.pointSizeF())
    if size > 0:
        return size
    return None


def _scale_authored(root: QWidget, point: float) -> None:
    for child in root.findChildren(QWidget):
        saved = _file_font(child)
        if saved is None:
            continue
        font = QFont(saved)
        font.setPointSizeF(point)
        child.setFont(font)
        setattr(child, _APPLIED, point)


def _restore_authored(root: QWidget) -> None:
    for child in root.findChildren(QWidget):
        saved = getattr(child, _FILE, None)
        if not isinstance(saved, QFont):
            continue
        child.setFont(QFont(saved))
        setattr(child, _APPLIED, font_point_size(saved))


def _file_font(child: QWidget) -> Optional[QFont]:
    saved = getattr(child, _FILE, None)
    applied = getattr(child, _APPLIED, None)
    current = QFont(child.font())
    current_pt = float(current.pointSizeF())
    stale = isinstance(saved, QFont) and isinstance(applied, (int, float))
    if stale and abs(current_pt - float(applied)) <= 0.05:
        stale = False
    if not isinstance(saved, QFont) or stale:
        if not _own_font(child):
            if isinstance(saved, QFont):
                delattr(child, _FILE)
            return None
        saved = current
        setattr(child, _FILE, saved)
    return saved


def _own_font(widget: QWidget) -> bool:
    return bool(widget.testAttribute(getattr(Qt, "WA_SetFont")))
