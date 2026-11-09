"""Stand-ins for widgets the editor must not build (UX-CONT-017).

An OpenGL widget or a Qt Quick view needs a GL context or a QML engine, and
user classes run code. The editor draws a labelled rectangle with the same
size policy and size hint instead, so the layout matches run time. Nothing
here creates a GL context or a QML engine.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.qt.QtCore import QRectF, QSize, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPen
from app.qt.QtWidgets import QWidget

from app.features.form_builder.qtside.theme.overlay import OVERLAY, OVERLAY_HIGH_CONTRAST, OverlayPalette

#: Qt class name to the friendly name on the stand-in (UX-CONT-017).
STAND_IN_NAMES: Dict[str, str] = {
    "QOpenGLWidget": "OpenGL widget",
    "QQuickWidget": "Qt Quick view",
}

_MIN_WIDTH = 80
_MIN_HEIGHT = 24
_DEFAULT_HINT = QSize(160, 96)
_TEXT_PIXELS = 11


def _rgba(raw: str) -> QColor:
    """Overlay tokens are ``#RRGGBBAA``; ``QColor`` alone reads eight digits as ``#AARRGGBB``."""
    text = raw[1:] if raw.startswith("#") else raw
    alpha = int(text[6:8], 16) if len(text) >= 8 else 255
    return QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), alpha)


def stand_in_name(qt_class: str) -> Optional[str]:
    """The friendly name for a class the editor draws as a stand-in, or None."""
    return STAND_IN_NAMES.get(qt_class)


class StandInWidget(QWidget):
    """A labelled rectangle: "{friendly name} · drawn by your code"."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        friendly: str = "OpenGL widget",
        high_contrast: bool = False,
        caption: str = "",
        hint: Optional[QSize] = None,
    ) -> None:
        super().__init__(parent)
        self._friendly = friendly
        self._forced_contrast = high_contrast
        self._caption = caption
        self._hint = hint

    @property
    def _palette(self) -> OverlayPalette:
        # The page must match a clean application under every shell theme
        # (UX-ISO-001/002), so the canvas never switches a stand-in to the
        # high-contrast tokens; only an explicit flag does.
        return OVERLAY_HIGH_CONTRAST if self._forced_contrast else OVERLAY

    def text(self) -> str:
        return self._caption or "%s · drawn by your code" % self._friendly

    def sizeHint(self) -> QSize:  # noqa: N802
        base = self._hint if self._hint is not None else _DEFAULT_HINT
        return QSize(max(_MIN_WIDTH, base.width()), max(_MIN_HEIGHT, base.height()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(_MIN_WIDTH, _MIN_HEIGHT)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        palette = self._palette
        try:
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.fillRect(QRectF(self.rect()), _rgba(palette.stand_in_fill))
            pen = QPen(_rgba(palette.stand_in_line))
            pen.setWidthF(palette.min_stroke)
            if palette.min_stroke < 2:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            font = QFont(self.font())
            font.setPixelSize(_TEXT_PIXELS)
            painter.setFont(font)
            painter.setPen(_rgba(palette.stand_in_text))
            flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)
            painter.drawText(QRectF(self.rect()).adjusted(4, 2, -4, -2), flags, self.text())
        finally:
            painter.end()


#: Stock bases whose own classes draw as a stand-in: they have no look of their own (UX-CUST-007).
PLAIN_BASES = frozenset({"QWidget", "QFrame"})


def own_class_caption(class_name: str, module: str) -> str:
    """The stand-in's words for your own class: "TillDisplay · from widgets.till_display"."""
    return "%s \u00b7 from %s" % (class_name, module)


def own_class_stand_in(
    parent: Optional[QWidget], *, class_name: str, module: str, size: Tuple[int, int]
) -> StandInWidget:
    """A sized stand-in for a plain QWidget or QFrame class of the project. It never runs the module."""
    return StandInWidget(
        parent,
        friendly=class_name,
        caption=own_class_caption(class_name, module),
        hint=QSize(size[0], size[1]),
    )


__all__ = [
    "PLAIN_BASES",
    "STAND_IN_NAMES",
    "StandInWidget",
    "own_class_caption",
    "own_class_stand_in",
    "stand_in_name",
]
