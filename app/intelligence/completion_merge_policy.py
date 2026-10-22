"""Tier-aware completion merge policy for editor display (§17.4.2)."""

from __future__ import annotations

from app.core.completion_tier import TIER_HEADER_SIDE_EFFECT, is_tier_header_item
from app.core.constants import UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT
from app.intelligence.completion_models import (
    CompletionEnvelope,
    CompletionItem,
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
    max_results: int = UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT,
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
    """Flatten tiers into one list, one row per label (the popup ranks it).

    A label seen in an earlier tier keeps its row; later tiers only fill in
    missing docs. No section headers: the popup orders rows by match quality.
    """

    merged_by_label: dict[str, CompletionItem] = {}
    label_to_row_index: dict[str, int] = {}
    rows: list[CompletionItem] = []
    for tier in tiers:
        for item in tier.items:
            if item.label in merged_by_label:
                merged = merge_completion_metadata(merged_by_label[item.label], item)
                merged_by_label[item.label] = merged
                rows[label_to_row_index[item.label]] = merged
                continue
            merged_by_label[item.label] = item
            label_to_row_index[item.label] = len(rows)
            rows.append(item)
    return rows[: max(0, max_results)]


def merge_completion_metadata(
    primary: CompletionItem,
    incoming: CompletionItem,
) -> CompletionItem:
    """Keep ``primary`` list identity; fill empty doc fields from ``incoming``."""

    documentation = (primary.documentation or "").strip() or (incoming.documentation or "").strip()
    signature = (primary.signature or "").strip() or (incoming.signature or "").strip()
    return_type = (primary.return_type or "").strip() or (incoming.return_type or "").strip()
    detail = (primary.detail or "").strip() or (incoming.detail or "").strip()
    resolvable_fields = primary.resolvable_fields
    resolve_provider = primary.resolve_provider
    item_id = primary.item_id
    # Runtime introspection knows overloads and the defining class; prefer it.
    adopt = not documentation and not signature and bool(incoming.resolve_provider) and (
        not primary.resolve_provider
        or (incoming.resolve_provider == "runtime_introspection" and primary.resolve_provider != incoming.resolve_provider)
    )
    if adopt and incoming.resolvable_fields:
        resolvable_fields = incoming.resolvable_fields
    if adopt:
        resolve_provider = incoming.resolve_provider
        item_id = incoming.item_id or primary.item_id
    return CompletionItem(
        label=primary.label,
        insert_text=primary.insert_text,
        kind=primary.kind,
        detail=detail,
        documentation=documentation,
        signature=signature,
        return_type=return_type,
        source_file_path=primary.source_file_path or incoming.source_file_path,
        engine=primary.engine or incoming.engine,
        source=primary.source,
        confidence=primary.confidence,
        semantic_kind=primary.semantic_kind or incoming.semantic_kind,
        replacement_start=primary.replacement_start,
        replacement_end=primary.replacement_end,
        trigger_kind=primary.trigger_kind,
        trigger_character=primary.trigger_character,
        side_effect_risk=primary.side_effect_risk or incoming.side_effect_risk,
        item_id=item_id,
        context_fingerprint=primary.context_fingerprint,
        resolve_provider=resolve_provider,
        resolvable_fields=resolvable_fields,
    )


def envelope_confidence(tiers: tuple[CompletionTier, ...]) -> str:
    """Return envelope confidence; never exact when any approximate item is present."""

    for tier in tiers:
        for item in tier.items:
            if item.confidence == "approximate" or item.source == "approximate":
                return "approximate"
    if any(tier.phase == CompletionTierPhase.SEMANTIC for tier in tiers):
        return "exact"
    return "approximate"


__all__ = [
    "TIER_HEADER_SIDE_EFFECT",
    "envelope_confidence",
    "flatten_tiered_items",
    "is_tier_header_item",
    "merge_completion_display",
    "merge_completion_metadata",
]
