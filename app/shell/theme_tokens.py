"""Theme token derivation utilities for shell styling."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from PySide2.QtGui import QColor, QPalette

from app.core import constants
from app.editors.syntax_engine import (
    DEFAULT_DARK_PALETTE,
    DEFAULT_HC_DARK_PALETTE,
    DEFAULT_HC_LIGHT_PALETTE,
    DEFAULT_LIGHT_PALETTE,
)
from app.shell.settings_models import resolve_dark_chrome_palette

# Re-export for callers that normalized at the token layer historically.
__all__ = [
    "ShellThemeTokens",
    "apply_syntax_token_overrides",
    "is_high_contrast_mode",
    "resolve_dark_chrome_palette",
    "resolve_ui_font_weight_css",
    "to_qcolor",
    "tokens_from_palette",
]


def is_high_contrast_mode(mode: str) -> bool:
    """Return True for the two High-Contrast theme.mode values."""
    return mode in (
        constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
        constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
    )


_UI_FONT_WEIGHT_CSS_MAP: dict[str, str] = {
    constants.UI_THEME_FONT_WEIGHT_NORMAL: "normal",
    constants.UI_THEME_FONT_WEIGHT_MEDIUM: "500",
    constants.UI_THEME_FONT_WEIGHT_BOLD: "600",
}


def resolve_ui_font_weight_css(ui_font_weight: str) -> str:
    """Translate a persisted ui_font_weight value into a Qt font-weight literal."""
    return _UI_FONT_WEIGHT_CSS_MAP.get(ui_font_weight, _UI_FONT_WEIGHT_CSS_MAP[constants.UI_THEME_FONT_WEIGHT_DEFAULT])


# Shared dark chrome tokens (#37 contrast floors). WCAG notes keyed by panel_bg:
#   standard #262C33: text_muted 8.43:1, gutter_text 4.58:1 on panel
#   neutral  #303030: text_muted ~8.2:1, gutter_text ~4.5:1 on panel
_DARK_CHROME_SHARED: dict[str, str | bool] = {
    "text_primary": "#E9ECEF",
    "text_muted": "#C2C9D1",
    "accent": "#5B8CFF",
    "gutter_text": "#8B949E",
    "icon_primary": "#CED4DA",
    "icon_muted": "#5B8CFF",
    "debug_paused_color": "#E5A100",
    "debug_running_color": "#3FB950",
    "diag_error_color": "#FF6B6B",
    "diag_warning_color": "#E5A100",
    "diag_info_color": "#5B8CFF",
    "test_passed_color": "#3FB950",
    "popup_shadow": "#000000",
    "is_dark": True,
}

_DARK_CHROME_SURFACES: dict[str, dict[str, str]] = {
    constants.UI_THEME_DARK_CHROME_PALETTE_STANDARD: {
        "window_bg": "#1F2428",
        "panel_bg": "#262C33",
        "editor_bg": "#1B1F23",
        "border": "#3C434A",
        "gutter_bg": "#1F2428",
        "line_highlight": "#252B33",
        "tree_hover_bg": "#2A3038",
        "tree_selected_bg": "#2D3A4A",
        "debug_current_frame_bg": "#2D3A4A",
        "row_alt_bg": "#1E2329",
        "search_match_bg": "#3A3D41",
        "search_current_match_bg": "#515C6A",
        "activity_bar_bg": "#1A1E22",
        "input_bg": "#1B1F23",
        "badge_bg": "#3C434A",
        "popup_bg": "#262C33",
        "popup_border": "#3C434A",
    },
    constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY: {
        "window_bg": "#2B2B2B",
        "panel_bg": "#303030",
        "editor_bg": "#282828",
        "border": "#454545",
        "gutter_bg": "#2B2B2B",
        "line_highlight": "#333333",
        "tree_hover_bg": "#353535",
        "tree_selected_bg": "#3A3A3A",
        "debug_current_frame_bg": "#3A3A3A",
        "row_alt_bg": "#2A2A2A",
        "search_match_bg": "#404040",
        "search_current_match_bg": "#4A4A4A",
        "activity_bar_bg": "#262626",
        "input_bg": "#282828",
        "badge_bg": "#3A3A3A",
        "popup_bg": "#303030",
        "popup_border": "#454545",
    },
}

_TOOLBAR_PRESETS: dict[str, dict[str, str]] = {
    "light": {
        "toolbar_run_bg": "#E6F4EA",
        "toolbar_run_hover_bg": "#D1EDDA",
        "toolbar_run_pressed_bg": "#B7DFC6",
        "toolbar_run_fg": "#15803D",
        "toolbar_stop_bg": "#FEE2E2",
        "toolbar_stop_hover_bg": "#FECACA",
        "toolbar_stop_pressed_bg": "#FCA5A5",
        "toolbar_stop_fg": "#B91C1C",
        "toolbar_debug_bg": "#FEF3C7",
        "toolbar_debug_hover_bg": "#FDE68A",
        "toolbar_debug_pressed_bg": "#FCD34D",
        "toolbar_debug_fg": "#B45309",
        "toolbar_package_bg": "#E8EEFF",
        "toolbar_package_hover_bg": "#D6E0FF",
        "toolbar_package_pressed_bg": "#C4D4FF",
        "toolbar_package_fg": "#2952CC",
        "chrome_hover_overlay": "rgba(0, 0, 0, 0.08)",
    },
    "dark": {
        "toolbar_run_bg": "#1B3D1B",
        "toolbar_run_hover_bg": "#22502A",
        "toolbar_run_pressed_bg": "#2A6434",
        "toolbar_run_fg": "#4ADE80",
        "toolbar_stop_bg": "#3D1B1B",
        "toolbar_stop_hover_bg": "#502222",
        "toolbar_stop_pressed_bg": "#642A2A",
        "toolbar_stop_fg": "#F87171",
        "toolbar_debug_bg": "#3D2E0A",
        "toolbar_debug_hover_bg": "#50400E",
        "toolbar_debug_pressed_bg": "#645214",
        "toolbar_debug_fg": "#FBBF24",
        "toolbar_package_bg": "#1B2A4A",
        "toolbar_package_hover_bg": "#243758",
        "toolbar_package_pressed_bg": "#2E4468",
        "toolbar_package_fg": "#7EA8FF",
        "chrome_hover_overlay": "rgba(255, 255, 255, 0.1)",
    },
    "hc_light": {
        "toolbar_run_bg": "#E6FFE6",
        "toolbar_run_hover_bg": "#CCFFCC",
        "toolbar_run_pressed_bg": "#B3FFB3",
        "toolbar_run_fg": "#005000",
        "toolbar_stop_bg": "#FFE6E6",
        "toolbar_stop_hover_bg": "#FFCCCC",
        "toolbar_stop_pressed_bg": "#FFB3B3",
        "toolbar_stop_fg": "#9C0000",
        "toolbar_debug_bg": "#FFF8E6",
        "toolbar_debug_hover_bg": "#FFEFCC",
        "toolbar_debug_pressed_bg": "#FFE6B3",
        "toolbar_debug_fg": "#7A4500",
        "toolbar_package_bg": "#E6E6FF",
        "toolbar_package_hover_bg": "#CCCCFF",
        "toolbar_package_pressed_bg": "#B3B3FF",
        "toolbar_package_fg": "#0000C0",
        "chrome_hover_overlay": "rgba(0, 0, 0, 0.12)",
    },
    "hc_dark": {
        "toolbar_run_bg": "#0A2A0A",
        "toolbar_run_hover_bg": "#0F3A0F",
        "toolbar_run_pressed_bg": "#144A14",
        "toolbar_run_fg": "#7FCB66",
        "toolbar_stop_bg": "#2A0A0A",
        "toolbar_stop_hover_bg": "#3A0F0F",
        "toolbar_stop_pressed_bg": "#4A1414",
        "toolbar_stop_fg": "#FF8080",
        "toolbar_debug_bg": "#2A2000",
        "toolbar_debug_hover_bg": "#3A2A00",
        "toolbar_debug_pressed_bg": "#4A3400",
        "toolbar_debug_fg": "#FFD700",
        "toolbar_package_bg": "#0A0A2A",
        "toolbar_package_hover_bg": "#0F0F3A",
        "toolbar_package_pressed_bg": "#14144A",
        "toolbar_package_fg": "#7CB7FF",
        "chrome_hover_overlay": "rgba(255, 255, 255, 0.15)",
    },
}


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
    toolbar_run_bg: str = ""
    toolbar_run_hover_bg: str = ""
    toolbar_run_pressed_bg: str = ""
    toolbar_run_fg: str = ""
    toolbar_stop_bg: str = ""
    toolbar_stop_hover_bg: str = ""
    toolbar_stop_pressed_bg: str = ""
    toolbar_stop_fg: str = ""
    toolbar_debug_bg: str = ""
    toolbar_debug_hover_bg: str = ""
    toolbar_debug_pressed_bg: str = ""
    toolbar_debug_fg: str = ""
    toolbar_package_bg: str = ""
    toolbar_package_hover_bg: str = ""
    toolbar_package_pressed_bg: str = ""
    toolbar_package_fg: str = ""
    chrome_hover_overlay: str = ""
    syntax_keyword: str = ""
    syntax_keyword_control: str = ""
    syntax_keyword_import: str = ""
    syntax_keyword_operator: str = ""
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
    popup_bg: str = ""
    popup_border: str = ""
    popup_shadow: str = ""
    ui_font_weight_css: str = "normal"
    is_high_contrast: bool = False
    focus_border_width: int = 1


def _shell_theme_tokens_dark(
    dark_chrome_palette: str,
    *,
    syntax_kwargs: dict[str, Any],
    ui_font_weight_css: str,
) -> ShellThemeTokens:
    surfaces = _DARK_CHROME_SURFACES.get(
        dark_chrome_palette,
        _DARK_CHROME_SURFACES[constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT],
    )
    shared = {key: value for key, value in _DARK_CHROME_SHARED.items() if key != "is_dark"}
    return ShellThemeTokens(
        **surfaces,
        **shared,
        is_dark=True,
        ui_font_weight_css=ui_font_weight_css,
        **_TOOLBAR_PRESETS["dark"],
        **syntax_kwargs,
    )


def tokens_from_palette(
    palette: QPalette,
    *,
    prefer_dark: bool = False,
    force_mode: str | None = None,
    ui_font_weight: str = constants.UI_THEME_FONT_WEIGHT_DEFAULT,
    dark_chrome_palette: str = constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT,
) -> ShellThemeTokens:
    """Derive theme tokens.

    ``dark_chrome_palette`` must already be normalized at the settings boundary.
    """
    is_high_contrast = is_high_contrast_mode(force_mode or "")
    if force_mode == constants.UI_THEME_MODE_HIGH_CONTRAST_DARK:
        is_dark = True
    elif force_mode == constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT:
        is_dark = False
    elif force_mode == "dark":
        is_dark = True
    elif force_mode == "light":
        is_dark = False
    else:
        window_color = palette.color(QPalette.Window)
        is_dark = prefer_dark or window_color.lightness() < 128
    if is_high_contrast:
        sp = DEFAULT_HC_DARK_PALETTE if is_dark else DEFAULT_HC_LIGHT_PALETTE
    else:
        sp = DEFAULT_DARK_PALETTE if is_dark else DEFAULT_LIGHT_PALETTE
    syntax_kwargs: dict[str, Any] = {
        field_name: sp[token_key]
        for token_key, field_name in _SYNTAX_OVERRIDE_FIELD_MAP.items()
        if token_key in sp
    }
    ui_font_weight_css = resolve_ui_font_weight_css(ui_font_weight)
    if is_high_contrast and is_dark:
        return ShellThemeTokens(
            window_bg="#000000",
            panel_bg="#000000",
            editor_bg="#000000",
            text_primary="#FFFFFF",
            text_muted="#E0E0E0",
            border="#FFFFFF",
            accent="#7CB7FF",
            gutter_bg="#000000",
            gutter_text="#D0D0D0",
            line_highlight="#1F1F1F",
            is_dark=True,
            tree_hover_bg="#1F1F1F",
            tree_selected_bg="#0A4D8C",
            icon_primary="#FFFFFF",
            icon_muted="#7CB7FF",
            debug_paused_color="#FFD700",
            debug_running_color="#7FCB66",
            debug_current_frame_bg="#0A4D8C",
            row_alt_bg="#0A0A0A",
            search_match_bg="#5A5A00",
            search_current_match_bg="#A06000",
            activity_bar_bg="#000000",
            input_bg="#000000",
            badge_bg="#1F1F1F",
            diag_error_color="#FF8080",
            diag_warning_color="#FFD700",
            diag_info_color="#7CB7FF",
            test_passed_color="#7FCB66",
            popup_bg="#000000",
            popup_border="#FFFFFF",
            popup_shadow="#000000",
            ui_font_weight_css=ui_font_weight_css,
            is_high_contrast=True,
            focus_border_width=2,
            **_TOOLBAR_PRESETS["hc_dark"],
            **syntax_kwargs,
        )
    if is_high_contrast and not is_dark:
        return ShellThemeTokens(
            window_bg="#FFFFFF",
            panel_bg="#FFFFFF",
            editor_bg="#FFFFFF",
            text_primary="#000000",
            text_muted="#1F1F1F",
            border="#000000",
            accent="#0000C0",
            gutter_bg="#FFFFFF",
            gutter_text="#2A2A2A",
            line_highlight="#E6F0FF",
            is_dark=False,
            tree_hover_bg="#E6E6E6",
            tree_selected_bg="#B8D7FF",
            icon_primary="#000000",
            icon_muted="#0000C0",
            debug_paused_color="#7A4500",
            debug_running_color="#005000",
            debug_current_frame_bg="#B8D7FF",
            row_alt_bg="#F2F2F2",
            search_match_bg="#FFE066",
            search_current_match_bg="#D17500",
            activity_bar_bg="#FFFFFF",
            input_bg="#FFFFFF",
            badge_bg="#E6E6E6",
            diag_error_color="#9C0000",
            diag_warning_color="#7A4500",
            diag_info_color="#0000C0",
            test_passed_color="#005000",
            popup_bg="#FFFFFF",
            popup_border="#000000",
            popup_shadow="#000000",
            ui_font_weight_css=ui_font_weight_css,
            is_high_contrast=True,
            focus_border_width=2,
            **_TOOLBAR_PRESETS["hc_light"],
            **syntax_kwargs,
        )
    if is_dark:
        return _shell_theme_tokens_dark(
            dark_chrome_palette,
            syntax_kwargs=syntax_kwargs,
            ui_font_weight_css=ui_font_weight_css,
        )
    return ShellThemeTokens(
        window_bg="#F8F9FA",
        panel_bg="#FFFFFF",
        editor_bg="#FFFFFF",
        text_primary="#212529",
        text_muted="#5A6168",
        border="#DEE2E6",
        accent="#3366FF",
        gutter_bg="#F1F3F5",
        gutter_text="#666F76",
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
        popup_bg="#FFFFFF",
        popup_border="#DEE2E6",
        popup_shadow="#000000",
        ui_font_weight_css=ui_font_weight_css,
        **_TOOLBAR_PRESETS["light"],
        **syntax_kwargs,
    )


def to_qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)


_SYNTAX_OVERRIDE_FIELD_MAP: dict[str, str] = {
    "keyword": "syntax_keyword",
    "keyword_control": "syntax_keyword_control",
    "keyword_import": "syntax_keyword_import",
    "keyword_operator": "syntax_keyword_operator",
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

_DARK_SHARED_FIELD_NAMES = (
    "text_primary",
    "text_muted",
    "accent",
    "gutter_text",
    "icon_primary",
    "icon_muted",
    "debug_paused_color",
    "debug_running_color",
    "diag_error_color",
    "diag_warning_color",
    "diag_info_color",
    "test_passed_color",
    "popup_shadow",
)


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
