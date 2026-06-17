"""Semantic navigation coordinator delegating to focused shell workflows."""

from __future__ import annotations

from collections.abc import Callable

from app.editors.code_editor_widget import CodeEditorWidget
from app.shell.intelligence_types import CompletionItem
from app.shell.editor_completion_workflow import EditorCompletionWorkflow
from app.shell.inline_intelligence_workflow import InlineIntelligenceWorkflow
from app.shell.semantic_navigation_host import (
    MainWindowSemanticNavigationHost,
    SemanticNavigationHost,
)
from app.shell.semantic_rename_workflow import SemanticRenameWorkflow
from app.shell.symbol_navigation_workflow import SymbolNavigationWorkflow

__all__ = [
    "MainWindowSemanticNavigationHost",
    "SemanticNavigationHost",
    "SemanticNavigationWorkflow",
]


class SemanticNavigationWorkflow:
    """Thin coordinator for semantic navigation and inline intelligence."""

    def __init__(self, host: SemanticNavigationHost) -> None:
        self._host = host
        self._symbols = SymbolNavigationWorkflow(host)
        self._inline = InlineIntelligenceWorkflow(host)
        self._rename = SemanticRenameWorkflow(host)
        self._completions = EditorCompletionWorkflow(host)

    def handle_go_to_definition_action(self) -> None:
        self._symbols.handle_go_to_definition_action()

    def record_editor_completion_acceptance(self, *, file_path: str, item: CompletionItem) -> None:
        self._completions.record_editor_completion_acceptance(file_path=file_path, item=item)

    def handle_signature_help_action(self) -> None:
        self._inline.handle_signature_help_action()

    def handle_hover_info_action(self) -> None:
        self._inline.handle_hover_info_action()

    def handle_goto_symbol_in_file_action(self) -> None:
        self._symbols.handle_goto_symbol_in_file_action()

    def request_inline_signature_text_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
        cursor_position: int,
        request_generation: int,
    ) -> None:
        self._inline.request_inline_signature_text_async(
            file_path=file_path,
            editor_widget=editor_widget,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
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
        self._inline.request_inline_hover_text_async(
            file_path=file_path,
            editor_widget=editor_widget,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
        )

    def request_editor_completions_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
        cursor_position: int,
        manual_trigger: bool,
        request_generation: int,
        trigger_kind: str,
        trigger_character: str,
    ) -> None:
        self._completions.request_editor_completions_async(
            file_path=file_path,
            editor_widget=editor_widget,
            source_text=source_text,
            cursor_position=cursor_position,
            manual_trigger=manual_trigger,
            request_generation=request_generation,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
        )

    def handle_find_references_action(self) -> None:
        self._symbols.handle_find_references_action()

    def handle_rename_symbol_action(self) -> None:
        self._rename.handle_rename_symbol_action()

    def request_completion_item_resolve_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        item: CompletionItem,
        source_text: str,
        cursor_position: int,
        request_generation: int,
    ) -> None:
        self._completions.request_completion_item_resolve_async(
            file_path=file_path,
            editor_widget=editor_widget,
            item=item,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
        )
