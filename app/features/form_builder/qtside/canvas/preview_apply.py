"""Put a preview font on a realized tree.

The root and every child take the preview point size. A child that already
had its own font keeps that font's other fields. Normal at 100% clears the
preview from children that had no font of their own. An application style
sheet blocks parent-font inheritance, so the point size is set on each child.
This module does not write the document, geometry, the application font, or
the application palette.
"""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import Qt
from app.qt.QtGui import QFont
from app.qt.QtWidgets import QWidget

from app.features.form_builder.engine.preview_state import PreviewState, applied_point_size

_FILE = "_cbcsFileFont"
_APPLIED = "_cbcsAppliedPt"
_FORCED = "_cbcsPreviewForced"


def apply_preview(root: QWidget, state: PreviewState, startup_font: QFont) -> None:
    """Idempotent. Normal at 100% puts the startup font back on the root."""
    startup_points = font_point_size(startup_font)
    if state.is_plain():
        root.setFont(QFont(startup_font))
        _restore_children(root)
    else:
        point = applied_point_size(state, startup_points)
        font = QFont(startup_font)
        font.setPointSizeF(point)
        root.setFont(font)
        _apply_children(root, point, startup_font)
    layout = root.layout()
    if layout is not None:
        layout.activate()


def font_point_size(font: QFont) -> Optional[float]:
    """None when the font is sized in pixels."""
    size = float(font.pointSizeF())
    if size > 0:
        return size
    return None


def _apply_children(root: QWidget, point: float, startup_font: QFont) -> None:
    for child in root.findChildren(QWidget):
        saved = _file_font(child)
        base = QFont(saved) if saved is not None else QFont(startup_font)
        base.setPointSizeF(point)
        child.setFont(base)
        setattr(child, _APPLIED, point)
        if saved is None:
            setattr(child, _FORCED, True)


def _restore_children(root: QWidget) -> None:
    for child in root.findChildren(QWidget):
        saved = _file_font(child)
        if saved is not None:
            child.setFont(QFont(saved))
            setattr(child, _APPLIED, font_point_size(saved))
            continue
        if not getattr(child, _FORCED, False):
            continue
        child.setAttribute(_set_font_flag(), False)
        setattr(child, _FORCED, False)
        if hasattr(child, _APPLIED):
            delattr(child, _APPLIED)


def _file_font(child: QWidget) -> Optional[QFont]:
    saved = getattr(child, _FILE, None)
    applied = getattr(child, _APPLIED, None)
    current = QFont(child.font())
    current_pt = float(current.pointSizeF())
    if getattr(child, _FORCED, False):
        if isinstance(applied, (int, float)) and abs(current_pt - float(applied)) <= 0.05:
            return None
        setattr(child, _FORCED, False)
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


def _set_font_flag() -> object:
    return getattr(getattr(Qt, "WidgetAttribute", Qt), "WA_SetFont")


def _own_font(widget: QWidget) -> bool:
    return bool(widget.testAttribute(getattr(Qt, "WA_SetFont")))
