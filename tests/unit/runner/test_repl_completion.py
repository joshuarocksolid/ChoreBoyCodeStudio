"""Unit tests for live Python Console completion service."""

from __future__ import annotations

import pytest

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.runner.repl_completion import (
    REPL_COMPLETION_DEGRADATION_JEDI_UNAVAILABLE,
    REPL_COMPLETION_DEGRADATION_NO_COMPLETIONS,
    REPL_COMPLETION_DEGRADATION_RUNTIME_INSPECTION,
    ReplCompletionRequest,
    ReplCompletionService,
)
from app.runner.repl_introspection import ReplIntrospectionRequest, ReplIntrospectionService

pytestmark = pytest.mark.unit


class SampleObject:
    class_attr = 1

    def method_alpha(self, value: int) -> int:
        return value


def _namespace() -> dict[str, object]:
    return {"__name__": "__console__", "__package__": None}


def _mock_introspection_items(*labels: str) -> CompletionEnvelope:
    return CompletionEnvelope(
        items=[
            CompletionItem(
                label=label,
                insert_text=label,
                kind=CompletionKind.ATTRIBUTE,
                engine="runtime_introspection",
                source="runtime_introspection",
            )
            for label in labels
        ],
        source="runtime_introspection",
        confidence="runtime_inspection",
    )


def test_repl_completion_uses_live_namespace_for_top_level_names() -> None:
    service = ReplCompletionService({"sample_value": 123})

    envelope = service.complete(ReplCompletionRequest(line_buffer="sam", cursor_offset=3))

    assert any(item.label == "sample_value" for item in envelope.items)


def test_repl_completion_returns_dotted_runtime_members() -> None:
    service = ReplCompletionService({"obj": SampleObject()})

    envelope = service.complete(
        ReplCompletionRequest(
            line_buffer="obj.method_",
            cursor_offset=len("obj.method_"),
            trigger_kind="trigger_character",
            trigger_character=".",
        )
    )

    method = next(item for item in envelope.items if item.label == "method_alpha")
    assert method.kind in {CompletionKind.METHOD, CompletionKind.FUNCTION}
    assert method.replacement_start == len("obj.")
    assert method.replacement_end == len("obj.method_")
    assert method.source == "runtime" or method.source == "runtime_inspection"
    assert method.side_effect_risk


