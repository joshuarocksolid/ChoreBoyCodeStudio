"""Unit tests for the REPL console runner (_QuietConsole and helpers)."""

from __future__ import annotations

import io
import sys

import pytest

from app.runner.runner_main import _QuietConsole, _make_clear_helper

pytestmark = pytest.mark.unit


class TestQuietConsoleRawInput:
    """_QuietConsole.raw_input must read stdin without writing prompts to stdout."""

    def test_does_not_write_prompt_to_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_stdin = io.StringIO("x = 1\n")
        captured_stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdin", fake_stdin)
        monkeypatch.setattr(sys, "stdout", captured_stdout)

        console = _QuietConsole()
        result = console.raw_input(">>> ")

        assert result == "x = 1"
        assert ">>>" not in captured_stdout.getvalue()
        assert "..." not in captured_stdout.getvalue()

    def test_raises_eof_on_empty_readline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_stdin = io.StringIO("")
        monkeypatch.setattr(sys, "stdin", fake_stdin)

        console = _QuietConsole()
        with pytest.raises(EOFError):
            console.raw_input(">>> ")

    def test_strips_trailing_newline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_stdin = io.StringIO("print('hi')\n")
        monkeypatch.setattr(sys, "stdin", fake_stdin)

        console = _QuietConsole()
        result = console.raw_input(">>> ")

        assert result == "print('hi')"

    def test_flushes_stdout_before_reading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        flush_calls: list[bool] = []
        fake_stdin = io.StringIO("a\n")

        class _TrackFlush(io.StringIO):
            def flush(self) -> None:
                flush_calls.append(True)
                super().flush()

        monkeypatch.setattr(sys, "stdin", fake_stdin)
        monkeypatch.setattr(sys, "stdout", _TrackFlush())

        console = _QuietConsole()
        console.raw_input(">>> ")

        assert len(flush_calls) >= 1


class TestClearHelper:
    """The clear helper injected into REPL locals."""

    def test_repr_shows_guidance(self) -> None:
        helper = _make_clear_helper()
        text = repr(helper)
        assert "Clear Console" in text

    def test_callable_prints_guidance(self, capsys: pytest.CaptureFixture[str]) -> None:
        helper = _make_clear_helper()
        helper()  # type: ignore[operator]
        captured = capsys.readouterr()
        assert "Clear Console" in captured.out
