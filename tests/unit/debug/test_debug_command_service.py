"""Unit tests for debug command generation helpers."""

from __future__ import annotations

import pytest

from app.debug.debug_command_service import (
    continue_command,
    evaluate_command,
    locals_command,
    stack_command,
    step_into_command,
    step_out_command,
    step_over_command,
)

pytestmark = pytest.mark.unit


def test_debug_command_helpers_return_expected_commands() -> None:
    assert continue_command() == "continue\n"
    assert step_over_command() == "next\n"
    assert step_into_command() == "step\n"
    assert step_out_command() == "return\n"
    assert stack_command() == "where\n"
    assert locals_command() == "p locals()\n"


def test_evaluate_command_formats_expression() -> None:
    assert evaluate_command("value + 1") == "p value + 1\n"
    assert evaluate_command("  ") == "\n"
