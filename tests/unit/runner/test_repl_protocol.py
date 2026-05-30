"""Unit tests for REPL control protocol serialization helpers."""

from __future__ import annotations

import pytest

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.runner.repl_protocol import (
    REPL_CONTROL_PROTOCOL,
    completion_item_from_dict,
    completion_item_to_dict,
    envelope_from_dict,
    envelope_to_dict,
)

pytestmark = pytest.mark.unit


def test_completion_item_round_trip_preserves_replacement_range() -> None:
    item = CompletionItem(
        label="sample_value",
        insert_text="sample_value",
        kind=CompletionKind.ATTRIBUTE,
        detail="live runtime",
        documentation="doc",
        signature="()",
        engine="runtime_dir",
        source="runtime",
        confidence="runtime_inspection",
        replacement_start=4,
        replacement_end=7,
        trigger_kind="invoked",
        trigger_character="",
        side_effect_risk="none",
    )

    restored = completion_item_from_dict(completion_item_to_dict(item))

    assert restored.label == item.label
    assert restored.kind == item.kind
    assert restored.replacement_start == item.replacement_start
    assert restored.replacement_end == item.replacement_end
    assert restored.side_effect_risk == item.side_effect_risk


def test_envelope_round_trip_preserves_degradation_metadata() -> None:
    envelope = CompletionEnvelope(
        items=[
            CompletionItem(
                label="obj",
                insert_text="obj",
                kind=CompletionKind.SYMBOL,
                source="runtime",
                confidence="runtime_inspection",
            )
        ],
        degradation_reason="repl_no_completions",
        source="runtime",
        confidence="runtime_inspection",
    )

    restored = envelope_from_dict(envelope_to_dict(envelope))

    assert restored.degradation_reason == envelope.degradation_reason
    assert restored.source == envelope.source
    assert restored.confidence == envelope.confidence
    assert len(restored.items) == 1
    assert restored.items[0].label == "obj"


def test_repl_control_protocol_constant_is_non_empty() -> None:
    assert REPL_CONTROL_PROTOCOL
