"""Inline hover and signature-help workflows for the shell."""

from __future__ import annotations

from PySide2.QtWidgets import QMessageBox

from app.editors.code_editor_widget import CodeEditorWidget
from app.shell.editor_stale_result_policy import deliver_revision_gated_editor_result
from app.shell.semantic_navigation_host import SemanticNavigationHost


class InlineIntelligenceWorkflow:
    """Menu and async inline hover/signature intelligence."""

    def __init__(self, host: SemanticNavigationHost) -> None:
        self._host = host

    def handle_signature_help_action(self) -> None:
        parent = self._host.dialog_parent()
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        editor_widget = self._host.active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Signature Help", "Open a file tab first.")
            return

        file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()
        request_generation = editor_widget.allocate_signature_help_request_generation()
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        requested_revision = self._host.editor_buffer_revision(file_path)

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            generation, signature = payload

            def deliver() -> None:
                tooltip_text = self._host.intelligence_controller().format_inline_signature_text(signature)
                if not tooltip_text:
                    QMessageBox.information(
                        parent,
                        "Signature Help",
                        "No callable signature information available.",
                    )
                    return
                editor_widget.show_calltip(tooltip_text)

            deliver_revision_gated_editor_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                editor_widget_for_path=self._host.editor_widget_for_path,
                buffer_revision=self._host.editor_buffer_revision,
                deliver=deliver,
                requested_generation=request_generation,
                current_generation=editor_widget.signature_help_request_generation(),
            )

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Signature Help", f"Lookup failed: {exc}")

        self._host.intelligence_controller().request_signature_help(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def handle_hover_info_action(self) -> None:
        parent = self._host.dialog_parent()
        editor_manager = self._host.editor_manager()
        active_tab = editor_manager.active_tab()
        editor_widget = self._host.active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(parent, "Hover Info", "Open a file tab first.")
            return

        file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()
        request_generation = editor_widget.allocate_hover_request_generation()
        loaded_project = self._host.loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        requested_revision = self._host.editor_buffer_revision(file_path)

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            generation, hover_info = payload

            def deliver() -> None:
                tooltip_text = self._host.intelligence_controller().format_inline_hover_text(hover_info)
                if not tooltip_text:
                    QMessageBox.information(parent, "Hover Info", "No symbol info available.")
                    return
                editor_widget.show_calltip(tooltip_text)

            deliver_revision_gated_editor_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                editor_widget_for_path=self._host.editor_widget_for_path,
                buffer_revision=self._host.editor_buffer_revision,
                deliver=deliver,
                requested_generation=request_generation,
                current_generation=editor_widget.hover_request_generation(),
            )

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(parent, "Hover Info", f"Lookup failed: {exc}")

        self._host.intelligence_controller().request_hover_info(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

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
                requested_generation=request_generation,
                current_generation=editor_widget.signature_help_request_generation(),
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
                requested_generation=request_generation,
                current_generation=editor_widget.hover_request_generation(),
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
