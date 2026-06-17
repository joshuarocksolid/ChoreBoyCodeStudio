"""Editor completion orchestration for the shell."""

from __future__ import annotations

import time
from collections.abc import Callable

from app.editors.code_editor_widget import CodeEditorWidget
from app.intelligence.completion_context import build_completion_context
from app.intelligence.completion_models import (
    CompletionEnvelope,
    CompletionItem,
    CompletionResolveRequest,
    CompletionResolveResult,
)
from app.intelligence.completion_service import CompletionRequest
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
        project_root = None if loaded_project is None else loaded_project.project_root
        completion_context = build_completion_context(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._host.completion_min_chars(),
            max_results=100,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            buffer_revision=requested_revision,
        )
        if not completion_context.should_offer_automatic_results:
            return

        request = CompletionRequest(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._host.completion_min_chars(),
            max_results=100,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            buffer_revision=requested_revision,
        )
        intelligence_controller = self._host.intelligence_controller()

        def on_paint(prefix: str, items: list[CompletionItem], envelope: CompletionEnvelope) -> None:
            def deliver() -> None:
                degradation_reason = envelope.degradation_reason
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
                            envelope.source_phase,
                            elapsed_ms,
                            len(items),
                            envelope.latency_breakdown,
                        )
                    else:
                        self._host.log_info(
                            "Completion telemetry: file=%s phase=%s elapsed_ms=%.2f count=%s timings=%s",
                            file_path,
                            envelope.source_phase,
                            elapsed_ms,
                            len(items),
                            envelope.latency_breakdown,
                        )
                editor_widget.show_completion_items_for_request(
                    request_generation=request_generation,
                    prefix=prefix,
                    items=items,
                )

            self._deliver_gated_completion_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                request_generation=request_generation,
                deliver=deliver,
            )

        def on_error(exc: Exception) -> None:
            self._host.log_warning("Async completion request failed for %s: %s", file_path, exc)

        intelligence_controller.request_editor_completions(
            request=request,
            request_generation=request_generation,
            completion_context=completion_context,
            on_paint=on_paint,
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
