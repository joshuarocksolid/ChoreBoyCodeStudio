"""Unit tests for async completion and inline semantic editor interactions."""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, Qt  # noqa: E402
from PySide2.QtGui import QHelpEvent, QKeyEvent  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402
from app.shell.theme_tokens import ShellThemeTokens  # noqa: E402

pytestmark = pytest.mark.unit

_LIGHT_TOKENS = ShellThemeTokens(
    window_bg="#F8F9FA",
    panel_bg="#FFFFFF",
    editor_bg="#FFFFFF",
    text_primary="#212529",
    text_muted="#495057",
    border="#CED4DA",
    accent="#3366FF",
    gutter_bg="#F1F3F5",
    gutter_text="#6C757D",
    line_highlight="#EEF7FF",
    is_dark=False,
)

_DARK_TOKENS = ShellThemeTokens(
    window_bg="#1F2428",
    panel_bg="#262C33",
    editor_bg="#1B1F23",
    text_primary="#E9ECEF",
    text_muted="#ADB5BD",
    border="#3C434A",
    accent="#5B8CFF",
    gutter_bg="#1F2428",
    gutter_text="#6C757D",
    line_highlight="#252B33",
    is_dark=True,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def editor() -> CodeEditorWidget:
    widget = CodeEditorWidget()
    widget.setPlainText("alpha")
    cursor = widget.textCursor()
    cursor.movePosition(cursor.End)
    widget.setTextCursor(cursor)
    return widget


def test_trigger_completion_uses_async_requester_when_available(editor: CodeEditorWidget) -> None:
    calls: list[tuple[str, str, int, bool, int]] = []
    editor.set_completion_requester(lambda prefix, source, position, manual, generation: calls.append((prefix, source, position, manual, generation)))
    editor.set_completion_provider(lambda *_args: pytest.fail("sync provider should not be used"))

    editor.trigger_completion(manual=True)

    assert calls == [("alpha", "alpha", 5, True, 1)]


def test_show_completion_items_for_stale_generation_is_ignored(editor: CodeEditorWidget) -> None:
    editor.set_completion_requester(lambda *_args: None)
    editor.trigger_completion(manual=True)
    editor.trigger_completion(manual=True)

    editor.show_completion_items_for_request(
        request_generation=1,
        prefix="alpha",
        items=[CompletionItem(label="alpha_local", insert_text="alpha_local", kind=CompletionKind.SYMBOL)],
    )

    assert editor._completion_items_by_label == {}


def test_show_completion_items_for_current_generation_updates_mapping(editor: CodeEditorWidget) -> None:
    editor.set_completion_requester(lambda *_args: None)
    editor.trigger_completion(manual=True)

    editor.show_completion_items_for_request(
        request_generation=1,
        prefix="alpha",
        items=[CompletionItem(label="alpha_local", insert_text="alpha_local", kind=CompletionKind.SYMBOL)],
    )

    assert "alpha_local" in editor._completion_items_by_label


def test_typing_open_paren_shows_inline_signature_help(editor: CodeEditorWidget) -> None:
    editor.set_signature_help_provider(lambda _source, _position: "helper(alpha)")
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")

    with patch.object(editor, "show_calltip") as show_calltip:
        editor.keyPressEvent(event)

    show_calltip.assert_called_once_with("helper(alpha)")


def test_tooltip_event_uses_hover_provider_when_no_diagnostic(editor: CodeEditorWidget) -> None:
    editor.set_hover_provider(lambda _source, _position: "Symbol: alpha")
    event = QHelpEvent(QEvent.ToolTip, editor.cursorRect().center(), editor.mapToGlobal(editor.cursorRect().center()))

    with patch("app.editors.code_editor_widget.QToolTip.showText") as show_text:
        handled = editor.event(event)

    assert handled is True
    show_text.assert_called_once()


def test_semantic_ui_theme_sanity_for_light_and_dark_modes(editor: CodeEditorWidget) -> None:
    editor.set_completion_requester(lambda *_args: None)
    editor.trigger_completion(manual=True)
    editor.show_completion_items_for_request(
        request_generation=1,
        prefix="alpha",
        items=[CompletionItem(label="alpha_local", insert_text="alpha_local", kind=CompletionKind.SYMBOL)],
    )

    editor.apply_theme(_LIGHT_TOKENS)
    assert editor._is_dark is False
    assert "alpha_local" in editor._completion_items_by_label

    editor.apply_theme(_DARK_TOKENS)
    assert editor._is_dark is True
    editor.show_calltip("Symbol: alpha")
