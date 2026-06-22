"""Unit tests for the single-owner semantic session wrapper."""
from __future__ import annotations

import threading

import pytest

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind, CompletionRequestResult
from app.intelligence.completion_service import CompletionRequest
from app.intelligence.semantic_models import (
    SemanticDefinitionResult,
    SemanticHoverResult,
    SemanticLocation,
    SemanticOperationMetadata,
    SemanticSignatureResult,
)
from app.intelligence.semantic_session import SemanticSession

pytestmark = pytest.mark.unit


def test_request_completion_routes_through_owned_completion_service() -> None:
    session = SemanticSession(
        dispatch_to_main_thread=lambda callback: callback(),
        cache_db_path=":memory:",
    )
    done = threading.Event()
    captured: list[CompletionRequestResult] = []

    class _CompletionServiceStub:
        def complete(self, request: CompletionRequest) -> CompletionEnvelope:
            assert request.current_file_path == "/tmp/example.py"
            return CompletionEnvelope(
                items=[CompletionItem(label="alpha", insert_text="alpha", kind=CompletionKind.SYMBOL)],
                degradation_reason="semantic_engine_error",
            )

        def complete_semantic(self, request: CompletionRequest) -> CompletionEnvelope:
            return self.complete(request)

        def record_acceptance(self, item: CompletionItem) -> None:
            raise AssertionError("not used in this test")

    session._completion_service = _CompletionServiceStub()  # type: ignore[assignment]

    session.request_completion(
        request=CompletionRequest(
            source_text="alpha",
            cursor_position=5,
            current_file_path="/tmp/example.py",
            project_root="/tmp",
            trigger_is_manual=True,
            min_prefix_chars=1,
        ),
        prefix="alpha",
        request_generation=3,
        on_success=lambda payload: (captured.append(payload), done.set()),
    )

    assert done.wait(timeout=1.0) is True
    assert captured[0].request_generation == 3
    assert captured[0].prefix == "alpha"
    assert captured[0].envelope.degradation_reason == "semantic_engine_error"
    assert [item.label for item in captured[0].envelope.items] == ["alpha"]
    session.shutdown()


