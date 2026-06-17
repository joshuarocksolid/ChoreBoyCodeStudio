"""Unit tests for Markdown preview post-render enhancements."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.markdown_preview_enhancements import enhance_preview_document  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


def _tokens(force_mode: str = "light"):
    palette = MagicMock()
    window_color = MagicMock()
    window_color.lightness.return_value = 50 if force_mode == "dark" else 200
    palette.color.return_value = window_color
    return tokens_from_palette(palette, force_mode=force_mode)


def test_enhance_preview_document_marks_external_links(qapp) -> None:  # type: ignore[no-untyped-def]
    from PySide2.QtWidgets import QTextBrowser

    browser = QTextBrowser()
    browser.setMarkdown("[Example](https://example.com)")

    enhance_preview_document(browser.document(), tokens=_tokens())

    assert "\u2197" in browser.toPlainText()
