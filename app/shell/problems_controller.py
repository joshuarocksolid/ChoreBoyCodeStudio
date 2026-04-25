"""Problems-panel and diagnostic chrome coordination."""

from __future__ import annotations

from typing import Any

from PySide2.QtGui import QIcon

from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity
from app.shell.problems_panel import tab_diagnostic_icon


class ProblemsController:
    """Mirrors diagnostics into editors, tab icons, status bar, and Problems panel."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def apply_lint_diagnostics_result(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        window = self._window
        window._stored_lint_diagnostics[file_path] = diagnostics
        self.push_diagnostics_to_editor(file_path, diagnostics)
        self.update_tab_diagnostic_indicator(file_path, diagnostics)
        self.render_merged_problems_panel()
        active_tab = window._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path == file_path:
            self.update_status_bar_diagnostics(diagnostics)

    def push_diagnostics_to_editor(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        editor_widget = self._window._editor_widgets_by_path.get(file_path)
        if editor_widget is None:
            return
        editor_widget.set_diagnostics(diagnostics)

    def update_tab_diagnostic_indicator(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        window = self._window
        if window._editor_tabs_widget is None:
            return
        tab_index = window._tab_index_for_path(file_path)
        if tab_index < 0:
            return
        has_error = any(d.severity == DiagnosticSeverity.ERROR for d in diagnostics)
        has_warning = any(d.severity == DiagnosticSeverity.WARNING for d in diagnostics)
        if has_error:
            icon = tab_diagnostic_icon(DiagnosticSeverity.ERROR, "#E03131")
        elif has_warning:
            icon = tab_diagnostic_icon(DiagnosticSeverity.WARNING, "#D97706")
        else:
            icon = QIcon()
        window._editor_tabs_widget.setTabIcon(tab_index, icon)

    def clear_all_tab_diagnostic_indicators(self) -> None:
        window = self._window
        if window._editor_tabs_widget is None:
            return
        empty = QIcon()
        for index in range(window._editor_tabs_widget.count()):
            window._editor_tabs_widget.setTabIcon(index, empty)

    def update_status_bar_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        window = self._window
        if window._status_controller is None:
            return
        errors = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.ERROR)
        warnings = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.WARNING)
        window._status_controller.set_diagnostics_counts(errors, warnings)

    def render_merged_problems_panel(self) -> None:
        window = self._window
        if window._problems_panel is None:
            return
        all_diags = [d for diags in window._stored_lint_diagnostics.values() for d in diags]
        window._problems_panel.set_quick_fixes_enabled(window._quick_fixes_enabled)
        window._problems_panel.set_diagnostics(all_diags, window._stored_runtime_problems)
        self.update_problems_tab_title(window._problems_panel.problem_count())

    def update_problems_tab_title(self, count: int) -> None:
        window = self._window
        if window._problems_tab_widget is None or window._problems_panel is None:
            return
        index = window._problems_tab_widget.indexOf(window._problems_panel)
        if index < 0:
            return
        title = f"Problems ({count})" if count > 0 else "Problems"
        window._problems_tab_widget.setTabText(index, title)
