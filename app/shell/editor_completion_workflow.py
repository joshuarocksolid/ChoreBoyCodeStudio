"""Editor completion orchestration for the shell."""

from __future__ import annotations

import time
from collections.abc import Callable

from app.editors.code_editor_widget import CodeEditorWidget
from app.intelligence.completion_context import build_completion_context
from app.intelligence.completion_models import (
    CompletionEnvelope,
    CompletionItem,
    CompletionRequestResult,
    CompletionResolveRequest,
    CompletionResolveResult,
)
from app.intelligence.completion_service import CompletionRequest
from app.intelligence.runtime_introspection import attach_replacement_metadata, resolve_runtime_introspection_query_with_inference
from app.shell.editor_stale_result_policy import deliver_revision_gated_editor_result
from app.shell.semantic_navigation_host import SemanticNavigationHost


class EditorCompletionWorkflow:
    """Async editor completion requests, resolve, and acceptance routing."""

    def __init__(self, host: SemanticNavigationHost) -> None:
        self._host = host

    def _deliver_gated_completion_result(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        requested_revision: int | None,
        request_generation: int,
        deliver: Callable[[], None],
    ) -> None:
        deliver_revision_gated_editor_result(
            file_path=file_path,
            editor_widget=editor_widget,
            requested_revision=requested_revision,
            editor_widget_for_path=self._host.editor_widget_for_path,
            buffer_revision=self._host.editor_buffer_revision,
            deliver=deliver,
            requested_generation=request_generation,
            current_generation=editor_widget.completion_request_generation(),
        )

    def record_editor_completion_acceptance(self, *, file_path: str, item: CompletionItem) -> None:
        """Route completion acceptance through the worker-serialized session lane."""
        _ = file_path
        self._host.intelligence_controller().request_record_completion_acceptance(item=item)

    def request_editor_completions_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        prefix: str,
        source_text: str,
        cursor_position: int,
        manual_trigger: bool,
        request_generation: int,
        trigger_kind: str,
        trigger_character: str,
    ) -> None:
        started_at = time.perf_counter()
        requested_revision = self._host.editor_buffer_revision(file_path)
        loaded_project = self._host.loaded_project()
        request = CompletionRequest(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if loaded_project is None else loaded_project.project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._host.completion_min_chars(),
            max_results=100,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            buffer_revision=requested_revision,
        )
        intelligence_controller = self._host.intelligence_controller()
        completion_context = build_completion_context(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if loaded_project is None else loaded_project.project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._host.completion_min_chars(),
            max_results=100,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            buffer_revision=requested_revision,
        )
        runtime_query = resolve_runtime_introspection_query_with_inference(
            context=completion_context,
            project_root=None if loaded_project is None else loaded_project.project_root,
            current_file_path=file_path,
            source_text=source_text,
        )
        coordinator = self._host.runtime_introspection_coordinator()
        runtime_items: list[CompletionItem] = []
        if coordinator is not None and runtime_query is not None:
            cached = coordinator.cached_items(runtime_query)
            if cached:
                runtime_items = attach_replacement_metadata(cached, context=completion_context)

        popup_prefix = completion_context.prefix
        fast_envelope: list[CompletionEnvelope | None] = [None]

        def on_fast_success(result) -> None:  # type: ignore[no-untyped-def]
            fast_envelope[0] = result.envelope
            merged = intelligence_controller.merge_completion_for_display(
                fast=result.envelope,
                runtime_items=runtime_items,
            )
            if not merged.items:
                return

            def deliver() -> None:
                if self._host.intelligence_metrics_logging_enabled():
                    self._host.log_info(
                        "Completion telemetry: file=%s phase=%s count=%s timings=%s",
                        file_path,
                        result.envelope.source_phase,
                        len(merged.items),
                        result.envelope.latency_breakdown,
                    )
                editor_widget.show_completion_items_for_request(
                    request_generation=result.request_generation,
                    prefix=popup_prefix,
                    items=merged.items,
                )

            self._deliver_gated_completion_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                request_generation=result.request_generation,
                deliver=deliver,
            )

        def on_fast_error(exc: Exception) -> None:
            self._host.log_warning("Fast completion request failed for %s: %s", file_path, exc)

        intelligence_controller.request_completion_fast(
            request=request,
            prefix=popup_prefix,
            request_generation=request_generation,
            on_success=on_fast_success,
            on_error=on_fast_error,
        )

        if (
            coordinator is not None
            and runtime_query is not None
            and coordinator.cached_items(runtime_query) is None
        ):
            introspection_key = f"runtime_introspect:{runtime_query.target_path}"

            def introspection_task(_cancellation: object) -> list[CompletionItem]:
                return coordinator.fetch_and_cache_from_runner(runtime_query)

            def introspection_success(items: list[CompletionItem]) -> None:
                attached = attach_replacement_metadata(items, context=completion_context)
                if not attached:
                    return
                runtime_items.extend(attached)
                merged = intelligence_controller.merge_completion_for_display(
                    fast=fast_envelope[0],
                    runtime_items=runtime_items,
                )
                if not merged.items:
                    return

                def deliver() -> None:
                    editor_widget.show_completion_items_for_request(
                        request_generation=request_generation,
                        prefix=popup_prefix,
                        items=merged.items,
                    )

                self._deliver_gated_completion_result(
                    file_path=file_path,
                    editor_widget=editor_widget,
                    requested_revision=requested_revision,
                    request_generation=request_generation,
                    deliver=deliver,
                )

            def introspection_error(exc: Exception) -> None:
                self._host.log_warning(
                    "Runtime introspection failed for %s: %s",
                    runtime_query.target_path,
                    exc,
                )

            self._host.background_tasks().run(
                key=introspection_key,
                task=introspection_task,
                on_success=introspection_success,
                on_error=introspection_error,
            )

        def on_success(result: CompletionRequestResult) -> None:
            generation = result.request_generation
            completion_prefix = result.prefix
            merged = intelligence_controller.merge_completion_for_display(
                fast=fast_envelope[0],
                semantic=result.envelope,
                runtime_items=runtime_items,
            )
            completions = merged.items

            def deliver() -> None:
                degradation_reason = result.envelope.degradation_reason
                if degradation_reason and degradation_reason not in self._host.reported_completion_degradation_reasons():
                    self._host.reported_completion_degradation_reasons().add(degradation_reason)
                    self._host.show_status_message(
                        "Python completion is using approximate results; semantic engine failed. See app log.",
                        5000,
                    )
                if self._host.intelligence_metrics_logging_enabled():
                    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                    if elapsed_ms > 150.0:
                        self._host.log_warning(
                            "Completion latency warning: file=%s phase=%s elapsed_ms=%.2f count=%s timings=%s",
                            file_path,
                            result.envelope.source_phase,
                            elapsed_ms,
                            len(completions),
                            result.envelope.latency_breakdown,
                        )
                    else:
                        self._host.log_info(
                            "Completion telemetry: file=%s phase=%s elapsed_ms=%.2f count=%s timings=%s",
                            file_path,
                            result.envelope.source_phase,
                            elapsed_ms,
                            len(completions),
                            result.envelope.latency_breakdown,
                        )
                editor_widget.show_completion_items_for_request(
                    request_generation=generation,
                    prefix=completion_prefix,
                    items=completions,
                )

            self._deliver_gated_completion_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                request_generation=generation,
                deliver=deliver,
            )

        def on_error(exc: Exception) -> None:
            self._host.log_warning("Async completion request failed for %s: %s", file_path, exc)

        intelligence_controller.request_completion(
            request=request,
            prefix=popup_prefix,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

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
        requested_revision = self._host.editor_buffer_revision(file_path)
        loaded_project = self._host.loaded_project()
        request = CompletionResolveRequest(
            item=item,
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if loaded_project is None else loaded_project.project_root,
            context_fingerprint=item.context_fingerprint,
            buffer_revision=requested_revision,
            request_generation=request_generation,
        )

        def on_success(result: CompletionResolveResult) -> None:
            def deliver() -> None:
                editor_widget.show_resolved_completion_item_for_request(
                    request_generation=result.request_generation,
                    item=result.item,
                )

            self._deliver_gated_completion_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                request_generation=request_generation,
                deliver=deliver,
            )

        def on_error(exc: Exception) -> None:
            self._host.log_warning("Completion item resolve failed for %s: %s", file_path, exc)

        self._host.intelligence_controller().request_completion_resolve(
            request=request,
            on_success=on_success,
            on_error=on_error,
        )
