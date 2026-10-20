"""Completion popup behavior in the code editor (v0.4.13 owner-approved rules)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, Qt  # noqa: E402
from PySide2.QtGui import QKeyEvent, QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.intelligence.completion_matcher import ACCEPTANCE_RECENCY  # noqa: E402
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402

pytestmark = pytest.mark.unit

MEMBERS = ["setText", "setToolTip", "statusTip", "text", "toolTip", "show"]
_KEYS = {".": Qt.Key_Period, " ": Qt.Key_Space, "_": Qt.Key_Underscore, '"': Qt.Key_QuoteDbl, "#": Qt.Key_NumberSign}


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


class Requests:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, str]] = []

    def __call__(self, text: str, cursor: int, manual: bool, generation: int, kind: str, char: str) -> None:
        self.calls.append((text, cursor, generation, kind))


@pytest.fixture()
def requests() -> Requests:
    return Requests()


@pytest.fixture()
def editor(requests: Requests) -> Iterator[CodeEditorWidget]:
    ACCEPTANCE_RECENCY.clear()
    widget = CodeEditorWidget()
    widget.set_completion_requester(requests)
    widget.set_completion_mode("manual")
    yield widget
    widget._completion_popup.hide()
    widget.hide()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _key(widget: CodeEditorWidget, key: int, text: str = "", modifiers: Qt.KeyboardModifiers = Qt.NoModifier) -> None:
    widget.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, modifiers, text))


def _type(widget: CodeEditorWidget, text: str) -> None:
    for ch in text:
        _key(widget, _KEYS.get(ch, ord(ch.upper()) if ch.isalnum() else 0), ch)


def _ctrl_space(widget: CodeEditorWidget) -> None:
    _key(widget, Qt.Key_Space, " ", Qt.ControlModifier)


def _deliver(widget: CodeEditorWidget, requests: Requests, names: list[str] = MEMBERS) -> None:
    generation = requests.calls[-1][2]
    items = [CompletionItem(label=name, insert_text=name, kind=CompletionKind.METHOD) for name in names]
    widget.show_completion_items_for_request(request_generation=generation, prefix="", items=items)


def _start(widget: CodeEditorWidget, text: str) -> None:
    widget.setPlainText(text)
    widget.moveCursor(QTextCursor.End)


def _rows(widget: CodeEditorWidget) -> list[str]:
    popup = widget._completion_popup
    return popup.visible_labels(50) if popup.is_visible() else []


@pytest.mark.parametrize(
    ("mode", "typed", "expected_requests"),
    [
        ("manual", "btn.", 0),
        ("manual", "ab", 0),
        ("typing", "btn.", 2),
        ("typing", "ab", 1),
        ("off", "btn.", 0),
    ],
)
def test_each_mode_opens_only_when_it_should(
    editor: CodeEditorWidget, requests: Requests, mode: str, typed: str, expected_requests: int
) -> None:
    editor.set_completion_mode(mode)

    _type(editor, typed)

    assert len(requests.calls) == expected_requests


def test_while_typing_requests_the_whole_member_list_at_the_dot(editor: CodeEditorWidget, requests: Requests) -> None:
    editor.set_completion_mode("typing")
    _start(editor, "btn")

    _type(editor, ".")

    text, cursor, _generation, kind = requests.calls[-1]
    assert (text, cursor, kind) == ("btn.", 4, "trigger_character")


def test_off_mode_ctrl_space_only_shows_a_hint(editor: CodeEditorWidget, requests: Requests) -> None:
    editor.set_completion_mode("off")
    hints: list[str] = []
    editor.completion_status = hints.append  # type: ignore[method-assign]
    _start(editor, "btn.")

    _ctrl_space(editor)

    assert requests.calls == []
    assert hints and "off" in hints[0].lower()


@pytest.mark.parametrize("mode", ["manual", "typing"])
@pytest.mark.parametrize("text", ["x = 1.", 's = "a.', "# btn."])
def test_ctrl_space_never_opens_after_a_number_or_in_strings_and_comments(
    editor: CodeEditorWidget, requests: Requests, mode: str, text: str
) -> None:
    editor.set_completion_mode(mode)
    _start(editor, text)

    _ctrl_space(editor)

    assert requests.calls == []


def test_ctrl_space_lists_everything_then_filters_as_you_type(editor: CodeEditorWidget, requests: Requests) -> None:
    _start(editor, "btn.")
    _ctrl_space(editor)
    _deliver(editor, requests)

    assert len(_rows(editor)) == len(MEMBERS)

    _type(editor, "sT")

    assert _rows(editor)[0] == "setText"
    assert len(requests.calls) == 1


def test_a_list_that_arrives_after_more_typing_is_filtered_by_all_of_it(
    editor: CodeEditorWidget, requests: Requests
) -> None:
    _start(editor, "btn.")
    _ctrl_space(editor)
    _type(editor, "tool")

    _deliver(editor, requests)

    assert _rows(editor) == ["toolTip"]


def test_accept_replaces_only_the_typed_prefix(editor: CodeEditorWidget, requests: Requests) -> None:
    _start(editor, 'title = btn.te + "!"')
    cursor = editor.textCursor()
    cursor.setPosition(len("title = btn.te"))
    editor.setTextCursor(cursor)
    _ctrl_space(editor)
    _deliver(editor, requests)

    _type(editor, "x")
    _key(editor, Qt.Key_Return, "\r")

    assert editor.toPlainText() == 'title = btn.text + "!"'
    assert not editor._completion_popup.is_visible()


def test_tab_accepts_without_parentheses(editor: CodeEditorWidget, requests: Requests) -> None:
    _start(editor, "btn.setTe")
    _ctrl_space(editor)
    _deliver(editor, requests)

    _key(editor, Qt.Key_Tab, "\t")

    assert editor.toPlainText() == "btn.setText"


def test_no_match_closes_and_backspace_reopens(editor: CodeEditorWidget, requests: Requests) -> None:
    _start(editor, "btn.sT")
    _ctrl_space(editor)
    _deliver(editor, requests)

    _type(editor, "zz")
    assert not editor._completion_popup.is_visible()

    _key(editor, Qt.Key_Backspace)
    _key(editor, Qt.Key_Backspace)

    assert _rows(editor)[0] == "setText"
    assert len(requests.calls) == 1


def test_backspace_after_escape_stays_closed(editor: CodeEditorWidget, requests: Requests) -> None:
    _start(editor, "btn.sT")
    _ctrl_space(editor)
    _deliver(editor, requests)

    _key(editor, Qt.Key_Escape)
    _key(editor, Qt.Key_Backspace)

    assert not editor._completion_popup.is_visible()


def test_typing_the_whole_name_closes_the_list(editor: CodeEditorWidget, requests: Requests) -> None:
    _start(editor, "btn.setTex")
    _ctrl_space(editor)
    _deliver(editor, requests)

    _type(editor, "t")

    assert not editor._completion_popup.is_visible()


def test_picked_row_stays_selected_while_it_still_matches(editor: CodeEditorWidget, requests: Requests) -> None:
    _start(editor, "btn.s")
    _ctrl_space(editor)
    _deliver(editor, requests)
    first = editor._completion_popup.current_item()
    _key(editor, Qt.Key_Down)
    picked = editor._completion_popup.current_item()

    _type(editor, "t")

    assert first is not None and picked is not None and picked.label != first.label
    current = editor._completion_popup.current_item()
    assert current is not None and current.label == picked.label
