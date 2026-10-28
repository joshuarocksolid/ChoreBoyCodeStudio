"""Stand-ins for widgets the editor must not build (UX-CONT-017).

An OpenGL widget or a Qt Quick view needs a GL context or a QML engine, and
user classes run code. The editor draws a labelled rectangle with the same
size policy and size hint instead, so the layout matches run time. Nothing
here creates a GL context or a QML engine.
"""

from __future__ import annotations

from typing import Dict, Optional

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
    ) -> None:
        super().__init__(parent)
        self._friendly = friendly
        self._palette: OverlayPalette = OVERLAY_HIGH_CONTRAST if high_contrast else OVERLAY

    def text(self) -> str:
        return "%s · drawn by your code" % self._friendly

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(max(_MIN_WIDTH, _DEFAULT_HINT.width()), max(_MIN_HEIGHT, _DEFAULT_HINT.height()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(_MIN_WIDTH, _MIN_HEIGHT)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.fillRect(QRectF(self.rect()), QColor(self._palette.stand_in_fill))
            pen = QPen(QColor(self._palette.stand_in_line))
            pen.setWidthF(self._palette.min_stroke)
            if self._palette.min_stroke < 2:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            font = QFont(self.font())
            font.setPixelSize(_TEXT_PIXELS)
            painter.setFont(font)
            painter.setPen(QColor(self._palette.stand_in_text))
            flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)
            painter.drawText(QRectF(self.rect()).adjusted(4, 2, -4, -2), flags, self.text())
        finally:
            painter.end()


__all__ = ["STAND_IN_NAMES", "StandInWidget", "stand_in_name"]
