"""Unit tests for shared semantic utilities."""
from __future__ import annotations

import pytest

from app.intelligence.semantic_utils import extract_symbol_under_cursor

pytestmark = pytest.mark.unit


def test_extract_symbol_under_cursor_returns_identifier_token() -> None:
    source = "result = helper_task(value)"
    cursor_position = source.index("helper_task") + 3

    symbol = extract_symbol_under_cursor(source, cursor_position)

    assert symbol == "helper_task"


def test_extract_symbol_under_cursor_returns_empty_for_non_identifier() -> None:
    source = "value = 1 + 2"

    symbol = extract_symbol_under_cursor(source, source.index("+"))

    assert symbol == ""