def test_repl_completion_sets_degradation_reason_when_jedi_fallback_used(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReplCompletionService({"sample_value": 123})

    def _raise_jedi_failure(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        raise RuntimeError("jedi unavailable")

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _raise_jedi_failure)

    envelope = service.complete(ReplCompletionRequest(line_buffer="sam", cursor_offset=3))

    assert envelope.degradation_reason == REPL_COMPLETION_DEGRADATION_RUNTIME_INSPECTION
    assert any(item.label == "sample_value" for item in envelope.items)


def test_repl_completion_sets_jedi_unavailable_when_jedi_and_fallback_both_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReplCompletionService({"sample_value": 123})

    def _raise_jedi_failure(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        raise RuntimeError("jedi unavailable")

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _raise_jedi_failure)

    envelope = service.complete(
        ReplCompletionRequest(line_buffer="from FreeCAD", cursor_offset=len("from FreeCAD"))
    )

    assert envelope.items == []
    assert envelope.degradation_reason == REPL_COMPLETION_DEGRADATION_JEDI_UNAVAILABLE


def test_repl_completion_sets_no_completions_when_jedi_and_fallback_both_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReplCompletionService(_namespace())

    def _empty_jedi(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        return []

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _empty_jedi)

    envelope = service.complete(
        ReplCompletionRequest(line_buffer="from FreeCAD", cursor_offset=len("from FreeCAD"))
    )

    assert envelope.items == []
    assert envelope.degradation_reason == REPL_COMPLETION_DEGRADATION_NO_COMPLETIONS


def test_repl_completion_from_freecad_dot_uses_trusted_runtime_when_jedi_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReplCompletionService(_namespace())

    def _empty_jedi(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        return []

    def _mock_introspect(
        _self: ReplIntrospectionService,
        request: ReplIntrospectionRequest,
    ) -> CompletionEnvelope:
        assert request.target_path == "FreeCAD"
        return _mock_introspection_items("ActiveDocument", "Console")

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _empty_jedi)
    monkeypatch.setattr(ReplIntrospectionService, "introspect", _mock_introspect)

    line_buffer = "from FreeCAD."
    envelope = service.complete(
        ReplCompletionRequest(
            line_buffer=line_buffer,
            cursor_offset=len(line_buffer),
            trigger_kind="trigger_character",
            trigger_character=".",
        )
    )

    labels = {item.label for item in envelope.items}
    assert "ActiveDocument" in labels
    assert "Console" in labels
    assert envelope.degradation_reason in {"", REPL_COMPLETION_DEGRADATION_RUNTIME_INSPECTION}
    assert envelope.source in {"static_api_index", "runtime_introspection"}
    active_document = next(item for item in envelope.items if item.label == "ActiveDocument")
    assert active_document.replacement_start == len("from FreeCAD.")
    assert active_document.replacement_end == len(line_buffer)


def test_repl_completion_import_freecad_dot_uses_api_index_when_jedi_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReplCompletionService(_namespace())

    def _empty_jedi(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        return []

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _empty_jedi)

    line_buffer = "import FreeCAD."
    envelope = service.complete(
        ReplCompletionRequest(
            line_buffer=line_buffer,
            cursor_offset=len(line_buffer),
            trigger_kind="trigger_character",
            trigger_character=".",
        )
    )

    labels = {item.label for item in envelope.items}
    assert "ActiveDocument" in labels
    assert envelope.degradation_reason in {"", REPL_COMPLETION_DEGRADATION_RUNTIME_INSPECTION}
    assert envelope.source in {"static_api_index", "runtime_introspection"}


def test_repl_completion_freecad_dot_without_namespace_import_uses_introspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReplCompletionService(_namespace())

    def _empty_jedi(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        return []

    def _mock_introspect(
        _self: ReplIntrospectionService,
        request: ReplIntrospectionRequest,
    ) -> CompletionEnvelope:
        assert request.target_path == "FreeCAD"
        return _mock_introspection_items("newDocument")

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _empty_jedi)
    monkeypatch.setattr(ReplIntrospectionService, "introspect", _mock_introspect)

    line_buffer = "FreeCAD."
    envelope = service.complete(
        ReplCompletionRequest(
            line_buffer=line_buffer,
            cursor_offset=len(line_buffer),
            trigger_kind="trigger_character",
            trigger_character=".",
        )
    )

    assert any(item.label == "newDocument" for item in envelope.items)
    assert envelope.degradation_reason in {"", REPL_COMPLETION_DEGRADATION_RUNTIME_INSPECTION}


def test_repl_completion_import_os_dot_uses_static_index_before_jedi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReplCompletionService(_namespace())
    jedi_calls: list[ReplCompletionRequest] = []

    def _track_jedi(_self: ReplCompletionService, request: ReplCompletionRequest) -> list:
        jedi_calls.append(request)
        return []

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _track_jedi)

    line_buffer = "import os\nos."
    envelope = service.complete(
        ReplCompletionRequest(
            line_buffer=line_buffer,
            cursor_offset=len(line_buffer),
            trigger_kind="trigger_character",
            trigger_character=".",
        )
    )

    assert any(item.label == "getcwd" for item in envelope.items)
    assert envelope.source == "static_api_index"
    assert jedi_calls == []


def test_repl_completion_from_freecad_without_dot_still_prefers_jedi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReplCompletionService(_namespace())

    def _jedi_modules(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        return [
            CompletionItem(
                label="FreeCAD",
                insert_text="FreeCAD",
                kind=CompletionKind.MODULE,
                engine="jedi_interpreter",
                source="runtime",
                confidence="semantic",
            )
        ]

    def _unexpected_trusted(_self: ReplCompletionService, _request: ReplCompletionRequest) -> list:
        raise AssertionError("trusted runtime should not run when Jedi returns items")

    monkeypatch.setattr(ReplCompletionService, "_complete_with_jedi", _jedi_modules)
    monkeypatch.setattr(ReplCompletionService, "_complete_with_trusted_runtime", _unexpected_trusted)

    envelope = service.complete(
        ReplCompletionRequest(line_buffer="from FreeCAD", cursor_offset=len("from FreeCAD"))
    )

    assert envelope.items[0].label == "FreeCAD"
    assert envelope.confidence == "semantic"
    assert envelope.degradation_reason == ""
