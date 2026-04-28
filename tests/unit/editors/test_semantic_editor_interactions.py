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
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


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

    assert editor._completion_popup.model().rowCount() == 0


def test_show_completion_items_for_current_generation_updates_mapping(editor: CodeEditorWidget) -> None:
    editor.set_completion_requester(lambda *_args: None)
    editor.trigger_completion(manual=True)

    editor.show_completion_items_for_request(
        request_generation=1,
        prefix="alpha",
        items=[CompletionItem(label="alpha_local", insert_text="alpha_local", kind=CompletionKind.SYMBOL)],
    )

    labels = [item.label for item in editor._completion_popup.model().items()]
    assert "alpha_local" in labels


def test_completion_selection_requests_lazy_resolution(editor: CodeEditorWidget) -> None:
    calls: list[tuple[str, str, int, int]] = []
    item = CompletionItem(
        label="alpha_local",
        insert_text="alpha_local",
        kind=CompletionKind.SYMBOL,
        source="semantic",
        resolve_provider="jedi",
        resolvable_fields=("documentation",),
    )
    editor.set_completion_requester(lambda *_args: None)
    editor.set_completion_resolve_requester(
        lambda selected, source, position, generation: calls.append(
            (selected.label, source, position, generation)
        )
    )
    editor.trigger_completion(manual=True)

    editor.show_completion_items_for_request(request_generation=1, prefix="alpha", items=[item])

    assert calls == [("alpha_local", "alpha", 5, 1)]


def test_show_resolved_completion_item_updates_visible_model(editor: CodeEditorWidget) -> None:
    item = CompletionItem(
        label="alpha_local",
        insert_text="alpha_local",
        kind=CompletionKind.SYMBOL,
        source="semantic",
        item_id="item-1",
        resolve_provider="jedi",
        resolvable_fields=("documentation",),
    )
    resolved = CompletionItem(
        label="alpha_local",
        insert_text="alpha_local",
        kind=CompletionKind.SYMBOL,
        documentation="Resolved docs",
        source="semantic",
        item_id="item-1",
        resolve_provider="jedi",
        resolvable_fields=("documentation",),
    )
    editor.set_completion_requester(lambda *_args: None)
    editor.trigger_completion(manual=True)
    editor.show_completion_items_for_request(request_generation=1, prefix="alpha", items=[item])

    editor.show_resolved_completion_item_for_request(request_generation=1, item=resolved)

    assert editor._completion_popup.model().items()[0].documentation == "Resolved docs"


def test_typing_open_paren_shows_inline_signature_help(editor: CodeEditorWidget) -> None:
    editor.set_signature_help_provider(lambda _source, _position: "helper(alpha)")
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")

    with patch.object(editor, "show_calltip") as show_calltip:
        editor.keyPressEvent(event)

    show_calltip.assert_called_once_with("helper(alpha)")


def test_tooltip_event_uses_hover_provider_when_no_diagnostic(editor: CodeEditorWidget) -> None:
    editor._hover_tooltip_enabled = True
    editor.set_hover_provider(lambda _source, _position: "Symbol: alpha")
    event = QHelpEvent(QEvent.ToolTip, editor.cursorRect().center(), editor.mapToGlobal(editor.cursorRect().center()))

    with patch("app.editors.code_editor_diagnostics.QToolTip.showText") as show_text:
        handled = editor.event(event)

    assert handled is True
    show_text.assert_called_once()


def test_typing_open_paren_uses_async_signature_requester_when_available(editor: CodeEditorWidget) -> None:
    calls: list[tuple[str, int, int]] = []
    editor.set_signature_help_requester(
        lambda source, position, generation: calls.append((source, position, generation))
    )
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")

    editor.keyPressEvent(event)

    assert calls == [("alpha(", 6, 1)]


