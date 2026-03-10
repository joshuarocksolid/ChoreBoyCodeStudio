"""Unit tests for syntax color preference helpers."""

from __future__ import annotations

import pytest

from app.shell.syntax_color_preferences import (
    THEME_DARK,
    THEME_LIGHT,
    normalize_hex_color,
    parse_syntax_color_overrides,
)

pytestmark = pytest.mark.unit


def test_normalize_hex_color_accepts_hash_and_non_hash_inputs() -> None:
    assert normalize_hex_color("#1a2b3c") == "#1A2B3C"
    assert normalize_hex_color("1a2b3c") == "#1A2B3C"


def test_normalize_hex_color_rejects_invalid_values() -> None:
    assert normalize_hex_color("#123") is None
    assert normalize_hex_color("bad-value") is None


def test_parse_syntax_color_overrides_validates_theme_shape_and_token_keys() -> None:
    parsed = parse_syntax_color_overrides(
        {
            "syntax_colors": {
                "light": {
                    "keyword": "#123456",
                    "keyword_control": "445566",
                    "keyword_import": "#abcdef",
                    "escape": "#0a0b0c",
                    "markdown_strong": "0d0e0f",
                    "unknown_token": "#654321",
                },
                "dark": "invalid-shape",
            }
        }
    )
    assert parsed[THEME_LIGHT] == {
        "keyword": "#123456",
        "keyword_control": "#445566",
        "keyword_import": "#ABCDEF",
        "escape": "#0A0B0C",
        "markdown_strong": "#0D0E0F",
    }
    assert parsed[THEME_DARK] == {}


def test_parse_syntax_color_overrides_returns_empty_maps_when_section_missing() -> None:
    parsed = parse_syntax_color_overrides({})
    assert parsed == {THEME_LIGHT: {}, THEME_DARK: {}}
