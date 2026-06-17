"""Data-driven SVG glyph registry for shell icons."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SvgGlyphSpec:
    """SVG path template and cache metadata for one shell glyph."""

    cache_name: str
    body: str
    view_box: str = "0 0 16 16"
    cached: bool = False
    two_color: bool = False


SVG_GLYPHS: dict[str, SvgGlyphSpec] = {
    "add_dependency_icon": SvgGlyphSpec(
        cache_name="add_dependency",
        body='<path d="M7 2l4.5 2.6v5L7 12.2 2.5 9.6v-5L7 2z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M2.7 4.8L7 7.2l4.3-2.4M7 7.2v5" fill="none" stroke="{color}" stroke-width="1.0"/><path d="M13.2 9.8v4.8M10.8 12.2h4.8" stroke="{badge_color}" stroke-width="1.5" stroke-linecap="round"/>',
        cached=True,
        two_color=True,
    ),
    "analyze_imports_icon": SvgGlyphSpec(
        cache_name="analyze_imports",
        body='<circle cx="4" cy="8" r="2" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1"/><circle cx="12" cy="4" r="2" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1"/><circle cx="12" cy="12" r="2" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1"/><path d="M5.8 7.1L10.1 4.9M5.8 8.9l4.3 2.2" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "app_log_icon": SvgGlyphSpec(
        cache_name="app_log",
        body='<path d="M3 1.5h6l3.5 3.5v9.5H3v-13z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M9 1.5V5h3.5M5 8h6M5 10.5h6M5 13h4" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "auto_save_icon": SvgGlyphSpec(
        cache_name="auto_save",
        body='<path d="M2.5 2.5h7l2 2v4.2h-9V2.5z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M5 2.5v3h4v-3" fill="none" stroke="{color}" stroke-width="1.1"/><path d="M12.5 9.3a3.3 3.3 0 1 1-1.1-2.4" fill="none" stroke="{badge_color}" stroke-width="1.2" stroke-linecap="round"/><path d="M11.2 5.3l.3 1.8-1.8.3" fill="none" stroke="{badge_color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=True,
    ),
    "breakpoint_icon": SvgGlyphSpec(
        cache_name="breakpoint",
        body='<circle cx="8" cy="8" r="5" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="1.3"/><circle cx="8" cy="8" r="2.2" fill="{color}"/>',
        cached=True,
        two_color=False,
    ),
    "clear_console_icon": SvgGlyphSpec(
        cache_name="clear_console",
        body='<rect x="2" y="3" width="12" height="10" rx="1.4" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M4 6l2 2-2 2M8.5 10.5l3-3 1.5 1.5-3 3H8.5v-1.5z" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "clear_override_icon": SvgGlyphSpec(
        cache_name="clear_override",
        body='<path d="M4 5h8M4 8h8M4 11h5M11.5 10l2.5 2.5M14 10l-2.5 2.5" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "copy_icon": SvgGlyphSpec(
        cache_name="copy",
        body='<path d="M5 3.5h7v9H5v-9z" fill="none" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M3 6.5v7h6" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "copy_path_icon": SvgGlyphSpec(
        cache_name="copy_path",
        body='<path d="M5.8 10.2L4.5 11.5a2.5 2.5 0 0 1-3.5-3.5l2-2" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/><path d="M10.2 5.8l1.3-1.3a2.5 2.5 0 0 1 3.5 3.5l-2 2" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/><path d="M5.5 8.5l5-5" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "cut_icon": SvgGlyphSpec(
        cache_name="cut",
        body='<circle cx="4" cy="4" r="1.7" fill="none" stroke="{color}" stroke-width="1.1"/><circle cx="4" cy="12" r="1.7" fill="none" stroke="{color}" stroke-width="1.1"/><path d="M5.3 5.3L13 13M5.3 10.7L13 3" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "dependency_icon": SvgGlyphSpec(
        cache_name="dependency",
        body='<path d="M8 1.8l5.5 3.1v6.2L8 14.2l-5.5-3.1V4.9L8 1.8z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M2.7 5L8 8l5.3-3M8 8v6" fill="none" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "duplicate_icon": SvgGlyphSpec(
        cache_name="duplicate",
        body='<path d="M5 2h7v9H5V2z" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M3 5h7v9H3V5z" fill="none" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "example_project_icon": SvgGlyphSpec(
        cache_name="example_project",
        body='<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M8.5 7l.6 1.3 1.3.6-1.3.6-.6 1.3-.6-1.3-1.3-.6 1.3-.6.6-1.3z" fill="none" stroke="{color}" stroke-width="1.0" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "exception_stops_icon": SvgGlyphSpec(
        cache_name="exception_stops",
        body='<path d="M8 2l6.2 11H1.8L8 2z" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 5.4v3.6" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="11.5" r=".8" fill="{color}"/>',
        cached=True,
        two_color=False,
    ),
    "exit_icon": SvgGlyphSpec(
        cache_name="exit",
        body='<path d="M3 2h6v12H3V2z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M8 8h6M11.5 5.5L14 8l-2.5 2.5" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.7" cy="8" r=".6" fill="{color}"/>',
        cached=True,
        two_color=False,
    ),
    "explorer_icon": SvgGlyphSpec(
        cache_name="explorer",
        body='<path d="M2 2h5l1.5 1.5H14v4H2V2z" fill="{color}" fill-opacity="0.15" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M2 7.5h12v5H2z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=False,
        two_color=False,
    ),
    "file_icon": SvgGlyphSpec(
        cache_name="file",
        body='<path d="M3 1h6l4 4v10H3V1z" fill="none" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/><path d="M9 1v4h4" fill="none" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/>',
        cached=False,
        two_color=False,
    ),
    "find_in_files_icon": SvgGlyphSpec(
        cache_name="find_in_files",
        body='<path d="M1.5 4h4L7 5.5h7.5v5h-13V4z" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><circle cx="7" cy="9.5" r="2.2" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M8.7 11.2l2 2" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "find_references_icon": SvgGlyphSpec(
        cache_name="find_references",
        body='<circle cx="4" cy="4" r="2" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1"/><circle cx="12" cy="5" r="2" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1"/><circle cx="7.5" cy="12" r="2" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1"/><path d="M5.9 4.2l4.2.5M5 5.7l1.5 4.5M10.7 6.6L8.8 10.3" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "folder_icon": SvgGlyphSpec(
        cache_name="folder",
        body='<path d="M1 3h5l1.5 1.5H15v9H1V3z" fill="{color}" fill-opacity="0.2" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=False,
        two_color=False,
    ),
    "folder_open_icon": SvgGlyphSpec(
        cache_name="folder_open",
        body='<path d="M1 3h5l1.5 1.5H15v2H3l-2 7V3z" fill="{color}" fill-opacity="0.15" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M1 13l2-7h12l-2 7H1z" fill="{color}" fill-opacity="0.2" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=False,
        two_color=False,
    ),
    "format_icon": SvgGlyphSpec(
        cache_name="format",
        body='<path d="M3 3h10M5 3v10M9 3v10M3.5 13h3M7.5 13h3" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "getting_started_icon": SvgGlyphSpec(
        cache_name="getting_started",
        body='<path d="M3 2.5h4.2c.8 0 1.3.5 1.3 1.3v10c0-.8-.5-1.3-1.3-1.3H3v-10zM8.5 3.8c0-.8.5-1.3 1.3-1.3H14v10H9.8c-.8 0-1.3.5-1.3 1.3" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "go_to_definition_icon": SvgGlyphSpec(
        cache_name="go_to_definition",
        body='<path d="M3 3h5v5H3V3zM8 8h5v5H8V8z" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M6.5 4.5h5v5M9.8 4.5h1.7v1.7" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "go_to_line_icon": SvgGlyphSpec(
        cache_name="go_to_line",
        body='<path d="M5.5 3h8M5.5 8h8M5.5 13h8" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/><path d="M2.3 2.5v3M1.6 2.5h1.4M1.6 5.5h1.8M1.6 10.5h2.2L1.6 13.5h2.3" fill="none" stroke="{color}" stroke-width="1.0" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "headless_notes_icon": SvgGlyphSpec(
        cache_name="headless_notes",
        body='<path d="M3 1.5h6l3.5 3.5v9.5H3v-13z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M9 1.5V5h3.5M5 8h5M5 10.5h5M5 13h3" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "health_check_icon": SvgGlyphSpec(
        cache_name="health_check",
        body='<path d="M2 8h2.5l1.2-3 2.4 6 1.4-3H14" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 2.5c3.5-2.2 7.6 2.8 0 10.5C.4 5.3 4.5.3 8 2.5z" fill="none" stroke="{color}" stroke-width="1.0" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "history_icon": SvgGlyphSpec(
        cache_name="history",
        body='<path d="M2.5 4a6 6 0 1 1-1 4.5" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/><path d="M2.5 1.5v3h3" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 5v3.3l2.2 1.3" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>',
        cached=False,
        two_color=False,
    ),
    "hover_info_icon": SvgGlyphSpec(
        cache_name="hover_info",
        body='<circle cx="8" cy="8" r="6" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.2"/><path d="M8 7.2v4" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="4.8" r=".8" fill="{color}"/>',
        cached=True,
        two_color=False,
    ),
    "indent_icon": SvgGlyphSpec(
        cache_name="indent",
        body='<path d="M8 3h6M8 8h6M8 13h6M2 5.5L5 8l-3 2.5V5.5z" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "inspect_token_icon": SvgGlyphSpec(
        cache_name="inspect_token",
        body='<rect x="2" y="3" width="7" height="5" rx="1" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.0"/><circle cx="9" cy="9" r="3" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M11.2 11.2L14 14" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "keyboard_icon": SvgGlyphSpec(
        cache_name="keyboard",
        body='<rect x="1.5" y="4" width="13" height="8" rx="1.4" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M4 6.5h1M7 6.5h1M10 6.5h1M4 9h1M7 9h1M10 9h2" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "language_mode_icon": SvgGlyphSpec(
        cache_name="language_mode",
        body='<path d="M6 3H5c-1 0-1.5.5-1.5 1.5V6c0 1-.6 1.5-1.5 1.5C2.9 7.5 3.5 8 3.5 9v1.5C3.5 11.5 4 12 5 12h1M10 3h1c1 0 1.5.5 1.5 1.5V6c0 1 .6 1.5 1.5 1.5-.9 0-1.5.5-1.5 1.5v1.5c0 1-.5 1.5-1.5 1.5h-1" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "lint_icon": SvgGlyphSpec(
        cache_name="lint",
        body='<path d="M3 4l1.4 1.4L7 3M3 9l1.4 1.4L7 8M9 4.5h4M9 9.5h4M3 13h10" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "markdown_preview_icon": SvgGlyphSpec(
        cache_name="markdown_preview",
        body='<path d="M1.8 8s2.2-4 6.2-4 6.2 4 6.2 4-2.2 4-6.2 4-6.2-4-6.2-4z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><circle cx="8" cy="8" r="2" fill="none" stroke="{color}" stroke-width="1.1"/>',
        cached=True,
        two_color=False,
    ),
    "markdown_source_icon": SvgGlyphSpec(
        cache_name="markdown_source",
        body='<rect x="2" y="3" width="12" height="10" rx="1.3" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M4 10V6l2 2 2-2v4M10 6v4M12 6v4" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "markdown_split_icon": SvgGlyphSpec(
        cache_name="markdown_split",
        body='<rect x="2" y="3" width="12" height="10" rx="1.2" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M8 3v10M4 9V6l1.3 1.4L6.6 6v3M10 6.5h2M10 9h1.5" fill="none" stroke="{color}" stroke-width="1.0" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "new_file_icon": SvgGlyphSpec(
        cache_name="new_file",
        body='<path d="M2 1h5.5l3.5 3.5V11H2V1z" fill="none" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M7.5 1v3.5H11" fill="none" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><line x1="12" y1="11" x2="12" y2="16" stroke="{badge_color}" stroke-width="1.6" stroke-linecap="round"/><line x1="9.5" y1="13.5" x2="14.5" y2="13.5" stroke="{badge_color}" stroke-width="1.6" stroke-linecap="round"/>',
        cached=False,
        two_color=True,
    ),
    "new_folder_icon": SvgGlyphSpec(
        cache_name="new_folder",
        body='<path d="M1 3h4.5L7 4.5H11v5H1V3z" fill="{color}" fill-opacity="0.2" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><line x1="13.5" y1="8.5" x2="13.5" y2="14" stroke="{badge_color}" stroke-width="1.6" stroke-linecap="round"/><line x1="11" y1="11.25" x2="16" y2="11.25" stroke="{badge_color}" stroke-width="1.6" stroke-linecap="round"/>',
        cached=False,
        two_color=True,
    ),
    "new_window_icon": SvgGlyphSpec(
        cache_name="new_window",
        body='<rect x="2" y="3" width="10" height="9" rx="1.3" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M2 5.5h10" stroke="{color}" stroke-width="1.1"/><path d="M13.5 9.5v5M11 12h5" stroke="{badge_color}" stroke-width="1.5" stroke-linecap="round"/>',
        cached=True,
        two_color=True,
    ),
    "onboarding_icon": SvgGlyphSpec(
        cache_name="onboarding",
        body='<circle cx="8" cy="8" r="6" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.2"/><path d="M10.5 5.5L9 9l-3.5 1.5L7 7l3.5-1.5z" fill="none" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "organize_imports_icon": SvgGlyphSpec(
        cache_name="organize_imports",
        body='<path d="M4 4h8M4 8h6M4 12h4M12 7l2 2-2 2M10 9h4" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "outdent_icon": SvgGlyphSpec(
        cache_name="outdent",
        body='<path d="M8 3h6M8 8h6M8 13h6M5 5.5L2 8l3 2.5V5.5z" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "paste_icon": SvgGlyphSpec(
        cache_name="paste",
        body='<path d="M4 4h8v10H4V4z" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M6 2.5h4v3H6v-3z" fill="{color}" fill-opacity="0.16" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M6 8h4M6 10.5h3" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "paste_reindent_icon": SvgGlyphSpec(
        cache_name="paste_reindent",
        body='<path d="M3.5 4h8v10h-8V4z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M5.5 2.5h4v3h-4v-3zM6 8h4M7.5 10.5H10M6 13h4" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "plugin_icon": SvgGlyphSpec(
        cache_name="plugin",
        body='<path d="M3 3.5h3a2 2 0 1 1 4 0h3v3a2 2 0 1 0 0 4v2.5H3v-3a2 2 0 1 0 0-4V3.5z" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "project_icon": SvgGlyphSpec(
        cache_name="project",
        body='<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M6.2 8L4.8 9.4l1.4 1.4M9.8 8l1.4 1.4-1.4 1.4" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "project_new_icon": SvgGlyphSpec(
        cache_name="project_new",
        body='<path d="M1.5 4h4L7 5.5h6v5h-11.5V4z" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M13.2 9.8v4.8M10.8 12.2h4.8" stroke="{badge_color}" stroke-width="1.5" stroke-linecap="round"/>',
        cached=True,
        two_color=True,
    ),
    "python_console_icon": SvgGlyphSpec(
        cache_name="python_console",
        body='<rect x="2" y="3" width="12" height="10" rx="1.4" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M4.2 6l2 2-2 2M7.8 10h3.5" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "rebuild_cache_icon": SvgGlyphSpec(
        cache_name="rebuild_cache",
        body='<ellipse cx="8" cy="4" rx="5" ry="2" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M3 4v4c0 1.1 2.2 2 5 2s5-.9 5-2V4" fill="none" stroke="{color}" stroke-width="1.1"/><path d="M12 10a3 3 0 1 1-1.1-2.3" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/><path d="M10.5 6.6l.5 1.6-1.6.5" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "redo_icon": SvgGlyphSpec(
        cache_name="redo",
        body='<path d="M10 4h3.2V.8M13 4.2a6 6 0 1 0-.7 7.6" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "refresh_icon": SvgGlyphSpec(
        cache_name="refresh",
        body='<path d="M13 3a6 6 0 1 0 1.4 6" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/><path d="M11 1l2.2 2.2L11 5.2" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=False,
        two_color=False,
    ),
    "rename_icon": SvgGlyphSpec(
        cache_name="rename",
        body='<path d="M3 11.5L11.5 3l1.5 1.5L4.5 13H3v-1.5z" fill="none" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/><path d="M10.5 4l1.5 1.5" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "replace_icon": SvgGlyphSpec(
        cache_name="replace",
        body='<path d="M3 4h8M9 2l2 2-2 2M13 12H5M7 10l-2 2 2 2" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="3" cy="12" r="1.1" fill="{color}"/>',
        cached=True,
        two_color=False,
    ),
    "reset_layout_icon": SvgGlyphSpec(
        cache_name="reset_layout",
        body='<rect x="2" y="3" width="12" height="10" rx="1.2" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M6 3v10M2 7h12M11.5 1.8l2 2-2 2" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "reveal_icon": SvgGlyphSpec(
        cache_name="reveal",
        body='<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M7 9h5M10 6.8L12.2 9 10 11.2" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "run_args_icon": SvgGlyphSpec(
        cache_name="run_args",
        body='<path d="M3 4l3 4-3 4M7 12h6" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10" cy="5" r="1" fill="{color}"/><circle cx="13" cy="5" r="1" fill="{color}"/>',
        cached=True,
        two_color=False,
    ),
    "run_config_icon": SvgGlyphSpec(
        cache_name="run_config",
        body='<path d="M3 4h10M3 8h10M3 12h10" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/><circle cx="6" cy="4" r="1.5" fill="{color}"/><circle cx="10" cy="8" r="1.5" fill="{color}"/><circle cx="5" cy="12" r="1.5" fill="{color}"/>',
        cached=True,
        two_color=False,
    ),
    "runtime_center_icon": SvgGlyphSpec(
        cache_name="runtime_center",
        body='<path d="M2.5 10a5.5 5.5 0 1 1 11 0" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/><path d="M8 10l3-3" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/><path d="M4 13h8" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "runtime_modules_icon": SvgGlyphSpec(
        cache_name="runtime_modules",
        body='<path d="M3 5l5-3 5 3v6l-5 3-5-3V5z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M11 7a3.3 3.3 0 1 1-1.2-2.5M9.6 3.2l.4 1.8-1.8.4" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "safe_fix_icon": SvgGlyphSpec(
        cache_name="safe_fix",
        body='<path d="M8 2l5 2v3.8c0 3-2 5.1-5 6.2-3-1.1-5-3.2-5-6.2V4l5-2z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M6.2 9.2l3.6-3.6 1.1 1.1-3.6 3.6H6.2V9.2z" fill="none" stroke="{badge_color}" stroke-width="1.0" stroke-linejoin="round"/>',
        cached=True,
        two_color=True,
    ),
    "save_all_icon": SvgGlyphSpec(
        cache_name="save_all",
        body='<path d="M4 2h7.5L13.5 4v8.5H4V2z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M2.5 5v9h8" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 2v3h4V2M6 9h4" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "save_as_icon": SvgGlyphSpec(
        cache_name="save_as",
        body='<path d="M2.5 2h8l2 2v8h-10V2z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M5 2v3.5h5V2M5 9.5h3" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/><path d="M10.5 13.2l2.9-2.9 1.2 1.2-2.9 2.9H10.5v-1.2z" fill="none" stroke="{badge_color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=True,
        two_color=True,
    ),
    "save_icon": SvgGlyphSpec(
        cache_name="save",
        body='<path d="M2.5 2h9l2 2v10h-11V2z" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/><path d="M5 2v4h6V2M5 11h6" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "search_icon": SvgGlyphSpec(
        cache_name="search",
        body='<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.4"/><line x1="10.5" y1="10.5" x2="14" y2="14" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>',
        cached=False,
        two_color=False,
    ),
    "settings_icon": SvgGlyphSpec(
        cache_name="settings",
        body='<circle cx="8" cy="8" r="2.2" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M8 1.8v2M8 12.2v2M3.6 3.6L5 5M11 11l1.4 1.4M1.8 8h2M12.2 8h2M3.6 12.4L5 11M11 5l1.4-1.4" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "signature_help_icon": SvgGlyphSpec(
        cache_name="signature_help",
        body='<path d="M3 12c1.2 0 1.2-8 2.6-8 .8 0 1.1 1.1 1.1 2.2M2.5 8h4" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/><path d="M9.5 5.5c1 .9 1.5 1.7 1.5 2.5s-.5 1.6-1.5 2.5M13 5.5c-1 .9-1.5 1.7-1.5 2.5S12 9.6 13 10.5" fill="none" stroke="{color}" stroke-width="1.1" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "source_root_icon": SvgGlyphSpec(
        cache_name="source_root",
        body='<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M8 8.5h4M10 6.5v4" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "source_root_unmark_icon": SvgGlyphSpec(
        cache_name="source_root_unmark",
        body='<path d="M1.5 4h4L7 5.5h7.5v7h-13V4z" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M8 8.5h4" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "support_bundle_icon": SvgGlyphSpec(
        cache_name="support_bundle",
        body='<path d="M3 3h10v10H3V3z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M3 6h10M6 3v10M8 4.5h1.5M8 7h1.5M8 9.5h1.5" fill="none" stroke="{color}" stroke-width="1.0" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "symbol_icon": SvgGlyphSpec(
        cache_name="symbol",
        body='<path d="M4 3h8v3H4V3zM2.5 9h5v4h-5V9zM9.5 9h4v4h-4V9z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "template_icon": SvgGlyphSpec(
        cache_name="template",
        body='<path d="M3 1.5h6l3.5 3.5v9.5H3v-13z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M9 1.5V5h3.5" fill="none" stroke="{color}" stroke-width="1.1"/><path d="M7.5 6.2l.7 1.6 1.6.7-1.6.7-.7 1.6-.7-1.6-1.6-.7 1.6-.7.7-1.6z" fill="none" stroke="{badge_color}" stroke-width="1.0" stroke-linejoin="round"/>',
        cached=True,
        two_color=True,
    ),
    "theme_dark_icon": SvgGlyphSpec(
        cache_name="theme_dark",
        body='<path d="M11.8 10.8A5.8 5.8 0 0 1 5.2 3a5.8 5.8 0 1 0 6.6 7.8z" fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "theme_high_contrast_dark_icon": SvgGlyphSpec(
        cache_name="theme_high_contrast_dark",
        body='<circle cx="8" cy="8" r="5.5" fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-width="1.3"/><path d="M8 2.5a5.5 5.5 0 0 0 0 11V2.5z" fill="none" stroke="{color}" stroke-width="1.2"/>',
        cached=True,
        two_color=False,
    ),
    "theme_high_contrast_light_icon": SvgGlyphSpec(
        cache_name="theme_high_contrast_light",
        body='<circle cx="8" cy="8" r="5.5" fill="none" stroke="{color}" stroke-width="1.3"/><path d="M8 2.5a5.5 5.5 0 0 1 0 11V2.5z" fill="{color}" fill-opacity="0.16"/><path d="M4.5 8h7" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "theme_light_icon": SvgGlyphSpec(
        cache_name="theme_light",
        body='<circle cx="8" cy="8" r="2.7" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "theme_system_icon": SvgGlyphSpec(
        cache_name="theme_system",
        body='<rect x="2" y="3" width="12" height="8" rx="1.3" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1"/><path d="M6 14h4M8 11v3" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "toggle_comment_icon": SvgGlyphSpec(
        cache_name="toggle_comment",
        body='<path d="M2.5 3h11v7.5h-5L5 13v-2.5H2.5V3z" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.1" stroke-linejoin="round"/><path d="M10.8 4.5L5.2 9.8" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "trash_icon": SvgGlyphSpec(
        cache_name="trash",
        body='<path d="M3.5 5h9l-.7 9H4.2L3.5 5z" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/><path d="M2.5 5h11M6 3h4M6.5 7v5M9.5 7v5" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "undo_icon": SvgGlyphSpec(
        cache_name="undo",
        body='<path d="M6 4H2.8V.8M3 4.2a6 6 0 1 1 .7 7.6" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
    "zoom_in_icon": SvgGlyphSpec(
        cache_name="zoom_in",
        body='<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.3"/><path d="M7 4.8v4.4M4.8 7h4.4M10.5 10.5L14 14" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "zoom_out_icon": SvgGlyphSpec(
        cache_name="zoom_out",
        body='<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.3"/><path d="M4.8 7h4.4M10.5 10.5L14 14" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>',
        cached=True,
        two_color=False,
    ),
    "zoom_reset_icon": SvgGlyphSpec(
        cache_name="zoom_reset",
        body='<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.3"/><path d="M5 7h4M10.5 10.5L14 14M12 2.5a3.5 3.5 0 0 1 1 2.5M13 2.5h-2.5V5" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>',
        cached=True,
        two_color=False,
    ),
}

