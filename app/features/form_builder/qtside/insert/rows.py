"""What the Insert pane lists, as plain rows (Qt-free). The delegate paints them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.qtside.insert.catalog._model import (
    CATEGORY_ORDER,
    WINDOW,
    Entry,
)
from app.features.form_builder.qtside.insert.catalog.search import Hit, normalise, search

RECENT_TITLE = "Recently used"
RECENT_LIMIT = 6
#: Categories that start collapsed (UX-CAT-005). The user's choice overrides this.
_START_COLLAPSED = frozenset({"FreeCAD"})

SECTION = "section"
HEADER = "header"
ENTRY = "entry"


@dataclass(frozen=True)
class Row:
    kind: str
    title: str
    key: str = ""
    category: str = ""
    count: int = 0
    expanded: bool = True
    description: str = ""
    glyph: str = ""
    via: str = ""
    match: Tuple[int, int] = (-1, -1)
    window: bool = False
    search: bool = False
    qt_class: str = ""


def is_collapsed(category: str, states: Mapping[str, bool]) -> bool:
    """True when the category is folded. The user's remembered state wins over the default."""
    if category in states:
        return not states[category]
    return category in _START_COLLAPSED


def recent_entries(entries: Sequence[Entry], keys: Sequence[str]) -> Tuple[Entry, ...]:
    by_key: Dict[str, Entry] = {entry.key: entry for entry in entries}
    found = []
    for key in keys[:RECENT_LIMIT]:
        entry = by_key.get(key)
        if entry is not None and entry not in found:
            found.append(entry)
    return tuple(found)


def browse_rows(
    entries: Sequence[Entry],
    recent_keys: Sequence[str],
    states: Mapping[str, bool],
) -> Tuple[Row, ...]:
    """Recently used, then each category with its count, in UX-CAT-002 order."""
    rows = []
    recent = recent_entries(entries, recent_keys)
    if recent:
        rows.append(Row(SECTION, RECENT_TITLE))
        rows.extend(_entry_row(entry) for entry in recent)
    for category in CATEGORY_ORDER:
        members = [entry for entry in entries if entry.category == category]
        if not members:
            continue
        collapsed = is_collapsed(category, states)
        rows.append(
            Row(HEADER, category, category=category, count=len(members), expanded=not collapsed)
        )
        if not collapsed:
            rows.extend(_entry_row(entry) for entry in members)
    return tuple(rows)


def search_rows(hits: Sequence[Hit], query: str) -> Tuple[Row, ...]:
    """A flat list for a filter (UX-CAT-008). The first row is current."""
    rows = []
    for hit in hits:
        entry = hit.entry
        title = entry.friendly.split(" · ")[0] if hit.window else entry.friendly
        rows.append(
            Row(
                ENTRY,
                entry.friendly,
                key=entry.key,
                category="" if hit.window else entry.category,
                description=entry.description,
                glyph=entry.glyph,
                via=hit.via,
                match=match_span(title, query),
                window=hit.window,
                search=True,
                qt_class=entry.qt_class,
            )
        )
    return tuple(rows)


def _entry_row(entry: Entry) -> Row:
    return Row(ENTRY, entry.friendly, key=entry.key, category=entry.category,
               description=entry.description, glyph=entry.glyph, qt_class=entry.qt_class)


def match_span(name: str, query: str) -> Tuple[int, int]:
    """Where the typed letters sit in ``name`` (for the match highlight). (-1, -1) when none."""
    text = query.strip().lower()
    if not text:
        return (-1, -1)
    lowered = name.lower()
    direct = lowered.find(text)
    if direct >= 0:
        return (direct, direct + len(text))
    # Spaces and hyphens in the query are optional; find the run in a space-free view of the name.
    squeezed = []
    origin = []
    for index, char in enumerate(lowered):
        if char in " -":
            continue
        squeezed.append(char)
        origin.append(index)
    needle = normalise(text)
    if not needle:
        return (-1, -1)
    found = "".join(squeezed).find(needle)
    if found < 0:
        return (-1, -1)
    start = origin[found]
    end = origin[found + len(needle) - 1] + 1
    return (start, end)


def quick_rows(entries: Sequence[Entry], recent_keys: Sequence[str], query: str) -> Tuple[Row, ...]:
    """The quick-insert list (UX-CAT-013): one flat list, the category on the right.

    An empty query shows Recently used first, then every entry by category. A query
    is the same search as the Insert pane, without window kinds (they never insert).
    """
    text = query.strip()
    if text:
        return search_rows(search(entries, (), text), text)
    rows = []
    recent = recent_entries(entries, recent_keys)
    if recent:
        rows.append(Row(SECTION, RECENT_TITLE))
        rows.extend(_quick_row(entry) for entry in recent)
    rows.extend(_quick_row(entry) for entry in entries)
    return tuple(rows)


def _quick_row(entry: Entry) -> Row:
    return Row(ENTRY, entry.friendly, key=entry.key, category=entry.category,
               description=entry.description, glyph=entry.glyph, qt_class=entry.qt_class, search=True)


def window_entries(windows: Sequence[Entry]) -> Tuple[Entry, ...]:
    return tuple(entry for entry in windows if entry.payload == WINDOW)


def entry_by_key(entries: Sequence[Entry], key: Optional[str]) -> Optional[Entry]:
    if not key:
        return None
    for entry in entries:
        if entry.key == key:
            return entry
    return None
