"""Unit tests for RunLogPanel live-streaming behaviour."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication  # noqa: E402

from app.qt.QtGui import QTextCursor  # noqa: E402

from app.shell.run_log_panel import RunInfo, RunLogPanel, startup_noise_tooltip  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    yield qapp


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


@pytest.mark.parametrize(
    "line",
    [
        "/opt/freecad/usr/lib/x86_64-linux-gnu:/opt/freecad/usr/lib",
        "/tmp/.mount_FreeCAxyz/usr/lib/x86_64-linux-gnu:/tmp/.mount_FreeCAxyz/usr/lib",
        "[stderr] connect failed: No such file or directory",
        "connect failed: No such file or directory",
    ],
)
def test_freecad_startup_noise_is_recognised(line: str) -> None:
    assert startup_noise_tooltip(line)


@pytest.mark.parametrize(
    "line",
    [
        "/opt/freecad/usr/lib/x86_64-linux-gnu:/home/user/usr/lib",
        "[stderr] connect failed: Connection refused",
        "[stderr] socket connect failed: No such file or directory",
        "print('/opt/freecad/usr/lib/x86_64-linux-gnu:/opt/freecad/usr/lib')",
    ],
)
def test_other_lines_are_not_startup_noise(line: str) -> None:
    assert startup_noise_tooltip(line) is None


def _format_of_line(panel: RunLogPanel, needle: str):  # type: ignore[no-untyped-def]
    document = panel._text.document()
    block = document.begin()
    while block.isValid():
        if needle in block.text():
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.NextCharacter)
            return cursor.charFormat()
        block = block.next()
    raise AssertionError(f"{needle!r} not in Run Log")


def test_startup_noise_stays_visible_dimmed_with_explanation(panel: RunLogPanel) -> None:
    panel.begin_run()
    panel.append_live_line("/opt/freecad/usr/lib/x86_64-linux-gnu:/opt/freecad/usr/lib\n", stream="stdout")
    panel.append_live_line("connect failed: No such file or directory\n", stream="stderr")
    panel.append_live_line("real output\n", stream="stdout")

    text = panel._text.toPlainText()
    assert "/opt/freecad/usr/lib/x86_64-linux-gnu:/opt/freecad/usr/lib" in text
    assert "[stderr] connect failed: No such file or directory" in text
    for needle in ("x86_64-linux-gnu", "connect failed"):
        fmt = _format_of_line(panel, needle)
        assert fmt.toolTip()
        assert fmt.foreground().color().name().lower() == panel._col_muted.lower()
    assert _format_of_line(panel, "real output").toolTip() == ""
    # The spacenav line is how CBCS learns the run opened a FreeCAD window (no /proc on ChoreBoy).
    assert panel.saw_freecad_window_start is True
    panel.begin_run()
    assert panel.saw_freecad_window_start is False
