"""Completion, hover, and signature-help behavior for CodeEditorWidget."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from PySide2.QtCore import Qt
from PySide2.QtGui import QKeyEvent, QTextCursor
from PySide2.QtWidgets import QToolTip

from app.editors.completion_popup import CompletionController
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_providers import extract_completion_prefix


if TYPE_CHECKING:
    from PySide2.QtCore import QPoint
    from PySide2.QtWidgets import QPlainTextEdit

    class _CodeEditorSemanticsBase(QPlainTextEdit):
        _completion_provider: Callable[[str, str, int, bool], list[CompletionItem]] | None
        _completion_requester: Callable[[str, str, int, bool, int, str, str], None] | None
        _completion_resolve_requester: Callable[[CompletionItem, str, int, int], None] | None
        _completion_accepted_callback: Callable[[CompletionItem], None] | None
        _hover_provider: Callable[[str, int], str | None] | None
        _hover_requester: Callable[[str, int, int], None] | None
        _signature_help_provider: Callable[[str, int], str | None] | None
        _signature_help_requester: Callable[[str, int, int], None] | None
        _completion_enabled: bool
        _completion_auto_trigger: bool
        _completion_min_chars: int
        _completion_request_generation: int
        _pending_completion_trigger_character: str
        _hover_request_generation: int
        _hover_request_global_pos: QPoint | None
        _hover_tooltip_enabled: bool
        _signature_help_request_generation: int
        _completion_popup: CompletionController

        def indent_selection(self) -> None: ...
        def outdent_selection(self) -> None: ...
        def _handle_smart_backspace(self) -> bool: ...
        def _insert_newline_with_auto_indent(self) -> None: ...
else:
    class _CodeEditorSemanticsBase:
        pass


class CodeEditorSemanticsMixin(_CodeEditorSemanticsBase):
    """Semantic UI behavior split out from the main editor widget."""

    def set_completion_provider(self, provider: Callable[[str, str, int, bool], list[CompletionItem]] | None) -> None:
        """Attach completion provider callback invoked during editor typing."""
        self._completion_provider = provider

    def set_completion_requester(
        self,
        requester: Callable[[str, str, int, bool, int, str, str], None] | None,
    ) -> None:
        """Attach asynchronous completion requester callback."""
        self._completion_requester = requester

    def set_completion_resolve_requester(
        self,
        requester: Callable[[CompletionItem, str, int, int], None] | None,
    ) -> None:
        """Attach async lazy metadata resolver for selected completion items."""
        self._completion_resolve_requester = requester

    def set_completion_accepted_callback(self, callback: Callable[[CompletionItem], None] | None) -> None:
        """Attach callback invoked when completion item is accepted."""
        self._completion_accepted_callback = callback

    def set_hover_provider(self, provider: Callable[[str, int], str | None] | None) -> None:
        """Attach hover provider used by tooltip interactions."""
        self._hover_provider = provider

    def set_hover_requester(self, requester: Callable[[str, int, int], None] | None) -> None:
        """Attach asynchronous hover requester used by tooltip interactions."""
        self._hover_requester = requester

    def set_signature_help_provider(self, provider: Callable[[str, int], str | None] | None) -> None:
        """Attach signature-help provider used by inline calltips."""
        self._signature_help_provider = provider

    def set_signature_help_requester(self, requester: Callable[[str, int, int], None] | None) -> None:
        """Attach asynchronous signature-help requester used by inline calltips."""
        self._signature_help_requester = requester

    def set_completion_preferences(self, *, enabled: bool, auto_trigger: bool, min_chars: int) -> None:
        """Apply completion behavior preferences."""
        self._completion_enabled = enabled
        self._completion_auto_trigger = auto_trigger
        self._completion_min_chars = max(1, min_chars)
        if not enabled:
            self._completion_popup.hide()

    def trigger_completion(
        self,
        *,
        manual: bool,
        force_empty_prefix: bool = False,
        trigger_character: str = "",
    ) -> None:
        """Request and display completion candidates at current cursor location."""
        if not self._completion_enabled:
            return
        source_text = self.toPlainText()
        cursor_position = self.textCursor().position()
        prefix = extract_completion_prefix(source_text, cursor_position)
        if not force_empty_prefix and not manual and len(prefix) < self._completion_min_chars:
            self._completion_popup.hide()
            return

        if self._completion_requester is not None:
            self._completion_request_generation += 1
            request_generation = self._completion_request_generation
            if self._completion_popup.is_visible():
                self._completion_popup.reuse_items_for_prefix(prefix)
            effective_trigger_character = trigger_character or self._pending_completion_trigger_character
            trigger_kind = "trigger_character" if effective_trigger_character else ("manual" if manual else "typing")
            requester = cast(Any, self._completion_requester)
            try:
                requester(
                    prefix,
                    source_text,
                    cursor_position,
                    manual or force_empty_prefix,
                    request_generation,
                    trigger_kind,
                    effective_trigger_character,
                )
            except TypeError:
                requester(
                    prefix,
                    source_text,
                    cursor_position,
                    manual or force_empty_prefix,
                    request_generation,
                )
            finally:
                self._pending_completion_trigger_character = ""
            return

        self._pending_completion_trigger_character = ""
        if self._completion_provider is None:
            return
        items = self._completion_provider(prefix, source_text, cursor_position, manual or force_empty_prefix)
        if not items:
            self._completion_popup.hide()
            return
        self._show_completion_items(items, prefix=prefix)

    def _request_completion_item_resolution(self, item: object) -> None:
        if not isinstance(item, CompletionItem):
            return
        if not item.resolvable_fields:
            return
        if self._completion_resolve_requester is None:
            return
        self._completion_resolve_requester(
            item,
            self.toPlainText(),
            self.textCursor().position(),
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
        self._completion_popup.replace_item(item)

    def _request_completion_with_metadata(
        self,
        *,
        prefix: str,
        source_text: str,
        cursor_position: int,
        manual: bool,
        request_generation: int,
        trigger_kind: str,
        trigger_character: str,
    ) -> None:
        if self._completion_requester is None:
            return
        requester = cast(Any, self._completion_requester)
        try:
            requester(
                prefix,
                source_text,
                cursor_position,
                manual,
                request_generation,
                trigger_kind,
                trigger_character,
            )
        except TypeError:
            requester(prefix, source_text, cursor_position, manual, request_generation)

    def show_completion_items_for_request(
        self,
        *,
        request_generation: int,
        prefix: str,
        items: list[CompletionItem],
    ) -> None:
        """Apply asynchronous completion results if still current."""
        if request_generation != self._completion_request_generation:
            return
        if not items:
            self._completion_popup.hide()
            return
        self._show_completion_items(items, prefix=prefix)

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

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802 - Qt signature
        if self._handle_completion_popup_navigation(e):
            return

        if e.key() == Qt.Key_Space and e.modifiers() & Qt.ControlModifier:
            self.trigger_completion(manual=True)
            e.accept()
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
            if self._handle_smart_backspace():
                e.accept()
                return
        if e.key() in {Qt.Key_Return, Qt.Key_Enter} and not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            self._insert_newline_with_auto_indent()
            e.accept()
            return

        super().keyPressEvent(e)
        if not self._completion_enabled or not self._completion_auto_trigger:
            if e.text() in {"(", ","}:
                self._show_signature_help()
            elif e.text() == ")":
                QToolTip.hideText()
            return

        inserted_text = e.text()
        if inserted_text in {"(", ","}:
            self._show_signature_help()
        elif inserted_text == ")":
            QToolTip.hideText()
        if inserted_text == ".":
            self._pending_completion_trigger_character = "."
            self.trigger_completion(manual=True, force_empty_prefix=True)
            return
        if inserted_text and (inserted_text.isalnum() or inserted_text == "_"):
            self.trigger_completion(manual=False)
            return
        if self._completion_popup.is_visible():
            self._completion_popup.hide()

    def _show_signature_help(self) -> None:
        if self._signature_help_requester is not None:
            self._signature_help_request_generation += 1
            self._signature_help_requester(
                self.toPlainText(),
                self.textCursor().position(),
                self._signature_help_request_generation,
            )
            return
        if self._signature_help_provider is None:
            return
        self.show_calltip(self._signature_help_provider(self.toPlainText(), self.textCursor().position()))

    def _handle_completion_popup_navigation(self, event: QKeyEvent) -> bool:
        return self._completion_popup.handle_navigation_event(event)

    def _show_completion_items(self, items: list[CompletionItem], *, prefix: str) -> None:
        if not items:
            self._completion_popup.hide()
            return

        self._completion_popup.set_items(items, prefix)
        rect = self.cursorRect()
        rect.setWidth(max(240, rect.width()))
        self._completion_popup.complete(rect)

    def _insert_completion_from_item(self, item: object) -> None:
        if not isinstance(item, CompletionItem):
            return

        cursor = self.textCursor()
        if item.replacement_start is not None and item.replacement_end is not None:
            cursor.setPosition(item.replacement_start)
            cursor.setPosition(item.replacement_end, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        else:
            current_prefix = extract_completion_prefix(self.toPlainText(), cursor.position())
            if current_prefix:
                cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(current_prefix))
                cursor.removeSelectedText()
        cursor.insertText(item.insert_text)
        self.setTextCursor(cursor)
        if self._completion_accepted_callback is not None:
            self._completion_accepted_callback(item)
