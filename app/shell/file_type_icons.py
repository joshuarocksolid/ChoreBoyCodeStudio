"""VS Code-style file type icons for the project tree and Quick Open.

Each file type gets a distinctive icon with a fixed color, recognizable at
16x16.  Badge-style icons (text on colored rounded rectangle) use QPainter
for reliable text rendering.  Symbol icons use inline SVG paths rendered
through QSvgRenderer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide2.QtCore import QByteArray, QRect, QSize, Qt
from PySide2.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide2.QtSvg import QSvgRenderer

_SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
_SVG_CLOSE = "</svg>"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _svg_icon(body: str) -> QIcon:
    svg = f"{_SVG_OPEN}{body}{_SVG_CLOSE}"
    data = QByteArray(svg.encode("utf-8"))
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(QSize(16, 16))
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def _badge_icon(bg: str, label: str, fg: str = "#FFFFFF") -> QIcon:
    pixmap = QPixmap(QSize(16, 16))
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(bg))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(1, 1, 14, 14, 2.5, 2.5)
    p.setPen(QColor(fg))
    font = QFont("sans-serif")
    n = len(label)
    font.setPixelSize(11 if n == 1 else 9 if n == 2 else 7)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRect(0, 0, 16, 16), Qt.AlignCenter, label)
    p.end()
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Badge icons  (text on colored background)
# ---------------------------------------------------------------------------

_python_file_icon_cache: QIcon | None = None


def _python_badge_fallback_icon() -> QIcon:
    return _badge_icon("#3572A5", "Py")


def _build_python_logo_icon() -> QIcon:
    """Rasterize bundled PSF two-snakes mark once; 16px + @2x for HiDPI trees."""
    path = Path(__file__).resolve().parents[1] / "ui" / "icons" / "python-logo-only.svg"
    if not path.is_file():
        return _python_badge_fallback_icon()
    renderer = QSvgRenderer(QByteArray(path.read_bytes()))
    if not renderer.isValid():
        return _python_badge_fallback_icon()
    icon = QIcon()
    for size, dpr in ((16, 1.0), (32, 2.0)):
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(dpr)
        icon.addPixmap(pixmap)
    return icon


def _python_icon() -> QIcon:
    global _python_file_icon_cache
    if _python_file_icon_cache is None:
        _python_file_icon_cache = _build_python_logo_icon()
    return _python_file_icon_cache


def _javascript_icon() -> QIcon:
    return _badge_icon("#F0DB4F", "JS", "#323330")


def _typescript_icon() -> QIcon:
    return _badge_icon("#3178C6", "TS")


def _css_icon() -> QIcon:
    return _badge_icon("#563D7C", "#")


def _c_icon() -> QIcon:
    return _badge_icon("#5C6BC0", "C")


def _header_icon() -> QIcon:
    return _badge_icon("#7B68AF", "H")


def _cpp_icon() -> QIcon:
    return _badge_icon("#659AD2", "C+")


def _rust_icon() -> QIcon:
    return _badge_icon("#CE422B", "Rs")


def _go_icon() -> QIcon:
    return _badge_icon("#00ADD8", "Go")


def _java_icon() -> QIcon:
    return _badge_icon("#B07219", "Jv")


def _ruby_icon() -> QIcon:
    return _badge_icon("#CC342D", "Rb")


def _makefile_icon() -> QIcon:
    return _badge_icon("#E8710A", "Mk")


# ---------------------------------------------------------------------------
# Symbol icons  (SVG paths)
# ---------------------------------------------------------------------------

def _json_icon() -> QIcon:
    return _svg_icon(
        '<path d="M5.5 2.5C4 2.5 3.5 3.5 3.5 4.5v2c0 .8-.7 1.3-1.5 1.5'
        ".8.2 1.5.7 1.5 1.5v2c0 1 .5 2 2 2"
        '" fill="none" stroke="#F5A623" stroke-width="1.5" stroke-linecap="round"/>'
        '<path d="M10.5 2.5c1.5 0 2 1 2 2v2c0 .8.7 1.3 1.5 1.5'
        "-.8.2-1.5.7-1.5 1.5v2c0 1-.5 2-2 2"
        '" fill="none" stroke="#F5A623" stroke-width="1.5" stroke-linecap="round"/>'
    )


def _html_icon() -> QIcon:
    return _svg_icon(
        '<path d="M6 3L2 8l4 5" fill="none" stroke="#E44D26" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M10 3l4 5-4 5" fill="none" stroke="#E44D26" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def _xml_icon() -> QIcon:
    return _svg_icon(
        '<path d="M5 3L1.5 8 5 13" fill="none" stroke="#E8710A" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M11 3l3.5 5L11 13" fill="none" stroke="#E8710A" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<line x1="9.5" y1="2" x2="6.5" y2="14" stroke="#E8710A" '
        'stroke-width="1.2" stroke-linecap="round"/>'
    )


def _markdown_icon() -> QIcon:
    return _svg_icon(
        '<rect x="0.5" y="2.5" width="15" height="11" rx="1.5" '
        'fill="none" stroke="#519ABA" stroke-width="1.2"/>'
        '<path d="M3 10V6l2.5 3L8 6v4" fill="none" stroke="#519ABA" '
        'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M13 8.5v-3l-2 2" fill="none" stroke="#519ABA" '
        'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def _shell_icon() -> QIcon:
    return _svg_icon(
        '<rect x="0.5" y="2" width="15" height="12" rx="1.5" '
        'fill="none" stroke="#4EAA25" stroke-width="1.2"/>'
        '<path d="M4 6l2.5 2.5L4 11" fill="none" stroke="#4EAA25" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        '<line x1="8.5" y1="11" x2="12" y2="11" stroke="#4EAA25" '
        'stroke-width="1.5" stroke-linecap="round"/>'
    )


def _yaml_icon() -> QIcon:
    return _svg_icon(
        '<circle cx="3" cy="3.5" r="1" fill="#CB171E"/>'
        '<line x1="5" y1="3.5" x2="10" y2="3.5" stroke="#CB171E" '
        'stroke-width="1.3" stroke-linecap="round"/>'
        '<circle cx="5.5" cy="6.5" r="1" fill="#CB171E"/>'
        '<line x1="7.5" y1="6.5" x2="13" y2="6.5" stroke="#CB171E" '
        'stroke-width="1.3" stroke-linecap="round"/>'
        '<circle cx="5.5" cy="9.5" r="1" fill="#CB171E"/>'
        '<line x1="7.5" y1="9.5" x2="11" y2="9.5" stroke="#CB171E" '
        'stroke-width="1.3" stroke-linecap="round"/>'
        '<circle cx="3" cy="12.5" r="1" fill="#CB171E"/>'
        '<line x1="5" y1="12.5" x2="9" y2="12.5" stroke="#CB171E" '
        'stroke-width="1.3" stroke-linecap="round"/>'
    )


def _toml_icon() -> QIcon:
    return _config_icon("#9C4221")


def _config_icon(color: str = "#6B7280") -> QIcon:
    return _svg_icon(
        f'<circle cx="8" cy="8" r="2.5" fill="none" stroke="{color}" stroke-width="1.3"/>'
        f'<line x1="8" y1="1.5" x2="8" y2="4" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>'
        f'<line x1="8" y1="12" x2="8" y2="14.5" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>'
        f'<line x1="1.5" y1="8" x2="4" y2="8" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>'
        f'<line x1="12" y1="8" x2="14.5" y2="8" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>'
        f'<line x1="3.4" y1="3.4" x2="5.2" y2="5.2" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>'
        f'<line x1="10.8" y1="10.8" x2="12.6" y2="12.6" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>'
        f'<line x1="12.6" y1="3.4" x2="10.8" y2="5.2" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>'
        f'<line x1="5.2" y1="10.8" x2="3.4" y2="12.6" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>'
    )


def _sql_icon() -> QIcon:
    return _svg_icon(
        '<ellipse cx="8" cy="4" rx="5.5" ry="2.5" fill="none" stroke="#336791" stroke-width="1.2"/>'
        '<path d="M2.5 4v8c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V4" '
        'fill="none" stroke="#336791" stroke-width="1.2"/>'
        '<path d="M2.5 8c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5" '
        'fill="none" stroke="#336791" stroke-width="0.8" opacity="0.5"/>'
    )


def _csv_icon() -> QIcon:
    return _svg_icon(
        '<rect x="1.5" y="1.5" width="13" height="13" rx="1" '
        'fill="none" stroke="#059669" stroke-width="1.2"/>'
        '<line x1="6" y1="1.5" x2="6" y2="14.5" stroke="#059669" stroke-width="0.9"/>'
        '<line x1="10.5" y1="1.5" x2="10.5" y2="14.5" stroke="#059669" stroke-width="0.9"/>'
        '<line x1="1.5" y1="5.5" x2="14.5" y2="5.5" stroke="#059669" stroke-width="0.9"/>'
        '<line x1="1.5" y1="10" x2="14.5" y2="10" stroke="#059669" stroke-width="0.9"/>'
    )


def _text_icon() -> QIcon:
    return _svg_icon(
        '<line x1="2" y1="3" x2="14" y2="3" stroke="#6B7280" stroke-width="1.3" stroke-linecap="round"/>'
        '<line x1="2" y1="6.5" x2="11" y2="6.5" stroke="#6B7280" stroke-width="1.3" stroke-linecap="round"/>'
        '<line x1="2" y1="10" x2="13" y2="10" stroke="#6B7280" stroke-width="1.3" stroke-linecap="round"/>'
        '<line x1="2" y1="13.5" x2="8" y2="13.5" stroke="#6B7280" stroke-width="1.3" stroke-linecap="round"/>'
    )


def _log_icon() -> QIcon:
    return _svg_icon(
        '<circle cx="3" cy="3.5" r="1.2" fill="#F97316"/>'
        '<line x1="6" y1="3.5" x2="14" y2="3.5" stroke="#F97316" stroke-width="1.3" stroke-linecap="round"/>'
        '<circle cx="3" cy="8" r="1.2" fill="#F97316"/>'
        '<line x1="6" y1="8" x2="12" y2="8" stroke="#F97316" stroke-width="1.3" stroke-linecap="round"/>'
        '<circle cx="3" cy="12.5" r="1.2" fill="#F97316"/>'
        '<line x1="6" y1="12.5" x2="13" y2="12.5" stroke="#F97316" stroke-width="1.3" stroke-linecap="round"/>'
    )


def _env_icon() -> QIcon:
    return _svg_icon(
        '<circle cx="5.5" cy="6" r="3.5" fill="none" stroke="#EAB308" stroke-width="1.4"/>'
        '<circle cx="5.5" cy="6" r="1.2" fill="#EAB308"/>'
        '<line x1="8.5" y1="8.5" x2="14" y2="14" stroke="#EAB308" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="11.5" y1="11.5" x2="13.5" y2="9.5" stroke="#EAB308" stroke-width="1.3" stroke-linecap="round"/>'
    )


def _git_icon() -> QIcon:
    return _svg_icon(
        '<circle cx="4" cy="3" r="1.8" fill="#F05032"/>'
        '<circle cx="12" cy="3" r="1.8" fill="#F05032"/>'
        '<circle cx="4" cy="13" r="1.8" fill="#F05032"/>'
        '<line x1="4" y1="4.8" x2="4" y2="11.2" stroke="#F05032" stroke-width="1.4"/>'
        '<path d="M12 4.8c0 3-3 4-8 6.2" fill="none" stroke="#F05032" stroke-width="1.4"/>'
    )


def _image_icon() -> QIcon:
    return _svg_icon(
        '<rect x="1" y="2" width="14" height="12" rx="1.5" fill="none" stroke="#0D9488" stroke-width="1.2"/>'
        '<circle cx="5" cy="5.5" r="1.5" fill="#0D9488" opacity="0.7"/>'
        '<path d="M1.5 12l3.5-4 2.5 2 3-3.5L15 12" fill="#0D9488" opacity="0.35"/>'
    )


def _ruby_diamond_icon() -> QIcon:
    return _svg_icon(
        '<path d="M8 1l6 5-6 9-6-9 6-5z" fill="#CC342D" fill-opacity="0.2" '
        'stroke="#CC342D" stroke-width="1.2" stroke-linejoin="round"/>'
        '<path d="M2 6h12M5 1l-3 5 6 9M11 1l3 5-6 9" fill="none" '
        'stroke="#CC342D" stroke-width="0.8" opacity="0.5"/>'
    )


def _ui_icon() -> QIcon:
    return _svg_icon(
        '<rect x="1" y="2" width="14" height="12" rx="1.5" fill="none" stroke="#41CD52" stroke-width="1.2"/>'
        '<line x1="1" y1="5.5" x2="15" y2="5.5" stroke="#41CD52" stroke-width="1"/>'
        '<circle cx="3.5" cy="3.8" r="0.9" fill="#41CD52"/>'
        '<circle cx="6" cy="3.8" r="0.9" fill="#41CD52"/>'
    )


# --- Filename-specific icons ---

def _dockerfile_icon() -> QIcon:
    return _svg_icon(
        '<rect x="1" y="7.5" width="14" height="6.5" rx="1" fill="none" stroke="#2496ED" stroke-width="1.2"/>'
        '<rect x="3" y="3" width="3" height="3.5" rx="0.5" fill="none" stroke="#2496ED" stroke-width="1"/>'
        '<rect x="7" y="3" width="3" height="3.5" rx="0.5" fill="none" stroke="#2496ED" stroke-width="1"/>'
        '<line x1="5" y1="9" x2="5" y2="12.5" stroke="#2496ED" stroke-width="0.8"/>'
        '<line x1="8" y1="9" x2="8" y2="12.5" stroke="#2496ED" stroke-width="0.8"/>'
        '<line x1="11" y1="9" x2="11" y2="12.5" stroke="#2496ED" stroke-width="0.8"/>'
        '<line x1="1" y1="10.8" x2="15" y2="10.8" stroke="#2496ED" stroke-width="0.8"/>'
    )


def _license_icon() -> QIcon:
    return _svg_icon(
        '<path d="M8 1L2 4v4c0 4 2.5 6.5 6 7.5 3.5-1 6-3.5 6-7.5V4L8 1z" '
        'fill="#D4A017" fill-opacity="0.2" stroke="#D4A017" stroke-width="1.2" stroke-linejoin="round"/>'
        '<path d="M6 8l1.5 1.5L10.5 6" fill="none" stroke="#D4A017" '
        'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def _readme_icon() -> QIcon:
    return _svg_icon(
        '<path d="M2 2v12l6-2 6 2V2l-6 2-6-2z" fill="#4183C4" fill-opacity="0.15" '
        'stroke="#4183C4" stroke-width="1.2" stroke-linejoin="round"/>'
        '<line x1="8" y1="4" x2="8" y2="12" stroke="#4183C4" stroke-width="1"/>'
    )


def _requirements_icon() -> QIcon:
    return _svg_icon(
        '<path d="M2 5.5l6-3 6 3v6l-6 3-6-3v-6z" fill="#3572A5" fill-opacity="0.15" '
        'stroke="#3572A5" stroke-width="1.2" stroke-linejoin="round"/>'
        '<path d="M2 5.5l6 3 6-3M8 8.5v6" fill="none" stroke="#3572A5" stroke-width="1"/>'
    )


def _desktop_icon() -> QIcon:
    return _svg_icon(
        '<rect x="1" y="1" width="6" height="6" rx="1" fill="#7B68AF" fill-opacity="0.3" '
        'stroke="#7B68AF" stroke-width="1"/>'
        '<rect x="9" y="1" width="6" height="6" rx="1" fill="#7B68AF" fill-opacity="0.3" '
        'stroke="#7B68AF" stroke-width="1"/>'
        '<rect x="1" y="9" width="6" height="6" rx="1" fill="#7B68AF" fill-opacity="0.3" '
        'stroke="#7B68AF" stroke-width="1"/>'
        '<rect x="9" y="9" width="6" height="6" rx="1" fill="#7B68AF" fill-opacity="0.3" '
        'stroke="#7B68AF" stroke-width="1"/>'
    )


# ---------------------------------------------------------------------------
# Extension -> icon builder mapping
# ---------------------------------------------------------------------------

_EXT_ICON_BUILDERS: dict[str, Callable[[], QIcon]] = {
    # Python
    ".py": _python_icon,
    ".pyw": _python_icon,
    ".pyi": _python_icon,
    # JavaScript
    ".js": _javascript_icon,
    ".mjs": _javascript_icon,
    ".cjs": _javascript_icon,
    ".jsx": _javascript_icon,
    # TypeScript
    ".ts": _typescript_icon,
    ".tsx": _typescript_icon,
    # CSS family
    ".css": _css_icon,
    ".scss": _css_icon,
    ".sass": _css_icon,
    ".less": _css_icon,
    # Data / config
    ".json": _json_icon,
    ".jsonc": _json_icon,
    ".json5": _json_icon,
    # Markup
    ".html": _html_icon,
    ".htm": _html_icon,
    ".xml": _xml_icon,
    ".xsl": _xml_icon,
    ".xslt": _xml_icon,
    ".md": _markdown_icon,
    ".markdown": _markdown_icon,
    ".rst": _markdown_icon,
    # Shell
    ".sh": _shell_icon,
    ".bash": _shell_icon,
    ".zsh": _shell_icon,
    ".fish": _shell_icon,
    # Config
    ".yaml": _yaml_icon,
    ".yml": _yaml_icon,
    ".toml": _toml_icon,
    ".cfg": _config_icon,
    ".ini": _config_icon,
    ".conf": _config_icon,
    ".env": _env_icon,
    # Database
    ".sql": _sql_icon,
    # Tabular
    ".csv": _csv_icon,
    ".tsv": _csv_icon,
    # Text / logs
    ".txt": _text_icon,
    ".log": _log_icon,
    # Images
    ".png": _image_icon,
    ".jpg": _image_icon,
    ".jpeg": _image_icon,
    ".gif": _image_icon,
    ".svg": _image_icon,
    ".webp": _image_icon,
    ".ico": _image_icon,
    ".bmp": _image_icon,
    # C / C++
    ".c": _c_icon,
    ".h": _header_icon,
    ".hpp": _header_icon,
    ".hxx": _header_icon,
    ".cpp": _cpp_icon,
    ".cxx": _cpp_icon,
    ".cc": _cpp_icon,
    # Rust
    ".rs": _rust_icon,
    # Go
    ".go": _go_icon,
    # Java
    ".java": _java_icon,
    ".jar": _java_icon,
    # Ruby
    ".rb": _ruby_diamond_icon,
    # Qt UI
    ".ui": _ui_icon,
    # Desktop entry
    ".desktop": _desktop_icon,
}

# ---------------------------------------------------------------------------
# Filename -> icon builder mapping  (keys are lowercase)
# ---------------------------------------------------------------------------

_FILENAME_ICON_BUILDERS: dict[str, Callable[[], QIcon]] = {
    "dockerfile": _dockerfile_icon,
    "docker-compose.yml": _dockerfile_icon,
    "docker-compose.yaml": _dockerfile_icon,
    "makefile": _makefile_icon,
    "cmakelists.txt": _makefile_icon,
    "license": _license_icon,
    "licence": _license_icon,
    "license.md": _license_icon,
    "licence.md": _license_icon,
    "license.txt": _license_icon,
    "licence.txt": _license_icon,
    "readme": _readme_icon,
    "readme.md": _readme_icon,
    "readme.txt": _readme_icon,
    "readme.rst": _readme_icon,
    "requirements.txt": _requirements_icon,
    "requirements-dev.txt": _requirements_icon,
    "pyproject.toml": _python_icon,
    "setup.py": _python_icon,
    "setup.cfg": _python_icon,
    ".gitignore": _git_icon,
    ".gitmodules": _git_icon,
    ".gitattributes": _git_icon,
    ".env": _env_icon,
    ".env.local": _env_icon,
    ".env.development": _env_icon,
    ".env.production": _env_icon,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_cached_ext_map: dict[str, QIcon] | None = None
_cached_name_map: dict[str, QIcon] | None = None


def build_file_type_icon_map() -> dict[str, QIcon]:
    """Return extension -> QIcon mapping.  Cached after first call."""
    global _cached_ext_map
    if _cached_ext_map is None:
        _cached_ext_map = {ext: builder() for ext, builder in _EXT_ICON_BUILDERS.items()}
    return _cached_ext_map


def build_filename_icon_map() -> dict[str, QIcon]:
    """Return lowercase-filename -> QIcon mapping.  Cached after first call."""
    global _cached_name_map
    if _cached_name_map is None:
        _cached_name_map = {name: builder() for name, builder in _FILENAME_ICON_BUILDERS.items()}
    return _cached_name_map
