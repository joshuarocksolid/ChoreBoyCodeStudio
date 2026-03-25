"""Editor completion orchestration and ranking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.completion_models import CompletionItem, CompletionKind, RankedCompletionItem
from app.intelligence.completion_providers import (
    detect_module_member_completion_context,
    extract_completion_prefix,
    provide_builtin_items,
    provide_current_file_symbol_items,
    provide_keyword_items,
    provide_module_member_items,
    provide_project_module_items,
    provide_project_symbol_items,
)
from app.intelligence.semantic_facade import SemanticFacade


@dataclass(frozen=True)
class CompletionRequest:
    """Completion query payload from the editor."""

    source_text: str
    cursor_position: int
    current_file_path: str
    project_root: str | None
    trigger_is_manual: bool
    min_prefix_chars: int
    max_results: int = 100


class CompletionService:
    """Build and rank completion candidates from multiple providers."""

    def __init__(self, *, cache_db_path: str, semantic_facade: SemanticFacade | None = None) -> None:
        self._cache_db_path = str(Path(cache_db_path).expanduser().resolve())
        self._acceptance_scores: dict[str, int] = {}
        self._semantic_facade = semantic_facade or SemanticFacade(cache_db_path=self._cache_db_path)

    def complete(self, request: CompletionRequest) -> list[CompletionItem]:
        """Return ranked completion candidates for one editor query."""
        prefix = extract_completion_prefix(request.source_text, request.cursor_position)
        module_context = detect_module_member_completion_context(request.source_text, request.cursor_position)
        effective_prefix = module_context.member_prefix if module_context is not None else prefix
        if not request.trigger_is_manual and len(effective_prefix) < max(1, request.min_prefix_chars):
            return []

        try:
            semantic_candidates = self._semantic_facade.complete(
                project_root=request.project_root,
                current_file_path=request.current_file_path,
                source_text=request.source_text,
                cursor_position=request.cursor_position,
                trigger_is_manual=request.trigger_is_manual,
                min_prefix_chars=request.min_prefix_chars,
                max_results=request.max_results * 2,
            )
        except Exception:
            semantic_candidates = []
        project_limit = max(request.max_results * 2, 120)
        if module_context is not None:
            module_candidates = provide_module_member_items(
                project_root=request.project_root,
                source_text=request.source_text,
                cursor_position=request.cursor_position,
                limit=project_limit,
            )
            if not semantic_candidates and not module_candidates:
                return []
            ranked = self._rank_candidates(
                [*semantic_candidates, *_mark_as_approximate(module_candidates)],
                prefix=effective_prefix,
                current_file_path=request.current_file_path,
            )
            return [entry.item for entry in ranked[: request.max_results]]

        raw_candidates = [*semantic_candidates, *_mark_as_approximate([
            *provide_current_file_symbol_items(
                request.source_text,
                prefix=prefix,
                file_path=request.current_file_path,
            ),
            *provide_project_symbol_items(
                project_root=request.project_root,
                cache_db_path=self._cache_db_path,
                prefix=prefix,
                limit=project_limit,
            ),
            *provide_project_module_items(
                project_root=request.project_root,
                prefix=prefix,
                limit=project_limit,
                cache_db_path=self._cache_db_path,
            ),
            *provide_builtin_items(prefix),
            *provide_keyword_items(prefix),
        ])]

        ranked = self._rank_candidates(raw_candidates, prefix=effective_prefix, current_file_path=request.current_file_path)
        return [entry.item for entry in ranked[: request.max_results]]

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

    def record_acceptance(self, item: CompletionItem) -> None:
        """Record a user-accepted completion for future ranking boosts."""
        key = self._acceptance_key(item)
        self._acceptance_scores[key] = min(self._acceptance_scores.get(key, 0) + 1, 100)

    def _acceptance_boost(self, item: CompletionItem) -> int:
        score = self._acceptance_scores.get(self._acceptance_key(item), 0)
        return min(score * 5, 50)

    @staticmethod
    def _acceptance_key(item: CompletionItem) -> str:
        return f"{item.insert_text}|{item.kind.value}"


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
    if candidate.kind == CompletionKind.SYMBOL and candidate.source_file_path == current_file_path:
        return 40
    if candidate.kind == CompletionKind.SYMBOL:
        return 25
    if candidate.kind == CompletionKind.MODULE:
        return 20
    if candidate.kind == CompletionKind.BUILTIN:
        return 10
    if candidate.kind == CompletionKind.KEYWORD:
        return 5
    return 0


def _mark_as_approximate(candidates: list[CompletionItem]) -> list[CompletionItem]:
    marked: list[CompletionItem] = []
    for candidate in candidates:
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
                source_file_path=candidate.source_file_path,
                engine=candidate.engine or "heuristic",
                source="approximate",
                confidence="approximate",
                semantic_kind=candidate.semantic_kind,
            )
        )
    return marked
