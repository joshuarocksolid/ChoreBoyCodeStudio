"""Slot geometry picks one drop target. No Qt."""

from __future__ import annotations

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropHost,
    DropPayload,
    NoDrop,
    RefusedDrop,
    SlotGeom,
    resolve_drop,
)
from app.features.form_builder.engine.query.hit_index import Rect

import pytest

pytestmark = pytest.mark.unit

N = NodeId


def _box() -> DropHost:
    return DropHost(
        N(1),
        "vbox",
        "form",
        Rect(0, 0, 200, 120),
        (
            SlotGeom(Rect(8, 8, 180, 28), 0, N(2), "Shop name"),
            SlotGeom(Rect(8, 44, 180, 28), 1, N(3), "Receipts"),
        ),
    )


def _payload(**kwargs: object) -> DropPayload:
    kind = kwargs.pop("kind", "widget")
    return DropPayload(kind=kind, **kwargs)  # type: ignore[arg-type]


def test_box_insert_uses_the_midpoint_not_the_gap() -> None:
    host = _box()
    target = resolve_drop(host, (40, 30), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.action == "box"
    assert target.index == 1
    assert target.sentence == "Insert between Shop name and Receipts"
    assert target.indicator.rect.height == 2
    assert target.indicator.rect.y == 39


def test_box_cross_axis_wraps_beside_the_field() -> None:
    host = _box()
    target = resolve_drop(host, (180, 16), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.action == "wrap"
    assert target.wrap_neighbour == N(2)
    assert target.wrap_side == "after"
    assert target.wrap_layout == "QHBoxLayout"
    assert target.chip == "Beside Shop name · makes a horizontal row"


def test_a_shrunk_nested_layout_still_accepts_the_pointer() -> None:
    inner = DropHost(N(9), "hbox", "row", Rect(0, 40, 200, 2), ())
    outer = DropHost(
        N(1),
        "vbox",
        "form",
        Rect(0, 0, 200, 80),
        (
            SlotGeom(Rect(0, 0, 200, 36), 0, N(2), "Shop name"),
            SlotGeom(Rect(0, 40, 200, 2), 1, N(9), "row"),
        ),
        (inner,),
    )
    target = resolve_drop(outer, (100, 41), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.host == N(9)
    assert target.action == "box"
    assert target.index == 0


def test_grid_empty_cell_names_the_row_and_column() -> None:
    host = DropHost(
        N(1),
        "grid",
        "grid",
        Rect(0, 0, 200, 80),
        (
            SlotGeom(Rect(0, 0, 100, 40), 0, N(2), "A", 0, 0),
            SlotGeom(Rect(100, 0, 100, 40), 0, None, "", 0, 1),
            SlotGeom(Rect(0, 40, 100, 40), 0, N(3), "C", 1, 0),
            SlotGeom(Rect(100, 40, 100, 40), 0, None, "", 1, 1),
        ),
    )
    target = resolve_drop(host, (150, 60), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.action == "grid_cell"
    assert (target.row, target.column) == (1, 1)
    assert target.sentence == "Into row 2, column 2 of the grid"
    assert target.chip == "Row 2, column 2"
    assert target.indicator.dashed is True


def test_grid_occupied_edge_inserts_a_column_and_the_centre_is_not_a_target() -> None:
    host = DropHost(
        N(1),
        "grid",
        "grid",
        Rect(0, 0, 200, 40),
        (SlotGeom(Rect(0, 0, 200, 40), 0, N(2), "Medium", 0, 0),),
    )
    edge = resolve_drop(host, (8, 20), _payload())
    assert isinstance(edge, AcceptedDrop)
    assert edge.action == "grid_column"
    assert edge.column == 0
    assert edge.chip == "New column before Medium"
    centre = resolve_drop(host, (100, 20), _payload())
    assert isinstance(centre, NoDrop)


def test_grid_ghost_row_past_the_last_row() -> None:
    host = DropHost(
        N(1),
        "grid",
        "grid",
        Rect(0, 0, 120, 40),
        (
            SlotGeom(Rect(0, 0, 60, 40), 0, N(2), "A", 0, 0),
            SlotGeom(Rect(60, 0, 60, 40), 0, N(3), "B", 0, 1),
        ),
    )
    target = resolve_drop(host, (30, 50), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.action == "grid_row"
    assert target.row == 1
    assert target.chip == "New row 2"
    assert target.indicator.dashed is True


def test_a_span_that_does_not_fit_is_refused() -> None:
    host = DropHost(
        N(1),
        "grid",
        "grid",
        Rect(0, 0, 80, 40),
        (
            SlotGeom(Rect(0, 0, 40, 40), 0, N(2), "A", 0, 0),
            SlotGeom(Rect(40, 0, 40, 40), 0, None, "", 0, 1),
        ),
    )
    payload = DropPayload("widget", (), 1, 2)
    target = resolve_drop(host, (50, 20), payload)
    assert isinstance(target, RefusedDrop)
    assert target.sentence == "Needs 2 free columns here"
    assert target.indicator.role == "problem"


def test_form_new_row_after_a_named_field_and_empty_label_cell() -> None:
    host = DropHost(
        N(1),
        "form",
        "form",
        Rect(0, 0, 200, 40),
        (
            SlotGeom(Rect(0, 0, 80, 40), 0, N(2), "Email", 0, 0, 1, 1, "label"),
            SlotGeom(Rect(80, 0, 120, 40), 0, None, "", 0, 1, 1, 1, "field"),
        ),
    )
    field = resolve_drop(host, (140, 20), _payload())
    assert isinstance(field, AcceptedDrop)
    assert field.action == "form_cell"
    assert field.role == "field"
    assert field.chip == "Field of row 1"
    new_row = resolve_drop(host, (20, 30), _payload())
    assert isinstance(new_row, AcceptedDrop)
    assert new_row.action == "form_row"
    assert new_row.row == 1
    assert new_row.chip == "New row after Email"
    empty_label = DropHost(
        N(1),
        "form",
        "form",
        Rect(0, 0, 200, 40),
        (
            SlotGeom(Rect(0, 0, 80, 40), 0, None, "", 0, 0, 1, 1, "label"),
            SlotGeom(Rect(80, 0, 120, 40), 0, N(3), "Email", 0, 1, 1, 1, "field"),
        ),
    )
    label = resolve_drop(empty_label, (20, 16), DropPayload("label"))
    assert isinstance(label, AcceptedDrop)
    assert label.action == "form_cell"
    assert label.role == "label"
    assert label.chip == "Label of row 1"


def test_a_spacer_cannot_sit_in_a_form() -> None:
    host = DropHost(
        N(1),
        "form",
        "form",
        Rect(0, 0, 200, 40),
        (SlotGeom(Rect(0, 0, 80, 40), 0, None, "", 0, 0, 1, 1, "label"),),
    )
    target = resolve_drop(host, (20, 10), DropPayload("spacer"))
    assert isinstance(target, RefusedDrop)
    assert target.sentence == "A spacer can't sit in a form."
    assert target.indicator.role == "problem"


def test_dropping_into_itself_is_refused() -> None:
    inner = DropHost(N(5), "bare_empty", "group", Rect(10, 10, 40, 40))
    outer = DropHost(N(1), "vbox", "form", Rect(0, 0, 200, 80), (SlotGeom(Rect(10, 10, 40, 40), 0, N(5), "group"),), (inner,))
    target = resolve_drop(outer, (20, 20), DropPayload("widget", (N(5),)), frozenset({N(5)}))
    assert isinstance(target, RefusedDrop)
    assert target.sentence == "A widget can't go inside itself."


def test_splitter_pane_boundary_names_the_previous_pane() -> None:
    host = DropHost(
        N(1),
        "splitter",
        "split",
        Rect(0, 0, 200, 80),
        (
            SlotGeom(Rect(0, 0, 200, 40), 0, N(2), "Customers list"),
            SlotGeom(Rect(0, 40, 200, 40), 1, N(3), "Details"),
        ),
    )
    target = resolve_drop(host, (20, 60), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.action == "splitter"
    assert target.index == 2
    assert target.chip == "New pane after Details"


def test_an_empty_container_makes_a_vertical_layout() -> None:
    host = DropHost(N(4), "bare_empty", "receiptGroup", Rect(0, 0, 180, 100))
    target = resolve_drop(host, (40, 40), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.action == "auto_layout"
    assert target.chip == "Into receiptGroup · makes a vertical layout"
    assert target.indicator.dashed is True


def test_a_bare_container_with_children_snaps_unless_shift_is_held() -> None:
    host = DropHost(N(4), "bare_free", "frame", Rect(0, 0, 200, 200))
    snapped = resolve_drop(host, (13, 19), _payload())
    assert isinstance(snapped, AcceptedDrop)
    assert snapped.action == "free"
    assert (snapped.x, snapped.y) == (8, 16)
    assert snapped.chip == "x 8, y 16"
    free = resolve_drop(host, (13, 19), DropPayload("widget", snap=False))
    assert isinstance(free, AcceptedDrop)
    assert (free.x, free.y) == (13, 19)


def test_a_tab_title_names_the_page() -> None:
    host = DropHost(
        N(1),
        "pages",
        "tabs",
        Rect(0, 0, 200, 120),
        (SlotGeom(Rect(0, 0, 60, 24), 0, N(7), "Settings", role="page"),),
    )
    target = resolve_drop(host, (10, 8), _payload())
    assert isinstance(target, AcceptedDrop)
    assert target.action == "page"
    assert target.page == N(7)
    assert target.sentence == "Into the Settings tab"
    assert target.spring_id == N(7)
