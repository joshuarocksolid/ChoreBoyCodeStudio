"""QPainter-drawn icons for the activity bar and other shell chrome."""

from __future__ import annotations

from PySide2.QtCore import QPointF, QRectF, Qt
from PySide2.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def _make_pixmap(
    size: int,
    color: QColor,
    draw_fn: callable,  # type: ignore[valid-type]
) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    draw_fn(painter, size, color)
    painter.end()
    return pixmap


def _build_icon(
    draw_fn: callable,  # type: ignore[valid-type]
    size: int,
    color_normal: QColor,
    color_active: QColor,
) -> QIcon:
    """Build a QIcon with Normal/Active/Selected mode pixmaps."""
    icon = QIcon()
    pm_normal = _make_pixmap(size, color_normal, draw_fn)
    pm_active = _make_pixmap(size, color_active, draw_fn)
    icon.addPixmap(pm_normal, QIcon.Normal, QIcon.Off)
    icon.addPixmap(pm_active, QIcon.Normal, QIcon.On)
    icon.addPixmap(pm_active, QIcon.Active, QIcon.Off)
    icon.addPixmap(pm_active, QIcon.Active, QIcon.On)
    icon.addPixmap(pm_active, QIcon.Selected, QIcon.Off)
    icon.addPixmap(pm_active, QIcon.Selected, QIcon.On)
    return icon


def _draw_folder(painter: QPainter, size: int, color: QColor) -> None:
    pen = QPen(color, 1.4)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    m = size * 0.15
    w = size - 2 * m
    h = size - 2 * m

    body_top = m + h * 0.30
    body = QRectF(m, body_top, w, h * 0.65)
    painter.drawRoundedRect(body, 1.5, 1.5)

    tab = QPolygonF(
        [
            QPointF(m + 1.5, body_top),
            QPointF(m + 1.5, body_top - h * 0.16),
            QPointF(m + w * 0.40, body_top - h * 0.16),
            QPointF(m + w * 0.48, body_top),
        ]
    )
    painter.drawPolyline(tab)


def _draw_search(painter: QPainter, size: int, color: QColor) -> None:
    pen = QPen(color, 1.4)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    m = size * 0.18
    lens_d = size * 0.48
    painter.drawEllipse(QRectF(m, m, lens_d, lens_d))

    cx = m + lens_d * 0.85
    cy = m + lens_d * 0.85
    end_x = size - m
    end_y = size - m
    painter.drawLine(QPointF(cx, cy), QPointF(end_x, end_y))


def explorer_icon(
    size: int = 20,
    *,
    color_normal: QColor | None = None,
    color_active: QColor | None = None,
) -> QIcon:
    cn = color_normal or QColor("#ADB5BD")
    ca = color_active or QColor("#E9ECEF")
    return _build_icon(_draw_folder, size, cn, ca)


def search_icon(
    size: int = 20,
    *,
    color_normal: QColor | None = None,
    color_active: QColor | None = None,
) -> QIcon:
    cn = color_normal or QColor("#ADB5BD")
    ca = color_active or QColor("#E9ECEF")
    return _build_icon(_draw_search, size, cn, ca)
