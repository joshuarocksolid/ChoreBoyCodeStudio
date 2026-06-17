"""Inline SVG icon factory for shell UI elements.

Generates QIcon objects from parameterized SVG templates so the shell
can produce theme-colored icons without external asset files.
"""

from __future__ import annotations

from PySide2.QtGui import QIcon

from app.shell.file_type_icons import build_file_type_icon_map, build_filename_icon_map
from app.shell.icons.render import clear_icon_caches, render_glyph_icon
from app.shell.icons.svg_registry import SVG_GLYPHS


__all__ = [
    "clear_icon_caches",
    "about_icon",
    "add_dependency_icon",
    "analyze_imports_icon",
    "app_log_icon",
    "auto_save_icon",
    "breakpoint_icon",
    "clear_console_icon",
    "clear_override_icon",
    "copy_icon",
    "copy_path_icon",
    "cut_icon",
    "dependency_icon",
    "duplicate_icon",
    "example_project_icon",
    "exception_stops_icon",
    "exit_icon",
    "explorer_icon",
    "file_icon",
    "find_in_files_icon",
    "find_references_icon",
    "folder_icon",
    "folder_open_icon",
    "format_icon",
    "getting_started_icon",
    "go_to_definition_icon",
    "go_to_line_icon",
    "headless_notes_icon",
    "health_check_icon",
    "history_icon",
    "hover_info_icon",
    "indent_icon",
    "inspect_token_icon",
    "keyboard_icon",
    "language_mode_icon",
    "lint_icon",
    "markdown_preview_icon",
    "markdown_source_icon",
    "markdown_split_icon",
    "new_file_icon",
    "new_folder_icon",
    "new_window_icon",
    "onboarding_icon",
    "organize_imports_icon",
    "outdent_icon",
    "paste_icon",
    "paste_reindent_icon",
    "plugin_icon",
    "project_icon",
    "project_new_icon",
    "python_console_icon",
    "rebuild_cache_icon",
    "redo_icon",
    "refresh_icon",
    "rename_icon",
    "replace_icon",
    "reset_layout_icon",
    "reveal_icon",
    "run_args_icon",
    "run_config_icon",
    "runtime_center_icon",
    "runtime_modules_icon",
    "safe_fix_icon",
    "save_all_icon",
    "save_as_icon",
    "save_icon",
    "search_icon",
    "settings_icon",
    "signature_help_icon",
    "source_root_icon",
    "source_root_unmark_icon",
    "support_bundle_icon",
    "symbol_icon",
    "template_icon",
    "theme_dark_icon",
    "theme_high_contrast_dark_icon",
    "theme_high_contrast_light_icon",
    "theme_light_icon",
    "theme_system_icon",
    "toggle_comment_icon",
    "trash_icon",
    "undo_icon",
    "zoom_in_icon",
    "zoom_out_icon",
    "zoom_reset_icon",
    "file_type_icon_map",
    "filename_icon_map",
]


def file_type_icon_map(primary_color: str = "") -> dict[str, QIcon]:
    """Return extension -> QIcon mapping with distinctive per-type icons.

    Icons use fixed colors per file type (VS Code style) so *primary_color*
    is accepted for call-site compatibility but not used.
    """
    return build_file_type_icon_map()


def filename_icon_map() -> dict[str, QIcon]:
    """Return lowercase-filename -> QIcon mapping for special filenames."""
    return build_filename_icon_map()


def about_icon(color: str) -> QIcon:
    """Info circle icon for About."""
    return hover_info_icon(color)


def add_dependency_icon(color: str, badge_color: str) -> QIcon:
    """Dependency cube with plus badge."""
    return render_glyph_icon(SVG_GLYPHS["add_dependency_icon"], color, badge_color)


def analyze_imports_icon(color: str) -> QIcon:
    """Import graph analysis icon."""
    return render_glyph_icon(SVG_GLYPHS["analyze_imports_icon"], color)


def app_log_icon(color: str) -> QIcon:
    """Application log document icon."""
    return render_glyph_icon(SVG_GLYPHS["app_log_icon"], color)


def auto_save_icon(color: str, badge_color: str) -> QIcon:
    """Save disk with circular autosave arrows."""
    return render_glyph_icon(SVG_GLYPHS["auto_save_icon"], color, badge_color)


def breakpoint_icon(color: str) -> QIcon:
    """Breakpoint dot icon."""
    return render_glyph_icon(SVG_GLYPHS["breakpoint_icon"], color)


def clear_console_icon(color: str) -> QIcon:
    """Terminal with eraser icon."""
    return render_glyph_icon(SVG_GLYPHS["clear_console_icon"], color)


