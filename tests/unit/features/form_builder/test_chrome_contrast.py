"""Chrome token pairs meet the contrast targets in every theme."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

import app.features.form_builder.qtside.theme.chrome as chrome  # noqa: E402
from app.core import constants  # noqa: E402
from app.features.form_builder.qtside.theme.chrome import (  # noqa: E402
    PAGE_TITLE_FILL,
    PAGE_TITLE_GLYPH,
    on_accent_for,
)
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_TEXT_PAIRS = ("text_primary", "text_muted", "gutter_text")
_NON_TEXT_PAIRS = ("accent",)


def _channel(value: int) -> float:
    scaled = value / 255.0
    if scaled <= 0.04045:
        return scaled / 12.92
    return ((scaled + 0.055) / 1.055) ** 2.4


def _luminance(color: str) -> float:
    text = color.lstrip("#")
    red = int(text[0:2], 16)
    green = int(text[2:4], 16)
    blue = int(text[4:6], 16)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast(foreground: str, background: str) -> float:
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def test_chrome_text_and_accent_clear_the_contrast_targets(qapp) -> None:  # type: ignore[no-untyped-def]
    modes = (
        "light",
        "dark",
        constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
        constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
    )
    for mode in modes:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        assert isinstance(tokens, ShellThemeTokens)
        text_floor = 7.0 if tokens.is_high_contrast else 4.5
        panel = tokens.panel_bg
        for name in _TEXT_PAIRS:
            ratio = _contrast(getattr(tokens, name), panel)
            assert ratio >= text_floor, "%s on panel in %s is %.2f" % (name, mode, ratio)
        for name in _NON_TEXT_PAIRS:
            ratio = _contrast(getattr(tokens, name), panel)
            assert ratio >= 3.0, "%s on panel in %s is %.2f" % (name, mode, ratio)


def test_builder_pairs_include_neutral_gray_and_the_page_title(qapp) -> None:  # type: ignore[no-untyped-def]
    """Every pair the builder paints, including the dark neutral-gray theme."""
    cases = (
        ("light", None),
        ("dark", constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT),
        ("dark", constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY),
        (constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT, None),
        (constants.UI_THEME_MODE_HIGH_CONTRAST_DARK, None),
    )
    for mode, palette in cases:
        kwargs = {"force_mode": mode}
        if palette is not None:
            kwargs["dark_chrome_palette"] = palette
        tokens = tokens_from_palette(qapp.palette(), **kwargs)
        text_floor = 7.0 if tokens.is_high_contrast else 4.5
        label = "%s/%s" % (mode, palette or "default")
        pairs = (
            ("fb.faint", tokens.gutter_text, tokens.panel_bg, text_floor),
            ("selected row", tokens.text_primary, tokens.tree_selected_bg, text_floor),
            ("on accent", on_accent_for(tokens.accent), tokens.accent, text_floor),
            ("chip", tokens.text_primary, tokens.panel_bg, text_floor),
        )
        for name, foreground, background, floor in pairs:
            ratio = _contrast(foreground, background)
            assert ratio >= floor, "%s in %s is %.2f" % (name, label, ratio)
    title_text = chrome.PAGE_TITLE_TEXT
    assert _contrast(title_text, PAGE_TITLE_FILL) >= 4.5
    assert _contrast(PAGE_TITLE_GLYPH, PAGE_TITLE_FILL) >= 3.0
