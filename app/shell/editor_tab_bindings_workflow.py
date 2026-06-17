"""Editor widget intelligence and lifecycle signal bindings."""

from __future__ import annotations

from typing import Any, Protocol

from app.editors.code_editor_widget import CodeEditorWidget
from app.intelligence.completion_models import CompletionItem


class EditorTabBindingsHost(Protocol):
    """Host ports for attaching per-tab editor widget bindings."""

    def semantic_navigation_workflow(self) -> Any:
        ...

    def enable_auto_reindent_flat_python_paste_from_hint(self) -> Any:
        ...

    def handle_paste_hint_repair_result(self) -> Any:
        ...


class EditorTabBindingsWorkflow:
    """Wires intelligence, debug, and tab lifecycle callbacks onto editor widgets."""

    def attach(
        self,
        host: EditorTabBindingsHost,
        editor_widget: CodeEditorWidget,
        file_path: str,
        *,
        tab_workflow: Any,
        debug_control_workflow: Any,
    ) -> None:
        semantic_navigation = host.semantic_navigation_workflow()

        def completion_requester(
            source_text: str,
            cursor_position: int,
            manual_trigger: bool,
            request_generation: int,
            trigger_kind: str,
            trigger_character: str,
        ) -> None:
            semantic_navigation.request_editor_completions_async(
                file_path=file_path,
                editor_widget=editor_widget,
                source_text=source_text,
                cursor_position=cursor_position,
                manual_trigger=manual_trigger,
                request_generation=request_generation,
                trigger_kind=trigger_kind,
                trigger_character=trigger_character,
            )

        def hover_requester(source_text: str, cursor_position: int, request_generation: int) -> None:
            semantic_navigation.request_inline_hover_text_async(
                file_path=file_path,
                editor_widget=editor_widget,
                source_text=source_text,
                cursor_position=cursor_position,
                request_generation=request_generation,
            )

        def signature_requester(source_text: str, cursor_position: int, request_generation: int) -> None:
            semantic_navigation.request_inline_signature_text_async(
                file_path=file_path,
                editor_widget=editor_widget,
                source_text=source_text,
                cursor_position=cursor_position,
                request_generation=request_generation,
            )

        def completion_resolve_requester(
            item: CompletionItem,
            source_text: str,
            cursor_position: int,
            request_generation: int,
        ) -> None:
            semantic_navigation.request_completion_item_resolve_async(
                file_path=file_path,
                editor_widget=editor_widget,
                item=item,
                source_text=source_text,
                cursor_position=cursor_position,
                request_generation=request_generation,
            )

        def on_breakpoint_toggled(line_number: int, enabled: bool) -> None:
            debug_control_workflow.handle_editor_breakpoint_toggled(file_path, line_number, enabled)

        def on_text_changed() -> None:
            tab_workflow.handle_editor_text_changed(file_path, editor_widget)

        def on_cursor_position_changed() -> None:
            tab_workflow.handle_editor_cursor_position_changed(file_path, editor_widget)

        def on_completion_accepted(item: CompletionItem) -> None:
            semantic_navigation.record_editor_completion_acceptance(
                file_path=file_path,
                item=item,
            )

        editor_widget.set_breakpoint_toggled_callback(on_breakpoint_toggled)
        editor_widget.set_completion_requester(completion_requester)
        editor_widget.set_completion_resolve_requester(completion_resolve_requester)
        editor_widget.set_completion_accepted_callback(on_completion_accepted)
        editor_widget.set_hover_requester(hover_requester)
        editor_widget.set_signature_help_requester(signature_requester)
        editor_widget.set_paste_hint_enable_always_callback(
            host.enable_auto_reindent_flat_python_paste_from_hint()
        )
        editor_widget.set_paste_hint_status_callback(host.handle_paste_hint_repair_result())
        editor_widget.set_breakpoints(
            debug_control_workflow.breakpoint_store.lines_for_file(file_path)
        )
        editor_widget.textChanged.connect(on_text_changed)
        editor_widget.cursorPositionChanged.connect(on_cursor_position_changed)


__all__ = ["EditorTabBindingsHost", "EditorTabBindingsWorkflow"]
