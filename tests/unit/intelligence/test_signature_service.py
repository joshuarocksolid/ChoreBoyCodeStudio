"""Unit tests for signature-help resolution service."""

from __future__ import annotations

import pytest

from app.intelligence.signature_service import parse_call_context, resolve_signature_help

pytestmark = pytest.mark.unit


def test_parse_call_context_returns_callable_and_argument_index() -> None:
    source = "result = run_task(1, value"
    context = parse_call_context(source, len(source))

    assert context is not None
    assert context.callable_name == "run_task"
    assert context.argument_index == 1


def test_parse_call_context_tracks_innermost_nested_call() -> None:
    source = "answer = outer(alpha(1, 2), beta(3, "
    context = parse_call_context(source, len(source))

    assert context is not None
    assert context.callable_name == "beta"
    assert context.argument_index == 1


def test_resolve_signature_help_prefers_current_file_function_definitions() -> None:
    source = (
        "def build_report(name, *, compact=False):\n"
        "    \"\"\"Build report summary.\"\"\"\n"
        "    return name\n\n"
        "build_report('alpha', compact="
    )
    signature = resolve_signature_help(source, len(source))

    assert signature is not None
    assert signature.source == "project"
    assert signature.signature_text == "build_report(name, *, compact=False)"
    assert signature.doc_summary == "Build report summary."
    assert signature.argument_index == 1


def test_resolve_signature_help_falls_back_to_builtin_callable() -> None:
    source = "print('hello', sep="
    signature = resolve_signature_help(source, len(source))

    assert signature is not None
    assert signature.source == "builtin"
    assert signature.signature_text.startswith("print(")


def test_resolve_signature_help_returns_none_when_not_in_call_context() -> None:
    assert resolve_signature_help("value = 1 + 2", len("value = 1 + 2")) is None
