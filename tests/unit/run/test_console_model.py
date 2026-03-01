"""Unit tests for console output model."""

import pytest

from app.run.console_model import ConsoleModel

pytestmark = pytest.mark.unit


def test_console_model_append_and_clear() -> None:
    """Console model should append lines and clear deterministically."""
    model = ConsoleModel()
    first = model.append("stdout", "hello")
    second = model.append("stderr", "oops")

    assert [line.stream for line in model.lines()] == ["stdout", "stderr"]
    assert first.text == "hello"
    assert second.text == "oops"

    model.clear()
    assert model.lines() == []


def test_console_model_trims_oldest_lines_when_max_exceeded() -> None:
    """Console should enforce bounded buffer for responsiveness."""
    model = ConsoleModel(max_lines=100)
    for index in range(101):
        model.append("stdout", f"line-{index}")

    assert len(model.lines()) == 100
    assert model.lines()[0].text == "line-1"
    assert model.lines()[-1].text == "line-100"
