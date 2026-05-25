"""Painted QIcon factories for the outline panel."""

from __future__ import annotations

from PySide2.QtCore import QPoint, Qt
from PySide2.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygon

_KIND_GLYPHS: dict[str, str] = {
    "class": "C",
    "function": "f",
    "async_function": "f",
    "method": "m",
    "async_method": "m",
    "property": "p",
    "constant": "K",
    "field": "v",
}

_KIND_COLORS_DARK: dict[str, str] = {
    "class": "#EE9D28",
    "function": "#B180D7",
    "async_function": "#B180D7",
    "method": "#B180D7",
    "async_method": "#B180D7",
    "property": "#75BEFF",
    "field": "#75BEFF",
    "constant": "#4FC1FF",
}
_KIND_COLORS_LIGHT: dict[str, str] = {
    "class": "#D67E00",
    "function": "#8052BD",
    "async_function": "#8052BD",
    "method": "#8052BD",
    "async_method": "#8052BD",
    "property": "#1F6FBF",
    "field": "#1F6FBF",
    "constant": "#0E7BC4",
}

_OUTLINE_ICON_CACHE: dict[tuple[str, str], QIcon] = {}
_CHEVRON_ICON_CACHE: dict[tuple[str, bool], QIcon] = {}


def kind_color_for(kind: str, *, is_dark: bool) -> str:
    palette = _KIND_COLORS_DARK if is_dark else _KIND_COLORS_LIGHT
    return palette.get(kind, "#888888")


def _make_kind_icon(kind: str, color_hex: str) -> QIcon:
    glyph = _KIND_GLYPHS.get(kind, "?")
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor(color_hex)
    soft = QColor(color)
    soft.setAlpha(40)
    painter.setPen(color)
    painter.setBrush(soft)
    if kind == "class":
        painter.drawEllipse(2, 2, 12, 12)
    elif kind == "constant":
        painter.setBrush(color)
        painter.drawRoundedRect(3, 3, 10, 10, 2, 2)
    elif kind == "property":
        painter.drawRoundedRect(2, 2, 12, 12, 4, 4)
    elif kind == "field":
        painter.drawRoundedRect(2, 4, 12, 8, 2, 2)
    else:
        painter.drawRoundedRect(2, 2, 12, 12, 2, 2)
    glyph_color = QColor(color)
    if kind == "constant":
        glyph_color = QColor("#FFFFFF")
    painter.setPen(glyph_color)
    font = QFont()
    font.setPointSize(8)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignCenter), glyph)
    painter.end()
    return QIcon(pixmap)


def kind_icon(kind: str, color_hex: str) -> QIcon:
    key = (kind, color_hex)
    cached = _OUTLINE_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    icon = _make_kind_icon(kind, color_hex)
    _OUTLINE_ICON_CACHE[key] = icon
    return icon


def _make_chevron_icon(color_hex: str, *, expanded: bool) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor(color_hex)
    painter.setPen(color)
    painter.setBrush(color)
    if expanded:
        triangle = QPolygon([QPoint(2, 4), QPoint(10, 4), QPoint(6, 9)])
    else:
        triangle = QPolygon([QPoint(4, 2), QPoint(9, 6), QPoint(4, 10)])
    painter.drawPolygon(triangle)
    painter.end()
    return QIcon(pixmap)


def chevron_icon(color_hex: str, *, expanded: bool) -> QIcon:
    key = (color_hex, expanded)
    cached = _CHEVRON_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    icon = _make_chevron_icon(color_hex, expanded=expanded)
    _CHEVRON_ICON_CACHE[key] = icon
    return icon


def make_codicon_text_icon(symbol: str, color_hex: str) -> QIcon:
    """Render a tiny single-glyph icon for action buttons (filter, sort ...)."""
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(color_hex))
    font = QFont()
    font.setPointSize(9)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignCenter), symbol)
    painter.end()
    return QIcon(pixmap)


def clear_icon_caches() -> None:
    """Release cached `QIcon` objects so Shiboken can tear down cleanly."""
    _OUTLINE_ICON_CACHE.clear()
    _CHEVRON_ICON_CACHE.clear()
