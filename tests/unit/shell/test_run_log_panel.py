"""Unit tests for RunLogPanel live-streaming behaviour."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication  # noqa: E402

from app.shell.run_log_panel import RunInfo, RunLogPanel  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def panel(_ensure_qapp):  # type: ignore[no-untyped-def]
    return RunLogPanel()


def test_begin_run_clears_text_and_sets_running(panel: RunLogPanel) -> None:
    panel._text.setPlainText("old content")
    panel.begin_run(RunInfo(mode="python_script", entry_file="main.py"))

    assert panel._text.toPlainText() == ""
    assert panel._status_dot.property("runLogState") == "running"


def test_append_live_line_streams_stdout(panel: RunLogPanel) -> None:
    panel.begin_run()
    panel.append_live_line("hello world\n", stream="stdout")
    panel.append_live_line("second line\n", stream="stdout")

    text = panel._text.toPlainText()
    assert "hello world" in text
    assert "second line" in text


def test_append_live_line_prefixes_stderr(panel: RunLogPanel) -> None:
    panel.begin_run()
    panel.append_live_line("oops\n", stream="stderr")

    text = panel._text.toPlainText()
    assert "[stderr] oops" in text


def test_append_live_line_prefixes_system(panel: RunLogPanel) -> None:
    panel.begin_run()
    panel.append_live_line("Run finished (code=0).\n", stream="system")

    text = panel._text.toPlainText()
    assert "[system] Run finished (code=0)." in text


def test_end_run_preserves_content_and_updates_status(panel: RunLogPanel) -> None:
    panel.begin_run()
    panel.append_live_line("output line\n", stream="stdout")
    panel.end_run(RunInfo(exit_code=0), log_path="/tmp/log.txt")

    assert "output line" in panel._text.toPlainText()
    assert panel._status_dot.property("runLogState") == "success"
    assert not panel._open_btn.isHidden()


def test_end_run_error_status(panel: RunLogPanel) -> None:
    panel.begin_run()
    panel.end_run(RunInfo(exit_code=1))

    assert panel._status_dot.property("runLogState") == "error"


def test_clear_resets_everything(panel: RunLogPanel) -> None:
    panel.begin_run()
    panel.append_live_line("data\n", stream="stdout")
    panel.clear()

    assert panel._text.toPlainText() == ""
    assert panel._status_dot.property("runLogState") == "idle"
