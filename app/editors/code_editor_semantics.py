"""Completion, hover, and signature-help behavior for CodeEditorWidget."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Tuple

from app.qt.QtCore import QRect, Qt
from app.qt.QtGui import QKeyEvent, QTextCursor
from app.qt.QtWidgets import QMainWindow, QToolTip

from app.editors.completion_popup import CompletionController
from app.editors.completion_popup.completion_replacement import resolve_insert_replacement_range
from app.intelligence.completion_mode import COMPLETION_MODE_DEFAULT, normalize_completion_mode
from app.intelligence.completion_models import CompletionItem
from app.shell.editor_completion_contracts import CompletionRequester

_STATUS_TIMEOUT_MS = 4000


if TYPE_CHECKING:
    from app.qt.QtCore import QPoint
    from app.qt.QtWidgets import QPlainTextEdit

    class _CodeEditorSemanticsBase(QPlainTextEdit):
        _completion_requester: CompletionRequester | None
        _completion_resolve_requester: Callable[[CompletionItem, str, int, int], None] | None
        _completion_accepted_callback: Callable[[CompletionItem], None] | None
        _hover_requester: Callable[[str, int, int], None] | None
        _signature_help_provider: Callable[[str, int], str | None] | None
        _signature_help_requester: Callable[[str, int, int], None] | None
        _completion_min_chars: int
        _completion_request_generation: int
        _hover_request_generation: int
        _hover_request_global_pos: QPoint | None
        _hover_tooltip_enabled: bool
        _signature_help_request_generation: int
        _completion_popup: CompletionController
        @property
        def _active_file_path(self) -> str | None: ...

        def indent_selection(self) -> None: ...
        def outdent_selection(self) -> None: ...
        def _handle_smart_backspace(self) -> bool: ...
        def _insert_newline_with_auto_indent(self) -> None: ...
else:
    class _CodeEditorSemanticsBase:
        pass


class CodeEditorSemanticsMixin(_CodeEditorSemanticsBase):
    """Semantic UI behavior split out from the main editor widget."""

    def allocate_signature_help_request_generation(self) -> int:
        """Return a new signature-help request generation token."""
        self._signature_help_request_generation += 1
        return self._signature_help_request_generation

    def allocate_hover_request_generation(self) -> int:
        """Return a new hover request generation token."""
        self._hover_request_generation += 1
        return self._hover_request_generation

    def set_completion_requester(
        self,
        requester: CompletionRequester | None,
    ) -> None:
        """Attach asynchronous completion requester callback."""
        self._completion_requester = requester

    def set_completion_resolve_requester(
        self,
        requester: Callable[[CompletionItem, str, int, int], None] | None,
    ) -> None:
        """Attach async lazy metadata resolver for selected completion items."""
        self._completion_resolve_requester = requester

    def set_completion_docs_resolving(self, resolving: bool) -> None:
        """Toggle the completion docs panel loading state."""

        self._completion_popup.set_docs_resolving(resolving)

    def set_completion_accepted_callback(self, callback: Callable[[CompletionItem], None] | None) -> None:
        """Attach callback invoked when completion item is accepted."""
        self._completion_accepted_callback = callback

    def set_hover_requester(self, requester: Callable[[str, int, int], None] | None) -> None:
        """Attach asynchronous hover requester used by tooltip interactions."""
        self._hover_requester = requester

    def set_signature_help_provider(self, provider: Callable[[str, int], str | None] | None) -> None:
        """Attach signature-help provider used by inline calltips."""
        self._signature_help_provider = provider

    def set_signature_help_requester(self, requester: Callable[[str, int, int], None] | None) -> None:
        """Attach asynchronous signature-help requester used by inline calltips."""
        self._signature_help_requester = requester

    def set_completion_mode(self, mode: str) -> None:
        """Apply the code-completion mode: ``off``, ``manual`` or ``typing``."""

        self._completion_popup.set_mode(mode)

    def completion_mode(self) -> str:
        return self._completion_popup.mode()

    def set_completion_preferences(self, *, mode: str, min_chars: int) -> None:
        """Apply the completion mode and the minimum typed length."""

        self._completion_min_chars = max(1, min_chars)
        self.set_completion_mode(normalize_completion_mode(mode) or COMPLETION_MODE_DEFAULT)

    def trigger_completion(self, *, manual: bool = True, **_ignored: object) -> None:
        """Open the completion list at the cursor, as Ctrl+Space does."""

        _ = manual
        self._completion_popup.open_manual()

    # ------------------------------------------------------------------
    # CompletionHost
    # ------------------------------------------------------------------

    def completion_text_and_cursor(self) -> Tuple[str, int]:
        return self.toPlainText(), self.textCursor().position()

    def completion_anchor_rect(self, position: int) -> QRect:
        cursor = QTextCursor(self.document())
        cursor.setPosition(max(0, min(position, self.document().characterCount() - 1)))
        return self.cursorRect(cursor).translated(self.viewport().pos())

    def completion_dispatch(self, text: str, cursor: int, trigger_kind: str, trigger_character: str) -> int:
        self._completion_request_generation += 1
        generation = self._completion_request_generation
        if self._completion_requester is not None:
            self._completion_requester(text, cursor, True, generation, trigger_kind, trigger_character)
        return generation

    def completion_status(self, message: str) -> None:
        window = self.window()
        if isinstance(window, QMainWindow):
            window.statusBar().showMessage(message, _STATUS_TIMEOUT_MS)
            return
        QToolTip.showText(self.mapToGlobal(self.cursorRect().bottomLeft()), message, self)

    # ------------------------------------------------------------------
    # Async results
    # ------------------------------------------------------------------

    def _request_completion_item_resolution(self, item: object) -> None:
        if not isinstance(item, CompletionItem) or not item.resolvable_fields:
            return
        if self._completion_resolve_requester is None:
            return
        site = self._completion_popup.site()
        if site is None:
            return
        # Ask about the full label at the expression's anchor, so engines that
        # filter by the typed prefix still find camelCase picks such as statusTip.
        text = self.toPlainText()
        cursor = self.textCursor().position()
        probe_text = text[: site.anchor] + item.label + text[cursor:]
        self._completion_popup.set_docs_resolving(True)
        self._completion_resolve_requester(
            item,
            probe_text,
            site.anchor + len(item.label),
            self._completion_request_generation,
        )

    def show_resolved_completion_item_for_request(
        self,
        *,
        request_generation: int,
        item: CompletionItem,
    ) -> None:
        """Apply lazy metadata for the selected item if still current."""
        if request_generation != self._completion_request_generation:
            return
        self._completion_popup.set_docs_resolving(False)
        self._completion_popup.replace_item(item)

    def completion_request_generation(self) -> int:
        """Return the current completion request generation counter."""
        return self._completion_request_generation

    def hover_request_generation(self) -> int:
        """Return the current inline hover request generation counter."""
        return self._hover_request_generation

    def signature_help_request_generation(self) -> int:
        """Return the current inline signature-help request generation counter."""
        return self._signature_help_request_generation

    def show_completion_items_for_request(
        self,
        *,
        request_generation: int,
        prefix: str,
        items: list[CompletionItem],
    ) -> None:
        """Apply an async completion list if it still belongs to the open request."""
        _ = prefix
        self._completion_popup.deliver_items(request_generation, items)

    def show_calltip(self, text: str | None) -> None:
        """Show or hide inline calltip near the cursor."""
        if not text:
            QToolTip.hideText()
            return
        QToolTip.showText(self.mapToGlobal(self.cursorRect().bottomRight()), text, self)

    def show_hover_text_for_request(self, *, request_generation: int, text: str | None) -> None:
        """Apply hover tooltip result if the request is still current."""
        if request_generation != self._hover_request_generation:
            return
        if not self._hover_tooltip_enabled:
            QToolTip.hideText()
            return
        if not text:
            QToolTip.hideText()
            return
        global_pos = self._hover_request_global_pos or self.mapToGlobal(self.cursorRect().center())
        QToolTip.showText(global_pos, text, self)

    def show_calltip_for_request(self, *, request_generation: int, text: str | None) -> None:
        """Apply signature-help result if the request is still current."""
        if request_generation != self._signature_help_request_generation:
            return
        self.show_calltip(text)

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802 - Qt signature
        popup = self._completion_popup
        if popup.handle_key_press(e):
            return

        if e.key() == Qt.Key_Tab and not e.modifiers():
            self.indent_selection()
            e.accept()
            return
        if e.key() == Qt.Key_Backtab:
            self.outdent_selection()
            e.accept()
            return
        if e.key() == Qt.Key_Backspace and not e.modifiers():
            with popup.editing():
                handled = self._handle_smart_backspace()
            if handled:
                e.accept()
                popup.after_backspace()
                return
        if e.key() in {Qt.Key_Return, Qt.Key_Enter} and not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            with popup.editing():
                self._insert_newline_with_auto_indent()
            popup.after_text_input("\n")
            e.accept()
            return

        with popup.editing():
            super().keyPressEvent(e)
        if e.key() == Qt.Key_Backspace:
            popup.after_backspace()
            return

        inserted_text = e.text()
        if inserted_text in {"(", ","}:
            self._show_signature_help()
        elif inserted_text == ")":
            QToolTip.hideText()
        if inserted_text and inserted_text.isprintable():
            popup.after_text_input(inserted_text)

    def _on_completion_cursor_moved(self) -> None:
        self._completion_popup.on_cursor_moved()

    def _hide_completion_popup(self) -> None:
        self._completion_popup.hide()

    def _show_signature_help(self) -> None:
        if self._signature_help_requester is not None:
            self._signature_help_requester_call()
            return
        if self._signature_help_provider is None:
            return
        self.show_calltip(self._signature_help_provider(self.toPlainText(), self.textCursor().position()))

    def _signature_help_requester_call(self) -> None:
        if self._signature_help_requester is None:
            return
        self._signature_help_request_generation += 1
        self._signature_help_requester(
            self.toPlainText(),
            self.textCursor().position(),
            self._signature_help_request_generation,
        )

    def _insert_completion_from_item(self, item: object) -> None:
        if not isinstance(item, CompletionItem):
            return
        cursor = self.textCursor()
        source_text = self.toPlainText()
        start, end = resolve_insert_replacement_range(source_text, cursor.position())
        with self._completion_popup.editing():
            if start < end:
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            cursor.insertText(item.label)
            self.setTextCursor(cursor)
        if self._completion_accepted_callback is not None:
            self._completion_accepted_callback(item)