def test_tooltip_event_uses_async_hover_requester_when_available(editor: CodeEditorWidget) -> None:
    editor._hover_tooltip_enabled = True
    calls: list[tuple[str, int, int]] = []
    editor.set_hover_requester(lambda source, position, generation: calls.append((source, position, generation)))
    event = QHelpEvent(QEvent.ToolTip, editor.cursorRect().center(), editor.mapToGlobal(editor.cursorRect().center()))

    handled = editor.event(event)

    assert handled is True
    assert calls == [("alpha", 5, 1)]


def test_tooltip_event_skips_hover_requester_when_hover_tooltip_disabled(editor: CodeEditorWidget) -> None:
    editor._hover_tooltip_enabled = False
    requester_calls: list[tuple[str, int, int]] = []
    editor.set_hover_requester(
        lambda source, position, generation: requester_calls.append((source, position, generation))
    )
    editor.set_hover_provider(lambda _source, _position: "Symbol: alpha")
    event = QHelpEvent(
        QEvent.ToolTip,
        editor.cursorRect().center(),
        editor.mapToGlobal(editor.cursorRect().center()),
    )

    with patch("app.editors.code_editor_diagnostics.QToolTip.showText") as show_text:
        handled = editor.event(event)

    assert handled is True
    assert requester_calls == []
    show_text.assert_not_called()


def test_tooltip_event_still_shows_diagnostic_when_hover_tooltip_disabled(editor: CodeEditorWidget) -> None:
    from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity

    editor._hover_tooltip_enabled = False
    editor.set_hover_provider(lambda _source, _position: pytest.fail("hover provider must not be consulted"))
    editor.set_diagnostics(
        [
            CodeDiagnostic(
                code="T001",
                severity=DiagnosticSeverity.WARNING,
                file_path="/tmp/main.py",
                line_number=1,
                message="warning",
                col_start=0,
                col_end=5,
            )
        ]
    )
    cursor_at_start = editor.textCursor()
    cursor_at_start.setPosition(1)
    editor.setTextCursor(cursor_at_start)
    pos = editor.cursorRect().topLeft()
    event = QHelpEvent(QEvent.ToolTip, pos, editor.mapToGlobal(pos))

    with patch("app.editors.code_editor_diagnostics.QToolTip.showText") as show_text:
        handled = editor.event(event)

    assert handled is True
    show_text.assert_called_once()
    args, _kwargs = show_text.call_args
    assert "[T001] warning" in args[1]


def test_show_calltip_for_stale_signature_request_is_ignored(editor: CodeEditorWidget) -> None:
    editor.set_signature_help_requester(lambda *_args: None)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_ParenLeft, Qt.NoModifier, "(")
    editor.keyPressEvent(event)

    with patch.object(editor, "show_calltip") as show_calltip:
        editor.show_calltip_for_request(request_generation=2, text="helper(alpha)")

    show_calltip.assert_not_called()


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
    light_labels = [item.label for item in editor._completion_popup.model().items()]
    assert "alpha_local" in light_labels

    editor.apply_theme(_DARK_TOKENS)
    assert editor._is_dark is True
    editor.show_calltip("Symbol: alpha")


def test_apply_theme_defers_hidden_editor_rehighlight_until_show(editor: CodeEditorWidget) -> None:
    class _FakeHighlighter:
        def __init__(self) -> None:
            self.rehighlight_calls = 0
            self.theme_calls: list[bool] = []

        def set_theme_palette(self, _palette, *, is_dark=None, rehighlight: bool = True) -> None:
            self.theme_calls.append(rehighlight)

        def rehighlight(self) -> None:
            self.rehighlight_calls += 1

    fake_highlighter = _FakeHighlighter()
    editor._highlighter = fake_highlighter

    assert editor.isVisible() is False

    editor.apply_theme(_DARK_TOKENS)

    assert fake_highlighter.theme_calls == [False]
    assert fake_highlighter.rehighlight_calls == 0
    assert editor._syntax_theme_refresh_pending is True

    editor.show()
    QApplication.processEvents()

    assert fake_highlighter.rehighlight_calls == 1
    assert editor._syntax_theme_refresh_pending is False
