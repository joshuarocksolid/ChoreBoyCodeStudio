"""Python style and quick-fix shell actions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol

from PySide2.QtWidgets import QMessageBox

from app.editors.formatting_service import format_text_basic
from app.intelligence.code_actions import apply_quick_fixes, plan_safe_fixes_for_file
from app.plugins.workflow_adapters import analyze_python_with_workflow, format_python_with_workflow, organize_imports_with_workflow
from app.python_tools.models import (
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PYTHON_TOOLING_STATUS_UNCHANGED,
)


class PythonStyleWorkflowHost(Protocol):
    """Typed host surface for :class:`PythonStyleWorkflow`."""

    def dialog_parent(self) -> Any:
        ...

    def editor_manager(self) -> Any:
        ...

    def editor_tab_workflow(self) -> Any:
        ...

    def workflow_broker(self) -> Any:
        ...

    def resolve_python_tooling_project_root(self, file_path: str) -> str | None:
        ...

    def save_workflow(self) -> Any:
        ...

    def lint_workflow(self) -> Any:
        ...

    def loaded_project(self) -> Any | None:
        ...

    def set_loaded_project(self, project: Any) -> None:
        ...

    def known_runtime_modules(self) -> frozenset[str] | None:
        ...

    def selected_linter(self) -> str:
        ...

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        ...

    def quick_fixes_enabled(self) -> bool:
        ...

    def quick_fix_require_preview_for_multifile(self) -> bool:
        ...

    def local_history_workflow(self) -> Any:
        ...

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        ...

    def project_tree_ui_workflow(self) -> Any:
        ...


class PythonStyleWorkflow:
    """Owns user-triggered formatting, import organization, lint, and safe fixes."""

    def __init__(self, host: PythonStyleWorkflowHost) -> None:
        self._host = host

    def handle_format_current_file_action(self) -> None:
        parent = self._host.dialog_parent()
        active_tab = self._host.editor_manager().active_tab()
        editor_widget = self._host.editor_tab_workflow().active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Format Current File", "Open a file tab first.")
            return

        source_text = editor_widget.toPlainText()
        if active_tab.file_path.lower().endswith(".py"):
            try:
                provider, result = format_python_with_workflow(
                    self._host.workflow_broker(),
                    source_text=source_text,
                    file_path=active_tab.file_path,
                    project_root=self._host.resolve_python_tooling_project_root(active_tab.file_path),
                )
            except Exception as exc:
                QMessageBox.warning(
                    parent,
                    "Format Current File",
                    f"Formatting failed: {exc}",
                )
                return
            if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
                QMessageBox.information(parent, "Format Current File", "File is already formatted.")
                return
            if result.status != PYTHON_TOOLING_STATUS_FORMATTED:
                QMessageBox.warning(
                    parent,
                    "Format Current File",
                    self._host.save_workflow().python_tooling_failure_message("Formatting", result),
                )
                return
            editor_widget.replace_document_text(result.formatted_text)
            QMessageBox.information(
                parent,
                "Format Current File",
                f"Formatting applied via {provider.title}.",
            )
            return

        result = format_text_basic(source_text)
        if not result.changed:
            QMessageBox.information(parent, "Format Current File", "File is already formatted.")
            return

        editor_widget.replace_document_text(result.formatted_text)
        QMessageBox.information(parent, "Format Current File", "Formatting applied.")

    def handle_organize_imports_action(self) -> None:
        parent = self._host.dialog_parent()
        active_tab = self._host.editor_manager().active_tab()
        editor_widget = self._host.editor_tab_workflow().active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Organize Imports", "Open a file tab first.")
            return
        if not active_tab.file_path.lower().endswith(".py"):
            QMessageBox.information(
                parent,
                "Organize Imports",
                "Organize Imports is currently available for Python files only.",
            )
            return

        try:
            provider, result = organize_imports_with_workflow(
                self._host.workflow_broker(),
                source_text=editor_widget.toPlainText(),
                file_path=active_tab.file_path,
                project_root=self._host.resolve_python_tooling_project_root(active_tab.file_path),
            )
        except Exception as exc:
            QMessageBox.warning(parent, "Organize Imports", f"Organize Imports failed: {exc}")
            return
        if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
            QMessageBox.information(parent, "Organize Imports", "Imports are already organized.")
            return
        if result.status != PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED:
            QMessageBox.warning(
                parent,
                "Organize Imports",
                self._host.save_workflow().python_tooling_failure_message("Organize Imports", result),
            )
            return

        editor_widget.replace_document_text(result.formatted_text)
        QMessageBox.information(parent, "Organize Imports", f"Imports organized via {provider.title}.")

    def handle_lint_current_file_action(self) -> None:
        parent = self._host.dialog_parent()
        active_tab = self._host.editor_manager().active_tab()
        if active_tab is None:
            QMessageBox.warning(parent, "Lint Current File", "Open a file tab first.")
            return
        if not active_tab.file_path.lower().endswith(".py"):
            QMessageBox.information(parent, "Lint Current File", "Linting is currently available for Python files only.")
            return
        self._host.lint_workflow().render_diagnostics_for_file(active_tab.file_path, trigger="manual")

    def handle_apply_safe_fixes_action(self) -> None:
        active_tab = self._host.editor_manager().active_tab()
        if active_tab is None:
            QMessageBox.warning(self._host.dialog_parent(), "Apply Safe Fixes", "Open a file tab first.")
            return
        self.apply_safe_fixes_for_file(active_tab.file_path)

    def apply_safe_fixes_for_file(self, file_path: str) -> None:
        parent = self._host.dialog_parent()
        if not self._host.quick_fixes_enabled():
            QMessageBox.information(parent, "Apply Safe Fixes", "Quick fixes are currently disabled in Settings.")
            return
        if not file_path.lower().endswith(".py"):
            QMessageBox.information(parent, "Apply Safe Fixes", "Safe fixes currently support Python files only.")
            return
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        project_metadata = None if loaded_project is None else loaded_project.metadata
        _provider, diagnostics = analyze_python_with_workflow(
            self._host.workflow_broker(),
            file_path=file_path,
            project_root=project_root,
            known_runtime_modules=self._host.known_runtime_modules(),
            allow_runtime_import_probe=False,
            selected_linter=self._host.selected_linter(),
            lint_rule_overrides=self._host.lint_rule_overrides(),
            project_metadata=project_metadata,
        )
        fixes = plan_safe_fixes_for_file(
            file_path,
            diagnostics,
            project_root=project_root,
            project_metadata=project_metadata,
        )
        if not fixes:
            QMessageBox.information(parent, "Apply Safe Fixes", "No safe fixes available for current file.")
            return

        affected_paths = {fix.file_path for fix in fixes}
        affected_paths.update(fix.target_path for fix in fixes if fix.target_path)
        should_confirm = self._host.quick_fix_require_preview_for_multifile() or len(affected_paths) > 1
        if should_confirm:
            preview = "\n".join(f"- {fix.title}" for fix in fixes[:20])
            if len(fixes) > 20:
                preview += f"\n- ... and {len(fixes) - 20} more"
            confirm = QMessageBox.question(
                parent,
                "Apply Safe Fixes",
                f"Apply {len(fixes)} safe fix(es)?\n\n{preview}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirm != QMessageBox.Yes:
                return

        try:
            source_root_fixes = [fix for fix in fixes if fix.action_kind == "add_source_root"]
            other_fixes = [fix for fix in fixes if fix.action_kind != "add_source_root"]
            changed_lines = apply_quick_fixes(other_fixes)
            changed_lines += self._apply_source_root_fixes(source_root_fixes, project_metadata=project_metadata)
        except OSError as exc:
            QMessageBox.warning(parent, "Apply Safe Fixes", f"Failed to apply fixes: {exc}")
            return

        if changed_lines <= 0:
            QMessageBox.information(parent, "Apply Safe Fixes", "No changes were applied.")
            return

        affected_files = sorted(path for path in affected_paths if path)
        local_history = self._host.local_history_workflow()
        local_history.record_transaction(
            local_history.capture_text_history_snapshots(affected_files),
            source="quick_fix",
            label="Apply Safe Fixes",
        )
        self._host.refresh_open_tabs_from_disk(affected_files)
        if loaded_project is not None and any(path != file_path for path in affected_files):
            self._host.project_tree_ui_workflow().reload_current_project()
        self._host.lint_workflow().render_diagnostics_for_file(file_path, trigger="manual")
        QMessageBox.information(parent, "Apply Safe Fixes", f"Applied {changed_lines} safe fix(es).")

    def _apply_source_root_fixes(self, fixes, *, project_metadata) -> int:  # type: ignore[no-untyped-def]
        from app.bootstrap.paths import project_manifest_path
        from app.project.project_manifest import append_project_source_root

        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            return 0
        manifest_path = project_manifest_path(loaded_project.project_root)
        applied = 0
        seen_roots: set[str] = set()
        for fix in fixes:
            source_root = str(fix.replacement_text or "").strip()
            if not source_root or source_root in seen_roots:
                continue
            seen_roots.add(source_root)
            updated_metadata = append_project_source_root(
                manifest_path,
                source_root,
                metadata_if_absent=loaded_project.metadata,
            )
            loaded_project = replace(
                loaded_project,
                metadata=updated_metadata,
                manifest_materialized=True,
            )
            self._host.set_loaded_project(loaded_project)
            applied += 1
        return applied


class MainWindowPythonStyleHost:
    """Host ports for ``PythonStyleWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> Any:
        return self._window

    def editor_manager(self) -> Any:
        return self._window._editor_manager

    def editor_tab_workflow(self) -> Any:
        return self._window._editor_tab_workflow

    def workflow_broker(self) -> Any:
        return self._window._workflow_broker

    def resolve_python_tooling_project_root(self, file_path: str) -> str | None:
        return self._window._resolve_python_tooling_project_root(file_path)

    def save_workflow(self) -> Any:
        return self._window._save_workflow

    def lint_workflow(self) -> Any:
        return self._window._lint_workflow

    def loaded_project(self) -> Any | None:
        return self._window._loaded_project

    def set_loaded_project(self, project: Any) -> None:
        self._window._loaded_project = project

    def known_runtime_modules(self) -> frozenset[str] | None:
        return self._window._known_runtime_modules

    def selected_linter(self) -> str:
        return self._window._selected_linter

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._window._lint_rule_overrides

    def quick_fixes_enabled(self) -> bool:
        return self._window._quick_fixes_enabled

    def quick_fix_require_preview_for_multifile(self) -> bool:
        return self._window._quick_fix_require_preview_for_multifile

    def local_history_workflow(self) -> Any:
        return self._window._local_history_workflow

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        self._window._refresh_open_tabs_from_disk(file_paths)

    def project_tree_ui_workflow(self) -> Any:
        return self._window._project_tree_ui_workflow


def build_python_style_workflow(window: Any) -> PythonStyleWorkflow:
    return PythonStyleWorkflow(MainWindowPythonStyleHost(window))
