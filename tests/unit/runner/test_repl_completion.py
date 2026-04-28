"""Unit tests for live Python Console completion service."""

from __future__ import annotations

import pytest

from app.intelligence.completion_models import CompletionKind
from app.runner.repl_completion import ReplCompletionRequest, ReplCompletionService

pytestmark = pytest.mark.unit


class SampleObject:
    class_attr = 1

    def method_alpha(self, value: int) -> int:
        return value


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
