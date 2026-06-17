"""Painted QIcon factories for the outline panel."""

from __future__ import annotations

from PySide2.QtCore import QPoint, Qt
from PySide2.QtGui import QColor, QFont, QIcon, QPainter, QPolygon

from app.shell.icons.render import render_painted_icon
from app.shell.theme_tokens import ShellThemeTokens

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

# Outline symbol kinds -> ShellThemeTokens field names (theme-agnostic table).
_KIND_TOKEN_FIELDS: dict[str, str] = {
    "class": "syntax_semantic_class",
    "function": "syntax_function",
    "async_function": "syntax_function",
    "method": "syntax_semantic_method",
    "async_method": "syntax_semantic_method",
    "property": "syntax_semantic_property",
    "field": "syntax_semantic_variable",
    "constant": "syntax_semantic_constant",
}

_OUTLINE_ICON_CACHE: dict[tuple[str, str], QIcon] = {}
_CHEVRON_ICON_CACHE: dict[tuple[str, bool], QIcon] = {}


def kind_color_for(kind: str, tokens: ShellThemeTokens) -> str:
    """Return the accent color for an outline symbol kind under ``tokens``."""
    token_field = _KIND_TOKEN_FIELDS.get(kind, "icon_muted")
    color = getattr(tokens, token_field, "") or ""
    if color:
        return color
    fallback = tokens.accent or tokens.text_primary or tokens.icon_muted or "#888888"
    return fallback


def _make_kind_icon(kind: str, color_hex: str) -> QIcon:
    glyph = _KIND_GLYPHS.get(kind, "?")

    def paint(painter: QPainter) -> None:
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
        painter.drawText(0, 0, 16, 16, int(Qt.AlignCenter), glyph)

    return render_painted_icon(16, 16, paint)


def kind_icon(kind: str, color_hex: str) -> QIcon:
    key = (kind, color_hex)
    cached = _OUTLINE_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    icon = _make_kind_icon(kind, color_hex)
    _OUTLINE_ICON_CACHE[key] = icon
    return icon


def _make_chevron_icon(color_hex: str, *, expanded: bool) -> QIcon:
    def paint(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(color_hex)
        painter.setPen(color)
        painter.setBrush(color)
        if expanded:
            triangle = QPolygon([QPoint(2, 4), QPoint(10, 4), QPoint(6, 9)])
        else:
            triangle = QPolygon([QPoint(4, 2), QPoint(9, 6), QPoint(4, 10)])
        painter.drawPolygon(triangle)

    return render_painted_icon(12, 12, paint)


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
    def paint(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(color_hex))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 0, 14, 14, int(Qt.AlignCenter), symbol)

    return render_painted_icon(14, 14, paint)


def clear_icon_caches() -> None:
    """Release cached `QIcon` objects so Shiboken can tear down cleanly."""
    _OUTLINE_ICON_CACHE.clear()
    _CHEVRON_ICON_CACHE.clear()
