"""Tier-aware completion merge policy for editor display (§17.4.2)."""

from __future__ import annotations

from app.core.completion_tier import TIER_HEADER_SIDE_EFFECT, is_tier_header_item
from app.intelligence.completion_models import (
    CompletionEnvelope,
    CompletionItem,
    CompletionKind,
    CompletionTier,
    CompletionTierPhase,
)


_TIER_LABELS = {
    CompletionTierPhase.FAST: "Indexed suggestions",
    CompletionTierPhase.RUNTIME: "Runtime introspection",
    CompletionTierPhase.SEMANTIC: "Python analysis",
}


def merge_completion_display(
    *,
    fast: CompletionEnvelope | None = None,
    semantic: CompletionEnvelope | None = None,
    runtime_items: list[CompletionItem] | None = None,
    max_results: int = 100,
) -> CompletionEnvelope:
    """Merge tiered completion results without mislabeling approximate items as exact."""

    tiers: list[CompletionTier] = []
    if fast is not None and fast.items:
        tiers.append(
            CompletionTier(
                phase=CompletionTierPhase.FAST,
                label=_TIER_LABELS[CompletionTierPhase.FAST],
                items=tuple(fast.items),
            )
        )
    if runtime_items:
        tiers.append(
            CompletionTier(
                phase=CompletionTierPhase.RUNTIME,
                label=_TIER_LABELS[CompletionTierPhase.RUNTIME],
                items=tuple(runtime_items),
            )
        )
    if semantic is not None and semantic.items:
        tiers.append(
            CompletionTier(
                phase=CompletionTierPhase.SEMANTIC,
                label=_TIER_LABELS[CompletionTierPhase.SEMANTIC],
                items=tuple(semantic.items),
            )
        )

    tier_tuple = tuple(tiers)
    flat_items = flatten_tiered_items(tier_tuple, max_results=max_results)
    metadata_source = semantic or fast
    return CompletionEnvelope(
        items=flat_items,
        tiers=tier_tuple,
        degradation_reason="" if semantic is None else semantic.degradation_reason,
        source=metadata_source.source if metadata_source is not None else "",
        confidence=envelope_confidence(tier_tuple),
        source_phase=metadata_source.source_phase if metadata_source is not None else "merged",
        request_id=metadata_source.request_id if metadata_source is not None else "",
        buffer_revision=metadata_source.buffer_revision if metadata_source is not None else None,
        context_fingerprint=metadata_source.context_fingerprint if metadata_source is not None else "",
        valid_for=metadata_source.valid_for if metadata_source is not None else None,
        latency_breakdown=dict(metadata_source.latency_breakdown) if metadata_source is not None else {},
    )


def flatten_tiered_items(
    tiers: tuple[CompletionTier, ...],
    *,
    max_results: int,
) -> list[CompletionItem]:
    """Flatten tiers into popup rows with section headers and deduped labels."""

    seen_labels: set[str] = set()
    rows: list[CompletionItem] = []
    for tier in tiers:
        tier_rows: list[CompletionItem] = []
        for item in tier.items:
            if item.label in seen_labels:
                continue
            seen_labels.add(item.label)
            tier_rows.append(item)
        if not tier_rows:
            continue
        rows.append(_tier_header_item(tier.label))
        rows.extend(tier_rows)
        if len(rows) >= max_results + len(tiers):
            break
    return rows[: max_results + len(tiers)]


def envelope_confidence(tiers: tuple[CompletionTier, ...]) -> str:
    """Return envelope confidence; never exact when any approximate item is present."""

    for tier in tiers:
        for item in tier.items:
            if item.confidence == "approximate" or item.source == "approximate":
                return "approximate"
    if any(tier.phase == CompletionTierPhase.SEMANTIC for tier in tiers):
        return "exact"
    return "approximate"


def _tier_header_item(label: str) -> CompletionItem:
    return CompletionItem(
        label=label,
        insert_text="",
        kind=CompletionKind.TEXT,
        detail="",
        source="tier_header",
        confidence="unsupported",
        side_effect_risk=TIER_HEADER_SIDE_EFFECT,
    )


__all__ = [
    "TIER_HEADER_SIDE_EFFECT",
    "envelope_confidence",
    "flatten_tiered_items",
    "is_tier_header_item",
    "merge_completion_display",
]
