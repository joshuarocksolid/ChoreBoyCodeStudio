"""Unit tests for tier-aware completion merge policy."""

from __future__ import annotations

import pytest

from app.intelligence.completion_merge_policy import (
    envelope_confidence,
    flatten_tiered_items,
    is_tier_header_item,
    merge_completion_display,
    merge_completion_metadata,
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


def test_merge_completion_display_dedupes_labels_without_headers() -> None:
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
    assert [item.label for item in merged.items] == ["alpha", "beta"]
    assert not any(is_tier_header_item(item) for item in merged.items)


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


def test_merge_takes_item_id_from_the_item_whose_resolve_provider_it_adopts() -> None:
    fast_item = CompletionItem(
        label="setText",
        insert_text="setText",
        kind=CompletionKind.METHOD,
        source="static_api_index",
        item_id="fast:setText",
        resolve_provider="jedi",
    )
    runtime_item = CompletionItem(
        label="setText",
        insert_text="setText",
        kind=CompletionKind.METHOD,
        source="runtime_introspection",
        item_id="runtime_introspection:PySide2.QtWidgets.QPushButton:setText",
        resolve_provider="runtime_introspection",
        resolvable_fields=("documentation", "signature"),
    )

    merged = merge_completion_metadata(fast_item, runtime_item)

    assert (merged.resolve_provider, merged.item_id) == (runtime_item.resolve_provider, runtime_item.item_id)


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
