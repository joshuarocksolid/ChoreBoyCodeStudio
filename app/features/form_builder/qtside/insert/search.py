"""UX-CAT-007 search over the catalog. Pure: no Qt, no I/O.

Matching ignores case, spaces and hyphens, and a leading "Q" when the query
starts with a capital Q followed by a capital ("QComboBox", "QLin"). Each
entry gets its best rank (1 to 8); ties go to category order, then catalog order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from app.features.form_builder.qtside.insert.catalog._model import (
    CATEGORY_ORDER,
    WINDOW,
    Entry,
)

_WORDS = re.compile(r"[a-z0-9]+")
_NO_RANK = 99


@dataclass(frozen=True)
class Hit:
    """One search result. ``via`` is the synonym that matched (rank 4 or 5), else ""."""

    entry: Entry
    rank: int
    via: str
    window: bool


def normalise(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch not in " -\t")


def _query_forms(query: str) -> Tuple[str, ...]:
    forms = [normalise(query)]
    if len(query) > 1 and query[0] == "Q" and query[1].isupper():
        stripped = normalise(query[1:])
        if stripped and stripped not in forms:
            forms.append(stripped)
    return tuple(forms)


def _bare_class(qt_class: str) -> str:
    local = qt_class.rsplit("::", 1)[-1]
    if len(local) > 1 and local[0] == "Q" and local[1].isupper():
        local = local[1:]
    return normalise(local)


def _name_of(entry: Entry) -> str:
    if entry.payload == WINDOW:
        return entry.friendly.split(" · ")[0]
    return entry.friendly


def _best(entry: Entry, forms: Sequence[str]) -> Tuple[int, str]:
    name = normalise(_name_of(entry))
    words = [normalise(part) for part in re.split(r"[ \-]+", _name_of(entry)) if part]
    qt_bare = _bare_class(entry.qt_class)
    description_words = _WORDS.findall(entry.description.lower())
    synonyms = [(normalise(item), item) for item in entry.synonyms]
    best = (_NO_RANK, "")
    for form in forms:
        found = _rank_one(form, name, words, qt_bare, description_words, synonyms)
        if found[0] < best[0]:
            best = found
    return best


def _rank_one(
    form: str,
    name: str,
    words: List[str],
    qt_bare: str,
    description_words: List[str],
    synonyms: List[Tuple[str, str]],
) -> Tuple[int, str]:
    if not form:
        return (_NO_RANK, "")
    if name == form:
        return (1, "")
    if name.startswith(form):
        return (2, "")
    if any(word.startswith(form) for word in words):
        return (3, "")
    for norm, original in synonyms:
        if norm == form:
            return (4, original)
    for norm, original in synonyms:
        if norm.startswith(form):
            return (5, original)
    if qt_bare.startswith(form):
        return (6, "")
    if form in name or form in qt_bare:
        return (7, "")
    if any(word.startswith(form) for word in description_words):
        return (8, "")
    return (_NO_RANK, "")


def _category_index(entry: Entry) -> int:
    try:
        return CATEGORY_ORDER.index(entry.category)
    except ValueError:
        return len(CATEGORY_ORDER)


def search(entries: Sequence[Entry], windows: Sequence[Entry], query: str) -> Tuple[Hit, ...]:
    """Widget results first (UX-CAT-007), then window-kind rows (UX-CAT-015)."""
    text = query.strip()
    if not text:
        return tuple(Hit(entry, 0, "", False) for entry in entries)
    forms = _query_forms(text)
    ranked = []
    for index, entry in enumerate(entries):
        rank, via = _best(entry, forms)
        if rank < _NO_RANK:
            ranked.append((rank, _category_index(entry), index, Hit(entry, rank, via, False)))
    ranked.sort(key=lambda item: item[:3])
    found = [item[3] for item in ranked]
    windows_found = []
    for index, entry in enumerate(windows):
        rank, via = _best(entry, forms)
        if rank < _NO_RANK:
            windows_found.append((rank, index, Hit(entry, rank, via, True)))
    windows_found.sort(key=lambda item: item[:2])
    found.extend(item[2] for item in windows_found)
    return tuple(found)


def first_widget(entries: Iterable[Entry], query: str, windows: Sequence[Entry] = ()) -> Optional[Entry]:
    """The first widget result for ``query``, or None when nothing matches."""
    for hit in search(tuple(entries), tuple(windows), query):
        if not hit.window:
            return hit.entry
    return None
