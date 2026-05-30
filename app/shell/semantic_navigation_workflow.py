"""Semantic navigation, inline intelligence, and import analysis for the shell."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Protocol, cast

from PySide2.QtWidgets import QDialog, QInputDialog, QMessageBox

from app.editors.code_editor_widget import CodeEditorWidget
from app.intelligence.completion_context import build_completion_context
from app.intelligence.completion_models import CompletionItem, CompletionRequestResult
from app.intelligence.completion_service import CompletionRequest
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity, find_unresolved_imports
from app.intelligence.lint_profile import LINT_SEVERITY_ERROR, LINT_SEVERITY_INFO, resolve_lint_rule_settings
from app.intelligence.outline_service import build_outline_from_source, flatten_symbols
from app.intelligence.runtime_introspection import (
    RuntimeIntrospectionCoordinator,
    attach_replacement_metadata,
    resolve_runtime_introspection_query_with_inference,
)
from app.shell.quick_symbol_dialog import QuickSymbolDialog
from app.support.runtime_explainer import build_import_issue_report


def is_stale_revision_gated_editor_request(
    *,
    file_path: str,
    editor_widget: CodeEditorWidget,
    requested_revision: int | None,
    editor_widget_for_path: Callable[[str], CodeEditorWidget | None],
    buffer_revision: Callable[[str], int | None],
) -> bool:
    """Return True when an async editor intelligence result should be dropped."""
    active_widget = editor_widget_for_path(file_path)
    if active_widget is not editor_widget:
        return True
    return buffer_revision(file_path) != requested_revision


def deliver_revision_gated_editor_result(
    *,
    file_path: str,
    editor_widget: CodeEditorWidget,
    requested_revision: int | None,
    editor_widget_for_path: Callable[[str], CodeEditorWidget | None],
    buffer_revision: Callable[[str], int | None],
    deliver: Callable[[], None],
) -> None:
    """Invoke ``deliver`` only when the editor buffer and widget are still current."""
    if is_stale_revision_gated_editor_request(
        file_path=file_path,
        editor_widget=editor_widget,
        requested_revision=requested_revision,
        editor_widget_for_path=editor_widget_for_path,
        buffer_revision=buffer_revision,
    ):
        return
    deliver()


class SemanticNavigationHost(Protocol):
    """Narrow host ports for :class:`SemanticNavigationWorkflow`."""

    def dialog_parent(self) -> Any:
        ...

    def loaded_project(self) -> object | None:
        ...

    def editor_manager(self) -> Any:
        ...

    def active_editor_widget(self) -> CodeEditorWidget | None:
        ...

    def editor_widget_for_path(self, file_path: str) -> CodeEditorWidget | None:
        ...

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        ...

    def intelligence_controller(self) -> Any:
        ...

    def editor_buffer_revision(self, file_path: str) -> int | None:
        ...

    def open_file_at_line(self, file_path: str, line_number: int) -> None:
        ...

    def outline_symbols_for_path(self, file_path: str) -> list[object] | None:
        ...

    def set_outline_symbols_for_path(self, file_path: str, symbols: list[object]) -> None:
        ...

    def background_tasks(self) -> Any:
        ...

    def problems_panel(self) -> Any | None:
        ...

    def update_problems_tab_title(self, problem_count: int) -> None:
        ...

    def focus_problems_tab(self) -> None:
        ...

    def set_latest_import_issue_report(self, report: object) -> None:
        ...

    def refresh_latest_runtime_issue_report(self) -> None:
        ...

    def open_runtime_center_dialog(self, *, title: str, report: object) -> None:
        ...

    def known_runtime_modules(self) -> set[str]:
        ...

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        ...

    def completion_min_chars(self) -> int:
        ...

    def intelligence_metrics_logging_enabled(self) -> bool:
        ...

    def reported_completion_degradation_reasons(self) -> set[str]:
        ...

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        ...

    def log_warning(self, message: str, *args: object) -> None:
        ...

    def log_info(self, message: str, *args: object) -> None:
        ...

    def runtime_introspection_coordinator(self) -> RuntimeIntrospectionCoordinator | None:
        ...


def _merge_completion_items(
    primary: list[CompletionItem],
    secondary: list[CompletionItem],
) -> list[CompletionItem]:
    seen = {item.label for item in primary}
    merged = list(primary)
    for item in secondary:
        if item.label in seen:
            continue
        merged.append(item)
        seen.add(item.label)
    return merged


class SemanticNavigationWorkflow:
    """Owns go-to-definition, hover/signature, completions, imports, and in-file symbols."""

    def __init__(self, host: SemanticNavigationHost) -> None:
        self._host = host

    def handle_go_to_definition_action(self) -> None:
        parent = self._host.dialog_parent()
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            QMessageBox.warning(parent, "Go To Definition", "Open a project first.")
            return
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        editor_widget = self._host.active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Go To Definition", "Open a file tab first.")
            return
        symbol_name = editor_widget.word_under_cursor()
        if not symbol_name:
            QMessageBox.information(parent, "Go To Definition", "Place cursor on a symbol first.")
            return
        project_root = loaded_project.project_root
        current_file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()

        def on_success(lookup) -> None:  # type: ignore[no-untyped-def]
            if not lookup.found:
                if lookup.metadata.unsupported_reason:
                    if lookup.metadata.source == "semantic_unavailable":
                        QMessageBox.warning(
                            parent,
                            "Go To Definition",
                            (
                                "Semantic definitions are currently unavailable.\n\n"
                                f"Reason: {lookup.metadata.unsupported_reason}"
                            ),
                        )
                        return
                    QMessageBox.information(
                        parent,
                        "Go To Definition",
                        f"No semantic definition found for '{symbol_name}'. The symbol may be dynamic or unresolved.",
                    )
                else:
                    QMessageBox.information(parent, "Go To Definition", f"No definition found for '{symbol_name}'.")
                return
            location = self._choose_definition_location(lookup.locations)
            if location is None:
                return
            selected_location = cast(Any, location)
            self._host.open_file_at_line(str(selected_location.file_path), int(selected_location.line_number))

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Go To Definition", f"Lookup failed: {exc}")

        self._host.intelligence_controller().request_lookup_definition(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            on_success=on_success,
            on_error=on_error,
        )

    def handle_signature_help_action(self) -> None:
        parent = self._host.dialog_parent()
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        editor_widget = self._host.active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Signature Help", "Open a file tab first.")
            return

        tooltip_text = self._build_inline_signature_text(
            file_path=active_tab.file_path,
            source_text=editor_widget.toPlainText(),
            cursor_position=editor_widget.textCursor().position(),
        )
        if not tooltip_text:
            QMessageBox.information(parent, "Signature Help", "No callable signature information available.")
            return
        editor_widget.show_calltip(tooltip_text)

    def handle_hover_info_action(self) -> None:
        parent = self._host.dialog_parent()
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        editor_widget = self._host.active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Hover Info", "Open a file tab first.")
            return

        tooltip_text = self._build_inline_hover_text(
            file_path=active_tab.file_path,
            source_text=editor_widget.toPlainText(),
            cursor_position=editor_widget.textCursor().position(),
        )
        if not tooltip_text:
            QMessageBox.information(parent, "Hover Info", "No symbol info available.")
            return
        editor_widget.show_calltip(tooltip_text)

    def handle_analyze_imports_action(self) -> None:
        parent = self._host.dialog_parent()
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            QMessageBox.warning(parent, "Analyze Imports", "Open a project first.")
            return
        project_root = loaded_project.project_root
        source_overrides: dict[str, str] = {}
        for path, widget in self._host.editor_widgets_by_path().items():
            source_overrides[path] = widget.toPlainText()

        known_modules = self._host.known_runtime_modules()
        lint_rule_overrides = self._host.lint_rule_overrides()

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return find_unresolved_imports(
                project_root,
                source_overrides=source_overrides,
                known_runtime_modules=known_modules,
                allow_runtime_import_probe=True,
                lint_rule_overrides=lint_rule_overrides,
            )

        def on_success(diagnostics) -> None:  # type: ignore[no-untyped-def]
            problems_panel = self._host.problems_panel()
            if problems_panel is None:
                return
            _, unresolved_import_severity = resolve_lint_rule_settings("PY200", lint_rule_overrides)
            if unresolved_import_severity == LINT_SEVERITY_ERROR:
                diagnostic_severity = DiagnosticSeverity.ERROR
            elif unresolved_import_severity == LINT_SEVERITY_INFO:
                diagnostic_severity = DiagnosticSeverity.INFO
            else:
                diagnostic_severity = DiagnosticSeverity.WARNING
            import_diags = [
                CodeDiagnostic(
                    code="PY200",
                    severity=diagnostic_severity,
                    file_path=d.file_path,
                    line_number=d.line_number,
                    message=d.message,
                )
                for d in diagnostics
            ]
            problems_panel.set_diagnostics(import_diags)
            self._host.update_problems_tab_title(problems_panel.problem_count())
            self._host.focus_problems_tab()
            import_report = build_import_issue_report(
                project_root,
                diagnostics,
                known_runtime_modules=known_modules,
                allow_runtime_import_probe=True,
            )
            self._host.set_latest_import_issue_report(import_report)
            self._host.refresh_latest_runtime_issue_report()
            if import_report.issues:
                self._host.open_runtime_center_dialog(title="Import Analysis", report=import_report)

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Analyze Imports", f"Import analysis failed: {exc}")

        self._host.background_tasks().run(key="analyze_imports", task=task, on_success=on_success, on_error=on_error)

    def handle_goto_symbol_in_file_action(self) -> None:
        parent = self._host.dialog_parent()
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.information(parent, "Go to Symbol", "Open a Python file first.")
            return
        file_path = active_tab.file_path
        if Path(file_path).suffix.lower() not in {".py", ".pyw", ".pyi"}:
            QMessageBox.information(parent, "Go to Symbol", "Open a Python file first.")
            return
        symbols = self._host.outline_symbols_for_path(file_path)
        if symbols is None:
            editor_widget = self._host.editor_widget_for_path(str(Path(file_path).expanduser().resolve()))
            source = editor_widget.toPlainText() if editor_widget is not None else active_tab.current_content
            symbols = build_outline_from_source(source or "")
            self._host.set_outline_symbols_for_path(file_path, symbols)
        flat = flatten_symbols(symbols)
        if not flat:
            QMessageBox.information(parent, "Go to Symbol", "No symbols in this file.")
            return
        editor_widget = self._host.editor_widget_for_path(str(Path(file_path).expanduser().resolve()))
        original_line = editor_widget.textCursor().blockNumber() + 1 if editor_widget is not None else 1

        dialog = QuickSymbolDialog(flat, parent=parent)

        def _on_preview(line: int) -> None:
            if editor_widget is not None:
                editor_widget.go_to_line(line)

        def _on_chosen(line: int) -> None:
            self._host.open_file_at_line(file_path, line)

        dialog.symbol_preview.connect(_on_preview)
        dialog.symbol_chosen.connect(_on_chosen)
        result = dialog.exec_()
        if result != QDialog.Accepted and editor_widget is not None:
            editor_widget.go_to_line(original_line)

    def request_inline_signature_text_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
        cursor_position: int,
        request_generation: int,
    ) -> None:
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        requested_revision = self._host.editor_buffer_revision(file_path)

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            generation, signature = payload

            def deliver() -> None:
                editor_widget.show_calltip_for_request(
                    request_generation=generation,
                    text=self._host.intelligence_controller().format_inline_signature_text(signature),
                )

            deliver_revision_gated_editor_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                editor_widget_for_path=self._host.editor_widget_for_path,
                buffer_revision=self._host.editor_buffer_revision,
                deliver=deliver,
            )

        def on_error(exc: Exception) -> None:
            self._host.log_warning("Signature-help request failed for %s: %s", file_path, exc)

        self._host.intelligence_controller().request_signature_help(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def request_inline_hover_text_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
        cursor_position: int,
        request_generation: int,
    ) -> None:
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        requested_revision = self._host.editor_buffer_revision(file_path)

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            generation, hover_info = payload

            def deliver() -> None:
                editor_widget.show_hover_text_for_request(
                    request_generation=generation,
                    text=self._host.intelligence_controller().format_inline_hover_text(hover_info),
                )

            deliver_revision_gated_editor_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                editor_widget_for_path=self._host.editor_widget_for_path,
                buffer_revision=self._host.editor_buffer_revision,
                deliver=deliver,
            )

        def on_error(exc: Exception) -> None:
            self._host.log_warning("Hover request failed for %s: %s", file_path, exc)

        self._host.intelligence_controller().request_hover_info(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def request_editor_completions_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        prefix: str,
        source_text: str,
        cursor_position: int,
        manual_trigger: bool,
        request_generation: int,
        trigger_kind: str,
        trigger_character: str,
    ) -> None:
        started_at = time.perf_counter()
        requested_revision = self._host.editor_buffer_revision(file_path)
        loaded_project = self._host.loaded_project()
        request = CompletionRequest(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if loaded_project is None else loaded_project.project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._host.completion_min_chars(),
            max_results=100,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            buffer_revision=requested_revision,
        )
        intelligence_controller = self._host.intelligence_controller()
        completion_context = build_completion_context(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if loaded_project is None else loaded_project.project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._host.completion_min_chars(),
            max_results=100,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            buffer_revision=requested_revision,
        )
        runtime_query = resolve_runtime_introspection_query_with_inference(
            context=completion_context,
            project_root=None if loaded_project is None else loaded_project.project_root,
            current_file_path=file_path,
            source_text=source_text,
        )
        coordinator = self._host.runtime_introspection_coordinator()
        runtime_items: list[CompletionItem] = []
        if coordinator is not None and runtime_query is not None:
            cached = coordinator.cached_items(runtime_query)
            if cached:
                runtime_items = attach_replacement_metadata(cached, context=completion_context)

        fast_envelope = intelligence_controller.complete_fast(request=request)
        merged_fast_items = _merge_completion_items(fast_envelope.items, runtime_items)
        if merged_fast_items:
            if not is_stale_revision_gated_editor_request(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                editor_widget_for_path=self._host.editor_widget_for_path,
                buffer_revision=self._host.editor_buffer_revision,
            ):
                if self._host.intelligence_metrics_logging_enabled():
                    self._host.log_info(
                        "Completion telemetry: file=%s phase=%s count=%s timings=%s",
                        file_path,
                        fast_envelope.source_phase,
                        len(fast_envelope.items),
                        fast_envelope.latency_breakdown,
                    )
                editor_widget.show_completion_items_for_request(
                    request_generation=request_generation,
                    prefix=prefix,
                    items=merged_fast_items,
                )

        if (
            coordinator is not None
            and runtime_query is not None
            and coordinator.cached_items(runtime_query) is None
        ):
            introspection_key = f"runtime_introspect:{runtime_query.target_path}"

            def introspection_task(_cancellation: object) -> list[CompletionItem]:
                return coordinator.fetch_and_cache_from_runner(runtime_query)

            def introspection_success(items: list[CompletionItem]) -> None:
                if is_stale_revision_gated_editor_request(
                    file_path=file_path,
                    editor_widget=editor_widget,
                    requested_revision=requested_revision,
                    editor_widget_for_path=self._host.editor_widget_for_path,
                    buffer_revision=self._host.editor_buffer_revision,
                ):
                    return
                attached = attach_replacement_metadata(items, context=completion_context)
                if not attached:
                    return
                merged = _merge_completion_items(fast_envelope.items, attached)
                editor_widget.show_completion_items_for_request(
                    request_generation=request_generation,
                    prefix=prefix,
                    items=merged,
                )

            def introspection_error(exc: Exception) -> None:
                self._host.log_warning(
                    "Runtime introspection failed for %s: %s",
                    runtime_query.target_path,
                    exc,
                )

            self._host.background_tasks().run(
                key=introspection_key,
                task=introspection_task,
                on_success=introspection_success,
                on_error=introspection_error,
            )

        def on_success(result: CompletionRequestResult) -> None:
            generation = result.request_generation
            completion_prefix = result.prefix
            completions = result.envelope.items

            def deliver() -> None:
                degradation_reason = result.envelope.degradation_reason
                if degradation_reason and degradation_reason not in self._host.reported_completion_degradation_reasons():
                    self._host.reported_completion_degradation_reasons().add(degradation_reason)
                    self._host.show_status_message(
                        "Python completion is using approximate results; semantic engine failed. See app log.",
                        5000,
                    )
                if self._host.intelligence_metrics_logging_enabled():
                    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                    if elapsed_ms > 150.0:
                        self._host.log_warning(
                            "Completion latency warning: file=%s phase=%s elapsed_ms=%.2f count=%s timings=%s",
                            file_path,
                            result.envelope.source_phase,
                            elapsed_ms,
                            len(completions),
                            result.envelope.latency_breakdown,
                        )
                    else:
                        self._host.log_info(
                            "Completion telemetry: file=%s phase=%s elapsed_ms=%.2f count=%s timings=%s",
                            file_path,
                            result.envelope.source_phase,
                            elapsed_ms,
                            len(completions),
                            result.envelope.latency_breakdown,
                        )
                editor_widget.show_completion_items_for_request(
                    request_generation=generation,
                    prefix=completion_prefix,
                    items=completions,
                )

            deliver_revision_gated_editor_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=result.buffer_revision,
                editor_widget_for_path=self._host.editor_widget_for_path,
                buffer_revision=self._host.editor_buffer_revision,
                deliver=deliver,
            )

        def on_error(exc: Exception) -> None:
            self._host.log_warning("Async completion request failed for %s: %s", file_path, exc)

        intelligence_controller.request_completion(
            request=request,
            prefix=prefix,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def _choose_definition_location(self, locations: list[object]):  # type: ignore[no-untyped-def]
        if not locations:
            return None
        if len(locations) == 1:
            return locations[0]

        parent = self._host.dialog_parent()
        labels: list[str] = []
        by_label: dict[str, object] = {}
        for location in locations:
            file_path = str(getattr(location, "file_path", ""))
            line_number = int(getattr(location, "line_number", 0) or 0)
            symbol_kind = str(getattr(location, "symbol_kind", "symbol"))
            label = f"{Path(file_path).name}:{line_number} ({symbol_kind})"
            labels.append(label)
            by_label[label] = location
        selected_label, ok = QInputDialog.getItem(
            parent,
            "Choose Definition Target",
            "Multiple definition targets found:",
            labels,
            0,
            editable=False,
        )
        if not ok or not selected_label:
            return None
        return by_label.get(selected_label)

    def _build_inline_signature_text(
        self,
        *,
        file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> str | None:
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        return self._host.intelligence_controller().build_inline_signature_text(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )

    def _build_inline_hover_text(
        self,
        *,
        file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> str | None:
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        return self._host.intelligence_controller().build_inline_hover_text(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )


class MainWindowSemanticNavigationHost:
    """Host ports for ``SemanticNavigationWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> Any:
        return self._window

    def loaded_project(self) -> object | None:
        return self._window._loaded_project

    def editor_manager(self) -> Any:
        return self._window._editor_manager

    def active_editor_widget(self) -> CodeEditorWidget | None:
        return self._window._active_editor_widget()

    def editor_widget_for_path(self, file_path: str) -> CodeEditorWidget | None:
        return self._window._editor_widgets_by_path.get(file_path)

    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        return self._window._editor_widgets_by_path

    def intelligence_controller(self) -> Any:
        return self._window._intelligence_controller

    def editor_buffer_revision(self, file_path: str) -> int | None:
        return self._window._editor_buffer_revision(file_path)

    def open_file_at_line(self, file_path: str, line_number: int) -> None:
        self._window._open_file_at_line(file_path, line_number)

    def outline_symbols_for_path(self, file_path: str) -> list[object] | None:
        return self._window._outline_symbols_by_path.get(file_path)

    def set_outline_symbols_for_path(self, file_path: str, symbols: list[object]) -> None:
        self._window._outline_symbols_by_path[file_path] = symbols

    def background_tasks(self) -> Any:
        return self._window._background_tasks

    def problems_panel(self) -> Any | None:
        return self._window._problems_panel

    def update_problems_tab_title(self, problem_count: int) -> None:
        self._window._update_problems_tab_title(problem_count)

    def focus_problems_tab(self) -> None:
        self._window._focus_problems_tab()

    def set_latest_import_issue_report(self, report: object) -> None:
        self._window._latest_import_issue_report = report

    def refresh_latest_runtime_issue_report(self) -> None:
        self._window._latest_runtime_issue_report = self._window._build_runtime_issue_report()

    def open_runtime_center_dialog(self, *, title: str, report: object) -> None:
        self._window._open_runtime_center_dialog(title=title, report=report)

    def known_runtime_modules(self) -> set[str]:
        return self._window._known_runtime_modules

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._window._lint_rule_overrides

    def completion_min_chars(self) -> int:
        return self._window._completion_min_chars

    def intelligence_metrics_logging_enabled(self) -> bool:
        return self._window._intelligence_runtime_settings.metrics_logging_enabled

    def reported_completion_degradation_reasons(self) -> set[str]:
        return self._window._reported_completion_degradation_reasons

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self._window.statusBar().showMessage(message, timeout_ms)

    def log_warning(self, message: str, *args: object) -> None:
        self._window._logger.warning(message, *args)

    def log_info(self, message: str, *args: object) -> None:
        self._window._logger.info(message, *args)

    def runtime_introspection_coordinator(self) -> RuntimeIntrospectionCoordinator | None:
        return self._window._runtime_introspection_coordinator
