"""Inline SVG icon factory for shell UI elements.

Generates QIcon objects from parameterized SVG templates so the shell
can produce theme-colored icons without external asset files.
"""

from __future__ import annotations

from PySide2.QtCore import QByteArray, QSize
from PySide2.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide2.QtSvg import QSvgRenderer

from app.shell.file_type_icons import build_file_type_icon_map, build_filename_icon_map


_CONTEXT_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def _render_svg(svg_text: str, size: int = 16) -> QPixmap:
    data = QByteArray(svg_text.encode("utf-8"))
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def _icon_from_svg(svg_text: str, size: int = 16) -> QIcon:
    return QIcon(_render_svg(svg_text, size))


def _cached_context_icon(name: str, color: str, svg_text: str) -> QIcon:
    key = (name, color)
    cached = _CONTEXT_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    icon = _icon_from_svg(svg_text)
    _CONTEXT_ICON_CACHE[key] = icon
    return icon


def file_icon(color: str) -> QIcon:
    """Document outline icon for generic files."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M3 1h6l4 4v10H3V1z" fill="none" stroke="{color}" '
        f'stroke-width="1.2" stroke-linejoin="round"/>'
        f'<path d="M9 1v4h4" fill="none" stroke="{color}" '
        f'stroke-width="1.2" stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def file_type_icon_map(primary_color: str = "") -> dict[str, QIcon]:
    """Return extension -> QIcon mapping with distinctive per-type icons.

    Icons use fixed colors per file type (VS Code style) so *primary_color*
    is accepted for call-site compatibility but not used.
    """
    return build_file_type_icon_map()


def filename_icon_map() -> dict[str, QIcon]:
    """Return lowercase-filename -> QIcon mapping for special filenames."""
    return build_filename_icon_map()


def folder_icon(color: str) -> QIcon:
    """Closed folder icon for directories."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M1 3h5l1.5 1.5H15v9H1V3z" fill="{color}" '
        f'fill-opacity="0.2" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def folder_open_icon(color: str) -> QIcon:
    """Open folder icon for expanded directories."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M1 3h5l1.5 1.5H15v2H3l-2 7V3z" fill="{color}" '
        f'fill-opacity="0.15" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f'<path d="M1 13l2-7h12l-2 7H1z" fill="{color}" '
        f'fill-opacity="0.2" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def new_file_icon(color: str, badge_color: str) -> QIcon:
    """Document with a '+' badge for the new-file action."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M2 1h5.5l3.5 3.5V11H2V1z" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M7.5 1v3.5H11" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linejoin="round"/>'
        f'<line x1="12" y1="11" x2="12" y2="16" stroke="{badge_color}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
        f'<line x1="9.5" y1="13.5" x2="14.5" y2="13.5" stroke="{badge_color}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def new_folder_icon(color: str, badge_color: str) -> QIcon:
    """Folder with a '+' badge for the new-folder action."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M1 3h4.5L7 4.5H11v5H1V3z" fill="{color}" '
        f'fill-opacity="0.2" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f'<line x1="13.5" y1="8.5" x2="13.5" y2="14" stroke="{badge_color}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
        f'<line x1="11" y1="11.25" x2="16" y2="11.25" stroke="{badge_color}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def refresh_icon(color: str) -> QIcon:
    """Circular arrow icon for the refresh action."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M13 3a6 6 0 1 0 1.4 6" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round"/>'
        f'<path d="M11 1l2.2 2.2L11 5.2" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def search_icon(color: str) -> QIcon:
    """Magnifying glass icon for search actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" '
        f'stroke-width="1.4"/>'
        f'<line x1="10.5" y1="10.5" x2="14" y2="14" stroke="{color}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def history_icon(color: str) -> QIcon:
    """Clock-with-counterclockwise-arrow icon for history/recovery surfaces."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M2.5 4a6 6 0 1 1-1 4.5" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round"/>'
        f'<path d="M2.5 1.5v3h3" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M8 5v3.3l2.2 1.3" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def explorer_icon(color: str) -> QIcon:
    """File explorer / tree icon."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M2 2h5l1.5 1.5H14v4H2V2z" fill="{color}" '
        f'fill-opacity="0.15" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f'<path d="M2 7.5h12v5H2z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _icon_from_svg(svg)


def rename_icon(color: str) -> QIcon:
    """Pencil icon for rename actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M3 11.5L11.5 3l1.5 1.5L4.5 13H3v-1.5z" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/>'
        f'<path d="M10.5 4l1.5 1.5" fill="none" stroke="{color}" '
        f'stroke-width="1.2" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("rename", color, svg)


def trash_icon(color: str) -> QIcon:
    """Trash can icon for move-to-trash actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M3.5 5h9l-.7 9H4.2L3.5 5z" fill="{color}" '
        f'fill-opacity="0.12" stroke="{color}" stroke-width="1.2" '
        f'stroke-linejoin="round"/>'
        f'<path d="M2.5 5h11M6 3h4M6.5 7v5M9.5 7v5" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("trash", color, svg)


def duplicate_icon(color: str) -> QIcon:
    """Overlapping documents icon for duplicate actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M5 2h7v9H5V2z" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M3 5h7v9H3V5z" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("duplicate", color, svg)


def copy_icon(color: str) -> QIcon:
    """Clipboard-copy icon for copy actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M5 3.5h7v9H5v-9z" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M3 6.5v7h6" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("copy", color, svg)


def cut_icon(color: str) -> QIcon:
    """Scissors icon for cut actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<circle cx="4" cy="4" r="1.7" fill="none" stroke="{color}" '
        f'stroke-width="1.1"/>'
        f'<circle cx="4" cy="12" r="1.7" fill="none" stroke="{color}" '
        f'stroke-width="1.1"/>'
        f'<path d="M5.3 5.3L13 13M5.3 10.7L13 3" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("cut", color, svg)


def paste_icon(color: str) -> QIcon:
    """Clipboard icon for paste actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M4 4h8v10H4V4z" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M6 2.5h4v3H6v-3z" fill="{color}" fill-opacity="0.16" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M6 8h4M6 10.5h3" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("paste", color, svg)


def copy_path_icon(color: str) -> QIcon:
    """Linked path icon for path-copy actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M5.8 10.2L4.5 11.5a2.5 2.5 0 0 1-3.5-3.5l2-2" '
        f'fill="none" stroke="{color}" stroke-width="1.3" '
        f'stroke-linecap="round"/>'
        f'<path d="M10.2 5.8l1.3-1.3a2.5 2.5 0 0 1 3.5 3.5l-2 2" '
        f'fill="none" stroke="{color}" stroke-width="1.3" '
        f'stroke-linecap="round"/>'
        f'<path d="M5.5 8.5l5-5" fill="none" stroke="{color}" '
        f'stroke-width="1.3" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("copy_path", color, svg)


def reveal_icon(color: str) -> QIcon:
    """Folder-with-arrow icon for reveal-in-file-manager actions."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" '
        f'fill-opacity="0.12" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f'<path d="M7 9h5M10 6.8L12.2 9 10 11.2" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("reveal", color, svg)


def source_root_icon(color: str) -> QIcon:
    """Folder badge icon for marking a sources root."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" '
        f'fill-opacity="0.12" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f'<path d="M8 8.5h4M10 6.5v4" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("source_root", color, svg)


def source_root_unmark_icon(color: str) -> QIcon:
    """Folder badge icon for unmarking a sources root."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" '
        f'fill-opacity="0.12" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>'
        f'<path d="M8 8.5h4" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round"/>'
        f"</svg>"
    )
    return _cached_context_icon("source_root_unmark", color, svg)
