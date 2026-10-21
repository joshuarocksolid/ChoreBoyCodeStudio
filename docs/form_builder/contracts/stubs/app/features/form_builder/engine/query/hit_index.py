"""Hit-test index (CONTRACTS.md section 5.5).

Qt-free: the index stores integer rects in form coordinates and gets them
through a ``GeometrySource`` that the Qt side implements over live widgets.
That keeps the index logic testable without Qt (a fake source).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId


@dataclass(frozen=True)
class Rect:
    """Integer rect in form (root widget) coordinates, unscaled by zoom."""

    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int) -> bool:
        ...


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
    """Implemented by ``qtside.canvas`` over the realized form."""

    def settle(self) -> None:
        """Make live geometry current: activate the root layout synchronously
        (processes pending LayoutRequest for the realized tree only)."""
        ...

    def entries(self) -> Sequence[GeoEntry]:
        """Every realized node's entry, parents before children. O(form) native
        calls; budget 4 ms CPU at 300 widgets."""
        ...


InvalidationReason = Literal[
    "changeset", "zoom", "root_resize", "page_switch", "scroll", "splitter",
    "font_preview", "style", "palette", "dpi", "realize_rebuild", "show_hide",
]


@dataclass(frozen=True)
class HitResult:
    """Deepest visible entry under the point, plus its chain to the root
    (``path``, deepest first) so controllers can pick "the layout around it"
    or "the container to drop into" without another query."""

    node: NodeId
    kind: str
    path: Tuple[NodeId, ...]


class HitIndex:
    """Lazily refreshed index.

    Contract:
    * ``invalidate(reason)`` is O(1): it bumps an epoch. It never reads geometry.
    * The index refreshes only inside ``ensure_fresh()``, which callers invoke at
      the start of a pointer event, a paint, or a keyboard navigation that needs
      rects. Refresh = ``source.settle()`` then ``source.entries()``. Never inside
      a ChangeSet listener and never on a timer.
    * During a drag (between press and release) the canvas does not invalidate;
      edits cannot happen mid-drag, and zoom/scroll during drag invalidate as usual.
    * ``query`` is O(depth x siblings) over the hit tree, not a scan of all entries.
    """

    def __init__(self, source: GeometrySource) -> None:
        ...

    def invalidate(self, reason: InvalidationReason) -> None:
        ...

    @property
    def epoch(self) -> int:
        ...

    def is_fresh(self) -> bool:
        ...

    def ensure_fresh(self) -> None:
        ...

    def query(self, x: int, y: int) -> Optional[HitResult]:
        """Asserts freshness (call ensure_fresh first)."""
        ...

    def rect_of(self, node: NodeId) -> Optional[Rect]:
        ...

    def entries_in(self, rect: Rect) -> Tuple[GeoEntry, ...]:
        """Rubber-band selection: visible widget entries whose rect intersects."""
        ...

    def children_of(self, container: NodeId) -> Tuple[GeoEntry, ...]:
        """Hit-tree children in z order (bottom first)."""
        ...

    @property
    def refresh_count(self) -> int:
        """For tests and the speed harness."""
        ...
