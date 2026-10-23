"""Scored builder chrome pairs against the four shell themes (UX-A11Y-006)."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.qtside.theme.chrome import (  # noqa: E402
    CONTRAST_PAIRS,
    ChromeKind,
    chrome_tokens,
    elevation,
)
from app.shell.contrast import contrast_ratio  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_THEMES = (
    ("light", ChromeKind.LIGHT, False),
    ("dark", ChromeKind.DARK, False),
    ("high_contrast_light", ChromeKind.HC_LIGHT, True),
    ("high_contrast_dark", ChromeKind.HC_DARK, True),
)


def _chrome(qapp, mode: str, palette: str = constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT):  # type: ignore[no-untyped-def]
    shell = tokens_from_palette(qapp.palette(), force_mode=mode, dark_chrome_palette=palette)
    return chrome_tokens(shell), shell


def test_scored_pairs_meet_their_contrast_floor(qapp) -> None:  # type: ignore[no-untyped-def]
    for mode, kind, high_contrast in _THEMES:
        chrome, _shell = _chrome(qapp, mode)
        assert chrome.kind is kind
        text_floor = 7.0 if high_contrast else 4.5
        for pair in CONTRAST_PAIRS:
            foreground = chrome.paint(pair.fg, pair.bg)
            background = chrome.color(pair.bg)
            ratio = contrast_ratio(foreground, background)
            floor = text_floor if pair.kind == "text" else 3.0
            assert ratio >= floor, "%s %s on %s is %.2f, floor %.1f" % (mode, pair.fg, pair.bg, ratio, floor)


def test_paint_rejects_a_pair_the_list_omits(qapp) -> None:  # type: ignore[no-untyped-def]
    chrome, _shell = _chrome(qapp, "light")
    with pytest.raises(KeyError):
        chrome.paint("warning", "panel")


def test_high_contrast_drops_shadows_and_dots(qapp) -> None:  # type: ignore[no-untyped-def]
    for mode in ("high_contrast_light", "high_contrast_dark"):
        chrome, _shell = _chrome(qapp, mode)
        assert chrome.dots == ""
        assert chrome.page_shadow == ""
        page = elevation(1, chrome)
        popover = elevation(2, chrome)
        assert page.shadows == ()
        assert popover.shadows == ()
        assert page.border_px == 1
        assert page.border_color == chrome.paint("text", "backdrop")
        assert popover.border_px == 2
        assert popover.border_color == chrome.paint("text", "popup")


def test_light_and_dark_page_cards_keep_a_shadow(qapp) -> None:  # type: ignore[no-untyped-def]
    for mode in ("light", "dark"):
        chrome, _shell = _chrome(qapp, mode)
        assert chrome.dots
        page = elevation(1, chrome)
        flat = elevation(0, chrome)
        assert page.shadows
        assert page.border_px == 0
        assert flat.shadows == ()
        assert flat.border_color == chrome.border


def test_neutral_gray_keeps_dark_builder_tokens_and_its_own_panel(qapp) -> None:  # type: ignore[no-untyped-def]
    standard, _standard_shell = _chrome(qapp, "dark")
    neutral, shell = _chrome(qapp, "dark", constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY)
    assert neutral.kind is ChromeKind.DARK
    assert neutral.backdrop == standard.backdrop
    assert neutral.dots == standard.dots
    assert neutral.page_shadow == standard.page_shadow
    assert neutral.page_border == standard.page_border
    assert neutral.on_accent == standard.on_accent
    assert neutral.panel == shell.panel_bg
    assert neutral.panel != standard.panel


def test_elevation_rejects_an_unknown_level(qapp) -> None:  # type: ignore[no-untyped-def]
    chrome, _shell = _chrome(qapp, "light")
    with pytest.raises(ValueError):
        elevation(3, chrome)
