"""Painted QIcon factories for the test explorer panel."""

from __future__ import annotations

from typing import Callable

from PySide2.QtCore import QPoint, Qt
from PySide2.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygon

from app.pytest.outcome_types import TestOutcome

_OUTCOME_ICON_CACHE: dict[tuple[TestOutcome, str], QIcon] = {}
_KIND_ICON_CACHE: dict[tuple[str, str], QIcon] = {}
_ACTION_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def _make_passed_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.setPen(QPen(QColor("#FFFFFF"), 1.6))
    p.drawLine(4, 7, 6, 10)
    p.drawLine(6, 10, 10, 4)
    p.end()
    return QIcon(px)


def _make_failed_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.setPen(QPen(QColor("#FFFFFF"), 1.6))
    p.drawLine(4, 4, 10, 10)
    p.drawLine(10, 4, 4, 10)
    p.end()
    return QIcon(px)


def _make_skipped_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    c.setAlpha(180)
    p.setPen(QPen(c, 1.4))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(2, 2, 10, 10)
    p.drawLine(5, 7, 9, 7)
    p.end()
    return QIcon(px)


def _make_error_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    tri = QPolygon()
    tri.append(QPoint(7, 1))
    tri.append(QPoint(13, 13))
    tri.append(QPoint(1, 13))
    p.drawPolygon(tri)
    p.setPen(QPen(QColor("#FFFFFF"), 1.4))
    p.drawLine(7, 5, 7, 9)
    p.drawPoint(7, 11)
    p.end()
    return QIcon(px)


def _make_not_run_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    c.setAlpha(120)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 6, 6)
    p.end()
    return QIcon(px)


_OUTCOME_BUILDERS: dict[TestOutcome, Callable[[str], QIcon]] = {
    "passed": _make_passed_icon,
    "failed": _make_failed_icon,
    "skipped": _make_skipped_icon,
    "error": _make_error_icon,
    "not_run": _make_not_run_icon,
}


def outcome_icon(outcome: TestOutcome, color_hex: str) -> QIcon:
    key = (outcome, color_hex)
    cached = _OUTCOME_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    builder = _OUTCOME_BUILDERS.get(outcome, _make_not_run_icon)
    icon = builder(color_hex)
    _OUTCOME_ICON_CACHE[key] = icon
    return icon


def _make_file_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    c.setAlpha(180)
    p.setPen(QPen(c, 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(2, 1, 10, 12, 2, 2)
    p.drawLine(2, 5, 12, 5)
    p.end()
    return QIcon(px)


def _make_class_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(1, 2, 12, 10, 2, 2)
    f = QFont()
    f.setPixelSize(9)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(px.rect(), Qt.AlignCenter, "C")
    p.end()
    return QIcon(px)


def _make_function_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(1, 2, 12, 10, 2, 2)
    f = QFont()
    f.setPixelSize(9)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(px.rect(), Qt.AlignCenter, "f")
    p.end()
    return QIcon(px)


_KIND_BUILDERS = {
    "file": _make_file_icon,
    "class": _make_class_icon,
    "function": _make_function_icon,
}


def kind_icon(kind: str, color_hex: str) -> QIcon:
    key = (kind, color_hex)
    cached = _KIND_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    builder = _KIND_BUILDERS.get(kind, _make_file_icon)
    icon = builder(color_hex)
    _KIND_ICON_CACHE[key] = icon
    return icon


def clear_icon_caches() -> None:
    """Release all cached QIcon objects so Shiboken can tear down cleanly."""
    _OUTCOME_ICON_CACHE.clear()
    _KIND_ICON_CACHE.clear()
    _ACTION_ICON_CACHE.clear()


def _make_play_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    tri = QPolygon()
    tri.append(QPoint(3, 2))
    tri.append(QPoint(12, 7))
    tri.append(QPoint(3, 12))
    p.drawPolygon(tri)
    p.end()
    return QIcon(px)


def _make_rerun_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color_hex), 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(2, 2, 10, 10, 30 * 16, 300 * 16)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    arrow = QPolygon()
    arrow.append(QPoint(9, 1))
    arrow.append(QPoint(12, 4))
    arrow.append(QPoint(8, 5))
    p.drawPolygon(arrow)
    p.end()
    return QIcon(px)


def _make_refresh_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color_hex), 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(2, 2, 10, 10, 60 * 16, 240 * 16)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    arrow = QPolygon()
    arrow.append(QPoint(10, 2))
    arrow.append(QPoint(13, 5))
    arrow.append(QPoint(9, 5))
    p.drawPolygon(arrow)
    p.end()
    return QIcon(px)


def action_icon(name: str, color_hex: str) -> QIcon:
    key = (name, color_hex)
    cached = _ACTION_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    builders = {"play": _make_play_icon, "rerun": _make_rerun_icon, "refresh": _make_refresh_icon}
    icon = builders.get(name, _make_play_icon)(color_hex)
    _ACTION_ICON_CACHE[key] = icon
    return icon
