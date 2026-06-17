"""Flat-Python paste hint overlay behavior for CodeEditorWidget."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide2.QtCore import QPoint, Qt
from PySide2.QtGui import QContextMenuEvent, QTextCursor
from PySide2.QtCore import QMimeData
from PySide2.QtWidgets import QApplication, QMenu

from app.core import constants
from app.editors.paste_hint_overlay import PasteHintOverlay
from app.editors.text_editing import (
    FLAT_PYTHON_CONFIDENCE_LOW,
    FlatPythonIndentRepairResult,
    auto_paste_accepts_repair,
    looks_like_flat_python_paste,
    repair_flat_python_indentation,
)
from app.shell.theme_tokens import ShellThemeTokens


if TYPE_CHECKING:
    from PySide2.QtWidgets import QPlainTextEdit, QWidget

    class _CodeEditorPasteHintBase(QPlainTextEdit):
        _auto_reindent_flat_python_paste: bool
        _last_paste_range: tuple[int, int] | None
        _paste_hint_overlay: PasteHintOverlay | None
        _paste_hint_dismissed_this_session: bool
        _paste_hint_anchor_block: int | None
        _paste_hint_enable_always_callback: Callable[[], object] | None
        _paste_hint_status_callback: Callable[[FlatPythonIndentRepairResult], object] | None
        _cached_theme_tokens: ShellThemeTokens | None

        def _indent_text(self) -> str: ...
        def _insert_text_as_paste(self, text: str, *, prefix_subsequent_lines: bool) -> None: ...
        def _select_paste_range_if_multiline(self, start: int, end: int, cursor: QTextCursor) -> None: ...
        def paste_reindented_flat_python(self) -> FlatPythonIndentRepairResult: ...
        def reindent_flat_python_selection(self) -> FlatPythonIndentRepairResult: ...
else:
    class _CodeEditorPasteHintBase:
        pass


class CodeEditorPasteHintMixin(_CodeEditorPasteHintBase):
    """Paste-hint overlay and flat-Python paste affordances split from the hub widget."""

    def _init_paste_hint_state(self) -> None:
        self._auto_reindent_flat_python_paste = constants.UI_EDITOR_AUTO_REINDENT_FLAT_PYTHON_PASTE_DEFAULT
        self._last_paste_range: tuple[int, int] | None = None
        self._paste_hint_overlay: PasteHintOverlay | None = None
        self._paste_hint_dismissed_this_session = False
        self._paste_hint_anchor_block: int | None = None
        self._paste_hint_enable_always_callback: Callable[[], object] | None = None
        self._paste_hint_status_callback: Callable[[FlatPythonIndentRepairResult], object] | None = None

    def _apply_paste_hint_theme(self, tokens: ShellThemeTokens) -> None:
        if self._paste_hint_overlay is not None:
            self._paste_hint_overlay.apply_theme(tokens)

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802 - Qt signature
        """Apply flat-Python repair when accepted, else paste literally and maybe hint."""
        pasted_text = source.text() if source.hasText() else ""
        if self._auto_reindent_flat_python_paste and pasted_text:
            result = repair_flat_python_indentation(pasted_text, indent_text=self._indent_text())
            if auto_paste_accepts_repair(result):
                self._insert_text_as_paste(result.text, prefix_subsequent_lines=True)
                if self._paste_hint_status_callback is not None:
                    self._paste_hint_status_callback(result)
                return

        start = self.textCursor().selectionStart() if self.textCursor().hasSelection() else self.textCursor().position()
        super().insertFromMimeData(source)
        end = self.textCursor().position()
        self._last_paste_range = (start, end)
        self._select_paste_range_if_multiline(start, end, self.textCursor())
        if pasted_text:
            self._maybe_show_flat_python_paste_hint(pasted_text, (start, end))

    def _show_context_menu(self, event: QContextMenuEvent) -> None:
        """Augment the default context menu with flat-Python smart-paste actions."""
        menu = self.createStandardContextMenu(event.pos())
        try:
            self._augment_context_menu_with_flat_python_actions(menu)
            menu.exec_(event.globalPos())
        finally:
            menu.deleteLater()

    def _augment_context_menu_with_flat_python_actions(self, menu: QMenu) -> None:
        """Insert *Paste and Re-indent* / *Re-indent Selection* actions when relevant."""
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text() if clipboard is not None else ""
        clipboard_looks_flat = bool(clipboard_text) and looks_like_flat_python_paste(clipboard_text)

        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        selection_text = cursor.selectedText().replace("\u2029", "\n") if has_selection else ""
        selection_looks_flat = bool(selection_text) and looks_like_flat_python_paste(selection_text)

        if not clipboard_looks_flat and not selection_looks_flat:
            return

        menu.addSeparator()
        if clipboard_looks_flat:
            paste_action = menu.addAction("Paste and Re-indent (Flat Python)")
            if paste_action is not None:
                paste_action.triggered.connect(self._context_menu_paste_reindent)
        if selection_looks_flat:
            reindent_action = menu.addAction("Re-indent Selection (Flat Python)")
            if reindent_action is not None:
                reindent_action.triggered.connect(self._context_menu_reindent_selection)

    def _context_menu_paste_reindent(self) -> None:
        result = self.paste_reindented_flat_python()
        if self._paste_hint_status_callback is not None:
            self._paste_hint_status_callback(result)

    def _context_menu_reindent_selection(self) -> None:
        result = self.reindent_flat_python_selection()
        if self._paste_hint_status_callback is not None:
            self._paste_hint_status_callback(result)

    def set_paste_hint_enable_always_callback(self, callback: Callable[[], object] | None) -> None:
        """Register the handler invoked when the user clicks "Always" on the paste hint."""
        self._paste_hint_enable_always_callback = callback

    def set_paste_hint_status_callback(
        self,
        callback: Callable[[FlatPythonIndentRepairResult], object] | None,
    ) -> None:
        """Register a handler that receives the repair result after any flat-Python re-indent."""
        self._paste_hint_status_callback = callback

    def has_flat_python_paste_hint_visible(self) -> bool:
        """Test helper: whether the paste-hint overlay is currently shown."""
        overlay = self._paste_hint_overlay
        if overlay is None:
            return False
        parent_widget = overlay.parentWidget()
        return bool(overlay.isVisibleTo(parent_widget))

    def trigger_flat_python_paste_hint_reindent(self) -> None:
        """Test helper: simulate the user clicking *Re-indent* on the paste hint."""
        if self._paste_hint_overlay is None:
            return
        self._paste_hint_overlay.reindentRequested.emit()

    def trigger_flat_python_paste_hint_always(self) -> None:
        """Test helper: simulate the user clicking *Always* on the paste hint."""
        if self._paste_hint_overlay is None:
            return
        self._paste_hint_overlay.enableAlwaysRequested.emit()

    def trigger_flat_python_paste_hint_dismiss(self) -> None:
        """Test helper: simulate the user clicking the dismiss (×) button."""
        if self._paste_hint_overlay is None:
            return
        self._paste_hint_overlay.dismissed.emit()
        self._paste_hint_overlay.hide_overlay()

    def _maybe_show_flat_python_paste_hint(
        self,
        pasted_text: str,
        paste_range: tuple[int, int],
    ) -> None:
        """Show the inline paste hint when conditions warrant."""
        if self._auto_reindent_flat_python_paste:
            return
        if self._paste_hint_dismissed_this_session:
            return
        if not pasted_text or not looks_like_flat_python_paste(pasted_text):
            return
        dry_run = repair_flat_python_indentation(pasted_text, indent_text=self._indent_text())
        if not dry_run.changed:
            return
        if dry_run.confidence == FLAT_PYTHON_CONFIDENCE_LOW:
            return

        overlay = self._ensure_paste_hint_overlay()
        self._paste_hint_anchor_block = self.document().findBlock(max(paste_range[0], paste_range[1] - 1)).blockNumber()
        anchor_point = self._compute_paste_hint_anchor_point(paste_range)
        overlay.show_at(self.viewport(), anchor_point)

    def _destroy_paste_hint_overlay_on_close(self) -> None:
        overlay = self._paste_hint_overlay
        if overlay is None:
            return
        self._paste_hint_overlay = None
        try:
            overlay.hide()
            overlay.deleteLater()
        except RuntimeError:
            pass

    def _ensure_paste_hint_overlay(self) -> PasteHintOverlay:
        overlay = self._paste_hint_overlay
        if overlay is None:
            overlay = PasteHintOverlay(self.viewport())
            overlay.reindentRequested.connect(self._handle_paste_hint_reindent)
            overlay.enableAlwaysRequested.connect(self._handle_paste_hint_always)
            overlay.dismissed.connect(self._handle_paste_hint_dismissed)
            if self._cached_theme_tokens is not None:
                overlay.apply_theme(self._cached_theme_tokens)
            self._paste_hint_overlay = overlay
        elif self._cached_theme_tokens is not None:
            overlay.apply_theme(self._cached_theme_tokens)
        return overlay

    def _compute_paste_hint_anchor_point(self, paste_range: tuple[int, int]) -> QPoint:
        viewport = self.viewport()
        cursor = QTextCursor(self.document())
        cursor.setPosition(paste_range[1])
        rect = self.cursorRect(cursor)
        margin_y = 4
        x = max(0, rect.left())
        y = rect.bottom() + margin_y
        if y > viewport.height() - 4:
            y = max(0, rect.top() - margin_y - 28)
        return QPoint(x, y)

    def _handle_paste_hint_reindent(self) -> None:
        if self._paste_hint_overlay is not None:
            self._paste_hint_overlay.hide_overlay()
        self._reindent_last_paste_range()

    def _handle_paste_hint_always(self) -> None:
        if self._paste_hint_overlay is not None:
            self._paste_hint_overlay.hide_overlay()
        if self._paste_hint_enable_always_callback is not None:
            self._paste_hint_enable_always_callback()
        self._reindent_last_paste_range()

    def _handle_paste_hint_dismissed(self) -> None:
        self._paste_hint_dismissed_this_session = True
        self._paste_hint_anchor_block = None

    def _reindent_last_paste_range(self) -> None:
        if self._last_paste_range is None:
            return
        result = self.reindent_flat_python_selection()
        if self._paste_hint_status_callback is not None:
            self._paste_hint_status_callback(result)
        self._paste_hint_anchor_block = None

    def _dismiss_flat_python_paste_hint(self, *, remember_session: bool) -> None:
        overlay = self._paste_hint_overlay
        if overlay is None or not overlay.isVisible():
            return
        overlay.hide_overlay()
        if remember_session:
            self._paste_hint_dismissed_this_session = True
        self._paste_hint_anchor_block = None

    def _maybe_dismiss_paste_hint_for_cursor(self) -> None:
        if self._paste_hint_anchor_block is None:
            return
        overlay = self._paste_hint_overlay
        if overlay is None or not overlay.isVisible():
            return
        cursor_block = self.textCursor().blockNumber()
        if abs(cursor_block - self._paste_hint_anchor_block) > 1:
            overlay.hide_overlay()
            self._paste_hint_anchor_block = None