def test_request_hover_and_signature_use_same_owned_semantic_facade() -> None:
    session = SemanticSession(
        dispatch_to_main_thread=lambda callback: callback(),
        cache_db_path=":memory:",
    )
    hover_done = threading.Event()
    signature_done = threading.Event()
    hover_results: list[tuple[int, SemanticHoverResult | None]] = []
    signature_results: list[tuple[int, SemanticSignatureResult | None]] = []

    class _FacadeStub:
        def resolve_hover_info(self, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["current_file_path"] == "/tmp/example.py"
            return SemanticHoverResult(
                symbol_name="helper",
                symbol_kind="function",
                file_path="/tmp/example.py",
                line_number=1,
                doc_summary="Hover docs",
                metadata=SemanticOperationMetadata(engine="stub", source="semantic", confidence="exact"),
            )

        def resolve_signature_help(self, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["project_root"] == "/tmp"
            return SemanticSignatureResult(
                callable_name="helper",
                signature_text="helper(alpha)",
                argument_index=0,
                doc_summary="Call docs",
                metadata=SemanticOperationMetadata(engine="stub", source="semantic", confidence="exact"),
            )

    session._semantic_facade = _FacadeStub()  # type: ignore[assignment]

    session.request_hover_info(
        project_root="/tmp",
        current_file_path="/tmp/example.py",
        source_text="helper(alpha)",
        cursor_position=7,
        request_generation=4,
        on_success=lambda payload: (hover_results.append(payload), hover_done.set()),
    )
    session.request_signature_help(
        project_root="/tmp",
        current_file_path="/tmp/example.py",
        source_text="helper(alpha)",
        cursor_position=7,
        request_generation=5,
        on_success=lambda payload: (signature_results.append(payload), signature_done.set()),
    )

    assert hover_done.wait(timeout=1.0) is True
    assert signature_done.wait(timeout=1.0) is True
    assert hover_results[0][0] == 4
    assert hover_results[0][1] is not None
    assert hover_results[0][1].symbol_name == "helper"
    assert signature_results[0][0] == 5
    assert signature_results[0][1] is not None
    assert signature_results[0][1].signature_text == "helper(alpha)"
    session.shutdown()


def test_concurrent_definition_requests_for_two_files_both_complete() -> None:
    """Per-file worker keys must not cancel cross-file navigation (CC-09 / INT-R-06)."""
    session = SemanticSession(
        dispatch_to_main_thread=lambda callback: callback(),
        cache_db_path=":memory:",
    )
    done_a = threading.Event()
    done_b = threading.Event()
    results_a: list[SemanticDefinitionResult] = []
    results_b: list[SemanticDefinitionResult] = []

    class _FacadeStub:
        def lookup_definition(self, **kwargs):  # type: ignore[no-untyped-def]
            file_path = kwargs["current_file_path"]
            return SemanticDefinitionResult(
                symbol_name="helper",
                locations=[
                    SemanticLocation(
                        name="helper",
                        file_path=file_path,
                        line_number=1,
                        column_number=0,
                        symbol_kind="function",
                    )
                ],
                metadata=SemanticOperationMetadata(engine="stub", source="semantic", confidence="exact"),
            )

    session._semantic_facade = _FacadeStub()  # type: ignore[assignment]

    session.request_lookup_definition(
        project_root="/tmp/project",
        current_file_path="/tmp/project/a.py",
        source_text="helper()\n",
        cursor_position=0,
        on_success=lambda result: (results_a.append(result), done_a.set()),
    )
    session.request_lookup_definition(
        project_root="/tmp/project",
        current_file_path="/tmp/project/b.py",
        source_text="helper()\n",
        cursor_position=0,
        on_success=lambda result: (results_b.append(result), done_b.set()),
    )

    assert done_a.wait(timeout=1.0) is True
    assert done_b.wait(timeout=1.0) is True
    assert results_a[0].locations[0].file_path == "/tmp/project/a.py"
    assert results_b[0].locations[0].file_path == "/tmp/project/b.py"
    session.shutdown()


def test_semantic_session_submit_priorities() -> None:
    """Document worker lane priorities for completion vs navigation (INT-R-09)."""
    session = SemanticSession(
        dispatch_to_main_thread=lambda callback: callback(),
        cache_db_path=":memory:",
    )
    captured: list[tuple[str, int]] = []

    def capture_submit(**kwargs):  # type: ignore[no-untyped-def]
        captured.append((kwargs["key"], kwargs["priority"]))
        result = kwargs["task"]()
        on_success = kwargs.get("on_success")
        if on_success is not None:
            on_success(result)

    session._worker.submit = capture_submit  # type: ignore[method-assign]

    class _FacadeStub:
        def lookup_definition(self, **_kwargs):  # type: ignore[no-untyped-def]
            return SemanticDefinitionResult(
                symbol_name="sym",
                locations=[],
                metadata=SemanticOperationMetadata(engine="stub", source="semantic", confidence="exact"),
            )

        def resolve_hover_info(self, **_kwargs):  # type: ignore[no-untyped-def]
            return None

    session._semantic_facade = _FacadeStub()  # type: ignore[assignment]
    session._completion_service.complete_fast = lambda _request: CompletionEnvelope(items=[])  # type: ignore[method-assign, assignment]
    session._completion_service.complete_semantic = lambda _request: CompletionEnvelope(items=[])  # type: ignore[method-assign, assignment]

    session.request_completion_fast(
        request=CompletionRequest(
            source_text="alpha",
            cursor_position=5,
            current_file_path="/tmp/a.py",
            project_root="/tmp",
            trigger_is_manual=True,
            min_prefix_chars=1,
        ),
        prefix="alpha",
        request_generation=1,
        on_success=lambda _result: None,
    )
    session.request_lookup_definition(
        project_root="/tmp",
        current_file_path="/tmp/a.py",
        source_text="alpha",
        cursor_position=5,
        on_success=lambda _result: None,
    )
    session.request_hover_info(
        project_root="/tmp",
        current_file_path="/tmp/a.py",
        source_text="alpha",
        cursor_position=5,
        request_generation=2,
        on_success=lambda _result: None,
    )

    assert captured == [
        ("completion_fast:/tmp/a.py", 0),
        ("definition:/tmp/a.py", 40),
        ("hover:/tmp/a.py", 30),
    ]
    session.shutdown()
