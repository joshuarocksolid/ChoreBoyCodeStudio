"""Unit tests for semantic token extraction helpers."""

from __future__ import annotations

import pytest

from app.intelligence.semantic_tokens import (
    MODIFIER_DECLARATION,
    MODIFIER_READONLY,
    MODIFIER_REFERENCE,
    PARSE_STATE_CANCELLED,
    PARSE_STATE_FAILED,
    PARSE_STATE_RECOVERED,
    TOKEN_CLASS,
    TOKEN_CONSTANT,
    TOKEN_FUNCTION,
    TOKEN_IMPORT,
    TOKEN_METHOD,
    TOKEN_PARAMETER,
    TOKEN_PROPERTY,
    TOKEN_VARIABLE,
    build_python_semantic_result,
    build_python_semantic_spans,
)

pytestmark = pytest.mark.unit


def test_extracts_function_class_parameter_and_import_spans() -> None:
    source = (
        "import os as operating\n"
        "from pathlib import Path\n"
        "def outside(item):\n"
        "    return item\n"
        "class Demo:\n"
        "    def build(self, value, *, strict=False):\n"
        "        return value\n"
    )
    spans = build_python_semantic_spans(source)
    token_types = {span.token_type for span in spans}
    assert TOKEN_CLASS in token_types
    assert TOKEN_FUNCTION in token_types
    assert TOKEN_METHOD in token_types
    assert TOKEN_PARAMETER in token_types
    assert TOKEN_IMPORT in token_types


def test_handles_partially_typed_python_source() -> None:
    source = (
        "class Demo:\n"
        "    def build(self, value):\n"
        "        return value\n"
        "    def broken(\n"
    )
    result = build_python_semantic_result(source)
    assert result.parse_state == PARSE_STATE_RECOVERED
    assert result.spans
    assert any(span.token_type == TOKEN_CLASS for span in result.spans)


def test_extracts_variable_and_property_tokens() -> None:
    source = (
        "class Demo:\n"
        "    def build(self, value):\n"
        "        self.total = value\n"
        "        local_item = self.total\n"
        "        return local_item\n"
    )
    spans = build_python_semantic_spans(source)
    token_types = {span.token_type for span in spans}
    assert TOKEN_VARIABLE in token_types
    assert TOKEN_PROPERTY in token_types


def test_extracts_identifier_references_for_calls_constants_and_classes() -> None:
    source = (
        "class Demo:\n"
        "    def run(self):\n"
        "        return self.value\n"
        "APP_DIR = '/tmp'\n"
        "app = Demo()\n"
        "app.run()\n"
        "print(APP_DIR)\n"
    )
    spans = build_python_semantic_spans(source)
    by_text = [(source[span.start:span.end], span.token_type, set(span.token_modifiers)) for span in spans]

    assert ("app", TOKEN_VARIABLE, {MODIFIER_REFERENCE}) in by_text
    assert ("run", TOKEN_METHOD, {MODIFIER_REFERENCE}) in by_text
    assert ("Demo", TOKEN_CLASS, {MODIFIER_REFERENCE, MODIFIER_READONLY}) in by_text
    assert ("APP_DIR", TOKEN_CONSTANT, {MODIFIER_DECLARATION, MODIFIER_READONLY}) in by_text
    assert ("APP_DIR", TOKEN_CONSTANT, {MODIFIER_REFERENCE, MODIFIER_READONLY}) in by_text


def test_extraction_honors_cancellation_signal() -> None:
    source = "x = 1\n" * 2000
    calls = 0

    def should_cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    result = build_python_semantic_result(source, should_cancel=should_cancel)
    assert result.spans == []
    assert result.parse_state == PARSE_STATE_CANCELLED


def test_reports_failed_parse_state_when_recovery_not_possible() -> None:
    result = build_python_semantic_result("def broken(\n")
    assert result.spans == []
    assert result.parse_state == PARSE_STATE_FAILED
