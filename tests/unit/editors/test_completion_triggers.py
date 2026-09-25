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
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


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


def test_shortened_prefix_refilters_from_base_without_redispatch(
    editor: CodeEditorWidget,
) -> None:
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
    _show_completion_popup(editor, [_symbol("abc"), _symbol("abd"), _symbol("xyz")], prefix="")
    assert editor._completion_popup.is_visible()
    assert editor._completion_popup.reuse_items_for_prefix("ab") is True
    assert [item.label for item in editor._completion_popup.model().items()] == ["abc", "abd"]

    editor.setPlainText("a")
    _set_cursor(editor, 1)
    editor.trigger_completion(manual=False)

    assert calls == []
    assert editor._completion_popup.is_visible()
    assert [item.label for item in editor._completion_popup.model().items()] == ["abc", "abd"]
    assert editor._completion_popup.model().prefix() == "a"


def test_backspace_refilters_toward_empty_prefix(editor: CodeEditorWidget) -> None:
    calls: list[object] = []
    editor.set_completion_requester(lambda *args: calls.append(args))
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(
        editor,
        [_symbol("abc"), _symbol("getcwd"), _symbol("getenv"), _symbol("getpid")],
        prefix="",
    )
    assert editor._completion_popup.is_visible()

    for typed, key in (("g", Qt.Key_G), ("e", Qt.Key_E), ("t", Qt.Key_T), ("c", Qt.Key_C)):
        editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, typed))
    assert [item.label for item in editor._completion_popup.model().items()] == ["getcwd"]
    assert editor.toPlainText() == "os.getc"

    for _ in range(4):
        editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))

    assert editor.toPlainText() == "os."
    assert editor._completion_popup.is_visible()
    assert [item.label for item in editor._completion_popup.model().items()] == [
        "abc",
        "getcwd",
        "getenv",
        "getpid",
    ]
    assert editor._completion_popup.model().prefix() == ""
    assert calls == []


def test_backspace_past_dot_closes_completion_popup(editor: CodeEditorWidget) -> None:
    editor.set_completion_requester(lambda *args: None)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(editor, [_symbol("getcwd"), _symbol("getenv")], prefix="")
    assert editor._completion_popup.is_visible()

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))

    assert editor.toPlainText() == "os"
    assert editor._completion_popup.is_visible() is False


def test_backspace_reopens_popup_after_no_match_close(editor: CodeEditorWidget) -> None:
    editor.show()
    items = [_symbol("getcwd"), _symbol("getenv")]

    def _requester(
        _source: str,
        _cursor: int,
        _manual: bool,
        request_generation: int,
        _trigger_kind: str,
        _trigger_character: str,
    ) -> None:
        editor.show_completion_items_for_request(
            request_generation=request_generation,
            prefix="",
            items=items,
        )

    editor.set_completion_requester(_requester)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(editor, items, prefix="")
    assert editor._completion_popup.is_visible()

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Z, Qt.NoModifier, "z"))
    assert editor._completion_popup.is_visible() is False
    assert editor._completion_popup.has_base_items() is False
    assert editor.toPlainText() == "os.z"

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))

    assert editor.toPlainText() == "os."
    assert editor._completion_popup.is_visible()
    assert [item.label for item in editor._completion_popup.model().items()] == [
        "getcwd",
        "getenv",
    ]


def test_backspace_without_prior_popup_does_not_request_completion(
    editor: CodeEditorWidget,
) -> None:
    requests: list[object] = []

    def _requester(*args: object) -> None:
        requests.append(args)

    editor.set_completion_requester(_requester)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("x = obj.valuee")
    _set_cursor(editor, len("x = obj.valuee"))

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))

    assert editor.toPlainText() == "x = obj.value"
    assert requests == []
    assert editor._completion_popup.is_visible() is False


def test_backspace_does_not_reopen_when_period_auto_trigger_disabled(
    editor: CodeEditorWidget,
) -> None:
    editor.set_completion_requester(lambda *args: None)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=False,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(editor, [_symbol("getcwd"), _symbol("getenv")], prefix="")
    assert editor._completion_popup.is_visible()

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Z, Qt.NoModifier, "z"))
    assert editor._completion_popup.is_visible() is False

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))

    assert editor.toPlainText() == "os."
    assert editor._completion_popup.is_visible() is False


