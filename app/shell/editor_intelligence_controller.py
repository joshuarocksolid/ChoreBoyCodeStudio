"""Controller for editor semantic routing and result formatting."""
from __future__ import annotations

from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_service import CompletionRequest
from app.intelligence.semantic_models import SemanticHoverResult, SemanticSignatureResult
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

    def complete_blocking(self, *, request: CompletionRequest) -> list[CompletionItem]:
        return self._semantic_session.complete_blocking(request=request)

    def request_completion(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._semantic_session.request_completion(**kwargs)

    def request_lookup_definition(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._semantic_session.request_lookup_definition(**kwargs)

    def request_find_references(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._semantic_session.request_find_references(**kwargs)

    def request_rename_plan(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._semantic_session.request_rename_plan(**kwargs)

    def request_apply_rename(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._semantic_session.request_apply_rename(**kwargs)

    def request_hover_info(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._semantic_session.request_hover_info(**kwargs)

    def request_signature_help(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._semantic_session.request_signature_help(**kwargs)

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