def clear_override_icon(color: str) -> QIcon:
    """Clear language override icon."""
    return render_glyph_icon(SVG_GLYPHS["clear_override_icon"], color)


def copy_icon(color: str) -> QIcon:
    """Clipboard-copy icon for copy actions."""
    return render_glyph_icon(SVG_GLYPHS["copy_icon"], color)


def copy_path_icon(color: str) -> QIcon:
    """Linked path icon for path-copy actions."""
    return render_glyph_icon(SVG_GLYPHS["copy_path_icon"], color)


def cut_icon(color: str) -> QIcon:
    """Scissors icon for cut actions."""
    return render_glyph_icon(SVG_GLYPHS["cut_icon"], color)


def dependency_icon(color: str) -> QIcon:
    """Package/dependency cube icon."""
    return render_glyph_icon(SVG_GLYPHS["dependency_icon"], color)


def duplicate_icon(color: str) -> QIcon:
    """Overlapping documents icon for duplicate actions."""
    return render_glyph_icon(SVG_GLYPHS["duplicate_icon"], color)


def example_project_icon(color: str) -> QIcon:
    """Example project folder with sparkle."""
    return render_glyph_icon(SVG_GLYPHS["example_project_icon"], color)


def exception_stops_icon(color: str) -> QIcon:
    """Stop-on-exception warning icon."""
    return render_glyph_icon(SVG_GLYPHS["exception_stops_icon"], color)


def exit_icon(color: str) -> QIcon:
    """Door-with-arrow icon for Exit."""
    return render_glyph_icon(SVG_GLYPHS["exit_icon"], color)


def explorer_icon(color: str) -> QIcon:
    """File explorer / tree icon."""
    return render_glyph_icon(SVG_GLYPHS["explorer_icon"], color)


def file_icon(color: str) -> QIcon:
    """Document outline icon for generic files."""
    return render_glyph_icon(SVG_GLYPHS["file_icon"], color)


def find_in_files_icon(color: str) -> QIcon:
    """Folder search icon."""
    return render_glyph_icon(SVG_GLYPHS["find_in_files_icon"], color)


def find_references_icon(color: str) -> QIcon:
    """Connected nodes icon for references."""
    return render_glyph_icon(SVG_GLYPHS["find_references_icon"], color)


def folder_icon(color: str) -> QIcon:
    """Closed folder icon for directories."""
    return render_glyph_icon(SVG_GLYPHS["folder_icon"], color)


def folder_open_icon(color: str) -> QIcon:
    """Open folder icon for expanded directories."""
    return render_glyph_icon(SVG_GLYPHS["folder_open_icon"], color)


def format_icon(color: str) -> QIcon:
    """Format text icon."""
    return render_glyph_icon(SVG_GLYPHS["format_icon"], color)


def getting_started_icon(color: str) -> QIcon:
    """Book icon for getting started."""
    return render_glyph_icon(SVG_GLYPHS["getting_started_icon"], color)


def go_to_definition_icon(color: str) -> QIcon:
    """Jump-to-symbol icon."""
    return render_glyph_icon(SVG_GLYPHS["go_to_definition_icon"], color)


def go_to_line_icon(color: str) -> QIcon:
    """Numbered lines icon."""
    return render_glyph_icon(SVG_GLYPHS["go_to_line_icon"], color)


def headless_notes_icon(color: str) -> QIcon:
    """Headless notes document icon."""
    return render_glyph_icon(SVG_GLYPHS["headless_notes_icon"], color)


def health_check_icon(color: str) -> QIcon:
    """Health check heartbeat icon."""
    return render_glyph_icon(SVG_GLYPHS["health_check_icon"], color)


def history_icon(color: str) -> QIcon:
    """Clock-with-counterclockwise-arrow icon for history/recovery surfaces."""
    return render_glyph_icon(SVG_GLYPHS["history_icon"], color)


def hover_info_icon(color: str) -> QIcon:
    """Information bubble icon."""
    return render_glyph_icon(SVG_GLYPHS["hover_info_icon"], color)


def indent_icon(color: str) -> QIcon:
    """Indent arrow icon."""
    return render_glyph_icon(SVG_GLYPHS["indent_icon"], color)


def inspect_token_icon(color: str) -> QIcon:
    """Magnifier over syntax token icon."""
    return render_glyph_icon(SVG_GLYPHS["inspect_token_icon"], color)


def keyboard_icon(color: str) -> QIcon:
    """Keyboard shortcuts icon."""
    return render_glyph_icon(SVG_GLYPHS["keyboard_icon"], color)