def _dot_member_symbol(label: str, *, member_start: int = 3) -> CompletionItem:
    """Match live `.` trigger items: empty prefix with a collapsed replacement span."""

    return CompletionItem(
        label=label,
        insert_text=label,
        kind=CompletionKind.SYMBOL,
        replacement_start=member_start,
        replacement_end=member_start,
    )


def test_editor_dot_popup_tab_replaces_typed_prefix(editor: CodeEditorWidget) -> None:
    editor.show()
    editor.set_completion_requester(lambda *args: None)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(
        editor,
        [
            _dot_member_symbol("abc"),
            _dot_member_symbol("pardir"),
            _dot_member_symbol("path"),
            _dot_member_symbol("pathsep"),
        ],
        prefix="",
    )
    assert editor._completion_popup.is_visible()

    for typed, key in (("p", Qt.Key_P), ("a", Qt.Key_A)):
        editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, typed))
    current = editor._completion_popup.current_item()
    assert current is not None
    assert current.label == "pardir"

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier, ""))

    assert editor.toPlainText() == "os.pardir"
    assert editor._completion_popup.is_visible() is False


def test_editor_dot_popup_enter_replaces_typed_prefix(editor: CodeEditorWidget) -> None:
    editor.show()
    editor.set_completion_requester(lambda *args: None)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(
        editor,
        [
            _dot_member_symbol("pardir"),
            _dot_member_symbol("path"),
            _dot_member_symbol("pathsep"),
        ],
        prefix="",
    )

    for typed, key in (("p", Qt.Key_P), ("a", Qt.Key_A)):
        editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, typed))
    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "\n"))

    assert editor.toPlainText() == "os.pardir"
    assert editor._completion_popup.is_visible() is False


def test_dismissed_dot_popup_does_not_delete_across_lines_on_accept(
    editor: CodeEditorWidget,
) -> None:
    """Click-away must drop retained items so a later accept cannot wipe lines."""

    editor.show()
    editor.set_completion_requester(lambda *args: None)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(
        editor,
        [
            _dot_member_symbol("pardir"),
            _dot_member_symbol("path"),
            _dot_member_symbol("pathsep"),
        ],
        prefix="",
    )
    for typed, key in (("p", Qt.Key_P), ("a", Qt.Key_A)):
        editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, typed))
    editor._completion_popup.hide()
    assert editor._completion_popup.has_base_items() is False

    buffer = "os.pa\nfoo = sys.pat\nbar = 1\n"
    editor.setPlainText(buffer)
    _set_cursor(editor, len("os.pa\nfoo = sys.pat"))
    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))
    assert editor._completion_popup.is_visible() is False
    assert editor.toPlainText() == "os.pa\nfoo = sys.pa\nbar = 1\n"

    # Even if a stale popup were forced visible, accept must not widen past the
    # live identifier under the cursor.
    stale = _dot_member_symbol("path", member_start=3)
    editor._insert_completion_from_item(stale)
    assert editor.toPlainText() == "os.pa\nfoo = sys.path\nbar = 1\n"
    assert "bar = 1" in editor.toPlainText()


def test_space_dismissed_dot_popup_does_not_delete_following_line_on_tab(
    editor: CodeEditorWidget,
) -> None:
    editor.show()
    editor.set_completion_requester(lambda *args: None)
    editor.set_completion_preferences(
        enabled=True,
        auto_trigger=False,
        min_chars=2,
        auto_trigger_period=True,
    )
    editor.setPlainText("os.")
    _set_cursor(editor, 3)
    _show_completion_popup(
        editor,
        [
            _dot_member_symbol("pardir"),
            _dot_member_symbol("path"),
            _dot_member_symbol("pathsep"),
        ],
        prefix="",
    )
    for typed, key in (("p", Qt.Key_P), ("a", Qt.Key_A)):
        editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, typed))
    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " "))
    assert editor._completion_popup.is_visible() is False
    assert editor._completion_popup.has_base_items() is False

    editor.setPlainText("os.pa \nfoo = x.pat")
    _set_cursor(editor, len("os.pa \nfoo = x.pat"))
    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))
    assert editor._completion_popup.is_visible() is False
    assert editor.toPlainText() == "os.pa \nfoo = x.pa"

    stale = _dot_member_symbol("pardir", member_start=3)
    editor._insert_completion_from_item(stale)
    assert editor.toPlainText() == "os.pa \nfoo = x.pardir"
    assert editor.toPlainText().startswith("os.pa")


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
