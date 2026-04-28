"""Tiered completion broker for fast first paint and semantic refinement."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Protocol

from app.intelligence.api_index import provide_api_index_member_items
from app.intelligence.completion_context import (
    CompletionContext,
    CompletionSyntacticContext,
    build_completion_context,
    context_matches_prefix,
)
from app.intelligence.completion_metrics import CompletionTelemetry
from app.intelligence.completion_models import (
    COMPLETION_DEGRADATION_SEMANTIC_ENGINE_ERROR,
    CompletionEnvelope,
    CompletionItem,
    CompletionKind,
    RankedCompletionItem,
)
from app.intelligence.completion_providers import (
    provide_builtin_items,
    provide_current_file_symbol_items,
    provide_keyword_items,
    provide_module_member_items,
    provide_project_module_items,
    provide_project_symbol_items,
)
from app.intelligence.semantic_facade import SemanticFacade

_logger = logging.getLogger(__name__)


class CompletionProvider(Protocol):
    """Provider contract consumed by the broker."""

    name: str
    priority: int
    timeout_budget_ms: float

    def supports(self, context: CompletionContext) -> bool:
        """Return whether this provider can serve ``context``."""
        ...

    def provide(self, context: CompletionContext) -> "CompletionProviderResult":
        """Return provider candidates for ``context``."""
        ...


@dataclass(frozen=True)
class CompletionProviderResult:
    """Items and metadata produced by a completion provider."""

    provider_name: str
    items: list[CompletionItem]
    source_phase: str
    duration_ms: float = 0.0
    degradation_reason: str = ""


@dataclass
class _CachedCompletionEnvelope:
    context: CompletionContext
    envelope: CompletionEnvelope


class CompletionBroker:
    """Owns tier selection, result reuse, ranking, and merge policy."""

    def __init__(self, *, cache_db_path: str, semantic_facade: SemanticFacade | None = None) -> None:
        self._cache_db_path = str(Path(cache_db_path).expanduser().resolve())
        self._semantic_facade = semantic_facade or SemanticFacade(cache_db_path=self._cache_db_path)
        self._acceptance_scores: dict[str, int] = {}
        self._result_cache: dict[str, _CachedCompletionEnvelope] = {}
        self._telemetry = CompletionTelemetry()

    def complete_fast(self, request: Any) -> CompletionEnvelope:
        """Return cached/indexed completion items without invoking Jedi."""

        context = self._context_from_request(request)
        if not context.should_offer_automatic_results:
            return self._empty_envelope(context, source_phase="fast")

        reused = self._reuse_cached_envelope(context)
        if reused is not None:
            return reused

        breakdown: dict[str, float] = {}
        with self._telemetry.span("fast_providers", breakdown):
            candidates = self._fast_candidates(context)
        with self._telemetry.span("rank_fast", breakdown):
            ranked = self._rank_candidates(candidates, prefix=context.prefix, current_file_path=context.file_path)
        envelope = self._envelope(
            context,
            items=[entry.item for entry in ranked[: context.max_results]],
            source_phase="fast",
            latency_breakdown=breakdown,
        )
        self._remember_envelope(context, envelope)
        return envelope

    def complete_semantic(self, request: Any) -> CompletionEnvelope:
        """Return semantic refinement merged with current fast providers."""

        context = self._context_from_request(request)
        if not context.should_offer_automatic_results:
            return self._empty_envelope(context, source_phase="semantic")

        breakdown: dict[str, float] = {}
        degradation_reason = ""
        with self._telemetry.span("fast_providers_for_merge", breakdown):
            candidates = self._fast_candidates(context)
        try:
            with self._telemetry.span("semantic_complete", breakdown):
                semantic_candidates = self._semantic_facade.complete(
                    project_root=context.project_root,
                    current_file_path=context.file_path,
                    source_text=context.source_text,
                    cursor_position=context.cursor_position,
                    trigger_is_manual=context.trigger_is_manual,
                    min_prefix_chars=context.min_prefix_chars,
                    max_results=context.max_results * 2,
                )
        except Exception as exc:
            _logger.warning("semantic completion failed: %s", exc)
            semantic_candidates = []
            degradation_reason = COMPLETION_DEGRADATION_SEMANTIC_ENGINE_ERROR
        candidates.extend(semantic_candidates)
        candidates = self._attach_context_metadata(candidates, context=context)
        with self._telemetry.span("rank_semantic", breakdown):
            ranked = self._rank_candidates(candidates, prefix=context.prefix, current_file_path=context.file_path)
        envelope = self._envelope(
            context,
            items=[entry.item for entry in ranked[: context.max_results]],
            source_phase="semantic",
            degradation_reason=degradation_reason,
            latency_breakdown=breakdown,
        )
        self._remember_envelope(context, envelope)
        return envelope

    def complete(self, request: Any) -> CompletionEnvelope:
        """Compatibility path returning the final merged completion envelope."""

        return self.complete_semantic(request)

    def record_acceptance(self, item: CompletionItem) -> None:
        """Record a user-accepted completion for future ranking boosts."""

        key = self._acceptance_key(item)
        self._acceptance_scores[key] = min(self._acceptance_scores.get(key, 0) + 1, 100)

    def _context_from_request(self, request: Any) -> CompletionContext:
        return build_completion_context(
            source_text=request.source_text,
            cursor_position=request.cursor_position,
            current_file_path=request.current_file_path,
            project_root=request.project_root,
            trigger_is_manual=request.trigger_is_manual,
            min_prefix_chars=request.min_prefix_chars,
            max_results=request.max_results,
            trigger_kind=request.trigger_kind,
            trigger_character=request.trigger_character,
            buffer_revision=request.buffer_revision,
        )

    def _fast_candidates(self, context: CompletionContext) -> list[CompletionItem]:
        if context.syntactic_context == CompletionSyntacticContext.STRING_OR_COMMENT:
            return []

        project_limit = max(context.max_results * 2, 120)
        if context.syntactic_context in {
            CompletionSyntacticContext.IMPORT_FROM_MEMBER,
            CompletionSyntacticContext.IMPORT_MODULE,
        }:
            items = provide_api_index_member_items(
                module_name=context.module_name,
                member_prefix=context.prefix,
                limit=project_limit,
            )
            return self._attach_context_metadata(items, context=context)

        if context.syntactic_context == CompletionSyntacticContext.DOTTED_MEMBER:
            items = provide_module_member_items(
                project_root=context.project_root,
                source_text=context.source_text,
                cursor_position=context.cursor_position,
                limit=project_limit,
            )
            return self._attach_context_metadata(_tag_approximate_items(items), context=context)

        items = _tag_approximate_items(
            [
                *provide_current_file_symbol_items(
                    context.source_text,
                    prefix=context.prefix,
                    file_path=context.file_path,
                ),
                *provide_project_symbol_items(
                    project_root=context.project_root,
                    cache_db_path=self._cache_db_path,
                    prefix=context.prefix,
                    limit=project_limit,
                ),
                *provide_project_module_items(
                    project_root=context.project_root,
                    prefix=context.prefix,
                    limit=project_limit,
                    cache_db_path=self._cache_db_path,
                ),
                *provide_builtin_items(context.prefix),
                *provide_keyword_items(context.prefix),
            ]
        )
        return self._attach_context_metadata(items, context=context)

    def _reuse_cached_envelope(self, context: CompletionContext) -> CompletionEnvelope | None:
        cached = self._result_cache.get(context.file_path)
        if cached is None:
            return None
        if not context.valid_for.matches(cached.context):
            return None
        if not context.prefix.startswith(cached.context.prefix):
            return None
        filtered = [
            _with_context_metadata(item, context=context)
            for item in cached.envelope.items
            if context_matches_prefix(item.label, context.prefix)
        ]
        if not filtered:
            return None
        return self._envelope(
            context,
            items=filtered[: context.max_results],
            source_phase="reuse",
            latency_breakdown={"reuse_filter": 0.0},
        )

    def _remember_envelope(self, context: CompletionContext, envelope: CompletionEnvelope) -> None:
        if envelope.items:
            self._result_cache[context.file_path] = _CachedCompletionEnvelope(context=context, envelope=envelope)

    def _rank_candidates(
        self,
        candidates: list[CompletionItem],
        *,
        prefix: str,
        current_file_path: str,
    ) -> list[RankedCompletionItem]:
        deduped: dict[str, RankedCompletionItem] = {}
        for candidate in candidates:
            score = _base_match_score(candidate.label, prefix)
            if score <= 0:
                continue
            score += _source_score(candidate, current_file_path=current_file_path)
            score += self._acceptance_boost(candidate)
            ranked_entry = RankedCompletionItem(item=candidate, score=score)
            dedupe_key = f"{candidate.insert_text}|{candidate.kind.value}"
            existing = deduped.get(dedupe_key)
            if existing is None or ranked_entry.score > existing.score:
                deduped[dedupe_key] = ranked_entry

        return sorted(
            deduped.values(),
            key=lambda entry: (
                -entry.score,
                entry.item.label.lower(),
                len(entry.item.label),
            ),
        )

    def _attach_context_metadata(
        self,
        candidates: list[CompletionItem],
        *,
        context: CompletionContext,
    ) -> list[CompletionItem]:
        return [_with_context_metadata(candidate, context=context) for candidate in candidates]

    def _envelope(
        self,
        context: CompletionContext,
        *,
        items: list[CompletionItem],
        source_phase: str,
        degradation_reason: str = "",
        latency_breakdown: dict[str, float] | None = None,
    ) -> CompletionEnvelope:
        return CompletionEnvelope(
            items=items,
            degradation_reason=degradation_reason,
            source=source_phase,
            confidence="exact" if source_phase == "semantic" else "approximate",
            source_phase=source_phase,
            request_id=context.fingerprint,
            buffer_revision=context.buffer_revision,
            context_fingerprint=context.fingerprint,
            valid_for=context.valid_for,
            latency_breakdown={} if latency_breakdown is None else dict(latency_breakdown),
        )

    def _empty_envelope(self, context: CompletionContext, *, source_phase: str) -> CompletionEnvelope:
        return self._envelope(context, items=[], source_phase=source_phase)

    def _acceptance_boost(self, item: CompletionItem) -> int:
        score = self._acceptance_scores.get(self._acceptance_key(item), 0)
        return min(score * 5, 50)

    @staticmethod
    def _acceptance_key(item: CompletionItem) -> str:
        return f"{item.insert_text}|{item.kind.value}"


def _with_context_metadata(item: CompletionItem, *, context: CompletionContext) -> CompletionItem:
    replacement_start = item.replacement_start
    if replacement_start is None:
        replacement_start = context.replacement_range.start
    replacement_end = item.replacement_end
    if replacement_end is None:
        replacement_end = context.replacement_range.end
    item_id = item.item_id or _item_id(item, context)
    resolve_provider = item.resolve_provider
    resolvable_fields = item.resolvable_fields
    if item.source == "semantic":
        resolve_provider = resolve_provider or "jedi"
        if not resolvable_fields:
            resolvable_fields = ("documentation", "signature", "return_type", "detail")
    elif item.source == "static_api_index":
        resolve_provider = resolve_provider or "api_index"
    return CompletionItem(
        label=item.label,
        insert_text=item.insert_text,
        kind=item.kind,
        detail=item.detail,
        documentation=item.documentation,
        signature=item.signature,
        return_type=item.return_type,
        source_file_path=item.source_file_path,
        engine=item.engine,
        source=item.source,
        confidence=item.confidence,
        semantic_kind=item.semantic_kind,
        replacement_start=replacement_start,
        replacement_end=replacement_end,
        trigger_kind=item.trigger_kind or context.trigger_kind,
        trigger_character=item.trigger_character or context.trigger_character,
        side_effect_risk=item.side_effect_risk,
        item_id=item_id,
        context_fingerprint=context.fingerprint,
        resolve_provider=resolve_provider,
        resolvable_fields=resolvable_fields,
    )


def _item_id(item: CompletionItem, context: CompletionContext) -> str:
    raw = "|".join(
        [
            context.fingerprint,
            item.label,
            item.insert_text,
            item.kind.value,
            item.source,
            item.source_file_path or "",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _tag_approximate_items(candidates: list[CompletionItem]) -> list[CompletionItem]:
    marked: list[CompletionItem] = []
    for candidate in candidates:
        if candidate.source == "static_api_index":
            marked.append(candidate)
            continue
        detail = candidate.detail
        if detail:
            detail = f"{detail} • approximate"
        else:
            detail = "approximate"
        marked.append(
            CompletionItem(
                label=candidate.label,
                insert_text=candidate.insert_text,
                kind=candidate.kind,
                detail=detail,
                documentation=candidate.documentation,
                signature=candidate.signature,
                return_type=candidate.return_type,
                source_file_path=candidate.source_file_path,
                engine=candidate.engine or "heuristic",
                source="approximate",
                confidence="approximate",
                semantic_kind=candidate.semantic_kind,
                replacement_start=candidate.replacement_start,
                replacement_end=candidate.replacement_end,
                trigger_kind=candidate.trigger_kind,
                trigger_character=candidate.trigger_character,
                side_effect_risk=candidate.side_effect_risk,
                item_id=candidate.item_id,
                context_fingerprint=candidate.context_fingerprint,
                resolve_provider=candidate.resolve_provider,
                resolvable_fields=candidate.resolvable_fields,
            )
        )
    return marked


def _base_match_score(label: str, prefix: str) -> int:
    if not label:
        return 0
    if not prefix:
        return 40

    label_lower = label.lower()
    prefix_lower = prefix.lower()
    if label.startswith(prefix):
        return 120
    if label_lower.startswith(prefix_lower):
        return 105
    if prefix_lower in label_lower:
        return 70
    return 0


def _source_score(candidate: CompletionItem, *, current_file_path: str) -> int:
    if candidate.source == "semantic":
        return 60
    if candidate.source == "static_api_index":
        return 55
    if candidate.kind == CompletionKind.SYMBOL and candidate.source_file_path == current_file_path:
        return 40
    if candidate.kind in {
        CompletionKind.METHOD,
        CompletionKind.FUNCTION,
        CompletionKind.PROPERTY,
        CompletionKind.ATTRIBUTE,
        CompletionKind.CLASS,
    }:
        return 35
    if candidate.kind == CompletionKind.SYMBOL:
        return 25
    if candidate.kind == CompletionKind.MODULE:
        return 20
    if candidate.kind == CompletionKind.BUILTIN:
        return 10
    if candidate.kind == CompletionKind.KEYWORD:
        return 5
    return 0
