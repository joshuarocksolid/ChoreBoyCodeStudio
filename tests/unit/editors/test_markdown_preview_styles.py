"""Unit tests for Markdown preview stylesheet builders."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.editors.markdown_preview_styles import (
    build_preview_document_stylesheet,
    build_preview_paused_html,
    build_preview_widget_stylesheet,
)
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit


def _tokens(force_mode: str = "light"):
    palette = MagicMock()
    window_color = MagicMock()
    window_color.lightness.return_value = 50 if force_mode == "dark" else 200
    palette.color.return_value = window_color
    return tokens_from_palette(palette, force_mode=force_mode)


@pytest.mark.parametrize(
    "force_mode",
    ["light", "dark", "high_contrast_light", "high_contrast_dark"],
)
def test_build_preview_document_stylesheet_uses_markdown_syntax_tokens(force_mode: str) -> None:
    tokens = _tokens(force_mode)
    stylesheet = build_preview_document_stylesheet(tokens)

    assert tokens.syntax_markdown_heading in stylesheet
    assert tokens.syntax_markdown_code in stylesheet
    assert tokens.syntax_markdown_emphasis in stylesheet
    assert tokens.syntax_markdown_strong in stylesheet
    assert "max-width: 860px" in stylesheet
    assert "font-family: monospace" in stylesheet


def test_build_preview_widget_stylesheet_includes_themed_scrollbar() -> None:
    tokens = _tokens("dark")
    stylesheet = build_preview_widget_stylesheet(tokens)

    assert "QScrollBar:vertical" in stylesheet
    assert tokens.border in stylesheet
    assert tokens.text_muted in stylesheet
    assert "padding: 20px 28px" in stylesheet


def test_build_preview_paused_html_uses_theme_tokens() -> None:
    tokens = _tokens("light")
    html = build_preview_paused_html(tokens, character_count=500_000, threshold=300_000)

    assert tokens.text_primary in html
    assert tokens.editor_bg in html
    assert tokens.syntax_markdown_heading in html
    assert "500,000" in html
    assert "300,000" in html