def language_mode_icon(color: str) -> QIcon:
    """Language mode braces icon."""
    return render_glyph_icon(SVG_GLYPHS["language_mode_icon"], color)


def lint_icon(color: str) -> QIcon:
    """Checklist icon for lint."""
    return render_glyph_icon(SVG_GLYPHS["lint_icon"], color)


def markdown_preview_icon(color: str) -> QIcon:
    """Markdown preview eye icon."""
    return render_glyph_icon(SVG_GLYPHS["markdown_preview_icon"], color)


def markdown_source_icon(color: str) -> QIcon:
    """Markdown source icon."""
    return render_glyph_icon(SVG_GLYPHS["markdown_source_icon"], color)


def markdown_split_icon(color: str) -> QIcon:
    """Split source/preview icon."""
    return render_glyph_icon(SVG_GLYPHS["markdown_split_icon"], color)


def new_file_icon(color: str, badge_color: str) -> QIcon:
    """Document with a '+' badge for the new-file action."""
    return render_glyph_icon(SVG_GLYPHS["new_file_icon"], color, badge_color)


def new_folder_icon(color: str, badge_color: str) -> QIcon:
    """Folder with a '+' badge for the new-folder action."""
    return render_glyph_icon(SVG_GLYPHS["new_folder_icon"], color, badge_color)


def new_window_icon(color: str, badge_color: str) -> QIcon:
    """Window with plus badge."""
    return render_glyph_icon(SVG_GLYPHS["new_window_icon"], color, badge_color)


def onboarding_icon(color: str) -> QIcon:
    """Compass icon for onboarding."""
    return render_glyph_icon(SVG_GLYPHS["onboarding_icon"], color)


def organize_imports_icon(color: str) -> QIcon:
    """Sorted import lines icon."""
    return render_glyph_icon(SVG_GLYPHS["organize_imports_icon"], color)


def outdent_icon(color: str) -> QIcon:
    """Outdent arrow icon."""
    return render_glyph_icon(SVG_GLYPHS["outdent_icon"], color)


def paste_icon(color: str) -> QIcon:
    """Clipboard icon for paste actions."""
    return render_glyph_icon(SVG_GLYPHS["paste_icon"], color)


def paste_reindent_icon(color: str) -> QIcon:
    """Clipboard with indent guide icon."""
    return render_glyph_icon(SVG_GLYPHS["paste_reindent_icon"], color)


def plugin_icon(color: str) -> QIcon:
    """Puzzle-piece icon for plugins."""
    return render_glyph_icon(SVG_GLYPHS["plugin_icon"], color)


def project_icon(color: str) -> QIcon:
    """Folder-with-code icon for project actions."""
    return render_glyph_icon(SVG_GLYPHS["project_icon"], color)


def project_new_icon(color: str, badge_color: str) -> QIcon:
    """Project folder with plus badge."""
    return render_glyph_icon(SVG_GLYPHS["project_new_icon"], color, badge_color)


def python_console_icon(color: str) -> QIcon:
    """Terminal prompt icon for the Python console."""
    return render_glyph_icon(SVG_GLYPHS["python_console_icon"], color)


def rebuild_cache_icon(color: str) -> QIcon:
    """Database refresh icon."""
    return render_glyph_icon(SVG_GLYPHS["rebuild_cache_icon"], color)


def redo_icon(color: str) -> QIcon:
    """Redo arrow icon."""
    return render_glyph_icon(SVG_GLYPHS["redo_icon"], color)


def refresh_icon(color: str) -> QIcon:
    """Circular arrow icon for the refresh action."""
    return render_glyph_icon(SVG_GLYPHS["refresh_icon"], color)


def rename_icon(color: str) -> QIcon:
    """Pencil icon for rename actions."""
    return render_glyph_icon(SVG_GLYPHS["rename_icon"], color)


def replace_icon(color: str) -> QIcon:
    """Find/replace arrows around text."""
    return render_glyph_icon(SVG_GLYPHS["replace_icon"], color)


def reset_layout_icon(color: str) -> QIcon:
    """Panel layout reset icon."""
    return render_glyph_icon(SVG_GLYPHS["reset_layout_icon"], color)


def reveal_icon(color: str) -> QIcon:
    """Folder-with-arrow icon for reveal-in-file-manager actions."""
    return render_glyph_icon(SVG_GLYPHS["reveal_icon"], color)


def run_args_icon(color: str) -> QIcon:
    """Command arguments icon."""
    return render_glyph_icon(SVG_GLYPHS["run_args_icon"], color)


def run_config_icon(color: str) -> QIcon:
    """Run configuration sliders icon."""
    return render_glyph_icon(SVG_GLYPHS["run_config_icon"], color)


