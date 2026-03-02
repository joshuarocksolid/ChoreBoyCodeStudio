"""Unit tests for deterministic formatting helpers."""

from __future__ import annotations

import pytest

from app.editors.formatting_service import format_text_basic

pytestmark = pytest.mark.unit


def test_format_text_basic_trims_trailing_whitespace_and_ensures_final_newline() -> None:
    source = "value = 1   \nprint(value)\t\t"

    result = format_text_basic(source)

    assert result.changed is True
    assert result.formatted_text == "value = 1\nprint(value)\n"


def test_format_text_basic_reports_no_change_for_already_normalized_content() -> None:
    source = "value = 1\nprint(value)\n"

    result = format_text_basic(source)

    assert result.changed is False
    assert result.formatted_text == source
