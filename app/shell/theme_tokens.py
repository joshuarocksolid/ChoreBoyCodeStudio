"""Theme token derivation utilities for shell styling."""

from __future__ import annotations

from dataclasses import dataclass

from PySide2.QtGui import QColor, QPalette


@dataclass(frozen=True)
class ShellThemeTokens:
    window_bg: str
    panel_bg: str
    editor_bg: str
    text_primary: str
    text_muted: str
    border: str
    accent: str
    gutter_bg: str
    gutter_text: str
    line_highlight: str
    is_dark: bool = False
    tree_hover_bg: str = ""
    tree_selected_bg: str = ""
    icon_primary: str = ""
    icon_muted: str = ""
    debug_paused_color: str = ""
    debug_running_color: str = ""
    debug_current_frame_bg: str = ""
    row_alt_bg: str = ""
    search_match_bg: str = ""
    search_current_match_bg: str = ""
    activity_bar_bg: str = ""
    input_bg: str = ""
    badge_bg: str = ""
    diag_error_color: str = ""
    diag_warning_color: str = ""
    diag_info_color: str = ""
    syntax_keyword: str = ""
    syntax_builtin: str = ""
    syntax_string: str = ""
    syntax_comment: str = ""
    syntax_number: str = ""
    syntax_function: str = ""
    syntax_class: str = ""
    syntax_decorator: str = ""
    syntax_operator: str = ""
    syntax_punctuation: str = ""
    syntax_parameter: str = ""
    syntax_json_key: str = ""
    syntax_json_literal: str = ""
    syntax_markdown_heading: str = ""
    syntax_markdown_emphasis: str = ""
    syntax_markdown_code: str = ""
    syntax_semantic_function: str = ""
    syntax_semantic_method: str = ""
    syntax_semantic_class: str = ""
    syntax_semantic_parameter: str = ""
    syntax_semantic_import: str = ""
    syntax_semantic_variable: str = ""
    syntax_semantic_property: str = ""
    syntax_semantic_constant: str = ""


def tokens_from_palette(
    palette: QPalette,
    *,
    prefer_dark: bool = False,
    force_mode: str | None = None,
) -> ShellThemeTokens:
    """Derive theme tokens.

    ``force_mode`` accepts ``"light"``, ``"dark"``, or ``None``.  When set it
    overrides both ``prefer_dark`` and the palette lightness heuristic.
    """
    if force_mode == "dark":
        is_dark = True
    elif force_mode == "light":
        is_dark = False
    else:
        window_color = palette.color(QPalette.Window)
        is_dark = prefer_dark or window_color.lightness() < 128
    if is_dark:
        return ShellThemeTokens(
            window_bg="#1F2428",
            panel_bg="#262C33",
            editor_bg="#1B1F23",
            text_primary="#E9ECEF",
            text_muted="#ADB5BD",
            border="#3C434A",
            accent="#5B8CFF",
            gutter_bg="#1F2428",
            gutter_text="#6C757D",
            line_highlight="#252B33",
            is_dark=True,
            tree_hover_bg="#2A3038",
            tree_selected_bg="#2D3A4A",
            icon_primary="#CED4DA",
            icon_muted="#5B8CFF",
            debug_paused_color="#E5A100",
            debug_running_color="#3FB950",
            debug_current_frame_bg="#2D3A4A",
            row_alt_bg="#1E2329",
            search_match_bg="#3A3D41",
            search_current_match_bg="#515C6A",
            activity_bar_bg="#1A1E22",
            input_bg="#1B1F23",
            badge_bg="#3C434A",
            diag_error_color="#FF6B6B",
            diag_warning_color="#E5A100",
            diag_info_color="#5B8CFF",
            syntax_keyword="#7EA8FF",
            syntax_builtin="#3CC68A",
            syntax_string="#FF8C5A",
            syntax_comment="#8B949E",
            syntax_number="#B18CFF",
            syntax_function="#79C0FF",
            syntax_class="#A5D6FF",
            syntax_decorator="#D2A8FF",
            syntax_operator="#C9D1D9",
            syntax_punctuation="#C9D1D9",
            syntax_parameter="#56D364",
            syntax_json_key="#6CB6FF",
            syntax_json_literal="#56D364",
            syntax_markdown_heading="#3BC9DB",
            syntax_markdown_emphasis="#B197FC",
            syntax_markdown_code="#FF8C5A",
            syntax_semantic_function="#79C0FF",
            syntax_semantic_method="#8CC8FF",
            syntax_semantic_class="#A5D6FF",
            syntax_semantic_parameter="#56D364",
            syntax_semantic_import="#D2A8FF",
            syntax_semantic_variable="#7EE787",
            syntax_semantic_property="#5CC8FF",
            syntax_semantic_constant="#FFD580",
        )
    return ShellThemeTokens(
        window_bg="#F8F9FA",
        panel_bg="#FFFFFF",
        editor_bg="#FFFFFF",
        text_primary="#212529",
        text_muted="#6C757D",
        border="#DEE2E6",
        accent="#3366FF",
        gutter_bg="#F1F3F5",
        gutter_text="#ADB5BD",
        line_highlight="#EEF7FF",
        is_dark=False,
        tree_hover_bg="#E9ECEF",
        tree_selected_bg="#D0E2FF",
        icon_primary="#495057",
        icon_muted="#3366FF",
        debug_paused_color="#D97706",
        debug_running_color="#16A34A",
        debug_current_frame_bg="#D0E2FF",
        row_alt_bg="#F6F8FA",
        search_match_bg="#FFE066",
        search_current_match_bg="#FF922B",
        activity_bar_bg="#E9ECEF",
        input_bg="#FFFFFF",
        badge_bg="#E9ECEF",
        diag_error_color="#E03131",
        diag_warning_color="#D97706",
        diag_info_color="#3366FF",
        syntax_keyword="#5B63FF",
        syntax_builtin="#0C8C64",
        syntax_string="#C73E0A",
        syntax_comment="#6C757D",
        syntax_number="#6741D9",
        syntax_function="#1C7ED6",
        syntax_class="#1864AB",
        syntax_decorator="#9C36B5",
        syntax_operator="#495057",
        syntax_punctuation="#495057",
        syntax_parameter="#2B8A3E",
        syntax_json_key="#1971C2",
        syntax_json_literal="#2B8A3E",
        syntax_markdown_heading="#0B7285",
        syntax_markdown_emphasis="#5F3DC4",
        syntax_markdown_code="#C73E0A",
        syntax_semantic_function="#1C7ED6",
        syntax_semantic_method="#1971C2",
        syntax_semantic_class="#1864AB",
        syntax_semantic_parameter="#2B8A3E",
        syntax_semantic_import="#9C36B5",
        syntax_semantic_variable="#2F9E44",
        syntax_semantic_property="#1A73E8",
        syntax_semantic_constant="#C97A00",
    )


def to_qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)
