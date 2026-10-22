"""Matching and ranking for the completion popup.

Match tiers (lower is better):

0. prefix, exact case: ``setT`` finds ``setText``
1. prefix, any case: ``sett`` finds ``setText`` (an upper-case query letter
   still has to match an upper-case letter)
2. camelCase or snake subwords with smart case: ``sT`` finds ``setText``,
   ``g_v`` finds ``get_value``
3. fuzzy subsequence, used only when tiers 0-2 match nothing

Within a tier: recently accepted first, public before private, then a small
penalty, then case-insensitive alphabetical. Dunder names are listed only
after the query starts with ``_``.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

FUZZY_TIER = 3


class Match(NamedTuple):
    tier: int
    penalty: int
    positions: Tuple[int, ...]


class RankedRow(NamedTuple):
    index: int
    positions: Tuple[int, ...]


def _word_starts(name: str) -> List[int]:
    starts: List[int] = []
    prev = ""
    for i, ch in enumerate(name):
        if ch == "_":
            prev = ch
            continue
        if (
            i == 0
            or prev == "_"
            or (ch.isupper() and not prev.isupper())
            or (ch.isdigit() and not prev.isdigit())
        ):
            starts.append(i)
        elif ch.isupper() and prev.isupper() and i + 1 < len(name) and name[i + 1].islower():
            starts.append(i)
        prev = ch
    return starts


def _camel_match(name: str, query: str) -> Optional[Tuple[int, ...]]:
    starts = _word_starts(name)
    letters = query.replace("_", "")
    if not starts or not letters:
        return None
    lower = name.lower()

    def search(qi: int, pos: int, word_idx: int) -> Optional[List[int]]:
        if qi == len(letters):
            return []
        raw = letters[qi]
        ch = raw.lower()
        next_start = starts[word_idx + 1] if word_idx + 1 < len(starts) else len(name)
        if qi > 0 and not raw.isupper() and pos < next_start and lower[pos] == ch and name[pos] != "_":
            rest = search(qi + 1, pos + 1, word_idx)
            if rest is not None:
                return [pos] + rest
        first = word_idx + 1 if qi > 0 else 0
        for wi in range(first, len(starts)):
            start = starts[wi]
            if lower[start] != ch:
                if qi == 0:
                    return None
                continue
            if raw.isupper() and not name[start].isupper() and start != 0:
                continue
            rest = search(qi + 1, start + 1, wi)
            if rest is not None:
                return [start] + rest
            if qi == 0:
                return None
        return None

    found = search(0, 0, 0)
    return tuple(found) if found is not None else None


def _fuzzy_match(name: str, query: str) -> Optional[Tuple[Tuple[int, ...], int]]:
    if len(query) < 3:
        return None
    lower = name.lower()
    positions: List[int] = []
    gaps = 0
    index = 0
    for ch in query:
        found = name.find(ch, index) if ch.isupper() else lower.find(ch, index)
        if found < 0:
            return None
        if positions and found != positions[-1] + 1:
            gaps += found - positions[-1] - 1
        positions.append(found)
        index = found + 1
    if positions[0] != 0 or gaps > len(query):
        return None
    return tuple(positions), gaps


def match_name(name: str, query: str) -> Optional[Match]:
    """Return how ``name`` matches ``query``, or ``None``."""

    if not query:
        return Match(1, 0, ())
    if name.startswith(query):
        return Match(0, 0, tuple(range(len(query))))
    if name.lower().startswith(query.lower()) and all(
        name[i].isupper() for i, ch in enumerate(query) if ch.isupper()
    ):
        return Match(1, 0, tuple(range(len(query))))
    camel = _camel_match(name, query)
    if camel is not None:
        return Match(2, len(name), camel)
    fuzzy = _fuzzy_match(name, query)
    if fuzzy is not None:
        positions, gaps = fuzzy
        return Match(FUZZY_TIER, gaps, positions)
    return None


def is_private_name(name: str) -> bool:
    return name.startswith("_")


def filter_and_rank(
    names: Sequence[str],
    query: str,
    *,
    recent: Optional[Dict[str, int]] = None,
    candidates: Optional[Sequence[int]] = None,
    matched_out: Optional[List[int]] = None,
) -> List[RankedRow]:
    """Return the rows of ``names`` that match ``query``, best first.

    ``recent`` maps a name to its acceptance counter (higher is newer).
    ``candidates`` narrows the scan to indices that matched a shorter query;
    ``matched_out`` collects every matching index for the next narrowing.
    """

    recent = recent or {}
    show_dunder = query.startswith("_")
    keyed: List[Tuple[Tuple[int, int, int, int, str], RankedRow]] = []
    indices = range(len(names)) if candidates is None else candidates
    best_tier = FUZZY_TIER + 1
    for index in indices:
        name = names[index]
        if not show_dunder and name.startswith("__"):
            continue
        found = match_name(name, query)
        if found is None:
            continue
        if matched_out is not None:
            matched_out.append(index)
        best_tier = min(best_tier, found.tier)
        key = (
            found.tier,
            -recent.get(name, 0),
            1 if is_private_name(name) else 0,
            found.penalty,
            name.lower(),
        )
        keyed.append((key, RankedRow(index, found.positions)))
    if best_tier < FUZZY_TIER:
        keyed = [entry for entry in keyed if entry[0][0] < FUZZY_TIER]
    keyed.sort(key=lambda entry: entry[0])
    return [row for _key, row in keyed]


def typed_full_name(names: Sequence[str], query: str) -> bool:
    """Return True when ``query`` is a whole name and no longer name extends it."""

    if not query:
        return False
    lowered = query.lower()
    found = False
    for name in names:
        if name == query:
            found = True
        elif name.lower().startswith(lowered):
            return False
    return found


class AcceptanceRecency:
    """Process-wide record of recently accepted completion names."""

    def __init__(self) -> None:
        self._counter = 0
        self._recent: Dict[str, int] = {}

    def note_accepted(self, name: str) -> None:
        self._counter += 1
        self._recent[name] = self._counter

    def snapshot(self) -> Dict[str, int]:
        return self._recent

    def clear(self) -> None:
        self._counter = 0
        self._recent = {}


ACCEPTANCE_RECENCY = AcceptanceRecency()


__all__ = [
    "ACCEPTANCE_RECENCY",
    "AcceptanceRecency",
    "FUZZY_TIER",
    "Match",
    "RankedRow",
    "filter_and_rank",
    "is_private_name",
    "match_name",
    "typed_full_name",
]
