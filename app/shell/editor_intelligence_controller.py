"""Controller for editor semantic routing and result formatting."""
from __future__ import annotations

from typing import Callable

from app.intelligence.completion_models import (
    CompletionEnvelope,
    CompletionItem,
    CompletionRequestResult,
    CompletionResolveRequest,
    CompletionResolveResult,
)
from app.intelligence.completion_service import CompletionRequest
from app.intelligence.semantic_models import (
    SemanticDefinitionResult,
    SemanticHoverResult,
    SemanticReferenceResult,
    SemanticRenameApplyResult,
    SemanticRenamePlan,
    SemanticSignatureResult,
)
from app.intelligence.semantic_session import SemanticSession


class EditorIntelligenceController:
    """Owns semantic request routing and inline result formatting."""

    def __init__(self, *, semantic_session: SemanticSession) -> None:
        self._semantic_session = semantic_session

    def cancel_all(self) -> None:
        self._semantic_session.cancel_all()

    def shutdown(self) -> None:
        self._semantic_session.shutdown()

    def record_completion_acceptance(self, item: CompletionItem) -> None:
        self._semantic_session.record_completion_acceptance(item)

    def complete_blocking(self, *, request: CompletionRequest) -> CompletionEnvelope:
        return self._semantic_session.complete_blocking(request=request)

    def complete_fast(self, *, request: CompletionRequest) -> CompletionEnvelope:
        return self._semantic_session.complete_fast(request=request)

    def request_completion(
        self,
        *,
        request: CompletionRequest,
        prefix: str,
        request_generation: int,
        on_success: Callable[[CompletionRequestResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_completion(
            request=request,
            prefix=prefix,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def request_completion_resolve(
        self,
        *,
        request: CompletionResolveRequest,
        on_success: Callable[[CompletionResolveResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_completion_resolve(
            request=request,
            on_success=on_success,
            on_error=on_error,
        )

    def request_lookup_definition(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        on_success: Callable[[SemanticDefinitionResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_lookup_definition(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            on_success=on_success,
            on_error=on_error,
        )

    def request_find_references(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        on_success: Callable[[SemanticReferenceResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_find_references(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            on_success=on_success,
            on_error=on_error,
        )

    def request_rename_plan(
        self,
        *,
        project_root: str,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        new_symbol: str,
        on_success: Callable[[SemanticRenamePlan | None], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_rename_plan(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            new_symbol=new_symbol,
            on_success=on_success,
            on_error=on_error,
        )

    def request_apply_rename(
        self,
        *,
        plan: SemanticRenamePlan,
        on_success: Callable[[SemanticRenameApplyResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_apply_rename(
            plan=plan,
            on_success=on_success,
            on_error=on_error,
        )

    def request_hover_info(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        request_generation: int,
        on_success: Callable[[tuple[int, SemanticHoverResult | None]], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_hover_info(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def request_signature_help(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        request_generation: int,
        on_success: Callable[[tuple[int, SemanticSignatureResult | None]], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._semantic_session.request_signature_help(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def build_inline_signature_text(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> str | None:
        signature = self._semantic_session.resolve_signature_help_blocking(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        return self.format_inline_signature_text(signature)

    def build_inline_hover_text(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> str | None:
        hover_info = self._semantic_session.resolve_hover_info_blocking(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        return self.format_inline_hover_text(hover_info)

    @staticmethod
    def format_inline_signature_text(signature: SemanticSignatureResult | None) -> str | None:
        if signature is None:
            return None
        details = [
            signature.signature_text,
            f"Active parameter index: {signature.argument_index}",
            f"Source: {signature.source}",
            f"Confidence: {signature.metadata.confidence}",
        ]
        if signature.doc_summary:
            details.insert(1, f"Doc: {signature.doc_summary}")
        return "\n".join(details)

    @staticmethod
    def format_inline_hover_text(hover_info: SemanticHoverResult | None) -> str | None:
        if hover_info is None:
            return None

        details = [f"Symbol: {hover_info.symbol_name}", f"Kind: {hover_info.symbol_kind}"]
        if hover_info.file_path:
            details.append(f"File: {hover_info.file_path}")
        if hover_info.line_number is not None:
            details.append(f"Line: {hover_info.line_number}")
        if hover_info.doc_summary:
            details.append(f"Doc: {hover_info.doc_summary}")
        details.append(f"Source: {hover_info.source}")
        details.append(f"Confidence: {hover_info.metadata.confidence}")
        if hover_info.metadata.unsupported_reason:
            details.append(f"Reason: {hover_info.metadata.unsupported_reason}")
        return "\n".join(details)
