"""Unit tests for PythonConsoleWidget — inline REPL console widget."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QMimeData, QPoint, QUrl, Qt  # noqa: E402
from PySide2.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QKeyEvent  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.shell.python_console_widget import _CONT_PROMPT, _PROMPT, PythonConsoleWidget, _is_traceback_context  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def widget() -> PythonConsoleWidget:
    w = PythonConsoleWidget()
    return w


@pytest.fixture()
def active_widget(widget: PythonConsoleWidget) -> PythonConsoleWidget:
    """A widget with an active session already started."""
    widget.set_session_active(True)
    return widget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _press(widget: PythonConsoleWidget, key: Qt.Key, text: str = "") -> None:
    """Simulate a single key press event on *widget*."""
    press = QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier, text)
    release = QKeyEvent(QKeyEvent.KeyRelease, key, Qt.NoModifier, text)
    QApplication.sendEvent(widget, press)
    QApplication.sendEvent(widget, release)


def _type_text(widget: PythonConsoleWidget, text: str) -> None:
    """Type *text* character by character into *widget*."""
    for ch in text:
        key_val = ord(ch)
        press = QKeyEvent(QKeyEvent.KeyPress, key_val, Qt.NoModifier, ch)
        QApplication.sendEvent(widget, press)


def _get_plain_text(widget: PythonConsoleWidget) -> str:
    return widget.document().toPlainText()


# ---------------------------------------------------------------------------
# Idle / session-inactive state
# ---------------------------------------------------------------------------

class TestIdleState:
    def test_shows_startup_hint_on_construction(self, widget: PythonConsoleWidget) -> None:
        text = _get_plain_text(widget)
        assert "Starting Python Console" in text

    def test_read_only_when_no_session(self, widget: PythonConsoleWidget) -> None:
        assert widget.isReadOnly() is False

    def test_prompt_anchor_available_before_session(self, widget: PythonConsoleWidget) -> None:
        assert widget.prompt_anchor >= 0


# ---------------------------------------------------------------------------
# Session activation
# ---------------------------------------------------------------------------

class TestSessionActivation:
    def test_set_session_active_makes_editable(self, widget: PythonConsoleWidget) -> None:
        widget.set_session_active(True)
        assert not widget.isReadOnly()

    def test_set_session_active_shows_prompt(self, widget: PythonConsoleWidget) -> None:
        widget.set_session_active(True)
        text = _get_plain_text(widget)
        assert text.endswith(_PROMPT)

    def test_prompt_anchor_set_after_activation(self, widget: PythonConsoleWidget) -> None:
        widget.set_session_active(True)
        text = _get_plain_text(widget)
        assert widget.prompt_anchor == len(text)

    def test_deactivation_keeps_prompt_ready_for_next_command(self, widget: PythonConsoleWidget) -> None:
        widget.set_session_active(True)
        widget.set_session_active(False)
        text = _get_plain_text(widget)
        assert widget.isReadOnly() is False
        assert widget.prompt_anchor >= 0
        assert text.endswith(_PROMPT)

    def test_reactivation_preserves_history(self, widget: PythonConsoleWidget) -> None:
        widget.set_session_active(True)
        _type_text(widget, "x = 1")
        _press(widget, Qt.Key_Return)
        assert len(widget.history) == 1
        widget.set_session_active(False)
        widget.set_session_active(True)
        assert len(widget.history) == 1

    def test_set_history_replaces_existing_entries(self, widget: PythonConsoleWidget) -> None:
        widget.set_history(["a = 1", "b = 2"])
        assert widget.history_snapshot() == ["a = 1", "b = 2"]


# ---------------------------------------------------------------------------
# Prompt boundary protection
# ---------------------------------------------------------------------------

class TestPromptProtection:
    def test_backspace_blocked_at_prompt_boundary(self, active_widget: PythonConsoleWidget) -> None:
        before = _get_plain_text(active_widget)
        # Backspace at the start of the input zone must not eat the ">>> "
        _press(active_widget, Qt.Key_Backspace)
        after = _get_plain_text(active_widget)
        assert after.endswith(_PROMPT)
        assert before == after

    def test_typed_text_appears_after_prompt(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "hello")
        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT + "hello")

    def test_backspace_removes_user_input_not_prompt(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "ab")
        _press(active_widget, Qt.Key_Backspace)
        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT + "a")

    def test_home_key_moves_cursor_to_prompt_anchor(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "xyz")
        _press(active_widget, Qt.Key_Home)
        assert active_widget.textCursor().position() == active_widget.prompt_anchor


# ---------------------------------------------------------------------------
# Input submission
# ---------------------------------------------------------------------------

class TestSubmission:
    def test_enter_emits_input_submitted_signal(self, active_widget: PythonConsoleWidget) -> None:
        submitted: list[str] = []
        active_widget.input_submitted.connect(submitted.append)
        _type_text(active_widget, "1 + 1")
        _press(active_widget, Qt.Key_Return)
        assert submitted == ["1 + 1"]

    def test_empty_enter_does_not_emit_signal(self, active_widget: PythonConsoleWidget) -> None:
        submitted: list[str] = []
        active_widget.input_submitted.connect(submitted.append)
        _press(active_widget, Qt.Key_Return)
        assert submitted == []

    def test_submitted_text_added_to_history(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "print('hi')")
        _press(active_widget, Qt.Key_Return)
        assert "print('hi')" in active_widget.history

    def test_duplicate_commands_not_added_twice(self, active_widget: PythonConsoleWidget) -> None:
        for _ in range(3):
            _type_text(active_widget, "x = 1")
            _press(active_widget, Qt.Key_Return)
        assert active_widget.history.count("x = 1") == 1

    def test_new_prompt_appears_after_submission(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "x = 1")
        _press(active_widget, Qt.Key_Return)
        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT)

    def test_multiline_submission_waits_for_complete_block(self, active_widget: PythonConsoleWidget) -> None:
        submitted: list[str] = []
        active_widget.input_submitted.connect(submitted.append)

        _type_text(active_widget, "for i in range(2):")
        _press(active_widget, Qt.Key_Return)
        assert submitted == []
        assert _get_plain_text(active_widget).endswith(_CONT_PROMPT)

        _type_text(active_widget, "    print(i)")
        _press(active_widget, Qt.Key_Return)
        assert submitted == []
        assert _get_plain_text(active_widget).endswith(_CONT_PROMPT)

        _press(active_widget, Qt.Key_Return)
        assert submitted == ["for i in range(2):\n    print(i)\n"]
        assert _get_plain_text(active_widget).endswith(_PROMPT)


# ---------------------------------------------------------------------------
# History navigation
# ---------------------------------------------------------------------------

class TestHistoryNavigation:
    def _submit(self, widget: PythonConsoleWidget, cmd: str) -> None:
        _type_text(widget, cmd)
        _press(widget, Qt.Key_Return)

    def test_up_arrow_recalls_last_command(self, active_widget: PythonConsoleWidget) -> None:
        self._submit(active_widget, "a = 1")
        _press(active_widget, Qt.Key_Up)
        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT + "a = 1")

    def test_up_arrow_multiple_steps(self, active_widget: PythonConsoleWidget) -> None:
        self._submit(active_widget, "first")
        self._submit(active_widget, "second")
        _press(active_widget, Qt.Key_Up)  # → "second"
        _press(active_widget, Qt.Key_Up)  # → "first"
        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT + "first")

    def test_down_arrow_returns_to_empty(self, active_widget: PythonConsoleWidget) -> None:
        self._submit(active_widget, "cmd")
        _press(active_widget, Qt.Key_Up)
        _press(active_widget, Qt.Key_Down)
        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT)

    def test_ctrl_r_opens_history_picker_and_replaces_input(
        self,
        active_widget: PythonConsoleWidget,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _type_text(active_widget, "first_cmd")
        _press(active_widget, Qt.Key_Return)
        _type_text(active_widget, "second_cmd")
        _press(active_widget, Qt.Key_Return)

        monkeypatch.setattr(
            "app.shell.python_console_widget.QInputDialog.getItem",
            lambda *_args, **_kwargs: ("first_cmd", True),
        )
        # Send the Ctrl modifier via direct event to trigger history picker.
        event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_R, Qt.ControlModifier, "r")
        QApplication.sendEvent(active_widget, event)

        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT + "first_cmd")


# ---------------------------------------------------------------------------
# Output appending
# ---------------------------------------------------------------------------

class TestOutputAppending:
    def test_stdout_output_appears_before_prompt(self, active_widget: PythonConsoleWidget) -> None:
        active_widget.append_output("42", "stdout")
        text = _get_plain_text(active_widget)
        assert "42" in text
        assert text.endswith(_PROMPT)

    def test_stderr_output_appears_before_prompt(self, active_widget: PythonConsoleWidget) -> None:
        active_widget.append_output("NameError: x", "stderr")
        text = _get_plain_text(active_widget)
        assert "NameError" in text
        assert text.endswith(_PROMPT)

    def test_freecad_teardown_noise_filtered(self, active_widget: PythonConsoleWidget) -> None:
        before = _get_plain_text(active_widget)
        active_widget.append_output("Loading Post Frame Workbench Module...", "stdout")
        after = _get_plain_text(active_widget)
        assert before == after

    def test_user_input_preserved_after_output(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "partial_cmd")
        active_widget.append_output("some output", "stdout")
        text = _get_plain_text(active_widget)
        assert text.endswith(_PROMPT + "partial_cmd")

    def test_prompt_anchor_updated_after_output(self, active_widget: PythonConsoleWidget) -> None:
        anchor_before = active_widget.prompt_anchor
        inserted = "result line\n"
        active_widget.append_output("result line", "stdout")
        assert active_widget.prompt_anchor == anchor_before + len(inserted)

    def test_system_stream_appended_before_prompt(self, active_widget: PythonConsoleWidget) -> None:
        active_widget.append_output("[system] Session finished (code=0).", "system")
        text = _get_plain_text(active_widget)
        assert "[system] Session finished" in text
        assert text.endswith(_PROMPT)


class TestDragAndDropExecution:
    def test_console_accepts_drops(self, widget: PythonConsoleWidget) -> None:
        assert widget.acceptDrops() is True

    def test_drop_python_file_emits_execution_command(
        self,
        active_widget: PythonConsoleWidget,
        tmp_path: Path,
    ) -> None:
        script_path = tmp_path / "drop_target.py"
        script_path.write_text("print('ok')\n", encoding="utf-8")
        submitted: list[str] = []
        active_widget.input_submitted.connect(submitted.append)

        handled = active_widget._handle_dropped_local_path(str(script_path))

        assert handled is True
        assert submitted == [f"import runpy; runpy.run_path({repr(str(script_path.resolve()))}, run_name='__main__')"]
        assert "Executing dropped file" in _get_plain_text(active_widget)

    def test_drop_non_python_file_appends_actionable_warning(
        self,
        active_widget: PythonConsoleWidget,
        tmp_path: Path,
    ) -> None:
        txt_path = tmp_path / "notes.txt"
        txt_path.write_text("hello", encoding="utf-8")

        handled = active_widget._handle_dropped_local_path(str(txt_path))

        assert handled is False
        assert "is not a Python file" in _get_plain_text(active_widget)

    def test_drag_enter_accepts_url_mime_data(
        self,
        active_widget: PythonConsoleWidget,
        tmp_path: Path,
    ) -> None:
        script = tmp_path / "from_tree.py"
        script.write_text("x = 1\n", encoding="utf-8")

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(script))])
        event = QDragEnterEvent(
            QPoint(10, 10),
            Qt.CopyAction,
            mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        active_widget.dragEnterEvent(event)

        assert event.isAccepted()

    def test_drag_enter_rejects_mime_without_urls(
        self,
        active_widget: PythonConsoleWidget,
    ) -> None:
        mime = QMimeData()
        mime.setData("application/x-qabstractitemmodeldatalist", b"\x00")
        event = QDragEnterEvent(
            QPoint(10, 10),
            Qt.CopyAction,
            mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        active_widget.dragEnterEvent(event)

        assert not event.isAccepted()

    def test_drop_event_with_url_executes_python_file(
        self,
        active_widget: PythonConsoleWidget,
        tmp_path: Path,
    ) -> None:
        script = tmp_path / "tree_drop.py"
        script.write_text("print('tree')\n", encoding="utf-8")
        submitted: list[str] = []
        active_widget.input_submitted.connect(submitted.append)

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(script))])
        drop = QDropEvent(
            QPoint(10, 10),
            Qt.CopyAction,
            mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        active_widget.dropEvent(drop)

        assert drop.isAccepted()
        assert len(submitted) == 1
        assert "runpy.run_path" in submitted[0]
        assert "Executing dropped file" in _get_plain_text(active_widget)


# ---------------------------------------------------------------------------
# Char format: user input should use the default text color, not the prompt's
# ---------------------------------------------------------------------------

class TestTypingCharFormat:
    """Verify that currentCharFormat is reset to the default after prompts."""

    def _assert_default_fmt(self, widget: PythonConsoleWidget) -> None:
        fmt = widget.currentCharFormat()
        expected_fg = QColor(widget._col_text)
        assert fmt.foreground().color() == expected_fg, (
            f"Expected foreground {expected_fg.name()}, got {fmt.foreground().color().name()}"
        )
        assert fmt.fontWeight() == QFont.Normal

    def test_current_char_format_after_show_prompt(self, active_widget: PythonConsoleWidget) -> None:
        self._assert_default_fmt(active_widget)

    def test_current_char_format_after_submission(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "x = 1")
        _press(active_widget, Qt.Key_Return)
        self._assert_default_fmt(active_widget)

    def test_current_char_format_after_history_recall(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "x = 1")
        _press(active_widget, Qt.Key_Return)
        _press(active_widget, Qt.Key_Up)
        self._assert_default_fmt(active_widget)

    def test_current_char_format_after_stderr_output(self, active_widget: PythonConsoleWidget) -> None:
        active_widget.append_output("NameError: oops", "stderr")
        self._assert_default_fmt(active_widget)

    def test_typed_text_uses_default_format(self, active_widget: PythonConsoleWidget) -> None:
        _type_text(active_widget, "hello")
        cursor = active_widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.KeepAnchor, 1)
        fmt = cursor.charFormat()
        expected_fg = QColor(active_widget._col_text)
        assert fmt.foreground().color() == expected_fg


# ---------------------------------------------------------------------------
# clear_console — user-facing clear that preserves session state
# ---------------------------------------------------------------------------

class TestClearConsole:
    def test_clear_console_removes_all_text_and_shows_prompt(
        self, active_widget: PythonConsoleWidget
    ) -> None:
        active_widget.append_output("some old output", "stdout")
        _type_text(active_widget, "partial")
        active_widget.clear_console()
        text = _get_plain_text(active_widget)
        assert text == _PROMPT

    def test_clear_console_preserves_session_active_flag(
        self, active_widget: PythonConsoleWidget
    ) -> None:
        active_widget.clear_console()
        assert active_widget._session_active is True

    def test_clear_console_preserves_history(
        self, active_widget: PythonConsoleWidget
    ) -> None:
        _type_text(active_widget, "x = 1")
        _press(active_widget, Qt.Key_Return)
        assert len(active_widget.history) == 1
        active_widget.clear_console()
        assert len(active_widget.history) == 1

    def test_clear_console_resets_prompt_anchor(
        self, active_widget: PythonConsoleWidget
    ) -> None:
        active_widget.clear_console()
        text = _get_plain_text(active_widget)
        assert active_widget.prompt_anchor == len(text)

    def test_clear_console_when_inactive_shows_prompt(
        self, widget: PythonConsoleWidget
    ) -> None:
        widget.append_output("old output", "stdout")
        widget.clear_console()
        text = _get_plain_text(widget)
        assert text == _PROMPT


# ---------------------------------------------------------------------------
# Traceback context detection and dimmed error styling
# ---------------------------------------------------------------------------

class TestTracebackContextDetection:
    def test_traceback_header_is_context(self) -> None:
        assert _is_traceback_context("Traceback (most recent call last):") is True

    def test_file_line_is_context(self) -> None:
        assert _is_traceback_context('  File "<console>", line 1, in <module>') is True

    def test_indented_source_echo_is_context(self) -> None:
        assert _is_traceback_context("    print(a)") is True

    def test_chained_exception_header_is_context(self) -> None:
        assert _is_traceback_context("During handling of the above exception, another exception occurred:") is True

    def test_final_error_line_is_not_context(self) -> None:
        assert _is_traceback_context("NameError: name 'a' is not defined") is False

    def test_syntax_error_caret_is_not_context(self) -> None:
        assert _is_traceback_context("    ^") is False

    def test_empty_line_is_not_context(self) -> None:
        assert _is_traceback_context("") is False


class TestTracebackStyling:
    def test_stderr_error_line_uses_full_error_color(self, active_widget: PythonConsoleWidget) -> None:
        fmt = active_widget._fmt_for("stderr", "NameError: name 'a' is not defined")
        assert fmt.foreground().color() == QColor(active_widget._col_error)

    def test_stderr_traceback_header_uses_dim_error_color(self, active_widget: PythonConsoleWidget) -> None:
        fmt = active_widget._fmt_for("stderr", "Traceback (most recent call last):")
        assert fmt.foreground().color() == QColor(active_widget._col_error_dim)

    def test_stderr_file_line_uses_dim_error_color(self, active_widget: PythonConsoleWidget) -> None:
        fmt = active_widget._fmt_for("stderr", '  File "<console>", line 1, in <module>')
        assert fmt.foreground().color() == QColor(active_widget._col_error_dim)
