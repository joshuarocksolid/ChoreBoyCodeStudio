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


def _cached_two_color_icon(name: str, color: str, badge_color: str, svg_text: str) -> QIcon:
    return _cached_context_icon(name, f"{color}|{badge_color}", svg_text)


def _menu_icon(name: str, color: str, body: str) -> QIcon:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{body}</svg>'
    return _cached_context_icon(name, color, svg)


def _menu_two_color_icon(name: str, color: str, badge_color: str, body: str) -> QIcon:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{body}</svg>'
    return _cached_two_color_icon(name, color, badge_color, svg)


def save_icon(color: str) -> QIcon:
    """Floppy-disk icon for save actions."""
    return _menu_icon(
        "save",
        color,
        f'<path d="M2.5 2h9l2 2v10h-11V2z" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/>'
        f'<path d="M5 2v4h6V2M5 11h6" fill="none" stroke="{color}" '
        f'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def save_as_icon(color: str, badge_color: str) -> QIcon:
    """Floppy disk with pencil badge for Save As."""
    return _menu_two_color_icon(
        "save_as",
        color,
        badge_color,
        f'<path d="M2.5 2h8l2 2v8h-10V2z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M5 2v3.5h5V2M5 9.5h3" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linecap="round"/>'
        f'<path d="M10.5 13.2l2.9-2.9 1.2 1.2-2.9 2.9H10.5v-1.2z" '
        f'fill="none" stroke="{badge_color}" stroke-width="1.1" stroke-linejoin="round"/>',
    )


def save_all_icon(color: str) -> QIcon:
    """Stacked disks for Save All."""
    return _menu_icon(
        "save_all",
        color,
        f'<path d="M4 2h7.5L13.5 4v8.5H4V2z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M2.5 5v9h8" fill="none" stroke="{color}" stroke-width="1.1" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M6 2v3h4V2M6 9h4" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linecap="round"/>',
    )


def settings_icon(color: str) -> QIcon:
    """Gear icon for settings and configuration actions."""
    return _menu_icon(
        "settings",
        color,
        f'<circle cx="8" cy="8" r="2.2" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<path d="M8 1.8v2M8 12.2v2M3.6 3.6L5 5M11 11l1.4 1.4M1.8 8h2M12.2 8h2'
        f'M3.6 12.4L5 11M11 5l1.4-1.4" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round"/>',
    )


def exit_icon(color: str) -> QIcon:
    """Door-with-arrow icon for Exit."""
    return _menu_icon(
        "exit",
        color,
        f'<path d="M3 2h6v12H3V2z" fill="{color}" fill-opacity="0.08" stroke="{color}" '
        f'stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M8 8h6M11.5 5.5L14 8l-2.5 2.5" fill="none" stroke="{color}" '
        f'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="6.7" cy="8" r=".6" fill="{color}"/>',
    )


def new_window_icon(color: str, badge_color: str) -> QIcon:
    """Window with plus badge."""
    return _menu_two_color_icon(
        "new_window",
        color,
        badge_color,
        f'<rect x="2" y="3" width="10" height="9" rx="1.3" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/>'
        f'<path d="M2 5.5h10" stroke="{color}" stroke-width="1.1"/>'
        f'<path d="M13.5 9.5v5M11 12h5" stroke="{badge_color}" stroke-width="1.5" '
        f'stroke-linecap="round"/>',
    )


def project_icon(color: str) -> QIcon:
    """Folder-with-code icon for project actions."""
    return _menu_icon(
        "project",
        color,
        f'<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" fill-opacity="0.12" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M6.2 8L4.8 9.4l1.4 1.4M9.8 8l1.4 1.4-1.4 1.4" fill="none" '
        f'stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def project_new_icon(color: str, badge_color: str) -> QIcon:
    """Project folder with plus badge."""
    return _menu_two_color_icon(
        "project_new",
        color,
        badge_color,
        f'<path d="M1.5 4h4L7 5.5h6v5h-11.5V4z" fill="{color}" fill-opacity="0.12" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M13.2 9.8v4.8M10.8 12.2h4.8" stroke="{badge_color}" '
        f'stroke-width="1.5" stroke-linecap="round"/>',
    )


def template_icon(color: str, badge_color: str) -> QIcon:
    """Sparkle-on-document icon for project templates."""
    return _menu_two_color_icon(
        "template",
        color,
        badge_color,
        f'<path d="M3 1.5h6l3.5 3.5v9.5H3v-13z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M9 1.5V5h3.5" fill="none" stroke="{color}" stroke-width="1.1"/>'
        f'<path d="M7.5 6.2l.7 1.6 1.6.7-1.6.7-.7 1.6-.7-1.6-1.6-.7 1.6-.7.7-1.6z" '
        f'fill="none" stroke="{badge_color}" stroke-width="1.0" stroke-linejoin="round"/>',
    )


def auto_save_icon(color: str, badge_color: str) -> QIcon:
    """Save disk with circular autosave arrows."""
    return _menu_two_color_icon(
        "auto_save",
        color,
        badge_color,
        f'<path d="M2.5 2.5h7l2 2v4.2h-9V2.5z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M5 2.5v3h4v-3" fill="none" stroke="{color}" stroke-width="1.1"/>'
        f'<path d="M12.5 9.3a3.3 3.3 0 1 1-1.1-2.4" fill="none" stroke="{badge_color}" '
        f'stroke-width="1.2" stroke-linecap="round"/>'
        f'<path d="M11.2 5.3l.3 1.8-1.8.3" fill="none" stroke="{badge_color}" '
        f'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def undo_icon(color: str) -> QIcon:
    """Undo arrow icon."""
    return _menu_icon(
        "undo",
        color,
        f'<path d="M6 4H2.8V.8M3 4.2a6 6 0 1 1 .7 7.6" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def redo_icon(color: str) -> QIcon:
    """Redo arrow icon."""
    return _menu_icon(
        "redo",
        color,
        f'<path d="M10 4h3.2V.8M13 4.2a6 6 0 1 0-.7 7.6" fill="none" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def replace_icon(color: str) -> QIcon:
    """Find/replace arrows around text."""
    return _menu_icon(
        "replace",
        color,
        f'<path d="M3 4h8M9 2l2 2-2 2M13 12H5M7 10l-2 2 2 2" fill="none" '
        f'stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="3" cy="12" r="1.1" fill="{color}"/>',
    )


def go_to_line_icon(color: str) -> QIcon:
    """Numbered lines icon."""
    return _menu_icon(
        "go_to_line",
        color,
        f'<path d="M5.5 3h8M5.5 8h8M5.5 13h8" stroke="{color}" stroke-width="1.2" '
        f'stroke-linecap="round"/>'
        f'<path d="M2.3 2.5v3M1.6 2.5h1.4M1.6 5.5h1.8M1.6 10.5h2.2L1.6 13.5h2.3" '
        f'fill="none" stroke="{color}" stroke-width="1.0" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def find_in_files_icon(color: str) -> QIcon:
    """Folder search icon."""
    return _menu_icon(
        "find_in_files",
        color,
        f'<path d="M1.5 4h4L7 5.5h7.5v5h-13V4z" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<circle cx="7" cy="9.5" r="2.2" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<path d="M8.7 11.2l2 2" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
    )


def find_references_icon(color: str) -> QIcon:
    """Connected nodes icon for references."""
    return _menu_icon(
        "find_references",
        color,
        f'<circle cx="4" cy="4" r="2" fill="{color}" fill-opacity="0.12" stroke="{color}" '
        f'stroke-width="1.1"/><circle cx="12" cy="5" r="2" fill="{color}" fill-opacity="0.12" '
        f'stroke="{color}" stroke-width="1.1"/><circle cx="7.5" cy="12" r="2" '
        f'fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1"/>'
        f'<path d="M5.9 4.2l4.2.5M5 5.7l1.5 4.5M10.7 6.6L8.8 10.3" fill="none" '
        f'stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>',
    )


def toggle_comment_icon(color: str) -> QIcon:
    """Comment bubble with slash."""
    return _menu_icon(
        "toggle_comment",
        color,
        f'<path d="M2.5 3h11v7.5h-5L5 13v-2.5H2.5V3z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M10.8 4.5L5.2 9.8" stroke="{color}" stroke-width="1.2" '
        f'stroke-linecap="round"/>',
    )


def indent_icon(color: str) -> QIcon:
    """Indent arrow icon."""
    return _menu_icon(
        "indent",
        color,
        f'<path d="M8 3h6M8 8h6M8 13h6M2 5.5L5 8l-3 2.5V5.5z" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def outdent_icon(color: str) -> QIcon:
    """Outdent arrow icon."""
    return _menu_icon(
        "outdent",
        color,
        f'<path d="M8 3h6M8 8h6M8 13h6M5 5.5L2 8l3 2.5V5.5z" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def go_to_definition_icon(color: str) -> QIcon:
    """Jump-to-symbol icon."""
    return _menu_icon(
        "go_to_definition",
        color,
        f'<path d="M3 3h5v5H3V3zM8 8h5v5H8V8z" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M6.5 4.5h5v5M9.8 4.5h1.7v1.7" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def signature_help_icon(color: str) -> QIcon:
    """Function signature icon."""
    return _menu_icon(
        "signature_help",
        color,
        f'<path d="M3 12c1.2 0 1.2-8 2.6-8 .8 0 1.1 1.1 1.1 2.2M2.5 8h4" '
        f'fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>'
        f'<path d="M9.5 5.5c1 .9 1.5 1.7 1.5 2.5s-.5 1.6-1.5 2.5M13 5.5c-1 .9-1.5 1.7-1.5 2.5S12 9.6 13 10.5" '
        f'fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>',
    )


def hover_info_icon(color: str) -> QIcon:
    """Information bubble icon."""
    return _menu_icon(
        "hover_info",
        color,
        f'<circle cx="8" cy="8" r="6" fill="{color}" fill-opacity="0.08" stroke="{color}" '
        f'stroke-width="1.2"/><path d="M8 7.2v4" stroke="{color}" stroke-width="1.4" '
        f'stroke-linecap="round"/><circle cx="8" cy="4.8" r=".8" fill="{color}"/>',
    )


def paste_reindent_icon(color: str) -> QIcon:
    """Clipboard with indent guide icon."""
    return _menu_icon(
        "paste_reindent",
        color,
        f'<path d="M3.5 4h8v10h-8V4z" fill="{color}" fill-opacity="0.08" stroke="{color}" '
        f'stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M5.5 2.5h4v3h-4v-3zM6 8h4M7.5 10.5H10M6 13h4" fill="none" '
        f'stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def run_args_icon(color: str) -> QIcon:
    """Command arguments icon."""
    return _menu_icon(
        "run_args",
        color,
        f'<path d="M3 4l3 4-3 4M7 12h6" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="10" cy="5" r="1" fill="{color}"/><circle cx="13" cy="5" r="1" fill="{color}"/>',
    )


def run_config_icon(color: str) -> QIcon:
    """Run configuration sliders icon."""
    return _menu_icon(
        "run_config",
        color,
        f'<path d="M3 4h10M3 8h10M3 12h10" stroke="{color}" stroke-width="1.2" '
        f'stroke-linecap="round"/><circle cx="6" cy="4" r="1.5" fill="{color}"/>'
        f'<circle cx="10" cy="8" r="1.5" fill="{color}"/><circle cx="5" cy="12" r="1.5" fill="{color}"/>',
    )


def breakpoint_icon(color: str) -> QIcon:
    """Breakpoint dot icon."""
    return _menu_icon(
        "breakpoint",
        color,
        f'<circle cx="8" cy="8" r="5" fill="{color}" fill-opacity="0.18" stroke="{color}" '
        f'stroke-width="1.3"/><circle cx="8" cy="8" r="2.2" fill="{color}"/>',
    )


def exception_stops_icon(color: str) -> QIcon:
    """Stop-on-exception warning icon."""
    return _menu_icon(
        "exception_stops",
        color,
        f'<path d="M8 2l6.2 11H1.8L8 2z" fill="{color}" fill-opacity="0.12" stroke="{color}" '
        f'stroke-width="1.2" stroke-linejoin="round"/>'
        f'<path d="M8 5.4v3.6" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>'
        f'<circle cx="8" cy="11.5" r=".8" fill="{color}"/>',
    )


def python_console_icon(color: str) -> QIcon:
    """Terminal prompt icon for the Python console."""
    return _menu_icon(
        "python_console",
        color,
        f'<rect x="2" y="3" width="12" height="10" rx="1.4" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/><path d="M4.2 6l2 2-2 2M7.8 10h3.5" '
        f'fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def clear_console_icon(color: str) -> QIcon:
    """Terminal with eraser icon."""
    return _menu_icon(
        "clear_console",
        color,
        f'<rect x="2" y="3" width="12" height="10" rx="1.4" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/><path d="M4 6l2 2-2 2M8.5 10.5l3-3 1.5 1.5-3 3H8.5v-1.5z" '
        f'fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def reset_layout_icon(color: str) -> QIcon:
    """Panel layout reset icon."""
    return _menu_icon(
        "reset_layout",
        color,
        f'<rect x="2" y="3" width="12" height="10" rx="1.2" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/><path d="M6 3v10M2 7h12M11.5 1.8l2 2-2 2" '
        f'fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def theme_system_icon(color: str) -> QIcon:
    """Monitor icon for system theme."""
    return _menu_icon(
        "theme_system",
        color,
        f'<rect x="2" y="3" width="12" height="8" rx="1.3" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/><path d="M6 14h4M8 11v3" stroke="{color}" '
        f'stroke-width="1.2" stroke-linecap="round"/>',
    )


def theme_light_icon(color: str) -> QIcon:
    """Sun icon for light theme."""
    return _menu_icon(
        "theme_light",
        color,
        f'<circle cx="8" cy="8" r="2.7" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4'
        f'M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" stroke="{color}" stroke-width="1.2" '
        f'stroke-linecap="round"/>',
    )


def theme_dark_icon(color: str) -> QIcon:
    """Moon icon for dark theme."""
    return _menu_icon(
        "theme_dark",
        color,
        f'<path d="M11.8 10.8A5.8 5.8 0 0 1 5.2 3a5.8 5.8 0 1 0 6.6 7.8z" '
        f'fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-width="1.2" '
        f'stroke-linejoin="round"/>',
    )


def theme_high_contrast_light_icon(color: str) -> QIcon:
    """High-contrast light theme icon."""
    return _menu_icon(
        "theme_hc_light",
        color,
        f'<circle cx="8" cy="8" r="5.5" fill="none" stroke="{color}" stroke-width="1.3"/>'
        f'<path d="M8 2.5a5.5 5.5 0 0 1 0 11V2.5z" fill="{color}" fill-opacity="0.16"/>'
        f'<path d="M4.5 8h7" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
    )


def theme_high_contrast_dark_icon(color: str) -> QIcon:
    """High-contrast dark theme icon."""
    return _menu_icon(
        "theme_hc_dark",
        color,
        f'<circle cx="8" cy="8" r="5.5" fill="{color}" fill-opacity="0.14" stroke="{color}" '
        f'stroke-width="1.3"/><path d="M8 2.5a5.5 5.5 0 0 0 0 11V2.5z" '
        f'fill="none" stroke="{color}" stroke-width="1.2"/>',
    )


def markdown_source_icon(color: str) -> QIcon:
    """Markdown source icon."""
    return _menu_icon(
        "markdown_source",
        color,
        f'<rect x="2" y="3" width="12" height="10" rx="1.3" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/><path d="M4 10V6l2 2 2-2v4M10 6v4M12 6v4" '
        f'fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def markdown_preview_icon(color: str) -> QIcon:
    """Markdown preview eye icon."""
    return _menu_icon(
        "markdown_preview",
        color,
        f'<path d="M1.8 8s2.2-4 6.2-4 6.2 4 6.2 4-2.2 4-6.2 4-6.2-4-6.2-4z" '
        f'fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/><circle cx="8" cy="8" r="2" fill="none" stroke="{color}" '
        f'stroke-width="1.1"/>',
    )


def markdown_split_icon(color: str) -> QIcon:
    """Split source/preview icon."""
    return _menu_icon(
        "markdown_split",
        color,
        f'<rect x="2" y="3" width="12" height="10" rx="1.2" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/><path d="M8 3v10M4 9V6l1.3 1.4L6.6 6v3'
        f'M10 6.5h2M10 9h1.5" fill="none" stroke="{color}" stroke-width="1.0" '
        f'stroke-linecap="round" stroke-linejoin="round"/>',
    )


def zoom_in_icon(color: str) -> QIcon:
    """Magnifier plus icon."""
    return _menu_icon(
        "zoom_in",
        color,
        f'<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.3"/>'
        f'<path d="M7 4.8v4.4M4.8 7h4.4M10.5 10.5L14 14" stroke="{color}" '
        f'stroke-width="1.4" stroke-linecap="round"/>',
    )


def zoom_out_icon(color: str) -> QIcon:
    """Magnifier minus icon."""
    return _menu_icon(
        "zoom_out",
        color,
        f'<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.3"/>'
        f'<path d="M4.8 7h4.4M10.5 10.5L14 14" stroke="{color}" stroke-width="1.4" '
        f'stroke-linecap="round"/>',
    )


def zoom_reset_icon(color: str) -> QIcon:
    """Magnifier reset icon."""
    return _menu_icon(
        "zoom_reset",
        color,
        f'<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.3"/>'
        f'<path d="M5 7h4M10.5 10.5L14 14M12 2.5a3.5 3.5 0 0 1 1 2.5M13 2.5h-2.5V5" '
        f'fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def plugin_icon(color: str) -> QIcon:
    """Puzzle-piece icon for plugins."""
    return _menu_icon(
        "plugin",
        color,
        f'<path d="M3 3.5h3a2 2 0 1 1 4 0h3v3a2 2 0 1 0 0 4v2.5H3v-3a2 2 0 1 0 0-4V3.5z" '
        f'fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>',
    )


def dependency_icon(color: str) -> QIcon:
    """Package/dependency cube icon."""
    return _menu_icon(
        "dependency",
        color,
        f'<path d="M8 1.8l5.5 3.1v6.2L8 14.2l-5.5-3.1V4.9L8 1.8z" fill="{color}" '
        f'fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M2.7 5L8 8l5.3-3M8 8v6" fill="none" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>',
    )


def add_dependency_icon(color: str, badge_color: str) -> QIcon:
    """Dependency cube with plus badge."""
    return _menu_two_color_icon(
        "add_dependency",
        color,
        badge_color,
        f'<path d="M7 2l4.5 2.6v5L7 12.2 2.5 9.6v-5L7 2z" fill="{color}" '
        f'fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M2.7 4.8L7 7.2l4.3-2.4M7 7.2v5" fill="none" stroke="{color}" '
        f'stroke-width="1.0"/><path d="M13.2 9.8v4.8M10.8 12.2h4.8" stroke="{badge_color}" '
        f'stroke-width="1.5" stroke-linecap="round"/>',
    )


def format_icon(color: str) -> QIcon:
    """Format text icon."""
    return _menu_icon(
        "format",
        color,
        f'<path d="M3 3h10M5 3v10M9 3v10M3.5 13h3M7.5 13h3" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
    )


def organize_imports_icon(color: str) -> QIcon:
    """Sorted import lines icon."""
    return _menu_icon(
        "organize_imports",
        color,
        f'<path d="M4 4h8M4 8h6M4 12h4M12 7l2 2-2 2M10 9h4" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def lint_icon(color: str) -> QIcon:
    """Checklist icon for lint."""
    return _menu_icon(
        "lint",
        color,
        f'<path d="M3 4l1.4 1.4L7 3M3 9l1.4 1.4L7 8M9 4.5h4M9 9.5h4M3 13h10" '
        f'fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def safe_fix_icon(color: str, badge_color: str) -> QIcon:
    """Shield with wrench icon for safe fixes."""
    return _menu_two_color_icon(
        "safe_fix",
        color,
        badge_color,
        f'<path d="M8 2l5 2v3.8c0 3-2 5.1-5 6.2-3-1.1-5-3.2-5-6.2V4l5-2z" '
        f'fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/><path d="M6.2 9.2l3.6-3.6 1.1 1.1-3.6 3.6H6.2V9.2z" '
        f'fill="none" stroke="{badge_color}" stroke-width="1.0" stroke-linejoin="round"/>',
    )


def rebuild_cache_icon(color: str) -> QIcon:
    """Database refresh icon."""
    return _menu_icon(
        "rebuild_cache",
        color,
        f'<ellipse cx="8" cy="4" rx="5" ry="2" fill="{color}" fill-opacity="0.08" stroke="{color}" '
        f'stroke-width="1.1"/><path d="M3 4v4c0 1.1 2.2 2 5 2s5-.9 5-2V4" '
        f'fill="none" stroke="{color}" stroke-width="1.1"/><path d="M12 10a3 3 0 1 1-1.1-2.3" '
        f'fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>'
        f'<path d="M10.5 6.6l.5 1.6-1.6.5" fill="none" stroke="{color}" stroke-width="1.1" '
        f'stroke-linecap="round" stroke-linejoin="round"/>',
    )


def runtime_modules_icon(color: str) -> QIcon:
    """Runtime module refresh icon."""
    return _menu_icon(
        "runtime_modules",
        color,
        f'<path d="M3 5l5-3 5 3v6l-5 3-5-3V5z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M11 7a3.3 3.3 0 1 1-1.2-2.5M9.6 3.2l.4 1.8-1.8.4" fill="none" '
        f'stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def analyze_imports_icon(color: str) -> QIcon:
    """Import graph analysis icon."""
    return _menu_icon(
        "analyze_imports",
        color,
        f'<circle cx="4" cy="8" r="2" fill="{color}" fill-opacity="0.10" stroke="{color}" '
        f'stroke-width="1.1"/><circle cx="12" cy="4" r="2" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.1"/><circle cx="12" cy="12" r="2" '
        f'fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1"/>'
        f'<path d="M5.8 7.1L10.1 4.9M5.8 8.9l4.3 2.2" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linecap="round"/>',
    )


def symbol_icon(color: str) -> QIcon:
    """Go-to-symbol icon."""
    return _menu_icon(
        "symbol",
        color,
        f'<path d="M4 3h8v3H4V3zM2.5 9h5v4h-5V9zM9.5 9h4v4h-4V9z" '
        f'fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>',
    )


def language_mode_icon(color: str) -> QIcon:
    """Language mode braces icon."""
    return _menu_icon(
        "language_mode",
        color,
        f'<path d="M6 3H5c-1 0-1.5.5-1.5 1.5V6c0 1-.6 1.5-1.5 1.5C2.9 7.5 3.5 8 3.5 9v1.5C3.5 11.5 4 12 5 12h1'
        f'M10 3h1c1 0 1.5.5 1.5 1.5V6c0 1 .6 1.5 1.5 1.5-.9 0-1.5.5-1.5 1.5v1.5c0 1-.5 1.5-1.5 1.5h-1" '
        f'fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )


def clear_override_icon(color: str) -> QIcon:
    """Clear language override icon."""
    return _menu_icon(
        "clear_override",
        color,
        f'<path d="M4 5h8M4 8h8M4 11h5M11.5 10l2.5 2.5M14 10l-2.5 2.5" fill="none" '
        f'stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
    )


def inspect_token_icon(color: str) -> QIcon:
    """Magnifier over syntax token icon."""
    return _menu_icon(
        "inspect_token",
        color,
        f'<rect x="2" y="3" width="7" height="5" rx="1" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.0"/><circle cx="9" cy="9" r="3" fill="none" '
        f'stroke="{color}" stroke-width="1.2"/><path d="M11.2 11.2L14 14" stroke="{color}" '
        f'stroke-width="1.2" stroke-linecap="round"/>',
    )


def runtime_center_icon(color: str) -> QIcon:
    """Runtime center gauge icon."""
    return _menu_icon(
        "runtime_center",
        color,
        f'<path d="M2.5 10a5.5 5.5 0 1 1 11 0" fill="none" stroke="{color}" '
        f'stroke-width="1.2" stroke-linecap="round"/><path d="M8 10l3-3" stroke="{color}" '
        f'stroke-width="1.3" stroke-linecap="round"/><path d="M4 13h8" stroke="{color}" '
        f'stroke-width="1.2" stroke-linecap="round"/>',
    )


def health_check_icon(color: str) -> QIcon:
    """Health check heartbeat icon."""
    return _menu_icon(
        "health_check",
        color,
        f'<path d="M2 8h2.5l1.2-3 2.4 6 1.4-3H14" fill="none" stroke="{color}" '
        f'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M8 2.5c3.5-2.2 7.6 2.8 0 10.5C.4 5.3 4.5.3 8 2.5z" fill="none" '
        f'stroke="{color}" stroke-width="1.0" stroke-linejoin="round"/>',
    )


def support_bundle_icon(color: str) -> QIcon:
    """Support bundle archive icon."""
    return _menu_icon(
        "support_bundle",
        color,
        f'<path d="M3 3h10v10H3V3z" fill="{color}" fill-opacity="0.08" stroke="{color}" '
        f'stroke-width="1.1" stroke-linejoin="round"/><path d="M3 6h10M6 3v10M8 4.5h1.5M8 7h1.5M8 9.5h1.5" '
        f'fill="none" stroke="{color}" stroke-width="1.0" stroke-linecap="round"/>',
    )


def headless_notes_icon(color: str) -> QIcon:
    """Headless notes document icon."""
    return _menu_icon(
        "headless_notes",
        color,
        f'<path d="M3 1.5h6l3.5 3.5v9.5H3v-13z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M9 1.5V5h3.5M5 8h5M5 10.5h5M5 13h3" fill="none" stroke="{color}" '
        f'stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
    )


def example_project_icon(color: str) -> QIcon:
    """Example project folder with sparkle."""
    return _menu_icon(
        "example_project",
        color,
        f'<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" fill-opacity="0.10" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>'
        f'<path d="M8.5 7l.6 1.3 1.3.6-1.3.6-.6 1.3-.6-1.3-1.3-.6 1.3-.6.6-1.3z" '
        f'fill="none" stroke="{color}" stroke-width="1.0" stroke-linejoin="round"/>',
    )


def app_log_icon(color: str) -> QIcon:
    """Application log document icon."""
    return _menu_icon(
        "app_log",
        color,
        f'<path d="M3 1.5h6l3.5 3.5v9.5H3v-13z" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M9 1.5V5h3.5'
        f'M5 8h6M5 10.5h6M5 13h4" fill="none" stroke="{color}" stroke-width="1.1" '
        f'stroke-linecap="round" stroke-linejoin="round"/>',
    )


def onboarding_icon(color: str) -> QIcon:
    """Compass icon for onboarding."""
    return _menu_icon(
        "onboarding",
        color,
        f'<circle cx="8" cy="8" r="6" fill="{color}" fill-opacity="0.08" stroke="{color}" '
        f'stroke-width="1.2"/><path d="M10.5 5.5L9 9l-3.5 1.5L7 7l3.5-1.5z" '
        f'fill="none" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
    )


def getting_started_icon(color: str) -> QIcon:
    """Book icon for getting started."""
    return _menu_icon(
        "getting_started",
        color,
        f'<path d="M3 2.5h4.2c.8 0 1.3.5 1.3 1.3v10c0-.8-.5-1.3-1.3-1.3H3v-10z'
        f'M8.5 3.8c0-.8.5-1.3 1.3-1.3H14v10H9.8c-.8 0-1.3.5-1.3 1.3" '
        f'fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" '
        f'stroke-linejoin="round"/>',
    )


def keyboard_icon(color: str) -> QIcon:
    """Keyboard shortcuts icon."""
    return _menu_icon(
        "keyboard",
        color,
        f'<rect x="1.5" y="4" width="13" height="8" rx="1.4" fill="{color}" fill-opacity="0.08" '
        f'stroke="{color}" stroke-width="1.1"/><path d="M4 6.5h1M7 6.5h1M10 6.5h1'
        f'M4 9h1M7 9h1M10 9h2" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>',
    )


def about_icon(color: str) -> QIcon:
    """Info circle icon for About."""
    return hover_info_icon(color)
