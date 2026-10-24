"""Hit-test index (CONTRACTS.md section 5.5). Qt-free.

Layout items are not entries. A widget in a layout item has the layout as its
``container``, so ``query`` depth equals visual depth. ``page_tab`` and
``menu_title`` entries carry the page's or menu's ``NodeId``. ``rect_of``
returns the widget entry, never the title entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Protocol, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId


@dataclass(frozen=True)
class Rect:
    """Integer rect in form (root widget) coordinates, unscaled by zoom."""

    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    def intersects(self, other: Rect) -> bool:
        return (
            self.x < other.x + other.width
            and other.x < self.x + self.width
            and self.y < other.y + other.height
            and other.y < self.y + self.height
        )


@dataclass(frozen=True)
class GeoEntry:
    """One indexed node. ``kind``: widget | layout | layoutitem | spacer | page_tab
    | menu_title | action_slot. ``container``: the entry this one is hit-tested
    inside (its parent in the hit tree). ``visible``: False for widgets on a
    non-current page, collapsed toolbox items, and hidden widgets."""

    node: NodeId
    kind: str
    rect: Rect
    container: Optional[NodeId]
    visible: bool
    z: int


class GeometrySource(Protocol):
    def settle(self) -> None:
        """Activate the root layout synchronously."""

    def entries(self) -> Sequence[GeoEntry]:
        """Every entry, parents before children."""


InvalidationReason = Literal[
    "changeset", "zoom", "root_resize", "page_switch", "scroll", "splitter",
    "font_preview", "style", "palette", "dpi", "realize_rebuild", "show_hide",
]


@dataclass(frozen=True)
class HitResult:
    """``path`` runs deepest first and ends at the root."""

    node: NodeId
    kind: str
    path: Tuple[NodeId, ...]


class StaleHitIndexError(RuntimeError):
    """A query ran on an index that was invalidated and not refreshed."""


# Title entries share their page's NodeId, so descending from one would walk
# the page's children.
_DESCENDS = frozenset({"widget", "layout"})
_TITLES = frozenset({"page_tab", "menu_title"})


class HitIndex:
    def __init__(self, source: GeometrySource) -> None:
        self._source = source
        self._epoch = 0
        self._fresh_epoch = -1
        self._refreshes = 0
        self._entries: Tuple[GeoEntry, ...] = ()
        self._children: Dict[Optional[NodeId], Tuple[GeoEntry, ...]] = {}
        self._rects: Dict[NodeId, Rect] = {}

    def invalidate(self, reason: InvalidationReason) -> None:
        self._epoch += 1

    @property
    def epoch(self) -> int:
        return self._epoch

    def is_fresh(self) -> bool:
        return self._fresh_epoch == self._epoch

    def ensure_fresh(self) -> None:
        if self.is_fresh():
            return
        self._source.settle()
        entries = tuple(self._source.entries())
        # Settling can resize the root and invalidate; what was read is still current.
        self._fresh_epoch = self._epoch
        self._refreshes += 1
        grouped: Dict[Optional[NodeId], List[GeoEntry]] = {}
        rects: Dict[NodeId, Rect] = {}
        for entry in entries:
            grouped.setdefault(entry.container, []).append(entry)
            if entry.kind not in _TITLES:
                rects[entry.node] = entry.rect
        self._entries = entries
        self._children = {
            container: tuple(sorted(group, key=lambda entry: entry.z))
            for container, group in grouped.items()
        }
        self._rects = rects

    def query(self, x: int, y: int) -> Optional[HitResult]:
        self._require_fresh()
        trail: List[GeoEntry] = []
        level = self._children.get(None, ())
        while level:
            hit = _topmost_at(level, x, y)
            if hit is None:
                break
            trail.append(hit)
            if hit.kind not in _DESCENDS:
                break
            level = self._children.get(hit.node, ())
        if not trail:
            return None
        deepest = trail[-1]
        return HitResult(deepest.node, deepest.kind, tuple(entry.node for entry in reversed(trail)))

    def rect_of(self, node: NodeId) -> Optional[Rect]:
        self._require_fresh()
        return self._rects.get(node)

    def entries_in(self, rect: Rect) -> Tuple[GeoEntry, ...]:
        self._require_fresh()
        return tuple(
            entry
            for entry in self._entries
            if entry.kind == "widget" and entry.visible and entry.rect.intersects(rect)
        )

    def children_of(self, container: NodeId) -> Tuple[GeoEntry, ...]:
        self._require_fresh()
        return self._children.get(container, ())

    def geometry(self) -> Tuple[GeoEntry, ...]:
        """The fresh entry tuple, parents before children. Titles included."""
        self._require_fresh()
        return self._entries

    @property
    def refresh_count(self) -> int:
        return self._refreshes

    def _require_fresh(self) -> None:
        if not self.is_fresh():
            raise StaleHitIndexError("hit index epoch %d was never refreshed" % self._epoch)


def _topmost_at(level: Tuple[GeoEntry, ...], x: int, y: int) -> Optional[GeoEntry]:
    for entry in reversed(level):
        if entry.visible and entry.rect.contains(x, y):
            return entry
    return None
