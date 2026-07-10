"""Unit tests for tier-aware completion merge policy."""

from __future__ import annotations

import pytest

from app.intelligence.completion_merge_policy import (
    envelope_confidence,
    flatten_tiered_items,
    is_tier_header_item,
    merge_completion_display,
)
from app.intelligence.completion_models import CompletionTier
from app.intelligence.completion_models import (
    CompletionEnvelope,
    CompletionItem,
    CompletionKind,
    CompletionTierPhase,
)

pytestmark = pytest.mark.unit


def _item(label: str, *, source: str = "semantic", confidence: str = "exact") -> CompletionItem:
    return CompletionItem(
        label=label,
        insert_text=label,
        kind=CompletionKind.SYMBOL,
        source=source,
        confidence=confidence,
    )


def test_merge_completion_display_adds_tier_headers_and_dedupes_labels() -> None:
    fast = CompletionEnvelope(
        items=[_item("alpha", source="static_api_index", confidence="approximate")],
        source_phase="fast",
        confidence="approximate",
    )
    semantic = CompletionEnvelope(
        items=[_item("alpha"), _item("beta")],
        source_phase="semantic",
        confidence="exact",
    )

    merged = merge_completion_display(fast=fast, semantic=semantic)

    assert merged.confidence == "approximate"
    assert [item.label for item in merged.items[:3]] == [
        "Indexed suggestions",
        "alpha",
        "Python analysis",
    ]
    assert merged.items[3].label == "beta"
    assert is_tier_header_item(merged.items[0])
    assert is_tier_header_item(merged.items[2])


def test_flatten_tiered_items_merges_documentation_from_later_tier() -> None:
    fast_item = CompletionItem(
        label="getcwd",
        insert_text="getcwd",
        kind=CompletionKind.FUNCTION,
        source="static_api_index",
        confidence="static",
        detail="os stdlib member",
    )
    semantic_item = CompletionItem(
        label="getcwd",
        insert_text="getcwd",
        kind=CompletionKind.FUNCTION,
        source="semantic",
        confidence="exact",
        documentation="Return the current working directory.",
        signature="getcwd()",
        resolve_provider="jedi",
        resolvable_fields=("documentation", "signature"),
    )
    tiers = (
        CompletionTier(
            phase=CompletionTierPhase.FAST,
            label="Indexed suggestions",
            items=(fast_item,),
        ),
        CompletionTier(
            phase=CompletionTierPhase.SEMANTIC,
            label="Python analysis",
            items=(semantic_item,),
        ),
    )

    rows = flatten_tiered_items(tiers, max_results=100)
    getcwd_rows = [item for item in rows if item.label == "getcwd"]

    assert len(getcwd_rows) == 1
    merged = getcwd_rows[0]
    assert merged.source == "static_api_index"
    assert merged.documentation == "Return the current working directory."
    assert merged.signature == "getcwd()"


def test_envelope_confidence_never_exact_when_approximate_item_present() -> None:
    tiers = (
        CompletionTier(
            phase=CompletionTierPhase.SEMANTIC,
            label="Python analysis",
            items=(
                _item("exact_one"),
                _item("approx_one", source="approximate", confidence="approximate"),
            ),
        ),
    )

    assert envelope_confidence(tiers) == "approximate"
