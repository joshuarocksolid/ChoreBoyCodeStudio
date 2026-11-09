"""HitIndex over a fake GeometrySource (CONTRACTS.md section 5.5)."""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

import pytest

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import (
    GeoEntry,
    HitIndex,
    Rect,
    StaleHitIndexError,
)

pytestmark = pytest.mark.unit


class FakeSource:
    def __init__(self, entries: Sequence[GeoEntry]) -> None:
        self.rows: List[GeoEntry] = list(entries)
        self.settles = 0
        self.reads = 0

    def settle(self) -> None:
        self.settles += 1

    def entries(self) -> Sequence[GeoEntry]:
        self.reads += 1
        return tuple(self.rows)


def _entry(
    node: int,
    kind: str,
    rect: Tuple[int, int, int, int],
    container: Optional[int],
    z: int = 0,
    visible: bool = True,
) -> GeoEntry:
    return GeoEntry(
        node=NodeId(node),
        kind=kind,
        rect=Rect(*rect),
        container=None if container is None else NodeId(container),
        visible=visible,
        z=z,
    )


FORM = 1
LAYOUT = 2
BUTTON = 3
GROUP = 4
LABEL = 5
HIDDEN = 6

NESTED = (
    _entry(FORM, "widget", (0, 0, 400, 300), None),
    _entry(LAYOUT, "layout", (9, 9, 382, 282), FORM, z=-1),
    _entry(BUTTON, "widget", (10, 10, 100, 30), LAYOUT, z=0),
    _entry(GROUP, "widget", (10, 50, 200, 200), LAYOUT, z=1),
    _entry(LABEL, "widget", (20, 70, 50, 20), GROUP, z=0),
    _entry(HIDDEN, "widget", (20, 70, 50, 20), GROUP, z=1, visible=False),
)


def _fresh(entries: Sequence[GeoEntry]) -> Tuple[HitIndex, FakeSource]:
    source = FakeSource(entries)
    index = HitIndex(source)
    index.ensure_fresh()
    return index, source


@pytest.mark.parametrize(
    ("point", "node", "path"),
    [
        ((25, 75), LABEL, (LABEL, GROUP, LAYOUT, FORM)),
        ((50, 20), BUTTON, (BUTTON, LAYOUT, FORM)),
        ((300, 250), LAYOUT, (LAYOUT, FORM)),
        ((3, 3), FORM, (FORM,)),
    ],
    ids=["deepest-skips-hidden-above", "laid-out-child", "layout-gap", "root-margin"],
)
def test_query_returns_deepest_visible_entry_and_its_path(
    point: Tuple[int, int], node: int, path: Tuple[int, ...]
) -> None:
    index, _ = _fresh(NESTED)
    hit = index.query(*point)
    assert hit is not None
    assert (hit.node, hit.path) == (node, path)


def test_query_outside_the_form_misses() -> None:
    index, _ = _fresh(NESTED)
    assert index.query(400, 10) is None


def test_higher_z_wins_where_siblings_overlap() -> None:
    above = _entry(3, "widget", (50, 50, 100, 100), FORM, z=1)
    below = _entry(2, "widget", (0, 0, 100, 100), FORM, z=0)
    index, _ = _fresh((_entry(FORM, "widget", (0, 0, 300, 300), None), above, below))
    overlap = index.query(60, 60)
    only_below = index.query(10, 10)
    assert overlap is not None and overlap.node == 3
    assert only_below is not None and only_below.node == 2


def test_children_of_lists_bottom_z_first() -> None:
    rows = (
        _entry(FORM, "widget", (0, 0, 300, 300), None),
        _entry(4, "widget", (0, 0, 10, 10), FORM, z=2),
        _entry(2, "widget", (0, 0, 10, 10), FORM, z=0),
        _entry(3, "widget", (0, 0, 10, 10), FORM, z=1),
    )
    index, _ = _fresh(rows)
    assert [entry.node for entry in index.children_of(NodeId(FORM))] == [2, 3, 4]


def test_entries_in_returns_visible_widgets_that_intersect() -> None:
    index, _ = _fresh(NESTED)
    hits = index.entries_in(Rect(15, 65, 10, 10))
    assert [entry.node for entry in hits] == [FORM, GROUP, LABEL]


def test_a_page_title_hits_its_page_without_entering_it() -> None:
    tabs, page, inner = 2, 3, 4
    rows = (
        _entry(FORM, "widget", (0, 0, 300, 300), None),
        _entry(tabs, "widget", (0, 0, 300, 300), FORM),
        _entry(page, "widget", (0, 24, 300, 276), tabs, z=0),
        _entry(page, "page_tab", (0, 0, 60, 24), tabs, z=1),
        _entry(inner, "widget", (0, 0, 60, 24), page),
    )
    index, _ = _fresh(rows)
    hit = index.query(10, 10)
    assert hit is not None
    assert (hit.node, hit.kind, hit.path) == (page, "page_tab", (page, tabs, FORM))
    assert index.rect_of(NodeId(page)) == Rect(0, 24, 300, 276)


def test_invalidate_never_reads_the_source() -> None:
    index, source = _fresh(NESTED)
    before = index.epoch
    for reason in ("changeset", "zoom", "root_resize"):
        index.invalidate(reason)
    assert (source.settles, source.reads) == (1, 1)
    assert not index.is_fresh()
    assert index.epoch == before + 3


_QUERIES: List[Tuple[str, Callable[[HitIndex], object]]] = [
    ("query", lambda index: index.query(1, 1)),
    ("rect_of", lambda index: index.rect_of(NodeId(FORM))),
    ("entries_in", lambda index: index.entries_in(Rect(0, 0, 10, 10))),
    ("children_of", lambda index: index.children_of(NodeId(FORM))),
]


@pytest.mark.parametrize("call", [call for _, call in _QUERIES], ids=[name for name, _ in _QUERIES])
def test_a_query_before_ensure_fresh_fails(call: Callable[[HitIndex], object]) -> None:
    index = HitIndex(FakeSource(NESTED))
    with pytest.raises(StaleHitIndexError):
        call(index)


@pytest.mark.parametrize("call", [call for _, call in _QUERIES], ids=[name for name, _ in _QUERIES])
def test_a_query_after_invalidate_fails_until_refreshed(call: Callable[[HitIndex], object]) -> None:
    index, _ = _fresh(NESTED)
    index.invalidate("changeset")
    with pytest.raises(StaleHitIndexError):
        call(index)


def test_ensure_fresh_settles_once_per_invalidation() -> None:
    index, source = _fresh(NESTED)
    index.ensure_fresh()
    assert (source.settles, index.refresh_count) == (1, 1)
    source.rows = [row for row in source.rows if row.node != BUTTON]
    index.invalidate("changeset")
    index.ensure_fresh()
    index.ensure_fresh()
    assert (source.settles, index.refresh_count) == (2, 2)
    hit = index.query(50, 20)
    assert hit is not None and hit.node == LAYOUT
