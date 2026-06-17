"""Shell icon pipeline: activity bar icons, SVG registry, and render primitives."""

from app.shell.icons.activity_bar import explorer_icon, search_icon, test_icon
from app.shell.icons.render import (
    clear_icon_caches,
    icon_from_svg,
    render_glyph_icon,
    render_painted_icon,
    render_svg_pixmap,
    render_themed_icon,
)
from app.shell.icons.svg_registry import SVG_GLYPHS, SvgGlyphSpec

__all__ = [
    "SVG_GLYPHS",
    "SvgGlyphSpec",
    "clear_icon_caches",
    "explorer_icon",
    "icon_from_svg",
    "render_glyph_icon",
    "render_painted_icon",
    "render_svg_pixmap",
    "render_themed_icon",
    "search_icon",
    "test_icon",
]
