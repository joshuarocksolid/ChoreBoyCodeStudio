"""Unit tests for runner output_bridge module."""

from __future__ import annotations

import io
from pathlib import Path
import sys

import pytest

from app.runner import output_bridge
from app.runner.output_bridge import redirect_output_to_log

pytestmark = pytest.mark.unit


def test_redirect_output_to_log_mirrors_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_capture)
    monkeypatch.setattr(sys, "stderr", stderr_capture)
    log_path = tmp_path / "logs" / "run.log"

    with redirect_output_to_log(str(log_path)):
        print("STDOUT_MARKER")
        print("STDERR_MARKER", file=sys.stderr)

    log_text = log_path.read_text(encoding="utf-8")
    assert "STDOUT_MARKER" in stdout_capture.getvalue()
    assert "STDERR_MARKER" in stderr_capture.getvalue()
    assert "STDOUT_MARKER" in log_text
    assert "STDERR_MARKER" in log_text


def test_redirect_output_to_log_falls_back_when_log_file_open_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_capture)
    monkeypatch.setattr(sys, "stderr", stderr_capture)

    def _raise_open_error(_self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("open denied")

    monkeypatch.setattr(output_bridge.Path, "open", _raise_open_error)

    with redirect_output_to_log(str(tmp_path / "logs" / "run.log")):
        print("FALLBACK_STDOUT")

    assert "FALLBACK_STDOUT" in stdout_capture.getvalue()
    assert "unable to open run log" in stderr_capture.getvalue()
