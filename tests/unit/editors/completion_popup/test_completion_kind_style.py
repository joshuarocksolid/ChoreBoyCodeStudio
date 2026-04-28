"""Parity guard ensuring every CompletionKind has a visible style."""

from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QPalette  # noqa: E402

from app.editors.completion_popup.completion_kind_style import (  # noqa: E402
    kind_style_for,
    kind_styles_for_tokens,
)
from app.intelligence.completion_models import CompletionKind  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_kind_has_glyph_and_color(mode: str) -> None:
    tokens = tokens_from_palette(QPalette(), force_mode=mode)
    styles = kind_styles_for_tokens(tokens)
    assert set(styles.keys()) == set(CompletionKind)
    for kind, style in styles.items():
        assert style.glyph, f"missing glyph for {kind}"
        assert style.accent_color, f"missing accent color for {kind}"
        assert style.accent_color.startswith("#"), f"non-hex color for {kind}: {style.accent_color}"
        assert style.label, f"missing label for {kind}"


def test_kind_style_for_falls_back_when_token_field_missing() -> None:
    tokens = tokens_from_palette(QPalette(), force_mode="dark")
    stripped = replace(tokens, syntax_function="")
    style = kind_style_for(CompletionKind.FUNCTION, stripped)
    assert style.accent_color == stripped.accent
