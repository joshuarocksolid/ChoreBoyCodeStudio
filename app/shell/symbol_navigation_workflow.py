"""Symbol navigation menu handlers for the shell."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from PySide2.QtWidgets import QDialog, QInputDialog, QLineEdit, QMessageBox

from app.shell.problems_panel import ResultItem
from app.shell.quick_symbol_dialog import QuickSymbolDialog
from app.shell.semantic_navigation_host import SemanticNavigationHost


class SymbolNavigationWorkflow:
    """Go-to-definition, find references, rename, and in-file symbol navigation."""

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
        editor_widget = self._host.editor_widget_for_path(str(Path(file_path).expanduser().resolve()))
        source = editor_widget.toPlainText() if editor_widget is not None else active_tab.current_content
        original_line = editor_widget.textCursor().blockNumber() + 1 if editor_widget is not None else 1

        def _show_symbol_dialog(flat: tuple[object, ...]) -> None:
            if not flat:
                QMessageBox.information(parent, "Go to Symbol", "No symbols in this file.")
                return
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

        def _on_outline_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Go to Symbol", f"Outline failed: {exc}")

        self._host.request_flat_outline_symbols_async(
            file_path,
            fallback_source=source or "",
            on_success=_show_symbol_dialog,
            on_error=_on_outline_error,
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

    def handle_find_references_action(self) -> None:
        parent = self._host.dialog_parent()
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            QMessageBox.warning(parent, "Find References", "Open a project first.")
            return
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        editor_widget = self._host.active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Find References", "Open a file tab first.")
            return
        project_root = loaded_project.project_root
        current_file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()
        started_at = time.perf_counter()

        def on_success(result) -> None:  # type: ignore[no-untyped-def]
            if self._host.intelligence_metrics_logging_enabled():
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                if elapsed_ms > 1200.0:
                    self._host.log_warning(
                        "References latency warning: file=%s symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        result.symbol_name,
                        elapsed_ms,
                        len(result.hits),
                    )
                else:
                    self._host.log_info(
                        "References telemetry: file=%s symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        result.symbol_name,
                        elapsed_ms,
                        len(result.hits),
                    )
            if not result.symbol_name:
                QMessageBox.information(parent, "Find References", "Place cursor on a symbol first.")
                return
            if not result.hits:
                if result.metadata.unsupported_reason:
                    if result.metadata.source == "semantic_unavailable":
                        QMessageBox.warning(
                            parent,
                            "Find References",
                            (
                                "Semantic references are currently unavailable.\n\n"
                                f"Reason: {result.metadata.unsupported_reason}"
                            ),
                        )
                        return
                    QMessageBox.information(
                        parent,
                        "Find References",
                        (
                            f"No semantic references found for '{result.symbol_name}'.\n\n"
                            "The symbol may be dynamic or unresolved. Use Find in Files for text search."
                        ),
                    )
                else:
                    QMessageBox.information(
                        parent,
                        "Find References",
                        f"No references found for '{result.symbol_name}'.",
                    )
                return

            problems_panel = self._host.problems_panel()
            if problems_panel is None:
                return
            ref_items = [
                ResultItem(
                    label=f"[{'def' if hit.is_definition else 'ref'}] {hit.line_text.strip()}",
                    file_path=hit.file_path,
                    line_number=hit.line_number,
                    tooltip=hit.file_path,
                )
                for hit in result.hits
            ]
            problems_panel.set_results(f"References: {result.symbol_name}", ref_items)
            self._host.update_problems_tab_title(problems_panel.problem_count())
            self._host.focus_problems_tab()

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Find References", f"Reference search failed: {exc}")

        self._host.intelligence_controller().request_find_references(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            on_success=on_success,
            on_error=on_error,
        )

    def handle_rename_symbol_action(self) -> None:
        parent = self._host.dialog_parent()
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            QMessageBox.warning(parent, "Rename Symbol", "Open a project first.")
            return
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        editor_widget = self._host.active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Rename Symbol", "Open a file tab first.")
            return

        old_symbol = editor_widget.word_under_cursor()
        if not old_symbol:
            QMessageBox.information(parent, "Rename Symbol", "Place cursor on a symbol first.")
            return
        new_symbol, ok = QInputDialog.getText(
            parent,
            "Rename Symbol",
            f"Rename '{old_symbol}' to:",
            QLineEdit.Normal,
            old_symbol,
        )
        if not ok:
            return
        new_symbol = new_symbol.strip()
        if not new_symbol or new_symbol == old_symbol:
            return
        if not new_symbol.isidentifier():
            QMessageBox.warning(parent, "Rename Symbol", "New name must be a valid Python identifier.")
            return

        if not self._host.save_all_files():
            QMessageBox.warning(parent, "Rename Symbol", "Fix save errors before renaming.")
            return
        project_root = loaded_project.project_root
        current_file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()
        started_at = time.perf_counter()

        def on_success(plan) -> None:  # type: ignore[no-untyped-def]
            if self._host.intelligence_metrics_logging_enabled():
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                hit_count = 0 if plan is None else len(plan.hits)
                if elapsed_ms > 800.0:
                    self._host.log_warning(
                        "Rename planning latency warning: file=%s old_symbol=%s new_symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        old_symbol,
                        new_symbol,
                        elapsed_ms,
                        hit_count,
                    )
                else:
                    self._host.log_info(
                        "Rename planning telemetry: file=%s old_symbol=%s new_symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        old_symbol,
                        new_symbol,
                        elapsed_ms,
                        hit_count,
                    )
            if plan is None or not plan.preview_patches:
                QMessageBox.information(
                    parent,
                    "Rename Symbol",
                    f"No safe semantic rename plan found for '{old_symbol}'.",
                )
                return

            preview_chunks = [patch.diff_text for patch in plan.preview_patches[:3]]
            preview_body = "\n\n".join(chunk for chunk in preview_chunks if chunk)
            if len(plan.preview_patches) > 3:
                preview_body += f"\n\n... and {len(plan.preview_patches) - 3} more file patch(es)"
            confidence_text = ""
            if plan.metadata and plan.metadata.confidence == "exact":
                confidence_text = "Confidence: proven by semantic engine"
            elif plan.metadata and plan.metadata.confidence == "approximate":
                confidence_text = "Confidence: approximate — review changes carefully"
            confirm = QMessageBox.question(
                parent,
                "Rename Preview",
                (
                    f"Rename '{plan.old_symbol}' to '{plan.new_symbol}'?\n"
                    f"Occurrences: {len(plan.hits)} across {len(plan.touched_files)} file(s)\n"
                    f"{confidence_text}\n\n"
                    f"{preview_body}"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirm != QMessageBox.Yes:
                return

            def on_apply_success(result) -> None:  # type: ignore[no-untyped-def]
                self._host.record_local_history_transaction(
                    {patch.file_path: patch.updated_content for patch in plan.preview_patches},
                    source="semantic_rename",
                    label=f"Rename '{plan.old_symbol}' to '{plan.new_symbol}'",
                )
                self._host.refresh_open_tabs_from_disk(result.changed_files)
                self._host.reload_current_project()
                QMessageBox.information(
                    parent,
                    "Rename Symbol",
                    f"Renamed {result.changed_occurrences} occurrence(s) across {len(result.changed_files)} file(s).",
                )

            def on_apply_error(exc: Exception) -> None:
                QMessageBox.warning(parent, "Rename Symbol", f"Failed to apply rename: {exc}")

            self._host.intelligence_controller().request_apply_rename(
                plan=plan,
                on_success=on_apply_success,
                on_error=on_apply_error,
            )

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Rename Symbol", f"Rename planning failed: {exc}")

        self._host.intelligence_controller().request_rename_plan(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            new_symbol=new_symbol,
            on_success=on_success,
            on_error=on_error,
        )
