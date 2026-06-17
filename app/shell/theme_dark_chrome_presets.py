"""Static dark chrome surface and shared token presets."""

from __future__ import annotations

from app.core import constants

# Shared dark chrome tokens (#37 contrast floors). WCAG notes keyed by panel_bg:
#   standard #262C33: text_muted 8.43:1, gutter_text 4.58:1 on panel
#   neutral  #303030: text_muted ~8.2:1, gutter_text ~4.5:1 on panel
DARK_CHROME_SHARED: dict[str, str | bool] = {
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

DARK_CHROME_SURFACES: dict[str, dict[str, str]] = {
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
        "bracket_match_bg": "#5C3D1A",
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
        "bracket_match_bg": "#5C3D1A",
        "activity_bar_bg": "#262626",
        "input_bg": "#282828",
        "badge_bg": "#3A3A3A",
        "popup_bg": "#303030",
        "popup_border": "#454545",
    },
}
