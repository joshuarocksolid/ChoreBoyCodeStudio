from __future__ import annotations

from app.features.form_builder.qtside.theme.chrome import FormChrome, chrome_from_values
from app.shell.theme_tokens import ShellThemeTokens


def chrome_for(tokens: ShellThemeTokens) -> FormChrome:
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
    )
