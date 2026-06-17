"""Wave 2 scaffold: syntax palette token round-trip contract."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtGui", exc_type=ImportError)

from PySide2.QtGui import QPalette  # noqa: E402

from app.syntax.palette import (  # noqa: E402
    DEFAULT_LIGHT_PALETTE,
    SYNTAX_PALETTE_FIELD_MAP,
    syntax_palette_from_tokens,
)
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("theme_mode", ["light", "dark", "high_contrast_light", "high_contrast_dark"])
def test_syntax_palette_keys_round_trip_through_theme_tokens(theme_mode: str) -> None:
    tokens = tokens_from_palette(QPalette(), force_mode=theme_mode)
    palette = syntax_palette_from_tokens(tokens)

    for token_key in DEFAULT_LIGHT_PALETTE:
        assert token_key in palette
        field_name = SYNTAX_PALETTE_FIELD_MAP[token_key]
        assert palette[token_key] == getattr(tokens, field_name)
