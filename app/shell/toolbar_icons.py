"""Programmatically generated toolbar icons (no external assets)."""

from __future__ import annotations

import os
import tempfile

from PySide2.QtCore import QPointF, QRectF, Qt
from PySide2.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


_SIZE = 16


def _new_pixmap() -> QPixmap:
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.transparent)
    return pm


def icon_run(color: str = "#16A34A") -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(4, 2),
        QPointF(14, 8),
        QPointF(4, 14),
    ]))
    p.end()
    return QIcon(pm)


def icon_debug(color: str = "#D97706") -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    # Bug body: oval
    p.drawEllipse(QRectF(4, 5, 8, 9))
    # Head
    p.drawEllipse(QRectF(5.5, 1, 5, 5))
    # Antennae
    p.setPen(c)
    p.drawLine(QPointF(6, 2), QPointF(3, 0))
    p.drawLine(QPointF(10, 2), QPointF(13, 0))
    # Legs
    p.drawLine(QPointF(4, 8), QPointF(1, 6))
    p.drawLine(QPointF(4, 11), QPointF(1, 13))
    p.drawLine(QPointF(12, 8), QPointF(15, 6))
    p.drawLine(QPointF(12, 11), QPointF(15, 13))
    p.end()
    return QIcon(pm)


def icon_stop(color: str = "#DC2626") -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(3, 3, 10, 10), 2, 2)
    p.end()
    return QIcon(pm)


def icon_restart(color: str) -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = p.pen()
    pen.setColor(c)
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(2, 2, 12, 12), 30 * 16, 300 * 16)
    # Arrowhead
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(12, 2),
        QPointF(15, 5),
        QPointF(10, 5),
    ]))
    p.end()
    return QIcon(pm)


def icon_continue(color: str) -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(5, 2),
        QPointF(14, 8),
        QPointF(5, 14),
    ]))
    # Vertical bar on left
    p.drawRect(QRectF(2, 2, 2, 12))
    p.end()
    return QIcon(pm)


def icon_pause(color: str) -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(3, 2, 3.5, 12), 1, 1)
    p.drawRoundedRect(QRectF(9.5, 2, 3.5, 12), 1, 1)
    p.end()
    return QIcon(pm)


def icon_step_over(color: str) -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = p.pen()
    pen.setColor(c)
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Arc going over a dot
    p.drawArc(QRectF(2, 1, 12, 10), 0, 180 * 16)
    # Arrowhead at right end
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(14, 3),
        QPointF(14, 9),
        QPointF(11, 6),
    ]))
    # Dot underneath
    p.drawEllipse(QRectF(6.5, 12, 3, 3))
    p.end()
    return QIcon(pm)


def icon_step_into(color: str) -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = p.pen()
    pen.setColor(c)
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Vertical line going down
    p.drawLine(QPointF(8, 1), QPointF(8, 10))
    # Arrow head
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(5, 8),
        QPointF(11, 8),
        QPointF(8, 12),
    ]))
    # Dot at bottom
    p.drawEllipse(QRectF(6.0, 13.0, 4.0, 3.0))
    p.end()
    return QIcon(pm)


def icon_step_out(color: str) -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = p.pen()
    pen.setColor(c)
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Vertical line going up
    p.drawLine(QPointF(8, 14), QPointF(8, 5))
    # Arrow head pointing up
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(5, 7),
        QPointF(11, 7),
        QPointF(8, 3),
    ]))
    # Dot at top
    p.drawEllipse(QRectF(6.0, 0.0, 4.0, 3.0))
    p.end()
    return QIcon(pm)


def icon_package(color: str = "#5B8CFF") -> QIcon:
    """Box icon representing project packaging."""
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    fill = QColor(color)
    fill.setAlpha(38)

    pen = p.pen()
    pen.setColor(c)
    pen.setWidthF(1.4)
    p.setPen(pen)

    p.setBrush(fill)
    p.drawRoundedRect(QRectF(2, 5, 12, 9.5), 1.2, 1.2)

    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(2, 9), QPointF(14, 9))
    p.drawLine(QPointF(8, 5), QPointF(8, 9))

    lid = QPolygonF([
        QPointF(2, 5), QPointF(5, 2), QPointF(11, 2), QPointF(14, 5),
    ])
    p.setBrush(fill)
    p.drawPolygon(lid)

    p.end()
    return QIcon(pm)


def icon_remove_all_breakpoints(color: str = "#DC2626") -> QIcon:
    pm = _new_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(1, 3, 10, 10))
    # X mark over the circle
    p.setPen(QColor("#FFFFFF"))
    pen = p.pen()
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawLine(QPointF(3.5, 5.5), QPointF(8.5, 10.5))
    p.drawLine(QPointF(8.5, 5.5), QPointF(3.5, 10.5))
    p.end()
    return QIcon(pm)


# Maps action ID suffix -> icon factory (color provided at build time)
_ICON_BUILDERS: dict[str, tuple[str, bool]] = {
    "shell.action.run.run": ("run", False),
    "shell.action.run.debug": ("debug", False),
    "shell.action.run.stop": ("stop", False),
    "shell.action.run.restart": ("restart", True),
    "shell.action.run.continue": ("continue", True),
    "shell.action.run.pause": ("pause", True),
    "shell.action.run.stepOver": ("step_over", True),
    "shell.action.run.stepInto": ("step_into", True),
    "shell.action.run.stepOut": ("step_out", True),
    "shell.action.run.removeAllBreakpoints": ("remove_all_breakpoints", False),
    "shell.action.build.package": ("package", True),
}


def generate_tab_close_icon(color: str, path: str) -> str:
    size = 16
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    margin = 5
    p.drawLine(margin, margin, size - margin, size - margin)
    p.drawLine(size - margin, margin, margin, size - margin)
    p.end()
    pm.save(path, "PNG")
    return path


def ensure_tab_close_icons(
    normal_color: str,
    hover_color: str,
) -> tuple[str, str]:
    tmp = tempfile.gettempdir()
    normal_path = os.path.join(tmp, "cbcs_tab_close.png")
    hover_path = os.path.join(tmp, "cbcs_tab_close_hover.png")
    generate_tab_close_icon(normal_color, normal_path)
    generate_tab_close_icon(hover_color, hover_path)
    return normal_path, hover_path


def build_toolbar_icon(action_id: str, accent_color: str) -> QIcon | None:
    """Return the icon for *action_id*, or ``None`` if no icon is defined."""
    entry = _ICON_BUILDERS.get(action_id)
    if entry is None:
        return None
    name, uses_accent = entry
    fn = globals().get(f"icon_{name}")
    if fn is None:
        return None
    if uses_accent:
        return fn(color=accent_color)
    return fn()