def runtime_center_icon(color: str) -> QIcon:
    """Runtime center gauge icon."""
    return render_glyph_icon(SVG_GLYPHS["runtime_center_icon"], color)


def runtime_modules_icon(color: str) -> QIcon:
    """Runtime module refresh icon."""
    return render_glyph_icon(SVG_GLYPHS["runtime_modules_icon"], color)


def safe_fix_icon(color: str, badge_color: str) -> QIcon:
    """Shield with wrench icon for safe fixes."""
    return render_glyph_icon(SVG_GLYPHS["safe_fix_icon"], color, badge_color)


def save_all_icon(color: str) -> QIcon:
    """Stacked disks for Save All."""
    return render_glyph_icon(SVG_GLYPHS["save_all_icon"], color)


def save_as_icon(color: str, badge_color: str) -> QIcon:
    """Floppy disk with pencil badge for Save As."""
    return render_glyph_icon(SVG_GLYPHS["save_as_icon"], color, badge_color)


def save_icon(color: str) -> QIcon:
    """Floppy-disk icon for save actions."""
    return render_glyph_icon(SVG_GLYPHS["save_icon"], color)


def search_icon(color: str) -> QIcon:
    """Magnifying glass icon for search actions."""
    return render_glyph_icon(SVG_GLYPHS["search_icon"], color)


def settings_icon(color: str) -> QIcon:
    """Gear icon for settings and configuration actions."""
    return render_glyph_icon(SVG_GLYPHS["settings_icon"], color)


def signature_help_icon(color: str) -> QIcon:
    """Function signature icon."""
    return render_glyph_icon(SVG_GLYPHS["signature_help_icon"], color)


def source_root_icon(color: str) -> QIcon:
    """Folder badge icon for marking a sources root."""
    return render_glyph_icon(SVG_GLYPHS["source_root_icon"], color)


def source_root_unmark_icon(color: str) -> QIcon:
    """Folder badge icon for unmarking a sources root."""
    return render_glyph_icon(SVG_GLYPHS["source_root_unmark_icon"], color)


def support_bundle_icon(color: str) -> QIcon:
    """Support bundle archive icon."""
    return render_glyph_icon(SVG_GLYPHS["support_bundle_icon"], color)


def symbol_icon(color: str) -> QIcon:
    """Go-to-symbol icon."""
    return render_glyph_icon(SVG_GLYPHS["symbol_icon"], color)


def template_icon(color: str, badge_color: str) -> QIcon:
    """Sparkle-on-document icon for project templates."""
    return render_glyph_icon(SVG_GLYPHS["template_icon"], color, badge_color)


def theme_dark_icon(color: str) -> QIcon:
    """Moon icon for dark theme."""
    return render_glyph_icon(SVG_GLYPHS["theme_dark_icon"], color)


def theme_high_contrast_dark_icon(color: str) -> QIcon:
    """High-contrast dark theme icon."""
    return render_glyph_icon(SVG_GLYPHS["theme_high_contrast_dark_icon"], color)


def theme_high_contrast_light_icon(color: str) -> QIcon:
    """High-contrast light theme icon."""
    return render_glyph_icon(SVG_GLYPHS["theme_high_contrast_light_icon"], color)


def theme_light_icon(color: str) -> QIcon:
    """Sun icon for light theme."""
    return render_glyph_icon(SVG_GLYPHS["theme_light_icon"], color)


def theme_system_icon(color: str) -> QIcon:
    """Monitor icon for system theme."""
    return render_glyph_icon(SVG_GLYPHS["theme_system_icon"], color)


def toggle_comment_icon(color: str) -> QIcon:
    """Comment bubble with slash."""
    return render_glyph_icon(SVG_GLYPHS["toggle_comment_icon"], color)


def trash_icon(color: str) -> QIcon:
    """Trash can icon for move-to-trash actions."""
    return render_glyph_icon(SVG_GLYPHS["trash_icon"], color)


def undo_icon(color: str) -> QIcon:
    """Undo arrow icon."""
    return render_glyph_icon(SVG_GLYPHS["undo_icon"], color)


def zoom_in_icon(color: str) -> QIcon:
    """Magnifier plus icon."""
    return render_glyph_icon(SVG_GLYPHS["zoom_in_icon"], color)


def zoom_out_icon(color: str) -> QIcon:
    """Magnifier minus icon."""
    return render_glyph_icon(SVG_GLYPHS["zoom_out_icon"], color)


def zoom_reset_icon(color: str) -> QIcon:
    """Magnifier reset icon."""
    return render_glyph_icon(SVG_GLYPHS["zoom_reset_icon"], color)


