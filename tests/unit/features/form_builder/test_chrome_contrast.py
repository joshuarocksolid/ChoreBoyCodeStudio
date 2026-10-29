"""Chrome token pairs meet the contrast targets in every theme."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

import app.features.form_builder.qtside.theme.chrome as chrome  # noqa: E402
from app.core import constants  # noqa: E402
from app.features.form_builder.qtside.theme.chrome import (  # noqa: E402
    PAGE_TITLE_FILL,
    PAGE_TITLE_GLYPH,
    control_qss,
    edge_on,
    field_qss,
    link_ink,
    on_accent_for,
)
from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.features.form_builder.integration.workbench import problems_link_color  # noqa: E402
from app.features.form_builder.qtside.inspector.pane import _stylesheet  # noqa: E402
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


def _assert_pseudo_on_every_selector(sheet: str, accent: str) -> None:
    """A focus border belongs only on selectors that name :focus."""
    for block in sheet.split("}"):
        if "{" not in block or accent not in block or "solid" not in block:
            continue
        selectors = block.split("{", 1)[0]
        for part in selectors.split(","):
            assert ":focus" in part, part


def _contrast(foreground: str, background: str) -> float:
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def test_unchecked_indicator_and_field_border_clear_three_to_one(qapp) -> None:  # type: ignore[no-untyped-def]
    """An empty box and a field edge stay visible on the panel in every theme."""
    modes = (
        "light",
        "dark",
        constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
        constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
    )
    for mode in modes:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        built = chrome_for(tokens)
        edge = edge_on(built, built.panel)
        ratio = _contrast(edge, built.panel)
        assert ratio >= 3.0, "indicator edge in %s is %.2f" % (mode, ratio)
        field_edge = edge_on(built, built.input)
        field_ratio = _contrast(field_edge, built.input)
        assert field_ratio >= 3.0, "field border in %s is %.2f" % (mode, field_ratio)
        floor = 7.0 if built.is_high_contrast else 4.5
        ink = link_ink(built)
        ink_ratio = _contrast(ink, built.panel)
        assert ink_ratio >= floor, "disclosure ink in %s is %.2f" % (mode, ink_ratio)
        disabled_ratio = _contrast(built.muted, built.input or built.panel)
        assert disabled_ratio >= 4.5, "disabled field text in %s is %.2f" % (mode, disabled_ratio)
        sheet = _stylesheet(built)
        assert edge in sheet and "QCheckBox::indicator" in sheet
        fields = field_qss(built, "QFrame#formBuilder\\.itemEditor")
        assert field_edge in fields
        links = control_qss(built)
        assert ink in links
        assert "formBuilder\\.translationToggle:focus" in links
        assert "formBuilder\\.itemMore:focus" in links
        assert "formBuilder\\.pagesAdd:focus" in links
        assert "formBuilder\\.addCustomProperty:focus" in links
        assert "translationToggle, QToolButton#formBuilder\\.itemMore:focus" not in links
        _assert_pseudo_on_every_selector(fields, built.accent)
        if built.is_high_contrast:
            assert "dashed" in fields
            assert "dashed" in sheet
            assert "underline" in links
        else:
            assert "text-decoration: none" in links


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
            ("show in problems link", problems_link_color(tokens), tokens.panel_bg, text_floor),
            ("checkbox text", chrome_for(tokens).text, chrome_for(tokens).panel, text_floor),
            ("inspector link", problems_link_color(tokens), chrome_for(tokens).panel, text_floor),
            ("alignment segment", chrome_for(tokens).text, chrome_for(tokens).input, text_floor),
            ("checked alignment segment", chrome_for(tokens).text, chrome_for(tokens).selected, text_floor),
            ("checked segment border", chrome_for(tokens).accent, chrome_for(tokens).selected, 3.0),
            ("go to widget detail", chrome_for(tokens).muted, chrome_for(tokens).panel, text_floor),
            ("go to widget detail, selected row", chrome_for(tokens).muted, chrome_for(tokens).selected, 4.5),
            ("why paragraph", chrome_for(tokens).muted, chrome_for(tokens).row_hover, text_floor),
            ("outlined size segment", chrome_for(tokens).accent, chrome_for(tokens).input, 3.0),
            (
                "disabled field text",
                chrome_for(tokens).muted,
                chrome_for(tokens).input,
                4.5,
            ),
        )
        for name, foreground, background, floor in pairs:
            ratio = _contrast(foreground, background)
            assert ratio >= floor, "%s in %s is %.2f" % (name, label, ratio)
    title_text = chrome.PAGE_TITLE_TEXT
    assert _contrast(title_text, PAGE_TITLE_FILL) >= 4.5
    assert _contrast(PAGE_TITLE_GLYPH, PAGE_TITLE_FILL) >= 3.0
    sheet = _stylesheet(chrome_for(tokens))
    assert "QCheckBox { color:" in sheet
    assert chrome_for(tokens).text in sheet
