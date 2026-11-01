"""Semantic rename symbol workflow for the shell."""

from __future__ import annotations

import time

from app.qt.QtWidgets import QInputDialog, QLineEdit, QMessageBox

from app.shell.semantic_navigation_host import SemanticNavigationHost


class SemanticRenameWorkflow:
    """Rename symbol menu action and apply flow."""

    def __init__(self, host: SemanticNavigationHost) -> None:
        self._host = host

    def handle_rename_symbol_action(self) -> None:
        parent = self._host.dialog_parent()
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            QMessageBox.warning(parent, "Rename Symbol", "Open a project first.")
            return
        hook = getattr(parent, "_form_builder_method_rename", None)
        seed_of = getattr(hook, "seed", None) if hook is not None else None
        seed = seed_of(parent) if callable(seed_of) else None
        if seed is not None:
            old_symbol = str(getattr(seed, "old_name", "") or "")
            current_file_path = str(getattr(seed, "window_path", "") or "")
            source_text = str(getattr(seed, "source", "") or "")
            cursor_position = int(getattr(seed, "cursor", 0) or 0)
        else:
            editor_manager = self._host.editor_manager()
            active_tab = editor_manager.active_tab()
            editor_widget = self._host.active_editor_widget()
            if active_tab is None or editor_widget is None:
                QMessageBox.warning(parent, "Rename Symbol", "Open a file tab first.")
                return
            old_symbol = editor_widget.word_under_cursor()
            current_file_path = active_tab.file_path
            source_text = editor_widget.toPlainText()
            cursor_position = editor_widget.textCursor().position()

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
        if hook is not None:
            refuse = getattr(hook, "refusal", None)
            sentence = refuse(parent, old_symbol, new_symbol, current_file_path) if callable(refuse) else ""
            if sentence:
                QMessageBox.warning(parent, "Rename Symbol", sentence)
                return

        if not self._host.save_all_files():
            QMessageBox.warning(parent, "Rename Symbol", "Fix save errors before renaming.")
            return
        project_root = loaded_project.project_root
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

            applied = plan
            if seed is not None and hook is not None:
                paired = getattr(hook, "apply_paired", None)
                if callable(paired):
                    follow = paired(parent, seed, plan)
                    if getattr(follow, "blocked", False):
                        message = str(getattr(follow, "message", "") or "")
                        if message:
                            QMessageBox.warning(parent, "Rename Symbol", message)
                        return
                    applied = getattr(follow, "plan", plan)
                    if not getattr(applied, "preview_patches", None):
                        QMessageBox.information(
                            parent,
                            "Rename Symbol",
                            f"Renamed '{old_symbol}' to '{new_symbol}'.",
                        )
                        return

            def on_apply_success(result) -> None:  # type: ignore[no-untyped-def]
                self._host.record_local_history_transaction(
                    {patch.file_path: patch.updated_content for patch in applied.preview_patches},
                    source="semantic_rename",
                    label=f"Rename '{applied.old_symbol}' to '{applied.new_symbol}'",
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
                plan=applied,
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
