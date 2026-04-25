"""Unit tests for safe debugger expression evaluation."""

from __future__ import annotations

import pytest

from app.debug.safe_eval import UnsafeExpressionError, safe_evaluate_expression

pytestmark = pytest.mark.unit


class _Box:
    def __init__(self) -> None:
        self.value = 41


def test_safe_evaluate_expression_allows_read_only_arithmetic_and_attributes() -> None:
    result = safe_evaluate_expression("box.value + values[0]", {}, {"box": _Box(), "values": [1]})

    assert result == 42


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo unsafe')",
        "(lambda: 1)()",
        "[item for item in values]",
        "box.__class__",
        "value = 1",
    ],
)
def test_safe_evaluate_expression_rejects_executable_shapes(expression: str) -> None:
    with pytest.raises(UnsafeExpressionError):
        safe_evaluate_expression(expression, {}, {"box": _Box(), "values": [1]})
