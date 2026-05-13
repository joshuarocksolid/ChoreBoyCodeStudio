"""Unit tests for theme token derivation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtGui", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.contrast import contrast_ratio  # noqa: E402
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

    @pytest.mark.parametrize(
        ("ui_font_weight", "expected_css"),
        [
            (constants.UI_THEME_FONT_WEIGHT_NORMAL, "normal"),
            (constants.UI_THEME_FONT_WEIGHT_MEDIUM, "500"),
            (constants.UI_THEME_FONT_WEIGHT_BOLD, "600"),
        ],
    )
    def test_ui_font_weight_translates_to_css_literal(
        self, ui_font_weight: str, expected_css: str
    ) -> None:
        tokens = tokens_from_palette(
            _make_palette(), force_mode="light", ui_font_weight=ui_font_weight
        )
        assert tokens.ui_font_weight_css == expected_css

    def test_unknown_ui_font_weight_falls_back_to_normal(self) -> None:
        tokens = tokens_from_palette(
            _make_palette(), force_mode="dark", ui_font_weight="extralight"
        )
        assert tokens.ui_font_weight_css == "normal"

    @pytest.mark.parametrize("mode", ["light", "dark"])
    def test_chrome_text_contrast_meets_wcag_aa(self, mode: str) -> None:
        """Guard the user-visible readability promise of #37 Tier 1.

        Both ``text_muted`` and ``gutter_text`` previously fell below WCAG AA
        on realistic surfaces (e.g. light gutter_text on gutter_bg ~1.87:1).
        This test pins the centrally-defined palette above the 4.5:1 normal
        text threshold so a future palette tweak cannot silently regress
        readability.
        """
        tokens = tokens_from_palette(_make_palette(), force_mode=mode)
        critical_pairs = (
            (tokens.text_muted, tokens.panel_bg, "text_muted on panel_bg"),
            (tokens.text_muted, tokens.editor_bg, "text_muted on editor_bg"),
            (tokens.text_muted, tokens.row_alt_bg, "text_muted on row_alt_bg"),
            (tokens.text_muted, tokens.tree_selected_bg, "text_muted on tree_selected_bg"),
            (tokens.gutter_text, tokens.gutter_bg, "gutter_text on gutter_bg"),
            (tokens.text_primary, tokens.panel_bg, "text_primary on panel_bg"),
            (tokens.text_primary, tokens.editor_bg, "text_primary on editor_bg"),
            (tokens.text_primary, tokens.tree_selected_bg, "text_primary on tree_selected_bg"),
        )
        failures: list[str] = []
        for fg, bg, label in critical_pairs:
            ratio = contrast_ratio(fg, bg)
            if ratio < 4.5:
                failures.append(f"{label}: {ratio:.2f}:1 (fg={fg}, bg={bg})")
        assert not failures, "WCAG AA regressions in {mode} palette: {fails}".format(
            mode=mode, fails=", ".join(failures)
        )

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
