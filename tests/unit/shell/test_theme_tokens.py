"""Unit tests for theme token derivation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtGui", exc_type=ImportError)

from app.shell.theme_tokens import apply_syntax_token_overrides, tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


def _make_palette(lightness: int = 240) -> MagicMock:
    palette = MagicMock()
    window_color = MagicMock()
    window_color.lightness.return_value = lightness
    palette.color.return_value = window_color
    return palette


class TestTokensFromPalette:
    def test_auto_detect_light_palette(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=200))
        assert tokens.is_dark is False
        assert tokens.editor_bg == "#FFFFFF"

    def test_auto_detect_dark_palette(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=50))
        assert tokens.is_dark is True
        assert tokens.editor_bg == "#1B1F23"

    def test_prefer_dark_overrides_light_palette(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=200), prefer_dark=True)
        assert tokens.is_dark is True

    def test_force_mode_dark_overrides_light_palette(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=200), force_mode="dark")
        assert tokens.is_dark is True
        assert tokens.editor_bg == "#1B1F23"

    def test_force_mode_light_overrides_dark_palette(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=50), force_mode="light")
        assert tokens.is_dark is False
        assert tokens.editor_bg == "#FFFFFF"

    def test_force_mode_light_overrides_prefer_dark(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=50), prefer_dark=True, force_mode="light")
        assert tokens.is_dark is False

    def test_force_mode_none_falls_back_to_auto(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=200), force_mode=None)
        assert tokens.is_dark is False

    def test_force_mode_unknown_falls_back_to_auto(self) -> None:
        tokens = tokens_from_palette(_make_palette(lightness=200), force_mode="invalid")
        assert tokens.is_dark is False

    def test_dark_tokens_have_expected_fields(self) -> None:
        tokens = tokens_from_palette(_make_palette(), force_mode="dark")
        assert tokens.window_bg == "#1F2428"
        assert tokens.accent == "#5B8CFF"
        assert tokens.tree_hover_bg != ""
        assert tokens.syntax_keyword != ""
        assert tokens.syntax_markdown_code != ""
        assert tokens.syntax_semantic_function != ""
        assert tokens.syntax_semantic_method != ""
        assert tokens.syntax_semantic_variable != ""
        assert tokens.syntax_semantic_property != ""
        assert tokens.syntax_semantic_constant != ""

    def test_light_tokens_have_expected_fields(self) -> None:
        tokens = tokens_from_palette(_make_palette(), force_mode="light")
        assert tokens.window_bg == "#F8F9FA"
        assert tokens.accent == "#3366FF"
        assert tokens.tree_hover_bg != ""
        assert tokens.syntax_keyword != ""
        assert tokens.syntax_markdown_code != ""
        assert tokens.syntax_semantic_function != ""
        assert tokens.syntax_semantic_method != ""
        assert tokens.syntax_semantic_variable != ""
        assert tokens.syntax_semantic_property != ""
        assert tokens.syntax_semantic_constant != ""

    def test_light_and_dark_produce_different_tokens(self) -> None:
        light = tokens_from_palette(_make_palette(), force_mode="light")
        dark = tokens_from_palette(_make_palette(), force_mode="dark")
        assert light.window_bg != dark.window_bg
        assert light.editor_bg != dark.editor_bg
        assert light.text_primary != dark.text_primary
        assert light.syntax_keyword != dark.syntax_keyword
        assert light.syntax_semantic_function != dark.syntax_semantic_function
        assert light.syntax_semantic_method != dark.syntax_semantic_method
        assert light.syntax_semantic_variable != dark.syntax_semantic_variable
        assert light.syntax_semantic_property != dark.syntax_semantic_property
        assert light.syntax_semantic_constant != dark.syntax_semantic_constant

    def test_apply_syntax_token_overrides_updates_target_fields_only(self) -> None:
        tokens = tokens_from_palette(_make_palette(), force_mode="light")
        overridden = apply_syntax_token_overrides(
            tokens,
            {
                "keyword": "#123456",
                "semantic_method": "#654321",
                "unknown": "#ABCDEF",
            },
        )
        assert overridden.syntax_keyword == "#123456"
        assert overridden.syntax_semantic_method == "#654321"
        assert overridden.syntax_string == tokens.syntax_string
