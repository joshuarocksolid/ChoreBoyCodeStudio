"""Catalog data types and the registry the entry modules register into (Qt-free)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment

#: UX-CAT-002 category order. Entries inside a category keep registration order.
CATEGORY_ORDER: Tuple[str, ...] = (
    "Layouts and spacers",
    "Text and numbers",
    "Choices",
    "Buttons",
    "Dates and times",
    "Lists and tables",
    "Containers",
    "Display",
    "FreeCAD",
    "Your widgets",
)

#: Window kinds (UX-CAT-015) are searchable rows, never inserted.
WINDOW_CATEGORY = "Window kinds"

#: Payload kinds the drop code understands (engine/query/drop_target.py PayloadKind).
WIDGET = "widget"
LABEL = "label"
SPACER = "spacer"
WINDOW = "window"


@dataclass(frozen=True)
class Entry:
    """One insertable class. ``build`` returns the default fragment (None for window kinds)."""

    key: str
    friendly: str
    qt_class: str
    category: str
    object_name: str
    description: str
    synonyms: Tuple[str, ...]
    glyph: str
    payload: str = WIDGET
    build: Optional[Callable[[], Fragment]] = None
    base_class: str = ""
    header: str = ""
    freecad: bool = False


class Registry:
    """What the entry modules register. Order of ``add`` calls is catalog order."""

    def __init__(self) -> None:
        self._entries: List[Entry] = []
        self._families: Dict[str, str] = {}

    def add(self, entry: Entry) -> None:
        if any(item.key == entry.key for item in self._entries):
            raise ValueError("duplicate catalog key %s" % entry.key)
        if entry.category not in CATEGORY_ORDER and entry.category != WINDOW_CATEGORY:
            raise ValueError("unknown category %s" % entry.category)
        self._entries.append(entry)

    def family(self, qt_class: str, friendly: str) -> None:
        """The friendly name shown for a class that several entries share (a slider, a line)."""
        self._families[qt_class] = friendly

    def entries(self) -> Tuple[Entry, ...]:
        return tuple(self._entries)

    def families(self) -> Mapping[str, str]:
        return dict(self._families)


@dataclass(frozen=True)
class Catalog:
    """The built catalog. ``entries`` are widgets in UX-CAT-002 order; ``windows`` are search-only."""

    entries: Tuple[Entry, ...]
    windows: Tuple[Entry, ...]
    families: Mapping[str, str]

    def get(self, key: str) -> Optional[Entry]:
        for entry in self.entries + self.windows:
            if entry.key == key:
                return entry
        return None

    def in_category(self, category: str) -> Tuple[Entry, ...]:
        return tuple(entry for entry in self.entries if entry.category == category)

    def friendly_for_class(self, qt_class: str) -> Optional[str]:
        """Friendly name of a Qt class, or None when no entry or family names it."""
        family = self.families.get(qt_class)
        if family is not None:
            return family
        for entry in self.entries:
            if entry.qt_class == qt_class:
                return entry.friendly
        for entry in self.windows:
            if entry.qt_class == qt_class:
                return entry.friendly
        return None


def build_registry(modules: Iterable[object]) -> Tuple[Registry, Sequence[str]]:
    """Run each module's ``register`` in the order given. Returns the registry and the names used."""
    registry = Registry()
    names: List[str] = []
    for module in modules:
        register = getattr(module, "register", None)
        if not callable(register):
            continue
        register(registry)
        names.append(getattr(module, "__name__", "?"))
    return registry, tuple(names)


def catalog_from(registry: Registry) -> Catalog:
    """Split the registry into widget entries (sorted by category, then catalog order) and windows."""
    widgets = [entry for entry in registry.entries() if entry.category != WINDOW_CATEGORY]
    windows = [entry for entry in registry.entries() if entry.category == WINDOW_CATEGORY]
    rank = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    ordered = sorted(widgets, key=lambda item: rank[item.category])
    return Catalog(tuple(ordered), tuple(windows), registry.families())
