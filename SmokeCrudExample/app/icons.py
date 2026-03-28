"""QPainter-based icons for the CRUD Showcase (no external assets).

Each factory returns a ``QIcon`` built from a 16x16 ``QPixmap``.  A *color*
parameter lets callers tint icons to match the active theme.
"""

from __future__ import annotations

from PySide2.QtCore import QPointF, QRectF, Qt
from PySide2.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap


_SIZE = 16


def _pm() -> QPixmap:
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.transparent)
    return pm


# ── Toolbar icons ───────────────────────────────────────────────────


def icon_add(color: str = "#16A34A") -> QIcon:
    """Plus sign in a circle."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(1.5, 1.5, 13, 13))
    p.drawLine(QPointF(8, 4.5), QPointF(8, 11.5))
    p.drawLine(QPointF(4.5, 8), QPointF(11.5, 8))
    p.end()
    return QIcon(pm)


def icon_edit(color: str = "#3366FF") -> QIcon:
    """Pencil."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.5)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Pencil body (angled line)
    p.drawLine(QPointF(3, 13), QPointF(12.5, 3.5))
    # Tip
    p.drawLine(QPointF(3, 13), QPointF(5, 12))
    # Eraser cap
    p.drawLine(QPointF(10.5, 5.5), QPointF(12.5, 3.5))
    # Pencil sides
    p.drawLine(QPointF(5, 12), QPointF(10.5, 5.5))
    p.drawLine(QPointF(3, 13), QPointF(12.5, 3.5))
    p.end()
    return QIcon(pm)


def icon_delete(color: str = "#DC2626") -> QIcon:
    """Trash can."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Lid
    p.drawLine(QPointF(2.5, 4.5), QPointF(13.5, 4.5))
    p.drawLine(QPointF(6, 4.5), QPointF(6, 2.5))
    p.drawLine(QPointF(10, 4.5), QPointF(10, 2.5))
    p.drawLine(QPointF(6, 2.5), QPointF(10, 2.5))
    # Body
    p.drawLine(QPointF(4, 4.5), QPointF(4.5, 13.5))
    p.drawLine(QPointF(12, 4.5), QPointF(11.5, 13.5))
    p.drawLine(QPointF(4.5, 13.5), QPointF(11.5, 13.5))
    # Interior lines
    p.drawLine(QPointF(6.5, 6.5), QPointF(6.5, 11.5))
    p.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 11.5))
    p.end()
    return QIcon(pm)


def icon_refresh(color: str = "#495057") -> QIcon:
    """Circular arrow."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.8)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(2, 2, 12, 12), 30 * 16, 300 * 16)
    from PySide2.QtGui import QPolygonF
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(12, 2),
        QPointF(15, 5),
        QPointF(10, 5),
    ]))
    p.end()
    return QIcon(pm)


def icon_search(color: str = "#6B7280") -> QIcon:
    """Magnifying glass."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(2, 2, 9, 9))
    p.drawLine(QPointF(9.5, 9.5), QPointF(13.5, 13.5))
    p.end()
    return QIcon(pm)


def icon_gear(color: str = "#6B7280") -> QIcon:
    """Simple gear for FreeCAD probe."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Inner circle
    p.drawEllipse(QRectF(5, 5, 6, 6))
    # Teeth (small lines radiating out)
    import math
    cx, cy, r_inner, r_outer = 8.0, 8.0, 5.0, 7.0
    for i in range(8):
        angle = math.radians(i * 45)
        x1 = cx + r_inner * math.cos(angle)
        y1 = cy + r_inner * math.sin(angle)
        x2 = cx + r_outer * math.cos(angle)
        y2 = cy + r_outer * math.sin(angle)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.end()
    return QIcon(pm)


def icon_info(color: str = "#3366FF") -> QIcon:
    """Info "i" in a circle."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(1.5, 1.5, 13, 13))
    # The "i" letter
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QRectF(7, 4, 2, 2))
    p.drawRoundedRect(QRectF(7, 7, 2, 5), 0.5, 0.5)
    p.end()
    return QIcon(pm)


def icon_tasks(color: str = "#3366FF") -> QIcon:
    """Checklist icon for the Tasks tab."""
    pm = _pm()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Three horizontal lines
    for y_offset in (4.0, 8.0, 12.0):
        p.drawLine(QPointF(6, y_offset), QPointF(14, y_offset))
    # Checkmark on first item
    p.drawLine(QPointF(2, 4), QPointF(3.5, 5.5))
    p.drawLine(QPointF(3.5, 5.5), QPointF(5, 3))
    # Dots on remaining items
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QRectF(2.5, 7, 2, 2))
    p.drawEllipse(QRectF(2.5, 11, 2, 2))
    p.end()
    return QIcon(pm)


def icon_app(color: str = "#3366FF") -> QIcon:
    """Small app icon — checkmark in a rounded square (window icon)."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(2, 2, 28, 28), 6, 6)
    # White checkmark
    pen = QPen(QColor("#FFFFFF"), 3.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawLine(QPointF(9, 17), QPointF(14, 22))
    p.drawLine(QPointF(14, 22), QPointF(23, 10))
    p.end()
    return QIcon(pm)


# ── Status dot helper ───────────────────────────────────────────────


def status_dot_pixmap(color: str, size: int = 10) -> QPixmap:
    """Small filled circle used as a status indicator."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    p.end()
    return pm
