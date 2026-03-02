"""Unit tests for PythonConsoleWidget — inline REPL console widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtGui import QKeyEvent  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.shell.python_console_widget import _CONT_PROMPT, _PROMPT, PythonConsoleWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
    def test_shows_idle_hint_on_construction(self, widget: PythonConsoleWidget) -> None:
        text = _get_plain_text(widget)
        assert "No active session" in text

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
