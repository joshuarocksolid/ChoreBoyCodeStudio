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

    @pytest.mark.parametrize("mode", ["light", "dark"])
    def test_all_color_token_fields_are_populated(self, mode: str) -> None:
        tokens = tokens_from_palette(_make_palette(), force_mode=mode)
        for field, value in vars(tokens).items():
            # Optional non-color fields default to "" by design (icon path overrides).
            if field.endswith("_path"):
                continue
            if isinstance(value, str):
                assert value, f"empty token {field} in {mode} mode"

    def test_light_and_dark_produce_different_tokens(self) -> None:
        light = tokens_from_palette(_make_palette(), force_mode="light")
        dark = tokens_from_palette(_make_palette(), force_mode="dark")
        assert light.window_bg != dark.window_bg
        assert light.editor_bg != dark.editor_bg

    def test_apply_syntax_token_overrides_updates_target_fields_only(self) -> None:
        tokens = tokens_from_palette(_make_palette(), force_mode="light")
        overridden = apply_syntax_token_overrides(
            tokens,
            {
                "keyword": "#123456",
                "keyword_control": "#112233",
                "keyword_import": "#332211",
                "escape": "#ABCDEF",
                "markdown_strong": "#FEDCBA",
                "semantic_method": "#654321",
                "unknown": "#ABCDEF",
            },
        )
        assert overridden.syntax_keyword == "#123456"
        assert overridden.syntax_keyword_control == "#112233"
        assert overridden.syntax_keyword_import == "#332211"
        assert overridden.syntax_escape == "#ABCDEF"
        assert overridden.syntax_markdown_strong == "#FEDCBA"
        assert overridden.syntax_semantic_method == "#654321"
        assert overridden.syntax_string == tokens.syntax_string
