"""Quick-open candidate indexing and fuzzy matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class QuickOpenCandidate:
    relative_path: str
    absolute_path: str
    is_open: bool = False


@dataclass(frozen=True)
class RankedCandidate:
    candidate: QuickOpenCandidate
    score: int
    match_positions: List[int] = field(default_factory=list)


_BOUNDARY_CHARS = frozenset("/_.-")


def _is_boundary(path: str, idx: int) -> bool:
    if idx == 0:
        return True
    prev = path[idx - 1]
    if prev in _BOUNDARY_CHARS:
        return True
    cur = path[idx]
    if prev.islower() and cur.isupper():
        return True
    return False


def _fuzzy_match(path_lower: str, path_original: str, query: str) -> Optional[Tuple[int, List[int]]]:
    """Try to fuzzy-match *query* against *path_lower*.

    Returns ``(score, positions)`` on success or ``None`` if no match.
    The algorithm greedily matches query characters left-to-right,
    preferring boundary positions and consecutive runs.
    """
    qlen = len(query)
    plen = len(path_lower)
    if qlen == 0:
        return (0, [])
    if qlen > plen:
        return None

    positions: List[int] = []
    qi = 0
    pi = 0
    while qi < qlen and pi < plen:
        if path_lower[pi] == query[qi]:
            positions.append(pi)
            qi += 1
        pi += 1

    if qi < qlen:
        return None

    boundary_pass_positions = _try_boundary_pass(path_lower, path_original, query)
    if boundary_pass_positions is not None:
        positions = boundary_pass_positions

    score = _score_positions(path_lower, path_original, positions, qlen)
    return (score, positions)


def _try_boundary_pass(path_lower: str, path_original: str, query: str) -> Optional[List[int]]:
    """Second pass: prefer matching at word boundaries when possible."""
    qlen = len(query)
    plen = len(path_lower)
    positions: List[int] = []
    qi = 0
    pi = 0
    while qi < qlen and pi < plen:
        if path_lower[pi] == query[qi]:
            if _is_boundary(path_original, pi) or len(positions) > 0 and positions[-1] == pi - 1:
                positions.append(pi)
                qi += 1
                pi += 1
                continue
            first_hit = pi
            found_boundary = False
            scan = pi + 1
            while scan < plen and scan - pi < 10:
                if path_lower[scan] == query[qi]:
                    if _is_boundary(path_original, scan):
                        positions.append(scan)
                        qi += 1
                        pi = scan + 1
                        found_boundary = True
                        break
                scan += 1
            if not found_boundary:
                positions.append(first_hit)
                qi += 1
                pi = first_hit + 1
        else:
            pi += 1

    if qi < qlen:
        return None
    return positions


def _score_positions(path_lower: str, path_original: str, positions: List[int], qlen: int) -> int:
    score = 0
    file_name_start = path_lower.rfind("/") + 1

    consecutive_bonus = 0
    for i, pos in enumerate(positions):
        if _is_boundary(path_original, pos):
            score += 12
        if pos >= file_name_start:
            score += 5
        if i > 0 and pos == positions[i - 1] + 1:
            consecutive_bonus += 8
            score += consecutive_bonus
        else:
            consecutive_bonus = 0

    file_name = path_lower[file_name_start:]
    if file_name.startswith(path_lower[positions[0]:positions[0] + 1] if positions else ""):
        first_in_filename = all(p >= file_name_start for p in positions[:min(3, len(positions))])
        if first_in_filename:
            score += 30

    score -= len(path_lower)
    score += qlen * 3

    return score


def rank_candidates(
    candidates: List[QuickOpenCandidate],
    query: str,
    *,
    limit: int = 100,
) -> List[RankedCandidate]:
    """Return candidates ranked by fuzzy match score."""
    normalized_query = query.strip().lower()

    if not normalized_query:
        open_files = [
            RankedCandidate(candidate=c, score=0)
            for c in candidates if c.is_open
        ]
        rest = [
            RankedCandidate(candidate=c, score=0)
            for c in candidates if not c.is_open
        ]
        return (open_files + rest)[:limit]

    scored: List[RankedCandidate] = []
    for candidate in candidates:
        path_lower = candidate.relative_path.lower()
        result = _fuzzy_match(path_lower, candidate.relative_path, normalized_query)
        if result is None:
            continue
        match_score, positions = result
        scored.append(RankedCandidate(
            candidate=candidate,
            score=match_score,
            match_positions=positions,
        ))

    scored.sort(key=lambda r: (-r.score, r.candidate.relative_path))
    return scored[:limit]
