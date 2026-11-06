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
        icon_muted=tokens.icon_muted,
        is_dark=tokens.is_dark,
        is_high_contrast=tokens.is_high_contrast,
        layout=_ink(overlay.layout),
        gap=_ink(overlay.gap),
        syntax_name=tokens.syntax_semantic_variable,
        syntax_number=tokens.syntax_number,
        syntax_string=tokens.syntax_string,
        syntax_operator=tokens.syntax_operator,
        syntax_function=tokens.syntax_function,
        syntax_keyword=tokens.syntax_keyword,
        warning=tokens.diag_warning_color,
        info=tokens.diag_info_color,
    )


def shell_chrome_pairs(tokens: ShellThemeTokens) -> tuple:
    """The Preview child has no shell. These pairs ride on ``Appearance.chrome``."""
    chrome = chrome_for(tokens)
    return (
        ("window", chrome.window),
        ("panel", chrome.panel),
        ("text", chrome.text),
        ("muted", chrome.muted),
        ("faint", chrome.faint),
        ("border", chrome.border),
        ("accent", chrome.accent),
        ("row_hover", chrome.row_hover),
        ("input", chrome.input),
        ("error", chrome.error),
        ("focus_width", str(chrome.focus_width)),
        ("selected", chrome.selected),
        ("glyph", chrome.glyph),
        ("icon_muted", chrome.icon_muted),
        ("is_dark", "1" if chrome.is_dark else "0"),
        ("is_high_contrast", "1" if chrome.is_high_contrast else "0"),
        ("warning", chrome.warning),
        ("info", chrome.info),
    )


def shell_dialog_parts() -> tuple:
    """The host dialog chrome. qtside cannot import ``app.shell``, so callers pass this in."""
    from app.shell.dialog_chrome import (
        FOOTER_ROLE_PRIMARY,
        FOOTER_ROLE_SECONDARY,
        add_footer_button,
        add_footer_stretch,
        build_dialog_chrome,
    )

    return (
        build_dialog_chrome,
        add_footer_button,
        add_footer_stretch,
        FOOTER_ROLE_PRIMARY,
        FOOTER_ROLE_SECONDARY,
    )
