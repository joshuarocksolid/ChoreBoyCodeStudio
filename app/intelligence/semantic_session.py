"""Serialized semantic session owning semantic engines and completion state."""
from __future__ import annotations

from typing import Callable, Optional, cast

from app.bootstrap.paths import PathInput
from app.intelligence.completion_models import CompletionItem
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
        state_root: Optional[PathInput] = None,
    ) -> None:
        self._semantic_facade = SemanticFacade(
            cache_db_path=cache_db_path,
            state_root=state_root,
        )
        self._completion_service = CompletionService(
            cache_db_path=cache_db_path,
            semantic_facade=self._semantic_facade,
        )
        self._worker = SemanticWorker(dispatch_to_main_thread=dispatch_to_main_thread)

    def shutdown(self) -> None:
        """Stop the backing worker thread."""
        self._worker.shutdown()

    def cancel_all(self) -> None:
        """Invalidate all queued semantic work."""
        self._worker.cancel_all()

    def record_completion_acceptance(self, item: CompletionItem) -> None:
        """Boost ranking for a user-accepted completion."""
        self._completion_service.record_acceptance(item)

    def complete_blocking(self, *, request: CompletionRequest) -> list[CompletionItem]:
        """Resolve completion candidates on the semantic thread and wait for them."""
        result = cast(
            list[CompletionItem],
            self._worker.call(
            key=f"completion_sync:{request.current_file_path}",
            task=lambda: list(self._completion_service.complete(request)),
            ),
        )
        return list(result)

    def request_completion(
        self,
        *,
        request: CompletionRequest,
        prefix: str,
        request_generation: int,
        on_success: Callable[[tuple[int, str, list[CompletionItem]]], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Resolve completion candidates asynchronously."""

        def task() -> tuple[int, str, list[CompletionItem]]:
            completions = list(self._completion_service.complete(request))
            return (request_generation, prefix, completions)

        self._worker.submit(
            key=f"completion:{request.current_file_path}",
            task=task,
            on_success=cast(Callable[[object], None], on_success),
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

        self._worker.submit(
            key="go_to_definition",
            task=task,
            on_success=cast(Callable[[object], None], on_success),
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

        self._worker.submit(
            key="find_references",
            task=task,
            on_success=cast(Callable[[object], None], on_success),
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

        self._worker.submit(
            key="rename_symbol",
            task=task,
            on_success=cast(Callable[[object], None], on_success),
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

        self._worker.submit(
            key="apply_rename",
            task=task,
            on_success=cast(Callable[[object], None], on_success),
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

        self._worker.submit(
            key=f"hover:{current_file_path}",
            task=task,
            on_success=cast(Callable[[object], None], on_success),
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

        self._worker.submit(
            key=f"signature:{current_file_path}",
            task=task,
            on_success=cast(Callable[[object], None], on_success),
            on_error=on_error,
        )

    def resolve_hover_info_blocking(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticHoverResult | None:
        """Resolve hover info on the semantic thread and wait for the result."""
        return cast(
            Optional[SemanticHoverResult],
            self._worker.call(
            key=f"hover_sync:{current_file_path}",
            task=lambda: self._semantic_facade.resolve_hover_info(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            ),
            ),
        )

    def resolve_signature_help_blocking(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticSignatureResult | None:
        """Resolve signature help on the semantic thread and wait for the result."""
        return cast(
            Optional[SemanticSignatureResult],
            self._worker.call(
            key=f"signature_sync:{current_file_path}",
            task=lambda: self._semantic_facade.resolve_signature_help(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            ),
            ),
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
        self._worker.submit(
            key=key,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )
