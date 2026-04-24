"""Unit tests for CodeEditorWidget completion trigger behavior."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, Qt  # noqa: E402
from PySide2.QtGui import QKeyEvent  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def editor() -> CodeEditorWidget:
    widget = CodeEditorWidget()
    widget.setPlainText("value = 1\n")
    return widget


def test_ctrl_space_triggers_manual_completion_even_when_auto_trigger_disabled(editor: CodeEditorWidget) -> None:
    editor.set_completion_preferences(enabled=True, auto_trigger=False, min_chars=2)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.ControlModifier, " ")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    trigger_completion.assert_called_once_with(manual=True)


def test_typing_identifier_does_not_trigger_completion_when_auto_trigger_disabled(editor: CodeEditorWidget) -> None:
    editor.set_completion_preferences(enabled=True, auto_trigger=False, min_chars=2)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier, "a")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    trigger_completion.assert_not_called()


def test_typing_identifier_triggers_completion_when_auto_trigger_enabled(editor: CodeEditorWidget) -> None:
    editor.set_completion_preferences(enabled=True, auto_trigger=True, min_chars=2)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier, "a")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    trigger_completion.assert_called_once_with(manual=False)


def test_typing_dot_triggers_manual_completion_with_empty_prefix(editor: CodeEditorWidget) -> None:
    editor.set_completion_preferences(enabled=True, auto_trigger=True, min_chars=2)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Period, Qt.NoModifier, ".")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    trigger_completion.assert_called_once_with(manual=True, force_empty_prefix=True)


def test_typing_dot_does_not_trigger_completion_when_auto_trigger_disabled(editor: CodeEditorWidget) -> None:
    editor.set_completion_preferences(enabled=True, auto_trigger=False, min_chars=2)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Period, Qt.NoModifier, ".")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    trigger_completion.assert_not_called()
