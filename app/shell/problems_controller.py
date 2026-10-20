"""Problems-panel and diagnostic chrome coordination."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide2.QtGui import QIcon

from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity
from app.shell.problems_panel import tab_diagnostic_icon


def retarget_diagnostics(diagnostics: list[CodeDiagnostic], file_path: str) -> list[CodeDiagnostic]:
    return [replace(diagnostic, file_path=file_path) for diagnostic in diagnostics]


class ProblemsController:
    """Mirrors diagnostics into editors, tab icons, status bar, and Problems panel.

    Stored lint diagnostics are keyed by buffer id for open files and by path
    for files that are not open (import analysis covers the whole project).
    """

    def __init__(self, window: Any) -> None:
        self._window = window

    def diagnostics_key(self, file_path: str) -> str:
        tab = self._window._editor_manager.get_tab(file_path)
        return file_path if tab is None else tab.buffer_id

    def apply_lint_diagnostics_result(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        window = self._window
        key = self.diagnostics_key(file_path)
        if key != file_path:
            window._stored_lint_diagnostics.pop(file_path, None)
        window._stored_lint_diagnostics[key] = diagnostics
        self.push_diagnostics_to_editor(file_path, diagnostics)
        self.update_tab_diagnostic_indicator(file_path, diagnostics)
        self.render_merged_problems_panel()
        active_tab = window._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path == file_path:
            self.update_status_bar_diagnostics(diagnostics)

    def optimistically_clear_file_diagnostics(self, file_path: str) -> None:
        """Drop stale overlays immediately while a fresh realtime lint is pending.

        Safe under AD-018: never re-applies old error results; the next current
        lint result replaces this empty state.
        """
        window = self._window
        key = self.diagnostics_key(file_path)
        if not window._stored_lint_diagnostics.get(key) and not self._editor_has_overlays(file_path):
            return
        window._stored_lint_diagnostics[key] = []
        self.push_diagnostics_to_editor(file_path, [])
        self.update_tab_diagnostic_indicator(file_path, [])
        self.render_merged_problems_panel()
        active_tab = window._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path == file_path:
            self.update_status_bar_diagnostics([])

    def retarget_buffer_diagnostics(self, file_path: str) -> None:
        """Point a moved buffer's stored diagnostics at its new ``file_path``."""
        window = self._window
        tab = window._editor_manager.get_tab(file_path)
        if tab is None:
            return
        stored = window._stored_lint_diagnostics.get(tab.buffer_id)
        if not stored:
            return
        window._stored_lint_diagnostics[tab.buffer_id] = retarget_diagnostics(stored, file_path)
        self.render_merged_problems_panel()

    def clear_all_editor_diagnostics(self) -> None:
        """Clear overlays on every open editor (stored state may already be empty)."""
        for file_path, editor_widget in self._window._workspace_controller.widgets_by_open_path().items():
            if hasattr(editor_widget, "clear_diagnostics"):
                editor_widget.clear_diagnostics()
            else:
                editor_widget.set_diagnostics([])
            self.update_tab_diagnostic_indicator(file_path, [])
        active_tab = self._window._editor_manager.active_tab()
        if active_tab is not None:
            self.update_status_bar_diagnostics([])

    def _editor_has_overlays(self, file_path: str) -> bool:
        editor_widget = self._window._workspace_controller.widget_for_path(file_path)
        if editor_widget is None:
            return False
        selections = getattr(editor_widget, "_diagnostic_selections", None)
        return bool(selections)

    def push_diagnostics_to_editor(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        editor_widget = self._window._workspace_controller.widget_for_path(file_path)
        if editor_widget is None:
            return
        editor_widget.set_diagnostics(diagnostics)

    def update_tab_diagnostic_indicator(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        window = self._window
        if window._editor_tabs_widget is None:
            return
        tab_state = window._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        has_error = any(d.severity == DiagnosticSeverity.ERROR for d in diagnostics)
        has_warning = any(d.severity == DiagnosticSeverity.WARNING for d in diagnostics)
        if has_error:
            icon = tab_diagnostic_icon(DiagnosticSeverity.ERROR, "#E03131")
        elif has_warning:
            icon = tab_diagnostic_icon(DiagnosticSeverity.WARNING, "#D97706")
        else:
            icon = QIcon()
        coordinator = window._editor_tabs_coordinator
        for tabs in coordinator.all_tab_widgets():
            tab_index = coordinator.tab_index_in(tabs, tab_state.buffer_id)
            if tab_index >= 0:
                tabs.setTabIcon(tab_index, icon)

    def clear_all_tab_diagnostic_indicators(self) -> None:
        window = self._window
        if window._editor_tabs_widget is None:
            return
        empty = QIcon()
        for tabs in window._editor_tabs_coordinator.all_tab_widgets():
            for index in range(tabs.count()):
                tabs.setTabIcon(index, empty)

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
