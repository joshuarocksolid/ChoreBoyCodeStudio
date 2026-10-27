"""Hit-test index (CONTRACTS.md section 5.5). Qt-free.

Layout items are not entries. A widget in a layout item has the layout as its
``container``, so ``query`` depth equals visual depth. ``page_tab`` and
``menu_title`` entries carry the page's or menu's ``NodeId``. ``rect_of``
returns the widget entry, never the title entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Literal, Optional, Protocol, Sequence, Tuple

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


@dataclass(frozen=True)
class RefreshScope:
    """The entries a ChangeSet made stale.

    A partial refresh reads these nodes and, only when a rect moved, their
    layout siblings and ancestors. ``full`` is the whole form (open, replace,
    zoom, and any invalidation that did not name nodes).
    """

    dirty: FrozenSet[NodeId] = field(default_factory=frozenset)
    removed: FrozenSet[NodeId] = field(default_factory=frozenset)
    added: FrozenSet[NodeId] = field(default_factory=frozenset)
    full: bool = False

    def merge(self, other: "RefreshScope") -> "RefreshScope":
        """O(changed). Two scopes before the next refresh are one scope."""
        if self.full or other.full:
            return RefreshScope(full=True)
        return RefreshScope(
            dirty=self.dirty | other.dirty,
            removed=self.removed | other.removed,
            added=self.added | other.added,
        )


@dataclass(frozen=True)
class IndexPatch:
    """One partial refresh. Empty replacements keep the stored entry tuple.

    ``visits`` is how many entries were read. ``changed`` is the nodes whose
    rect or visibility moved. None from the source means the caller walks
    the whole form instead.
    """

    replacements: Tuple[Tuple[int, GeoEntry], ...] = ()
    extra: Tuple[GeoEntry, ...] = ()
    drop: FrozenSet[NodeId] = field(default_factory=frozenset)
    visits: int = 0
    changed: Tuple[NodeId, ...] = ()


# Title entries share their page's NodeId, so descending from one would walk
# the page's children.
_DESCENDS = frozenset({"widget", "layout"})
_TITLES = frozenset({"page_tab", "menu_title", "title_band"})


class HitIndex:
    def __init__(self, source: GeometrySource) -> None:
        self._source = source
        self._epoch = 0
        self._fresh_epoch = -1
        self._refreshes = 0
        self._entries: Tuple[GeoEntry, ...] = ()
        self._children: Dict[Optional[NodeId], Tuple[GeoEntry, ...]] = {}
        self._rects: Dict[NodeId, Rect] = {}
        self._need_full = True
        self._scope: Optional[RefreshScope] = None
        self._last_visits = 0
        self._last_changed: Optional[Tuple[NodeId, ...]] = None

    def invalidate(self, reason: InvalidationReason, scope: Optional[RefreshScope] = None) -> None:
        """O(1) epoch bump. A named ``changeset`` scope refreshes only those entries.

        Any other reason, or a missing scope, walks the form on the next refresh.
        """
        self._epoch += 1
        if reason != "changeset" or scope is None or scope.full:
            self._need_full = True
            self._scope = None
            return
        if self._need_full:
            return
        self._scope = scope if self._scope is None else self._scope.merge(scope)

    @property
    def epoch(self) -> int:
        return self._epoch

    def is_fresh(self) -> bool:
        return self._fresh_epoch == self._epoch

    def ensure_fresh(self) -> None:
        """Refresh a stale index. A ChangeSet scope is O(changed). Everything else walks the form."""
        if self.is_fresh():
            return
        scope = None if self._need_full else self._scope
        self._need_full = False
        self._scope = None
        if scope is not None and self._entries:
            retouch = getattr(self._source, "retouch", None)
            if retouch is not None:
                patch = retouch(self._entries, scope)
                if isinstance(patch, IndexPatch):
                    self._apply_patch(patch)
                    return
        self._source.settle()
        entries = tuple(self._source.entries())
        # Settling can resize the root and invalidate; what was read is still current.
        self._install_full(entries)

    def _install_full(self, entries: Tuple[GeoEntry, ...]) -> None:
        """O(form). Open, replace, zoom, and any refresh the partial path refused."""
        self._fresh_epoch = self._epoch
        self._refreshes += 1
        self._last_visits = len(entries)
        self._last_changed = None
        self._bind(entries)

    def _bind(self, entries: Tuple[GeoEntry, ...]) -> None:
        """O(entries passed in). Rebuilds the hit maps from ``entries``."""
        grouped: Dict[Optional[NodeId], List[GeoEntry]] = {}
        rects: Dict[NodeId, Rect] = {}
        for entry in entries:
            if entry.kind in _TITLES:
                continue
            grouped.setdefault(entry.container, []).append(entry)
            rects[entry.node] = entry.rect
        self._entries = entries
        self._children = {
            container: tuple(sorted(group, key=lambda entry: entry.z))
            for container, group in grouped.items()
        }
        self._rects = rects

    def _apply_patch(self, patch: IndexPatch) -> None:
        """O(changed) when only rects move. A structural patch rebinds the stored entries."""
        self._fresh_epoch = self._epoch
        self._refreshes += 1
        self._last_visits = patch.visits
        self._last_changed = patch.changed
        if not patch.replacements and not patch.extra and not patch.drop:
            return
        items = list(self._entries)
        for index, entry in patch.replacements:
            if 0 <= index < len(items):
                items[index] = entry
        if patch.drop:
            items = [entry for entry in items if entry.node not in patch.drop]
        if patch.extra:
            items.extend(patch.extra)
        if patch.drop or patch.extra:
            self._bind(tuple(items))
            return
        for index, entry in patch.replacements:
            previous = self._entries[index]
            if entry.kind in _TITLES:
                continue
            self._rects[entry.node] = entry.rect
            self._swap_child(previous, entry)
        self._entries = tuple(items)

    def _swap_child(self, previous: GeoEntry, entry: GeoEntry) -> None:
        """O(siblings in this container)."""
        group = self._children.get(previous.container, ())
        self._children[previous.container] = tuple(
            entry if item is previous else item for item in group
        )

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
        title = _title_over(self._entries, trail, x, y)
        if title is not None:
            trail.append(title)
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

    def indexed_entries(self) -> Tuple[GeoEntry, ...]:
        """The entries from the last ``ensure_fresh``. Order is the walk order."""
        return self._entries

    def title_entries(self) -> Tuple[GeoEntry, ...]:
        self._require_fresh()
        return tuple(entry for entry in self._entries if entry.kind in _TITLES and entry.visible)

    def plus_at(self, x: int, y: int) -> Optional[Tuple[NodeId, Rect]]:
        """The '+' after the last tab of one tab bar, in form pixels."""
        self._require_fresh()
        groups: Dict[NodeId, List[GeoEntry]] = {}
        for entry in self._entries:
            if entry.kind != "page_tab" or not entry.visible or entry.container is None:
                continue
            groups.setdefault(entry.container, []).append(entry)
        for container, tabs in groups.items():
            last = max(tabs, key=lambda entry: entry.rect.x + entry.rect.width)
            side = max(last.rect.height, 18)
            rect = Rect(last.rect.x + last.rect.width + 4, last.rect.y, side, side)
            if rect.contains(x, y):
                return container, rect
        return None

    @property
    def refresh_count(self) -> int:
        return self._refreshes

    @property
    def last_visit_count(self) -> int:
        """Entries read by the last refresh. A full walk visits every entry."""
        return self._last_visits

    @property
    def last_changed(self) -> Optional[Tuple[NodeId, ...]]:
        """Nodes whose rect moved on the last partial refresh.

        None means the last refresh walked the form, so callers cannot assume
        a short change list.
        """
        return self._last_changed

    def _require_fresh(self) -> None:
        if not self.is_fresh():
            raise StaleHitIndexError("hit index epoch %d was never refreshed" % self._epoch)


def _topmost_at(level: Tuple[GeoEntry, ...], x: int, y: int) -> Optional[GeoEntry]:
    for entry in reversed(level):
        if entry.kind in _TITLES:
            continue
        if entry.visible and entry.rect.contains(x, y):
            return entry
    return None


def _title_over(entries: Tuple[GeoEntry, ...], trail: Sequence[GeoEntry], x: int, y: int) -> Optional[GeoEntry]:
    """A tab or menu title drawn on top of the widget trail. It is not a child."""
    depth = {entry.node: index for index, entry in enumerate(trail)}
    found: Optional[GeoEntry] = None
    rank: Optional[Tuple[int, int]] = None
    for entry in entries:
        if entry.kind not in _TITLES or not entry.visible or entry.container not in depth:
            continue
        if not entry.rect.contains(x, y):
            continue
        key = (depth[entry.container], entry.z)
        if rank is None or key > rank:
            rank = key
            found = entry
    return found
