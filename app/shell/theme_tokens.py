"""Theme token derivation utilities for shell styling."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from PySide2.QtGui import QColor, QPalette

from app.editors.syntax_engine import DEFAULT_DARK_PALETTE, DEFAULT_LIGHT_PALETTE


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
    test_passed_color: str = ""
    syntax_keyword: str = ""
    syntax_keyword_control: str = ""
    syntax_keyword_import: str = ""
    syntax_builtin: str = ""
    syntax_escape: str = ""
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
    syntax_markdown_strong: str = ""
    syntax_markdown_code: str = ""
    syntax_semantic_function: str = ""
    syntax_semantic_method: str = ""
    syntax_semantic_class: str = ""
    syntax_semantic_parameter: str = ""
    syntax_semantic_import: str = ""
    syntax_semantic_variable: str = ""
    syntax_semantic_property: str = ""
    syntax_semantic_constant: str = ""
    tab_close_icon_path: str = ""
    tab_close_icon_hover_path: str = ""


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
    sp = DEFAULT_DARK_PALETTE if is_dark else DEFAULT_LIGHT_PALETTE
    syntax_kwargs = {
        field_name: sp[token_key]
        for token_key, field_name in _SYNTAX_OVERRIDE_FIELD_MAP.items()
        if token_key in sp
    }
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
            test_passed_color="#3FB950",
            **syntax_kwargs,
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
        test_passed_color="#1A7F37",
        **syntax_kwargs,
    )


def to_qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)


_SYNTAX_OVERRIDE_FIELD_MAP: dict[str, str] = {
    "keyword": "syntax_keyword",
    "keyword_control": "syntax_keyword_control",
    "keyword_import": "syntax_keyword_import",
    "builtin": "syntax_builtin",
    "escape": "syntax_escape",
    "string": "syntax_string",
    "comment": "syntax_comment",
    "number": "syntax_number",
    "function": "syntax_function",
    "class": "syntax_class",
    "decorator": "syntax_decorator",
    "operator": "syntax_operator",
    "punctuation": "syntax_punctuation",
    "parameter": "syntax_parameter",
    "json_key": "syntax_json_key",
    "json_literal": "syntax_json_literal",
    "markdown_heading": "syntax_markdown_heading",
    "markdown_emphasis": "syntax_markdown_emphasis",
    "markdown_strong": "syntax_markdown_strong",
    "markdown_code": "syntax_markdown_code",
    "semantic_function": "syntax_semantic_function",
    "semantic_method": "syntax_semantic_method",
    "semantic_class": "syntax_semantic_class",
    "semantic_parameter": "syntax_semantic_parameter",
    "semantic_import": "syntax_semantic_import",
    "semantic_variable": "syntax_semantic_variable",
    "semantic_property": "syntax_semantic_property",
    "semantic_constant": "syntax_semantic_constant",
}


def apply_syntax_token_overrides(tokens: ShellThemeTokens, overrides: Mapping[str, str]) -> ShellThemeTokens:
    """Return tokens with syntax color overrides applied."""
    updates: dict[str, str] = {}
    for token_key, color_value in overrides.items():
        field_name = _SYNTAX_OVERRIDE_FIELD_MAP.get(token_key)
        if field_name is None:
            continue
        updates[field_name] = color_value
    if not updates:
        return tokens
    return replace(tokens, **updates)
