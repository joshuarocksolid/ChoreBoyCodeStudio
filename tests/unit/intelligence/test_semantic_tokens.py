"""Unit tests for semantic token extraction helpers."""

from __future__ import annotations

import pytest

from app.intelligence.semantic_tokens import (
    TOKEN_CLASS,
    TOKEN_FUNCTION,
    TOKEN_IMPORT,
    TOKEN_PARAMETER,
    build_python_semantic_spans,
)

pytestmark = pytest.mark.unit


def test_extracts_function_class_parameter_and_import_spans() -> None:
    source = (
        "import os as operating\n"
        "from pathlib import Path\n"
        "class Demo:\n"
        "    def build(self, value, *, strict=False):\n"
        "        return value\n"
    )
    spans = build_python_semantic_spans(source)
    token_types = {span.token_type for span in spans}
    assert TOKEN_CLASS in token_types
    assert TOKEN_FUNCTION in token_types
    assert TOKEN_PARAMETER in token_types
    assert TOKEN_IMPORT in token_types


def test_handles_partially_typed_python_source() -> None:
    source = (
        "class Demo:\n"
        "    def build(self, value):\n"
        "        return value\n"
        "    def broken(\n"
    )
    spans = build_python_semantic_spans(source)
    assert spans
    assert any(span.token_type == TOKEN_CLASS for span in spans)
