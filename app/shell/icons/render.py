"""Shared SVG and painted-icon rendering primitives for shell UI."""

from __future__ import annotations

from typing import Callable

from PySide2.QtCore import QByteArray, QSize
from PySide2.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide2.QtSvg import QSvgRenderer

from app.shell.icons.svg_registry import SvgGlyphSpec
from app.shell.theme_tokens import ShellThemeTokens

_CONTEXT_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def clear_icon_caches() -> None:
    """Release cached ``QIcon`` objects so Shiboken can tear down cleanly."""
    _CONTEXT_ICON_CACHE.clear()


def format_glyph_body(body: str, *, color: str, badge_color: str = "") -> str:
    return body.format(color=color, badge_color=badge_color)


def svg_document(body: str, view_box: str = "0 0 16 16") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">{body}</svg>'


def render_svg_pixmap(svg_text: str, size: int = 16) -> QPixmap:
    data = QByteArray(svg_text.encode("utf-8"))
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def icon_from_svg(svg_text: str, size: int = 16) -> QIcon:
    return QIcon(render_svg_pixmap(svg_text, size))


def _cache_key(spec: SvgGlyphSpec, color: str, badge_color: str) -> tuple[str, str]:
    if spec.two_color:
        return spec.cache_name, f"{color}|{badge_color}"
    return spec.cache_name, color


def render_glyph_icon(
    spec: SvgGlyphSpec,
    color: str,
    badge_color: str = "",
    *,
    size: int = 16,
) -> QIcon:
    body = format_glyph_body(spec.body, color=color, badge_color=badge_color)
    svg_text = svg_document(body, spec.view_box)
    if spec.cached:
        key = _cache_key(spec, color, badge_color)
        cached = _CONTEXT_ICON_CACHE.get(key)
        if cached is not None:
            return cached
        icon = icon_from_svg(svg_text, size)
        _CONTEXT_ICON_CACHE[key] = icon
        return icon
    return icon_from_svg(svg_text, size)


def render_themed_icon(
    spec: SvgGlyphSpec,
    tokens: ShellThemeTokens,
    *,
    badge_muted: bool = True,
    size: int = 16,
) -> QIcon:
    badge_color = tokens.icon_muted if badge_muted else tokens.icon_primary
    if spec.two_color:
        return render_glyph_icon(spec, tokens.icon_primary, badge_color, size=size)
    return render_glyph_icon(spec, tokens.icon_primary, size=size)


def transparent_pixmap(width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(0, 0, 0, 0))
    return pixmap


def render_painted_icon(
    width: int,
    height: int,
    paint: Callable[[QPainter], None],
) -> QIcon:
    pixmap = transparent_pixmap(width, height)
    painter = QPainter(pixmap)
    try:
        paint(painter)
    finally:
        painter.end()
    return QIcon(pixmap)
