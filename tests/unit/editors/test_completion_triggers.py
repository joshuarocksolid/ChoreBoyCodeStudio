"""Unit tests for CodeEditorWidget completion trigger behavior."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, Qt  # noqa: E402
from PySide2.QtGui import QKeyEvent  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.core.constants import UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT  # noqa: E402
from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def editor() -> Iterator[CodeEditorWidget]:
    widget = CodeEditorWidget()
    widget.setPlainText("value = 1\n")
    yield widget
    widget._completion_debounce_timer.stop()
    widget._completion_popup.hide()
    widget.hide()
    widget.deleteLater()


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
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=False,
    )
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Period, Qt.NoModifier, ".")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    trigger_completion.assert_not_called()


def test_typing_dot_triggers_completion_when_period_auto_trigger_enabled(editor: CodeEditorWidget) -> None:
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Period, Qt.NoModifier, ".")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    trigger_completion.assert_called_once_with(manual=True, force_empty_prefix=True)


def _set_cursor(editor: CodeEditorWidget, position: int) -> None:
    cursor = editor.textCursor()
    cursor.setPosition(position)
    editor.setTextCursor(cursor)


def _symbol(label: str) -> CompletionItem:
    return CompletionItem(label=label, insert_text=label, kind=CompletionKind.SYMBOL)


def _show_completion_popup(
    editor: CodeEditorWidget,
    items: list[CompletionItem],
    *,
    prefix: str,
) -> None:
    editor.show_completion_items_for_request(
        request_generation=editor.completion_request_generation(),
        prefix=prefix,
        items=items,
    )
    if not editor._completion_popup.is_visible():
        editor._completion_popup.popup().show()


@pytest.mark.parametrize(
    ("source", "cursor_position", "triggers"),
    [
        ("value = 0", len("value = 0"), False),
        ("1", 1, False),
        ("314", 1, False),
        ("obj", 3, True),
        ("foo1", 4, True),
        (")", 1, True),
    ],
)
def test_period_auto_trigger_skips_numeric_literals(
    editor: CodeEditorWidget,
    source: str,
    cursor_position: int,
    triggers: bool,
) -> None:
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText(source)
    _set_cursor(editor, cursor_position)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Period, Qt.NoModifier, ".")

    with patch.object(editor, "trigger_completion") as trigger_completion:
        editor.keyPressEvent(event)

    if triggers:
        trigger_completion.assert_called_once_with(manual=True, force_empty_prefix=True)
    else:
        trigger_completion.assert_not_called()


@pytest.mark.parametrize(
    ("typed", "key", "kept_label"),
    [
        ("a", Qt.Key_A, "alpha"),
        ("_", Qt.Key_Underscore, "_private"),
    ],
)
def test_visible_popup_filters_word_character_when_auto_trigger_disabled(
    editor: CodeEditorWidget,
    typed: str,
    key: Qt.Key,
    kept_label: str,
) -> None:
    calls: list[object] = []
    editor.set_completion_requester(lambda *args: calls.append(args))
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("")
    _set_cursor(editor, 0)
    _show_completion_popup(
        editor,
        [_symbol("alpha"), _symbol("beta"), _symbol("_private")],
        prefix="",
    )
    assert editor._completion_popup.is_visible()

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, typed))

    labels = [item.label for item in editor._completion_popup.model().items()]
    current = editor._completion_popup.current_item()
    assert editor._completion_popup.is_visible()
    assert labels == [kept_label]
    assert current is not None
    assert current.label == kept_label
    assert calls == []


def test_visible_popup_hides_when_typed_prefix_matches_nothing(editor: CodeEditorWidget) -> None:
    calls: list[object] = []
    editor.set_completion_requester(lambda *args: calls.append(args))
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("")
    _set_cursor(editor, 0)
    _show_completion_popup(editor, [_symbol("alpha"), _symbol("beta")], prefix="")
    assert editor._completion_popup.is_visible()

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Z, Qt.NoModifier, "z"))

    assert editor._completion_popup.is_visible() is False
    assert calls == []


def test_prefix_reuse_invalidates_stale_empty_prefix_paint(editor: CodeEditorWidget) -> None:
    editor.set_completion_requester(lambda *args: None)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("")
    _set_cursor(editor, 0)
    stale_generation = editor.completion_request_generation()
    _show_completion_popup(
        editor,
        [_symbol("alpha"), _symbol("beta"), _symbol("gamma")],
        prefix="",
    )

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier, "a"))
    labels_after_filter = [item.label for item in editor._completion_popup.model().items()]
    assert labels_after_filter == ["alpha"]
    assert editor.completion_request_generation() == stale_generation + 1

    editor.show_completion_items_for_request(
        request_generation=stale_generation,
        prefix="",
        items=[_symbol("alpha"), _symbol("beta"), _symbol("gamma")],
    )

    assert [item.label for item in editor._completion_popup.model().items()] == ["alpha"]
    assert editor._completion_popup.is_visible()


def test_visible_popup_hides_on_space_when_auto_trigger_disabled(editor: CodeEditorWidget) -> None:
    calls: list[object] = []
    editor.set_completion_requester(lambda *args: calls.append(args))
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("obj")
    _set_cursor(editor, 3)
    _show_completion_popup(editor, [_symbol("object")], prefix="obj")
    assert editor._completion_popup.is_visible()

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " "))

    assert editor._completion_popup.is_visible() is False
    assert calls == []


def test_shortened_prefix_redispatches_completion(editor: CodeEditorWidget) -> None:
    calls: list[object] = []
    editor.set_completion_requester(lambda *args: calls.append(args))
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("ab")
    _set_cursor(editor, 2)
    _show_completion_popup(editor, [_symbol("abc"), _symbol("abd")], prefix="ab")
    assert editor._completion_popup.is_visible()

    editor.setPlainText("a")
    _set_cursor(editor, 1)
    editor.trigger_completion(manual=False)

    assert len(calls) == 1
    assert editor._completion_popup.is_visible()


def test_editor_completion_context_uses_raised_max_results(editor: CodeEditorWidget) -> None:
    context = editor._build_editor_completion_context(
        source_text="obj.",
        cursor_position=4,
        manual=False,
        force_empty_prefix=False,
        trigger_kind="typing",
        trigger_character="",
    )

    assert context.max_results == UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT == 500
