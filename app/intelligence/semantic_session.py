"""Serialized semantic session owning semantic engines and completion state."""
from __future__ import annotations

from collections.abc import Callable
import threading
import time
from typing import TypeVar, cast

T = TypeVar("T")
U = TypeVar("U")

from app.bootstrap.paths import PathInput
from app.core.constants import UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT
from app.intelligence.completion_context import (
    CompletionContext,
    CompletionSyntacticContext,
    build_completion_context,
)
from app.intelligence.completion_metrics import log_completion_phase
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
from app.intelligence.runtime_members import RUNTIME_INTROSPECTION_PROVIDER
from app.intelligence.runtime_introspection import (
    RuntimeIntrospectionCoordinator,
    RuntimeIntrospectionQuery,
    resolve_runtime_introspection_query,
    resolve_runtime_introspection_query_with_inference,
)
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
from app.project.file_inventory import ProjectInventorySnapshot


_PAINT_GRACE_SECONDS = 0.04


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
        self._repl_listing_warmed = False
        # Runtime docs are one REPL round trip (about 1 ms); do not queue them behind Jedi.
        self._runtime_docs_worker = SemanticWorker(dispatch_to_main_thread=dispatch_to_main_thread)
        self._runtime_targets: dict[tuple[str, str], str] = {}

    def bind_runtime_members(self, runtime_coordinator: RuntimeIntrospectionCoordinator | None) -> None:
        """Let lazy docs resolve runtime members (editor and Python Console rows)."""

        self._completion_resolver.bind_runtime_members(runtime_coordinator)

    def set_inventory_snapshot_provider(
        self,
        provider: Callable[[], ProjectInventorySnapshot | None],
    ) -> None:
        self._completion_service.set_inventory_snapshot_provider(provider)

    def _submit(
        self,
        *,
        key: str,
        priority: int,
        task: Callable[[], T],
        on_success: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        dispatch_on_main_thread: bool = True,
    ) -> None:
        self._worker.submit(
            key=key,
            task=task,
            on_success=cast(Callable[[object], None], on_success) if on_success is not None else None,
            on_error=on_error,
            priority=priority,
            dispatch_on_main_thread=dispatch_on_main_thread,
        )

    def _submit_generation_result(
        self,
        *,
        key: str,
        priority: int,
        request_generation: int,
        resolve: Callable[[], U | None],
        on_success: Callable[[tuple[int, U | None]], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        def task() -> tuple[int, U | None]:
            return (request_generation, resolve())

        self._submit(
            key=key,
            priority=priority,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def request_completion_warmup(
        self,
        *,
        project_root: str | None,
        repl_warm: Callable[[], bool] | None = None,
        refresh_repl: bool = False,
    ) -> None:
        """Queue Jedi warmup on the semantic worker. ``repl_warm`` runs there too."""

        if refresh_repl:
            self._repl_listing_warmed = False

        def task() -> None:
            started_at = time.perf_counter()
            try:
                self._semantic_facade.warm_completion(project_root=project_root)
            finally:
                log_completion_phase(
                    "completion_warmup",
                    (time.perf_counter() - started_at) * 1000.0,
                )
                if repl_warm is not None and not self._repl_listing_warmed:
                    self._repl_listing_warmed = bool(repl_warm())

        self._submit(
            key="completion_warmup",
            priority=80,
            task=task,
            dispatch_on_main_thread=False,
        )

    def request_buffer_warmup(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        prefetch_target: Callable[[str], None] | None = None,
    ) -> None:
        """Infer the open buffer while the worker is otherwise idle.

        Stores a dotted receiver's runtime target and may prefetch its member
        list so the next Ctrl+Space paints without building a Jedi script.
        """

        def task() -> None:
            started_at = time.perf_counter()
            try:
                target = self._semantic_facade.warm_open_buffer(
                    project_root=project_root,
                    current_file_path=current_file_path,
                    source_text=source_text,
                    cursor_position=cursor_position,
                )
                context = build_completion_context(
                    source_text=source_text,
                    cursor_position=cursor_position,
                    current_file_path=current_file_path,
                    project_root=project_root,
                    trigger_is_manual=True,
                    min_prefix_chars=1,
                )
                if (
                    target
                    and context.syntactic_context == CompletionSyntacticContext.DOTTED_MEMBER
                    and context.base_expression
                ):
                    self._runtime_targets[(current_file_path, context.base_expression)] = target
                    if prefetch_target is not None:
                        try:
                            prefetch_target(target)
                        except Exception:
                            log_completion_phase("buffer_warmup_prefetch", 0.0, ok=False)
            finally:
                log_completion_phase(
                    "buffer_warmup",
                    (time.perf_counter() - started_at) * 1000.0,
                )

        self._submit(
            key=f"buffer_warmup:{current_file_path}",
            priority=70,
            task=task,
            dispatch_on_main_thread=False,
        )

    def shutdown(self) -> None:
        """Stop the backing worker threads."""
        self._worker.shutdown()
        self._runtime_docs_worker.shutdown()

    def cancel_all(self) -> None:
        """Invalidate all queued semantic work."""
        self._worker.cancel_all()
        self._runtime_docs_worker.cancel_all()

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
        max_results: int = UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT,
    ) -> CompletionEnvelope:
        """Merge tiered completion envelopes for editor popup display."""
        return self._completion_service.merge_for_editor_display(
            fast=fast,
            semantic=semantic,
            runtime_items=runtime_items,
            max_results=max_results,
        )

    def request_editor_completions(
        self,
        *,
        request: CompletionRequest,
        request_generation: int,
        completion_context: CompletionContext,
        runtime_coordinator: RuntimeIntrospectionCoordinator | None,
        schedule_background_task: Callable[
            [
                str,
                Callable[[object], list[CompletionItem]],
                Callable[[list[CompletionItem]], None],
                Callable[[Exception], None],
            ],
            None,
        ]
        | None,
        on_paint: Callable[[str, list[CompletionItem], CompletionEnvelope], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Orchestrate fast, semantic, and runtime completion tiers for one editor request."""

        popup_prefix = completion_context.prefix
        self._worker.invalidate(f"buffer_warmup:{request.current_file_path}")
        self._completion_resolver.bind_runtime_members(runtime_coordinator)
        runtime_items: list[CompletionItem] = []
        worker_calls: list[Callable[[], None]] = []
        fast_envelope: list[CompletionEnvelope | None] = [None]
        semantic_envelope: list[CompletionEnvelope | None] = [None]

        def paint_merged(*, fast: CompletionEnvelope | None, semantic: CompletionEnvelope | None) -> None:
            merged = self.merge_completion_for_display(
                fast=fast,
                semantic=semantic,
                runtime_items=runtime_items,
                max_results=request.max_results,
            )
            if not merged.items:
                return
            on_paint(popup_prefix, merged.items, merged)

        runtime_target: list[str] = [""]

        def add_runtime_items(target_path: str, items: list[CompletionItem]) -> None:
            attached = self._completion_service.attach_runtime_replacement_metadata(
                items,
                context=completion_context,
            )
            if not attached:
                return
            if target_path != runtime_target[0]:
                # A fresh inference replaced a remembered target: drop the old rows.
                runtime_items.clear()
                runtime_target[0] = target_path
            elif runtime_items:
                return
            runtime_items.extend(attached)
            paint_merged(fast=fast_envelope[0], semantic=semantic_envelope[0])

        members_in_flight = [False]
        released = [False]

        def release_after_paint() -> None:
            if released[0]:
                return
            released[0] = True

            def submit() -> None:
                for call in worker_calls:
                    call()

            if runtime_items:
                # The list is already on the UI thread. Jedi holds the GIL, so
                # wait until that paint has a turn before the next script.
                timer = threading.Timer(_PAINT_GRACE_SECONDS, submit)
                timer.daemon = True
                timer.start()
            else:
                submit()

        def start_runtime_tier(runtime_query: RuntimeIntrospectionQuery | None) -> None:
            coordinator = runtime_coordinator
            if coordinator is None or runtime_query is None:
                return
            target_path = runtime_query.target_path
            cached = coordinator.cached_items(runtime_query)
            if cached is not None:
                add_runtime_items(target_path, cached)
                return
            if schedule_background_task is None:
                return

            def introspection_task(_cancellation: object) -> list[CompletionItem]:
                return coordinator.fetch_and_cache_from_runner(
                    runtime_query,
                    max_results=request.max_results,
                )

            def on_members(items: list[CompletionItem]) -> None:
                add_runtime_items(target_path, items)
                release_after_paint()

            def introspection_error(exc: Exception) -> None:
                if on_error is not None:
                    on_error(exc)
                release_after_paint()

            members_in_flight[0] = True
            schedule_background_task(
                f"runtime_introspect:{target_path}",
                introspection_task,
                on_members,
                introspection_error,
            )

        def on_fast_success(result: CompletionFastResult) -> None:
            fast_envelope[0] = result.envelope
            paint_merged(fast=result.envelope, semantic=semantic_envelope[0])

        def on_fast_error(exc: Exception) -> None:
            if on_error is not None:
                on_error(exc)

        def submit_runtime_infer(
            on_inferred: Callable[[RuntimeIntrospectionQuery | None], None],
            *,
            reuse_if_warmed: bool = False,
        ) -> None:
            project_cache, state_root = self._semantic_facade.jedi_inference_scope()

            def task() -> RuntimeIntrospectionQuery | None:
                if reuse_if_warmed:
                    # Warmup can store the target while this infer waits.
                    warmed = self._runtime_targets.get(receiver_key)
                    if warmed:
                        return RuntimeIntrospectionQuery(target_path=warmed, member_prefix="")
                return resolve_runtime_introspection_query_with_inference(
                    context=completion_context,
                    project_root=completion_context.project_root,
                    current_file_path=completion_context.file_path,
                    source_text=completion_context.source_text,
                    project_cache=project_cache,
                    state_root=state_root,
                )

            self._submit(
                key=f"runtime_infer:{request.current_file_path}",
                priority=-1,
                task=task,
                on_success=on_inferred,
                on_error=on_fast_error,
            )

        cold_infer: list[Callable[[], None]] = []
        direct_query = resolve_runtime_introspection_query(completion_context)
        if direct_query is not None:
            start_runtime_tier(direct_query)
        elif (
            runtime_coordinator is not None
            and completion_context.syntactic_context == CompletionSyntacticContext.DOTTED_MEMBER
        ):
            receiver_key = (request.current_file_path, completion_context.base_expression)
            remembered = self._runtime_targets.get(receiver_key)

            def on_inferred(runtime_query: RuntimeIntrospectionQuery | None) -> None:
                if runtime_query is None:
                    self._runtime_targets.pop(receiver_key, None)
                    if not members_in_flight[0]:
                        release_after_paint()
                    return
                self._runtime_targets[receiver_key] = runtime_query.target_path
                start_runtime_tier(runtime_query)
                if not members_in_flight[0]:
                    release_after_paint()

            if remembered:
                # The member list can paint before Jedi runs again. A later
                # infer still corrects the type if the receiver changed.
                start_runtime_tier(
                    RuntimeIntrospectionQuery(target_path=remembered, member_prefix="")
                )
                worker_calls.append(lambda: submit_runtime_infer(on_inferred))
            else:
                def start_cold_infer() -> None:
                    remembered_now = self._runtime_targets.get(receiver_key)
                    if remembered_now:
                        on_inferred(
                            RuntimeIntrospectionQuery(
                                target_path=remembered_now,
                                member_prefix="",
                            )
                        )
                        return
                    submit_runtime_infer(on_inferred, reuse_if_warmed=True)

                cold_infer.append(start_cold_infer)

        worker_calls.append(lambda: self.request_completion_fast(
            request=request,
            prefix=popup_prefix,
            request_generation=request_generation,
            on_success=on_fast_success,
            on_error=on_fast_error,
        ))

        def on_semantic_success(result: CompletionRequestResult) -> None:
            semantic_envelope[0] = result.envelope
            paint_merged(fast=fast_envelope[0], semantic=result.envelope)

        def on_semantic_error(exc: Exception) -> None:
            if on_error is not None:
                on_error(exc)

        worker_calls.append(lambda: self.request_completion(
            request=request,
            prefix=popup_prefix,
            request_generation=request_generation,
            on_success=on_semantic_success,
            on_error=on_semantic_error,
        ))

        if cold_infer:
            # The target is unknown, so inference is the list. Fast and semantic
            # are submitted only after that list is in hand, from on_inferred.
            cold_infer[0]()
        elif not members_in_flight[0]:
            release_after_paint()

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

        key = f"completion_resolve:{request.current_file_path}:{request.item.item_id or request.item.label}"
        if request.item.resolve_provider == RUNTIME_INTROSPECTION_PROVIDER:
            self._runtime_docs_worker.submit(
                key=key,
                task=task,
                on_success=cast(Callable[[object], None], on_success),
                on_error=on_error,
                priority=5,
            )
            return
        self._submit(key=key, priority=5, task=task, on_success=on_success, on_error=on_error)

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
        self._submit(
            key=f"definition:{current_file_path}",
            priority=40,
            task=lambda: self._semantic_facade.lookup_definition(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            ),
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
        self._submit(
            key=f"references:{current_file_path}",
            priority=70,
            task=lambda: self._semantic_facade.find_references(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            ),
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
        self._submit(
            key=f"rename:{current_file_path}",
            priority=70,
            task=lambda: self._semantic_facade.plan_rename(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
                new_symbol=new_symbol,
            ),
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
        self._submit(
            key="apply_rename",
            priority=60,
            task=lambda: self._semantic_facade.apply_rename(plan),
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
        self._submit_generation_result(
            key=f"hover:{current_file_path}",
            priority=30,
            request_generation=request_generation,
            resolve=lambda: self._semantic_facade.resolve_hover_info(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            ),
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
        self._submit_generation_result(
            key=f"signature:{current_file_path}",
            priority=25,
            request_generation=request_generation,
            resolve=lambda: self._semantic_facade.resolve_signature_help(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            ),
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
