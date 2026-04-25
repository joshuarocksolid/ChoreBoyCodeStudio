"""Unit tests for the single-owner semantic session wrapper."""
from __future__ import annotations

import threading

import pytest

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind, CompletionRequestResult
from app.intelligence.completion_service import CompletionRequest
from app.intelligence.semantic_models import SemanticHoverResult, SemanticOperationMetadata, SemanticSignatureResult
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
