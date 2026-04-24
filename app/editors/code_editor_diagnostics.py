"""Diagnostics overlay behavior for CodeEditorWidget."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide2.QtCore import QEvent, QPoint
from PySide2.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide2.QtWidgets import QTextEdit, QToolTip

from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity


if TYPE_CHECKING:
    from PySide2.QtWidgets import QPlainTextEdit

    class _CodeEditorDiagnosticsBase(QPlainTextEdit):
        _diagnostic_selections: list[Any]
        _diagnostic_lines: dict[int, DiagnosticSeverity]
        _diagnostic_ranges: list[tuple[int, int, str]]
        _diag_error_color: QColor
        _diag_warning_color: QColor
        _diag_info_color: QColor
        _line_number_area: Any
        _hover_provider: Any
        _hover_requester: Any
        _hover_request_generation: int
        _hover_request_global_pos: QPoint | None
        _hover_tooltip_enabled: bool

        def _mark_overlay_cache_dirty(self) -> None: ...
        def _refresh_extra_selections(self) -> None: ...
else:
    class _CodeEditorDiagnosticsBase:
        pass


class CodeEditorDiagnosticsMixin(_CodeEditorDiagnosticsBase):
    """Diagnostics state and tooltip handling split from the main editor widget."""

    def set_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        """Apply diagnostics: build squiggly underlines, gutter markers, and hover ranges."""
        self._diagnostic_selections.clear()
        self._diagnostic_lines.clear()
        self._diagnostic_ranges.clear()

        severity_priority = {
            DiagnosticSeverity.ERROR: 0,
            DiagnosticSeverity.WARNING: 1,
            DiagnosticSeverity.INFO: 2,
        }

        document = self.document()
        for diagnostic in diagnostics:
            color = self._diag_color_for_severity(diagnostic.severity)
            block = document.findBlockByNumber(diagnostic.line_number - 1)
            if not block.isValid():
                continue

            block_start = block.position()
            line_text = block.text()

            if diagnostic.col_start is not None and diagnostic.col_end is not None:
                start_pos = block_start + diagnostic.col_start
                end_pos = block_start + diagnostic.col_end
            else:
                stripped = line_text.lstrip()
                leading = len(line_text) - len(stripped)
                start_pos = block_start + leading
                end_pos = block_start + len(line_text)

            if start_pos >= end_pos:
                end_pos = block_start + max(len(line_text), 1)

            selection = cast(Any, QTextEdit.ExtraSelection())
            selection.format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
            selection.format.setUnderlineColor(color)
            cursor = QTextCursor(document)
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
            selection.cursor = cursor
            self._diagnostic_selections.append(selection)

            tooltip = f"[{diagnostic.code}] {diagnostic.message}"
            self._diagnostic_ranges.append((start_pos, end_pos, tooltip))

            current_severity = self._diagnostic_lines.get(diagnostic.line_number)
            if current_severity is None or severity_priority.get(diagnostic.severity, 2) < severity_priority.get(current_severity, 2):
                self._diagnostic_lines[diagnostic.line_number] = diagnostic.severity

        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()
        self._line_number_area.update()

    def clear_diagnostics(self) -> None:
        self._diagnostic_selections.clear()
        self._diagnostic_lines.clear()
        self._diagnostic_ranges.clear()
        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()
        self._line_number_area.update()

    def _diag_color_for_severity(self, severity: DiagnosticSeverity) -> QColor:
        if severity == DiagnosticSeverity.ERROR:
            return self._diag_error_color
        if severity == DiagnosticSeverity.WARNING:
            return self._diag_warning_color
        return self._diag_info_color

    def event(self, e: QEvent) -> bool:  # type: ignore[override]
        if e.type() == QEvent.ToolTip:
            pos = e.pos()  # type: ignore[union-attr]
            cursor = self.cursorForPosition(pos)
            cursor_pos = cursor.position()
            for start, end, tooltip in self._diagnostic_ranges:
                if start <= cursor_pos < end:
                    QToolTip.showText(e.globalPos(), tooltip, self)  # type: ignore[union-attr]
                    return True
            if not self._hover_tooltip_enabled:
                QToolTip.hideText()
                return True
            if self._hover_requester is not None:
                self._hover_request_generation += 1
                self._hover_request_global_pos = QPoint(e.globalPos())  # type: ignore[union-attr]
                self._hover_requester(
                    self.toPlainText(),
                    cursor_pos,
                    self._hover_request_generation,
                )
                return True
            if self._hover_provider is not None:
                hover_text = self._hover_provider(self.toPlainText(), cursor_pos)
                if hover_text:
                    QToolTip.showText(e.globalPos(), hover_text, self)  # type: ignore[union-attr]
                    return True
            QToolTip.hideText()
            return True
        return super().event(e)
