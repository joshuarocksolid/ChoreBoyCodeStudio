from __future__ import annotations

from app.features.form_builder.qtside.theme.chrome import FormChrome, chrome_from_values
from app.features.form_builder.qtside.theme.overlay import overlay_palette
from app.shell.theme_tokens import ShellThemeTokens


def _ink(color: str) -> str:
    """``#RRGGBB`` from an overlay ``#RRGGBBAA`` string. ``QColor`` reads eight digits as ``#AARRGGBB``."""
    if color.startswith("#") and len(color) >= 7:
        return color[:7]
    return color


def chrome_for(tokens: ShellThemeTokens) -> FormChrome:
    # The high-contrast overlay inks are tuned for the light form surface; on
    # HC-dark chrome they fall below 3:1, so HC dark keeps the standard inks.
    overlay = overlay_palette(tokens.is_high_contrast and not tokens.is_dark)
    return chrome_from_values(
        window=tokens.window_bg,
        panel=tokens.panel_bg,
        text=tokens.text_primary,
        muted=tokens.text_muted,
        faint=tokens.gutter_text,
        border=tokens.border,
        accent=tokens.accent,
        row_hover=tokens.tree_hover_bg,
        input_bg=tokens.input_bg,
        error=tokens.diag_error_color,
        focus_width=tokens.focus_border_width,
        search_match_bg=tokens.search_match_bg,
        selected=tokens.tree_selected_bg,
        popup=tokens.popup_bg,
        popup_border=tokens.popup_border,
        glyph=tokens.icon_primary,
        is_dark=tokens.is_dark,
        is_high_contrast=tokens.is_high_contrast,
        layout=_ink(overlay.layout),
        gap=_ink(overlay.gap),
    )
