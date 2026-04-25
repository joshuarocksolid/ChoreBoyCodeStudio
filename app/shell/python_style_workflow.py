"""Python style and quick-fix shell actions."""

from __future__ import annotations

from typing import Any

from PySide2.QtWidgets import QMessageBox

from app.editors.formatting_service import format_text_basic
from app.intelligence.code_actions import apply_quick_fixes, plan_safe_fixes_for_file
from app.plugins.workflow_adapters import analyze_python_with_workflow, format_python_with_workflow, organize_imports_with_workflow
from app.python_tools.models import (
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PYTHON_TOOLING_STATUS_UNCHANGED,
)


class PythonStyleWorkflow:
    """Owns user-triggered formatting, import organization, lint, and safe fixes."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def handle_format_current_file_action(self) -> None:
        window = self._window
        active_tab = window._editor_manager.active_tab()
        editor_widget = window._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(window, "Format Current File", "Open a file tab first.")
            return

        source_text = editor_widget.toPlainText()
        if active_tab.file_path.lower().endswith(".py"):
            try:
                provider, result = format_python_with_workflow(
                    window._workflow_broker,
                    source_text=source_text,
                    file_path=active_tab.file_path,
                    project_root=window._resolve_python_tooling_project_root(active_tab.file_path),
                )
            except Exception as exc:
                QMessageBox.warning(
                    window,
                    "Format Current File",
                    f"Formatting failed: {exc}",
                )
                return
            if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
                QMessageBox.information(window, "Format Current File", "File is already formatted.")
                return
            if result.status != PYTHON_TOOLING_STATUS_FORMATTED:
                QMessageBox.warning(
                    window,
                    "Format Current File",
                    window._save_workflow.python_tooling_failure_message("Formatting", result),
                )
                return
            editor_widget.replace_document_text(result.formatted_text)
            QMessageBox.information(
                window,
                "Format Current File",
                f"Formatting applied via {provider.title}.",
            )
            return

        result = format_text_basic(source_text)
        if not result.changed:
            QMessageBox.information(window, "Format Current File", "File is already formatted.")
            return

        editor_widget.replace_document_text(result.formatted_text)
        QMessageBox.information(window, "Format Current File", "Formatting applied.")

    def handle_organize_imports_action(self) -> None:
        window = self._window
        active_tab = window._editor_manager.active_tab()
        editor_widget = window._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(window, "Organize Imports", "Open a file tab first.")
            return
        if not active_tab.file_path.lower().endswith(".py"):
            QMessageBox.information(
                window,
                "Organize Imports",
                "Organize Imports is currently available for Python files only.",
            )
            return

        try:
            provider, result = organize_imports_with_workflow(
                window._workflow_broker,
                source_text=editor_widget.toPlainText(),
                file_path=active_tab.file_path,
                project_root=window._resolve_python_tooling_project_root(active_tab.file_path),
            )
        except Exception as exc:
            QMessageBox.warning(window, "Organize Imports", f"Organize Imports failed: {exc}")
            return
        if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
            QMessageBox.information(window, "Organize Imports", "Imports are already organized.")
            return
        if result.status != PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED:
            QMessageBox.warning(
                window,
                "Organize Imports",
                window._save_workflow.python_tooling_failure_message("Organize Imports", result),
            )
            return

        editor_widget.replace_document_text(result.formatted_text)
        QMessageBox.information(window, "Organize Imports", f"Imports organized via {provider.title}.")

    def handle_lint_current_file_action(self) -> None:
        window = self._window
        active_tab = window._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(window, "Lint Current File", "Open a file tab first.")
            return
        if not active_tab.file_path.lower().endswith(".py"):
            QMessageBox.information(window, "Lint Current File", "Linting is currently available for Python files only.")
            return
        window._render_lint_diagnostics_for_file(active_tab.file_path, trigger="manual")

    def handle_apply_safe_fixes_action(self) -> None:
        window = self._window
        active_tab = window._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(window, "Apply Safe Fixes", "Open a file tab first.")
            return
        self.apply_safe_fixes_for_file(active_tab.file_path)

    def apply_safe_fixes_for_file(self, file_path: str) -> None:
        window = self._window
        if not window._quick_fixes_enabled:
            QMessageBox.information(window, "Apply Safe Fixes", "Quick fixes are currently disabled in Settings.")
            return
        if not file_path.lower().endswith(".py"):
            QMessageBox.information(window, "Apply Safe Fixes", "Safe fixes currently support Python files only.")
            return
        project_root = None if window._loaded_project is None else window._loaded_project.project_root
        _provider, diagnostics = analyze_python_with_workflow(
            window._workflow_broker,
            file_path=file_path,
            project_root=project_root,
            known_runtime_modules=window._known_runtime_modules,
            allow_runtime_import_probe=True,
            selected_linter=window._selected_linter,
            lint_rule_overrides=window._lint_rule_overrides,
        )
        fixes = plan_safe_fixes_for_file(file_path, diagnostics, project_root=project_root)
        if not fixes:
            QMessageBox.information(window, "Apply Safe Fixes", "No safe fixes available for current file.")
            return

        affected_paths = {fix.file_path for fix in fixes}
        affected_paths.update(fix.target_path for fix in fixes if fix.target_path)
        should_confirm = window._quick_fix_require_preview_for_multifile or len(affected_paths) > 1
        if should_confirm:
            preview = "\n".join(f"- {fix.title}" for fix in fixes[:20])
            if len(fixes) > 20:
                preview += f"\n- ... and {len(fixes) - 20} more"
            confirm = QMessageBox.question(
                window,
                "Apply Safe Fixes",
                f"Apply {len(fixes)} safe fix(es)?\n\n{preview}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirm != QMessageBox.Yes:
                return

        try:
            changed_lines = apply_quick_fixes(fixes)
        except OSError as exc:
            QMessageBox.warning(window, "Apply Safe Fixes", f"Failed to apply fixes: {exc}")
            return

        if changed_lines <= 0:
            QMessageBox.information(window, "Apply Safe Fixes", "No changes were applied.")
            return

        affected_files = sorted(path for path in affected_paths if path)
        window._local_history_workflow.record_transaction(
            window._local_history_workflow.capture_text_history_snapshots(affected_files),
            source="quick_fix",
            label="Apply Safe Fixes",
        )
        window._refresh_open_tabs_from_disk(affected_files)
        if window._loaded_project is not None and any(path != file_path for path in affected_files):
            window._reload_current_project()
        window._render_lint_diagnostics_for_file(file_path, trigger="manual")
        QMessageBox.information(window, "Apply Safe Fixes", f"Applied {changed_lines} safe fix(es).")
