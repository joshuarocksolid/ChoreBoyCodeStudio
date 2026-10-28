# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""UX-TOK-005 chrome tokens: aliases follow the shell, and every text or UI pair meets UX-A11Y-006."""

from __future__ import annotations

import pytest

from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.theme.chrome import ChromeTokens, FormChrome, chrome_tokens
from app.qt.QtGui import QPalette  # type: ignore[reportAttributeAccessIssue]
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")


def _shell(mode: str) -> ShellThemeTokens:
    return tokens_from_palette(QPalette(), force_mode=mode)


def _luminance(color: str) -> float:
    value = color.lstrip("#")
    channels = []
    for index in (0, 2, 4):
        channel = int(value[index:index + 2], 16) / 255.0
        channels.append(channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _pairs(chrome: FormChrome, tokens: ChromeTokens) -> list:
    """(name, foreground, background, target). Text is 4.5 : 1, or 7 : 1 in high contrast.

    ``fb.popup_border`` is left out on purpose: it is the 1 px separator of a popover
    (UX-ELEV-001 gives the popover its shadow), not a control border, so 3 : 1 does not apply.
    """
    text_target = 7.0 if chrome.is_high_contrast else 4.5
    return [
        ("text on panel", chrome.text, chrome.panel, text_target),
        ("faint on panel", chrome.faint, chrome.panel, text_target),
        ("text on popup", chrome.text, tokens.popup, text_target),
        ("text on match", chrome.text, tokens.match, text_target),
        ("handle border on fill", tokens.handle_border, tokens.handle_fill, 3.0),
        ("handle current on fill", tokens.handle_current_border, tokens.handle_fill, 3.0),
    ]


@pytest.mark.parametrize("mode", _MODES)
def test_aliases_follow_the_shell(mode: str) -> None:
    shell = _shell(mode)
    chrome = chrome_for(shell)
    tokens = chrome_tokens(chrome)
    assert tokens.tile_hover == shell.tree_hover_bg
    assert tokens.tile_current == shell.tree_selected_bg
    assert tokens.glyph == shell.icon_primary
    assert tokens.match == shell.search_match_bg
    assert tokens.popup == shell.popup_bg
    assert tokens.popup_border == shell.popup_border


@pytest.mark.parametrize("mode", _MODES)
def test_text_and_ui_pairs_meet_contrast_targets(mode: str) -> None:
    chrome = chrome_for(_shell(mode))
    tokens = chrome.fb
    failures = []
    for name, foreground, background, target in _pairs(chrome, tokens):
        ratio = _contrast(foreground, background)
        if ratio < target:
            failures.append("%s %.2f < %.1f" % (name, ratio, target))
    assert not failures, "%s: %s" % (mode, "; ".join(failures))


def test_high_contrast_handles_are_two_pixel_and_mode_specific() -> None:
    light = chrome_for(_shell("high_contrast_light")).fb
    dark = chrome_for(_shell("high_contrast_dark")).fb
    assert light.handle_border_px == 2.0 and dark.handle_border_px == 2.0
    assert light.handle_border != dark.handle_border
    assert light.checker_a != dark.checker_a
