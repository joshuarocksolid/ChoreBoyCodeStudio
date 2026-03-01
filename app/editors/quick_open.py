"""Quick-open candidate indexing and matching helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuickOpenCandidate:
    """One quick-open candidate."""

    relative_path: str
    absolute_path: str


def rank_candidates(candidates: list[QuickOpenCandidate], query: str, *, limit: int = 100) -> list[QuickOpenCandidate]:
    """Return candidates ranked by simple substring/path heuristics."""
    normalized_query = query.strip().lower()
    if not normalized_query:
        return candidates[:limit]

    scored: list[tuple[int, QuickOpenCandidate]] = []
    for candidate in candidates:
        path = candidate.relative_path.lower()
        file_name = path.rsplit("/", 1)[-1]
        if normalized_query not in path:
            continue

        score = 0
        if file_name.startswith(normalized_query):
            score += 50
        if normalized_query in file_name:
            score += 30
        score += max(0, 20 - path.index(normalized_query))
        score -= len(path)
        scored.append((score, candidate))

    scored.sort(key=lambda item: (-item[0], item[1].relative_path))
    return [candidate for _, candidate in scored[:limit]]
