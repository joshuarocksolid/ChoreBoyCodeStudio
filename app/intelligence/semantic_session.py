"""Serialized semantic session owning semantic engines and completion state."""
from __future__ import annotations

from typing import Callable, TypeVar, cast

T = TypeVar("T")

from app.bootstrap.paths import PathInput
from app.intelligence.completion_models import (
    CompletionFastResult,
    CompletionEnvelope,
    CompletionItem,
    CompletionRequestResult,
    CompletionResolveRequest,
    CompletionResolveResult,
)
from app.intelligence.completion_resolver import CompletionResolver
from app.intelligence.completion_service import CompletionRequest, CompletionService
from app.intelligence.semantic_facade import SemanticFacade
from app.intelligence.semantic_models import (
    SemanticDefinitionResult,
    SemanticHoverResult,
    SemanticRenameApplyResult,
    SemanticReferenceResult,
    SemanticRenamePlan,
    SemanticSignatureResult,
)
from app.intelligence.semantic_worker import SemanticWorker


class SemanticSession:
    """Owns semantic engines behind one serialized worker lane."""

    def __init__(
        self,
        *,
        dispatch_to_main_thread: Callable[[Callable[[], None]], None],
        cache_db_path: str,
        state_root: PathInput | None = None,
    ) -> None:
        self._semantic_facade = SemanticFacade(
            cache_db_path=cache_db_path,
            state_root=state_root,
        )
        self._completion_service = CompletionService(
            cache_db_path=cache_db_path,
            semantic_facade=self._semantic_facade,
        )
        self._completion_resolver = CompletionResolver(semantic_facade=self._semantic_facade)
        self._worker = SemanticWorker(dispatch_to_main_thread=dispatch_to_main_thread)

    def _submit(
        self,
        *,
        key: str,
        priority: int,
        task: Callable[[], T],
        on_success: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._worker.submit(
            key=key,
            task=task,
            on_success=cast(Callable[[object], None], on_success) if on_success is not None else None,
            on_error=on_error,
            priority=priority,
        )

    def shutdown(self) -> None:
        """Stop the backing worker thread."""
        self._worker.shutdown()

    def cancel_all(self) -> None:
        """Invalidate all queued semantic work."""
        self._worker.cancel_all()

    def request_record_completion_acceptance(
        self,
        *,
        item: CompletionItem,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Record completion acceptance on the semantic worker."""

        def task() -> None:
            self._completion_service.record_acceptance(item)

        self._submit(key="completion_acceptance", priority=5, task=task, on_error=on_error)

    def request_completion_fast(
        self,
        *,
        request: CompletionRequest,
        prefix: str,
        request_generation: int,
        on_success: Callable[[CompletionFastResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Resolve fast-tier completion candidates on the semantic worker."""

        def task() -> CompletionFastResult:
            envelope = self._completion_service.complete_fast(request)
            return CompletionFastResult(
                request_generation=request_generation,
                prefix=prefix,
                envelope=envelope,
                buffer_revision=request.buffer_revision,
            )

        self._submit(
            key=f"completion_fast:{request.current_file_path}",
            priority=0,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def request_completion(
        self,
        *,
        request: CompletionRequest,
        prefix: str,
        request_generation: int,
        on_success: Callable[[CompletionRequestResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Resolve completion candidates asynchronously."""

        def task() -> CompletionRequestResult:
            envelope = self._completion_service.complete_semantic(request)
            return CompletionRequestResult(
                request_generation=request_generation,
                prefix=prefix,
                envelope=envelope,
                buffer_revision=request.buffer_revision,
            )

        self._submit(
            key=f"completion:{request.current_file_path}",
            priority=10,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def merge_completion_for_display(
        self,
        *,
        fast: CompletionEnvelope | None = None,
        semantic: CompletionEnvelope | None = None,
        runtime_items: list[CompletionItem] | None = None,
        max_results: int = 100,
    ) -> CompletionEnvelope:
        """Merge tiered completion envelopes for editor popup display."""
        return self._completion_service.merge_for_editor_display(
            fast=fast,
            semantic=semantic,
            runtime_items=runtime_items,
            max_results=max_results,
        )

    def request_completion_resolve(
        self,
        *,
        request: CompletionResolveRequest,
        on_success: Callable[[CompletionResolveResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Resolve lazy metadata for a selected completion item."""

        def task() -> CompletionResolveResult:
            item = self._completion_resolver.resolve(request)
            return CompletionResolveResult(
                request_generation=request.request_generation,
                item=item,
                buffer_revision=request.buffer_revision,
                context_fingerprint=request.context_fingerprint,
            )

        self._submit(
            key=f"completion_resolve:{request.current_file_path}:{request.item.item_id or request.item.label}",
            priority=5,
            task=task,
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
        """Resolve go-to-definition on the semantic worker."""

        def task() -> SemanticDefinitionResult:
            return self._semantic_facade.lookup_definition(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            )

        self._submit(
            key=f"definition:{current_file_path}",
            priority=40,
            task=task,
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
        """Resolve project references on the semantic worker."""

        def task() -> SemanticReferenceResult:
            return self._semantic_facade.find_references(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            )

        self._submit(
            key=f"references:{current_file_path}",
            priority=70,
            task=task,
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
        """Plan a semantic rename on the semantic worker."""

        def task() -> SemanticRenamePlan | None:
            return self._semantic_facade.plan_rename(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
                new_symbol=new_symbol,
            )

        self._submit(
            key=f"rename:{current_file_path}",
            priority=70,
            task=task,
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
        """Apply a semantic rename on the semantic worker."""

        def task() -> SemanticRenameApplyResult:
            return self._semantic_facade.apply_rename(plan)

        self._submit(
            key="apply_rename",
            priority=60,
            task=task,
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
        """Resolve hover info asynchronously for one editor request."""

        def task() -> tuple[int, SemanticHoverResult | None]:
            result = self._semantic_facade.resolve_hover_info(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            )
            return (request_generation, result)

        self._submit(
            key=f"hover:{current_file_path}",
            priority=30,
            task=task,
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
        """Resolve signature-help asynchronously for one editor request."""

        def task() -> tuple[int, SemanticSignatureResult | None]:
            result = self._semantic_facade.resolve_signature_help(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            )
            return (request_generation, result)

        self._submit(
            key=f"signature:{current_file_path}",
            priority=25,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def request_custom(
        self,
        *,
        key: str,
        task: Callable[[], object],
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Expose one serialized lane for semantic controller extensions."""
        self._submit(key=key, priority=50, task=task, on_success=on_success, on_error=on_error)
