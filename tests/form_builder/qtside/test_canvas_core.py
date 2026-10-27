"""Qt-free canvas core. Gesture, snap, chips, and the overlay frame."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Iterator, Optional, Sequence, Tuple
from contextlib import contextmanager
from dataclasses import replace

import pytest

from app.features.form_builder.engine.commands.catalog import InsertFragment, SetGeometry, SetLayoutCell
from app.features.form_builder.engine.commands.placement import InContainer
from app.features.form_builder.engine.commands.catalog_ext.sizing import ApplySizing
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.direct import (
    FreeRect,
    Knob,
    KnobSet,
    LayoutFacts,
    PrimaryFacts,
    Survey,
    Track,
    knob_set,
    survey_scope,
)
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, DropIndicator
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.chips import (
    CHIP_GAP,
    LABEL_CORNERS,
    BesideSeat,
    ChipRequest,
    CornerSeat,
    DockSeat,
    GutterSeat,
    Obstacle,
    corner_rect,
    place_chips,
)
from app.features.form_builder.qtside.canvas.core.frame import (
    Caption,
    Chip,
    FrameBasis,
    Handle,
    OnChip,
    OnHandle,
    OnKnob,
    OnPageEdge,
    OnSpace,
    OnWidget,
    OpenLayoutPopover,
    OverlayFrame,
    Stroke,
)
from app.features.form_builder.qtside.canvas.core.gesture import (
    Banding,
    Commit,
    Cursor,
    Gesture,
    Idle,
    Inert,
    Key,
    KeyUp,
    Mods,
    Move,
    MovedItem,
    Moving,
    Narrate,
    PageResizing,
    Placing,
    Press,
    Pressed,
    Release,
    Reveal,
    Select,
    Toggle,
    Turning,
    World,
    aim,
    band_hits,
    previewing,
    step,
)
from app.features.form_builder.qtside.canvas.core.place import payload_for
from app.features.form_builder.qtside.canvas.core.structure import Free, free_origin, nearest_in_direction, positioning_of
from app.features.form_builder.qtside.canvas.core.overlay import FrameInputs, build_frame, build_static
from app.features.form_builder.qtside.canvas.core.snap import snap_move, snap_page
from app.features.form_builder.qtside.canvas.core.space import (
    CanvasPoint,
    CanvasRect,
    CanvasSize,
    Fit,
    Fixed,
    FormPoint,
    PortPoint,
    Size,
    ViewMap,
    ZoomFit,
    ZoomStep,
    ZoomTo,
    apply_zoom,
    GUTTERS,
    layout_page,
    page_request,
    zoom_factor,
)
pytestmark = pytest.mark.unit


class _Source:
    def __init__(self, rows: Sequence[GeoEntry]) -> None:
        self.rows = tuple(rows)

    def settle(self) -> None:
        return None

    def entries(self) -> Sequence[GeoEntry]:
        return self.rows


def _ui(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n <class>Form</class>\n%s\n</ui>\n' % body
    )


BARE = _ui(
    """
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QFrame" name="box">
   <property name="geometry"><rect><x>20</x><y>30</y><width>200</width><height>140</height></rect></property>
   <widget class="QPushButton" name="ok">
    <property name="geometry"><rect><x>10</x><y>16</y><width>80</width><height>24</height></rect></property>
   </widget>
   <widget class="QLineEdit" name="email">
    <property name="geometry"><rect><x>10</x><y>50</y><width>120</width><height>24</height></rect></property>
   </widget>
  </widget>
 </widget>
"""
)

LAID = _ui(
    """
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
 </widget>
"""
)

EMPTY = _ui(
    """
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout"/>
 </widget>
"""
)


@contextmanager
def _opened(text: str) -> Iterator[FormSession]:
    session = FormSession.open(
        text,
        path="/tmp/cbcs-m31-core.ui",
        scope=FormScope(kind="external", ui_path="/tmp/cbcs-m31-core.ui"),
    )
    try:
        yield session
    finally:
        session.dispose()


def _nid(session: FormSession, name: str) -> NodeId:
    found = session.document.by_name(name)
    assert len(found) == 1
    return found[0]


def _entry(
    node: NodeId,
    kind: str,
    rect: Tuple[int, int, int, int],
    container: Optional[NodeId],
    z: int = 0,
) -> GeoEntry:
    return GeoEntry(node, kind, Rect(*rect), container, True, z)


def _index(rows: Sequence[GeoEntry]) -> HitIndex:
    index = HitIndex(_Source(rows))
    index.ensure_fresh()
    return index


def _view(factor: float = 1.0, width: int = 400, height: int = 300) -> ViewMap:
    return ViewMap(factor, CanvasPoint(96, 64), Size(width, height))


def _blank_frame(index: HitIndex, view: ViewMap, selection: SelectionState) -> OverlayFrame:
    return OverlayFrame(FrameBasis(index.epoch, view, selection, 0), (), (), ())


def _world(
    session: FormSession,
    index: HitIndex,
    view: ViewMap,
    selection: SelectionState = SelectionState(),
    frame: Optional[OverlayFrame] = None,
) -> World:
    return World(
        session.document,
        selection,
        index,
        view,
        frame if frame is not None else _blank_frame(index, view, selection),
        Size(80, 60),
        "token",
    )


def _inputs(
    session: FormSession,
    view: ViewMap,
    selection: SelectionState,
    gesture: Gesture,
    knobs: Optional[KnobSet] = None,
) -> FrameInputs:
    inputs = FrameInputs(
        session.document,
        selection,
        gesture,
        view,
        False,
        {},
        0,
        None,
        (),
        lambda text: len(text) * 6,
    )
    return inputs if knobs is None else replace(inputs, knobs=knobs)


def _knobs(
    session: FormSession,
    index: HitIndex,
    view: ViewMap,
    primary: NodeId,
    layouts: Tuple[LayoutFacts, ...] = (),
) -> KnobSet:
    """What the live surveyor would measure, built from the hand-made index."""
    document = session.document
    rect = index.rect_of(primary)
    assert rect is not None
    free = free_origin(document, index, primary) if isinstance(positioning_of(document, primary), Free) else None
    facts = PrimaryFacts(primary, rect, ("Minimum", "Fixed"), free)
    survey = Survey(index.epoch, survey_scope(document, primary, ()), facts, layouts, ())
    return knob_set(survey, document, view.factor)


def _drag(world: World, frame: OverlayFrame, start: CanvasPoint, end: CanvasPoint, mods: Mods = Mods()) -> Tuple[Gesture, Tuple[object, ...]]:
    """Press, move and release through ``step``. Returns the last gesture and the release effects."""
    world = replace(world, frame=frame)
    pressed = step(Idle(), Press(start, PortPoint(0, 0), "left", mods, False), world)
    moved = step(
        pressed.gesture,
        Move(end, PortPoint(end.x - start.x, end.y - start.y), frozenset(("left",)), mods),
        world,
    )
    released = step(moved.gesture, Release(end, PortPoint(0, 0), "left", mods), world)
    return moved.gesture, tuple(released.effects)


def _centre(rect: CanvasRect) -> CanvasPoint:
    return CanvasPoint(rect.x + rect.width // 2, rect.y + rect.height // 2)


def _size_knob(frame: OverlayFrame, at: str) -> Tuple[CanvasRect, Knob]:
    for rect, target in frame.targets:
        if isinstance(target, OnKnob) and target.knob.key[0] == "size" and target.knob.pull == at:
            return rect, target.knob
    raise AssertionError(at)


def _bare_index(session: FormSession) -> HitIndex:
    form = _nid(session, "Form")
    box = _nid(session, "box")
    ok = _nid(session, "ok")
    email = _nid(session, "email")
    return _index(
        (
            _entry(form, "widget", (0, 0, 400, 300), None),
            _entry(box, "widget", (20, 30, 200, 140), form),
            _entry(ok, "widget", (30, 46, 80, 24), box),
            _entry(email, "widget", (30, 80, 120, 24), box),
        )
    )


def _canvas(view: ViewMap, x: int, y: int) -> CanvasPoint:
    return CanvasPoint(view.page_origin.x + x, view.page_origin.y + y)


def test_page_request_keeps_a_positive_document_size() -> None:
    assert page_request(RectValue(0, 0, 640, 480), Size(10, 10), Size(80, 60)) is None
    assert page_request(RectValue(0, 0, 0, 480), Size(10, 10), Size(80, 60)) == Size(80, 60)
    assert page_request(None, Size(100, 40), Size(80, 60)) == Size(100, 60)


def test_snap_lands_on_the_grid_unless_shift_is_down() -> None:
    origin = RectValue(10, 16, 80, 24)
    dx, dy = snap_move(origin, FormPoint(20, 3), True)
    assert (origin.x + dx) % 8 == 0
    assert (origin.y + dy) % 8 == 0
    free = snap_move(origin, FormPoint(20.4, 3.2), False)
    assert free == (round(30.4) - 10, round(19.2) - 16)


def test_snap_page_keeps_the_minimum() -> None:
    assert snap_page(Size(100, 100), "se", FormPoint(-40, -40), True, Size(80, 70)) == Size(80, 70)


def test_zoom_steps_stay_on_the_table_and_fit_is_capped() -> None:
    assert apply_zoom(Fixed(1.0), ZoomStep(1), 1.0) == Fixed(1.1)
    assert apply_zoom(Fixed(1.0), ZoomStep(-1), 1.0) == Fixed(0.9)
    assert apply_zoom(Fixed(1.0), ZoomTo(2.0), 1.0) == Fixed(2.0)
    assert isinstance(apply_zoom(Fixed(1.0), ZoomFit(), 1.0), Fit)
    assert zoom_factor(Fit(), Size(100, 100), CanvasSize(2000, 2000)) == 1.0
    assert zoom_factor(Fit(), Size(1000, 1000), CanvasSize(300, 300)) == 0.75


def test_layout_page_centres_inside_the_gutters() -> None:
    centred = layout_page(Size(100, 80), 1.0, CanvasSize(800, 800), 0)
    assert centred.page_origin == CanvasPoint(350, 360)
    parked = layout_page(Size(400, 300), 1.0, CanvasSize(200, 200), 0)
    assert parked.page_origin == CanvasPoint(GUTTERS.left, GUTTERS.top)


def test_blocked_corners_seat_the_chip_beside_its_target() -> None:
    page = CanvasRect(0, 0, 200, 100)
    target = CanvasRect(80, 40, 40, 20)
    size = CanvasSize(30, 18)
    blockers = tuple(
        Obstacle(NodeId(index + 1), corner_rect(target, size, corner))
        for index, corner in enumerate(LABEL_CORNERS)
    )
    requests = tuple(
        ChipRequest(index, target, size, LABEL_CORNERS, frozenset()) for index in range(8)
    )
    seats = place_chips(requests, blockers, (), page, page.grown(400))
    first = seats[0]
    assert isinstance(first, BesideSeat) and first.leader is None
    assert first.rect.x == target.x + target.width + CHIP_GAP
    for seat in seats:
        assert not seat.rect.intersects(target)
        assert all(not seat.rect.intersects(blocker.rect) for blocker in blockers)
        leader = getattr(seat, "leader", None)
        if leader is None:
            continue
        assert leader.start.y == leader.end.y
        for other in seats:
            if other is not seat:
                assert not _segment_hits(leader.start.x, leader.end.x, leader.start.y, other.rect)


def test_a_chip_outside_the_viewport_is_not_pulled_onto_the_page() -> None:
    page = CanvasRect(0, 0, 500, 400)
    viewport = CanvasRect(40, 40, 200, 150)
    dock = CanvasRect(40, 40, 200, 22)
    target = CanvasRect(50, 50, 30, 20)
    blocker = Obstacle(NodeId(1), CanvasRect(40, 40, 200, 80))
    request = ChipRequest("chip", target, CanvasSize(40, 16), LABEL_CORNERS, frozenset())
    assert place_chips((request,), (blocker,), (), page, viewport, dock) == ()
    required = ChipRequest("chip", target, CanvasSize(40, 16), LABEL_CORNERS, frozenset(), required=True)
    (seat,) = place_chips((required,), (blocker,), (dock,), page, viewport, dock)
    assert isinstance(seat, DockSeat)
    assert seat.rect.y >= dock.y and seat.rect.y + seat.rect.height <= dock.y + dock.height
    # Without caption chrome the stand-in strip may not cover content.
    assert place_chips((required,), (blocker,), (), page, viewport) == ()
    # A widget scrolled fully out of view gets no chip pointing at nothing.
    gone = ChipRequest("chip", CanvasRect(300, 300, 30, 20), CanvasSize(40, 16), LABEL_CORNERS, frozenset(), required=True)
    assert place_chips((gone,), (blocker,), (dock,), page, viewport, dock) == ()


def test_a_chip_larger_than_the_viewport_is_omitted() -> None:
    page = CanvasRect(0, 0, 400, 300)
    viewport = CanvasRect(0, 0, 40, 40)
    target = CanvasRect(0, 0, 20, 20)
    request = ChipRequest("chip", target, CanvasSize(80, 20), LABEL_CORNERS, frozenset())
    assert place_chips((request,), (), (), page, viewport) == ()


def test_an_open_corner_inside_the_viewport_stays_there() -> None:
    page = CanvasRect(0, 0, 400, 300)
    target = CanvasRect(80, 80, 40, 20)
    request = ChipRequest("chip", target, CanvasSize(30, 14), ("above_left",), frozenset())
    seats = place_chips((request,), (), (), page, page.grown(80))
    assert len(seats) == 1
    assert isinstance(seats[0], CornerSeat)
    assert seats[0].rect.y < target.y


def test_shift_click_on_the_only_selected_widget_selects_the_form() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        form = _nid(session, "Form")
        selection = SelectionState((ok,), ok)
        world = _world(session, index, view, selection)
        result = step(
            Idle(),
            Press(_canvas(view, 40, 50), PortPoint(0, 0), "left", Mods(shift=True), False),
            world,
        )
        chosen = [effect for effect in result.effects if isinstance(effect, (Select, Toggle))]
        assert chosen == [Select((form,), form)]


def test_tab_selects_the_next_widget_and_reveals_it() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        box = _nid(session, "box")
        ok = _nid(session, "ok")
        world = _world(session, index, view, SelectionState((box,), box))
        result = step(Idle(), Key("tab", Mods()), world)
        assert Select((ok,), ok) in result.effects
        assert Reveal(Rect(30, 46, 80, 24)) in result.effects


def test_escape_selects_the_parent_and_stops_on_the_form() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        box = _nid(session, "box")
        form = _nid(session, "Form")
        child = step(Idle(), Key("escape", Mods()), _world(session, index, view, SelectionState((ok,), ok)))
        assert Select((box,), box) in child.effects
        root = step(Idle(), Key("escape", Mods()), _world(session, index, view, SelectionState((form,), form)))
        assert root.effects == ()
        assert root.consumed


def test_a_free_drag_commits_once_on_release() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        world = _world(session, index, view)
        start = _canvas(view, 40, 50)
        pressed = step(Idle(), Press(start, PortPoint(0, 0), "left", Mods(), False), world)
        assert not any(isinstance(effect, Commit) for effect in pressed.effects)
        assert isinstance(pressed.gesture, Pressed)
        moved_at = _canvas(view, 60, 50)
        moving = step(
            pressed.gesture,
            Move(moved_at, PortPoint(10, 0), frozenset(("left",)), Mods()),
            world,
        )
        assert isinstance(moving.gesture, Moving)
        assert previewing(moving.gesture)
        assert not any(isinstance(effect, Commit) for effect in moving.effects)
        released = step(moving.gesture, Release(moved_at, PortPoint(10, 0), "left", Mods()), world)
        commits = [effect for effect in released.effects if isinstance(effect, Commit)]
        assert len(commits) == 1
        assert commits[0].label == "Move"
        assert len(commits[0].commands) == 1
        command = commits[0].commands[0]
        assert isinstance(command, SetGeometry)
        assert command.id == ok
        assert command.rect.x % 8 == 0
        assert command.rect != RectValue(10, 16, 80, 24)


def test_a_press_inside_the_drag_threshold_does_not_commit() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        world = _world(session, index, view)
        start = _canvas(view, 40, 50)
        pressed = step(Idle(), Press(start, PortPoint(0, 0), "left", Mods(), False), world)
        held = step(
            pressed.gesture,
            Move(start, PortPoint(4, 0), frozenset(("left",)), Mods()),
            world,
        )
        assert isinstance(held.gesture, Pressed)
        released = step(held.gesture, Release(start, PortPoint(4, 0), "left", Mods()), world)
        assert not any(isinstance(effect, Commit) for effect in released.effects)


def test_dragging_a_laid_out_widget_waits_for_release() -> None:
    with _opened(LAID) as session:
        view = _view()
        form = _nid(session, "Form")
        layout = _nid(session, "verticalLayout")
        ok = _nid(session, "ok")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(layout, "layout", (9, 9, 382, 282), form),
                _entry(ok, "widget", (20, 20, 100, 30), layout),
            )
        )
        world = _world(session, index, view)
        start = _canvas(view, 30, 30)
        pressed = step(Idle(), Press(start, PortPoint(0, 0), "left", Mods(), False), world)
        dragged = step(
            pressed.gesture,
            Move(_canvas(view, 50, 30), PortPoint(20, 0), frozenset(("left",)), Mods()),
            world,
        )
        assert isinstance(dragged.gesture, Placing)
        assert not any(isinstance(effect, Commit) for effect in dragged.effects)
        released = step(
            dragged.gesture,
            Release(_canvas(view, 50, 30), PortPoint(20, 0), "left", Mods()),
            world,
        )
        commits = [effect for effect in released.effects if isinstance(effect, Commit)]
        assert len(commits) <= 1
        if commits:
            assert commits[0].label == "Move"


@pytest.mark.parity("R3-25")
@pytest.mark.parametrize("mods", (Mods(ctrl=True), Mods(alt=True)))
def test_ctrl_or_alt_release_of_a_placing_drag_inserts_a_copy(mods: Mods) -> None:
    with _opened(LAID) as session:
        view = _view()
        form = _nid(session, "Form")
        layout = _nid(session, "verticalLayout")
        ok = _nid(session, "ok")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(layout, "layout", (9, 9, 382, 282), form),
                _entry(ok, "widget", (20, 20, 100, 30), layout),
            )
        )
        world = _world(session, index, view)
        target = AcceptedDrop(
            "",
            "",
            layout,
            "box",
            DropIndicator(Rect(0, 0, 10, 2)),
            Rect(0, 0, 100, 40),
            index=1,
        )
        placing = Placing("t", payload_for(session.document, (ok,)), "", FormPoint(0, 0), FormPoint(0, 0), target, False)
        held = step(placing, Key("other", mods), world)
        assert any(isinstance(effect, Cursor) and effect.shape == "copy" for effect in held.effects)
        released = step(held.gesture, Release(CanvasPoint(0, 0), PortPoint(0, 0), "left", mods), world)
        commits = [effect for effect in released.effects if isinstance(effect, Commit)]
        assert len(commits) == 1
        assert commits[0].label == "Duplicate"
        command = commits[0].commands[0]
        assert isinstance(command, InsertFragment)
        session.log.execute(command)
        assert session.document.by_name("ok")
        assert session.document.by_name("ok_2")


def test_ctrl_release_of_a_free_drag_inserts_beside_the_original() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        box = _nid(session, "box")
        world = _world(session, index, view)
        item = MovedItem(ok, RectValue(10, 16, 80, 24), Rect(30, 46, 80, 24))
        state = Moving("t", ok, (item,), FormPoint(0, 0), FormPoint(24, 16), False)
        released = step(state, Release(CanvasPoint(0, 0), PortPoint(0, 0), "left", Mods(ctrl=True)), world)
        commits = [effect for effect in released.effects if isinstance(effect, Commit)]
        assert len(commits) == 1
        command = commits[0].commands[0]
        assert isinstance(command, InsertFragment)
        assert command.auto_layout is False
        assert isinstance(command.placement, InContainer)
        assert command.placement.widget == box
        session.log.execute(command)
        assert len(session.document.by_name("ok")) == 1
        copy = session.document.node(session.document.by_name("ok_2")[0])
        geometry = copy.prop("geometry")
        assert geometry is not None
        assert isinstance(geometry.value, RectValue)
        assert (geometry.value.x, geometry.value.y) == (34, 32)
        up = step(state, KeyUp("other", Mods()), world)
        assert not any(isinstance(effect, Cursor) and effect.shape == "copy" for effect in up.effects)


def test_every_drag_state_consumes_release_without_an_empty_commit() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        form = _nid(session, "Form")
        item = MovedItem(ok, RectValue(8, 16, 80, 24), Rect(30, 46, 80, 24))
        origin = FormPoint(0, 0)
        free = Knob(("size", ok, "e"), ok, "e", "", FreeRect(ok, "e", item.origin, item.drawn))
        states = (
            Moving("t", ok, (item,), origin, origin, True),
            Turning("t", free, origin, origin, False),
            PageResizing("t", "e", Size(400, 300), Size(80, 60), origin, origin, True),
            Banding(form, origin, FormPoint(2, 2), False, (), ()),
            Inert(""),
        )
        world = _world(session, index, view)
        release = Release(CanvasPoint(0, 0), PortPoint(0, 0), "left", Mods())
        for state in states:
            result = step(state, release, world)
            assert result.consumed
            assert not any(isinstance(effect, Commit) for effect in result.effects)


def test_aim_returns_the_deepest_widget() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        box = _nid(session, "box")
        form = _nid(session, "Form")
        frame = _blank_frame(index, view, SelectionState())
        document = session.document
        deepest = aim(_canvas(view, 40, 50), frame, index, document, view)
        parent = aim(_canvas(view, 25, 35), frame, index, document, view)
        margin = aim(_canvas(view, 3, 3), frame, index, document, view)
        assert isinstance(deepest, OnWidget) and deepest.node == ok
        assert isinstance(parent, OnSpace) and parent.band_owner == box
        assert isinstance(margin, OnSpace) and margin.select == form


def test_hover_stroke_is_drawn_only_while_idle() -> None:
    with _opened(LAID) as session:
        view = _view()
        form = _nid(session, "Form")
        layout = _nid(session, "verticalLayout")
        ok = _nid(session, "ok")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(layout, "layout", (9, 9, 382, 282), form),
                _entry(ok, "widget", (20, 20, 100, 30), layout),
            )
        )
        static = build_static(session.document, index, view)
        hovering = build_frame(static, _inputs(session, view, SelectionState(), Idle(ok)))
        hover = [item for item in hovering.items if isinstance(item, Stroke) and item.role == "hover"]
        parent = [
            item
            for item in hovering.items
            if isinstance(item, Stroke) and item.role == "layout" and item.alpha == 0.6
        ]
        assert len(hover) == 1
        assert len(parent) == 1
        item = MovedItem(ok, RectValue(0, 0, 100, 30), Rect(20, 20, 100, 30))
        dragging = Moving("t", ok, (item,), FormPoint(0, 0), FormPoint(0, 0), True)
        hidden = build_frame(
            static,
            FrameInputs(
                session.document,
                SelectionState((ok,), ok),
                dragging,
                view,
                False,
                {},
                0,
                None,
                (),
                lambda text: len(text) * 6,
            ),
        )
        assert not any(isinstance(item, Stroke) and item.role == "hover" for item in hidden.items)
        assert not any(isinstance(item, Stroke) and item.role == "layout_faint" for item in hidden.items)


def test_a_free_widget_handle_resizes_on_the_grid() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        selection = SelectionState((ok,), ok)
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, selection, Idle(), _knobs(session, index, view, ok)),
        )
        handles = [target for _rect, target in frame.targets if isinstance(target, OnKnob)]
        assert {target.knob.pull for target in handles} == {"nw", "n", "ne", "e", "se", "s", "sw", "w"}
        east, _knob = _size_knob(frame, "e")
        start = _centre(east)
        _gesture, effects = _drag(_world(session, index, view, selection), frame, start, CanvasPoint(start.x + 13, start.y))
        commits = [effect for effect in effects if isinstance(effect, Commit)]
        # Stored x 10 and width 80: the east edge goes from 90 to 103 and lands on 104.
        assert [command.rect for commit in commits for command in commit.commands if isinstance(command, SetGeometry)] == [
            RectValue(10, 16, 94, 24)
        ]


def test_a_laid_out_widget_handle_writes_fixed() -> None:
    with _opened(LAID) as session:
        view = _view()
        form = _nid(session, "Form")
        layout = _nid(session, "verticalLayout")
        ok = _nid(session, "ok")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(layout, "layout", (9, 9, 382, 282), form),
                _entry(ok, "widget", (20, 20, 100, 30), layout),
            )
        )
        selection = SelectionState((ok,), ok)
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, selection, Idle(), _knobs(session, index, view, ok)),
        )
        assert {target.knob.pull for _rect, target in frame.targets if isinstance(target, OnKnob)} == {"e", "s", "se"}
        east, _knob = _size_knob(frame, "e")
        start = _centre(east)
        _gesture, effects = _drag(_world(session, index, view, selection), frame, start, CanvasPoint(start.x + 40, start.y))
        commit = next(effect for effect in effects if isinstance(effect, Commit))
        sizing = commit.commands[0]
        assert isinstance(sizing, ApplySizing) and sizing.owner == ok
        assert sizing.policy is not None and sizing.policy.hsizetype == "Fixed"
        assert commit.readout is not None and commit.readout.text.startswith("Fixed 140 × ")
        assert commit.merge is None


GRID = _ui(
    """
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0">
    <widget class="QPushButton" name="a"/>
   </item>
   <item row="1" column="1">
    <widget class="QPushButton" name="b"/>
   </item>
  </layout>
 </widget>
"""
)


@pytest.mark.parametrize("shift", [False, True])
def test_a_grid_widget_handle_spans_until_shift(shift: bool) -> None:
    with _opened(GRID) as session:
        view = _view()
        form = _nid(session, "Form")
        grid = _nid(session, "gridLayout")
        a = _nid(session, "a")
        b = _nid(session, "b")
        columns = (Track(9, 195), Track(201, 391))
        rows = (Track(9, 39), Track(45, 75))
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(grid, "layout", (0, 0, 400, 300), form),
                _entry(a, "widget", (columns[0].start, rows[0].start, 186, 30), grid),
                _entry(b, "widget", (columns[1].start, rows[1].start, 190, 30), grid),
            )
        )
        facts = LayoutFacts(grid, Rect(0, 0, 400, 300), (9, 9, 9, 9), columns, rows)
        selection = SelectionState((a,), a)
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, selection, Idle(), _knobs(session, index, view, a, (facts,))),
        )
        east, _knob = _size_knob(frame, "e")
        start = _centre(east)
        end = CanvasPoint(start.x + columns[1].end - columns[0].end, start.y)
        _gesture, effects = _drag(_world(session, index, view, selection), frame, start, end, Mods(shift=shift))
        commit = next(effect for effect in effects if isinstance(effect, Commit))
        written = commit.commands[0]
        if shift:
            assert isinstance(written, ApplySizing) and written.owner == a
        else:
            assert isinstance(written, SetLayoutCell) and written.colspan == 2
            assert commit.readout is not None and commit.readout.text == "Spans 2 columns"


def test_a_selected_layout_handle_writes_nothing() -> None:
    with _opened(LAID) as session:
        view = _view()
        form = _nid(session, "Form")
        layout = _nid(session, "verticalLayout")
        ok = _nid(session, "ok")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(layout, "layout", (9, 9, 382, 282), form),
                _entry(ok, "widget", (20, 20, 100, 30), layout),
            )
        )
        selection = SelectionState((layout,), layout)
        frame = build_frame(build_static(session.document, index, view), _inputs(session, view, selection, Idle()))
        handles = [(rect, target) for rect, target in frame.targets if isinstance(target, OnHandle)]
        assert {target.at for _rect, target in handles} == {"e", "s", "se"}
        start = _centre(handles[0][0])
        world = replace(_world(session, index, view, selection), frame=frame)
        pressed = step(Idle(), Press(start, PortPoint(0, 0), "left", Mods(), False), world)
        moved = step(pressed.gesture, Move(CanvasPoint(start.x + 30, start.y), PortPoint(30, 0), frozenset(("left",)), Mods()), world)
        assert any(isinstance(effect, Narrate) and effect.sentence for effect in moved.effects)
        released = step(moved.gesture, Release(CanvasPoint(start.x + 30, start.y), PortPoint(30, 0), "left", Mods()), world)
        assert not any(isinstance(effect, Commit) for effect in released.effects)


def test_handles_stay_a_fixed_screen_size_when_the_page_is_zoomed() -> None:
    with _opened(BARE) as session:
        view = _view(factor=2.0)
        index = _bare_index(session)
        ok = _nid(session, "ok")
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, SelectionState((ok,), ok), Idle(), _knobs(session, index, view, ok)),
        )
        handles = [item for item in frame.items if isinstance(item, Handle)]
        assert handles
        assert all(item.rect.width == 7 and item.rect.height == 7 for item in handles)
        selected = next(item for item in frame.items if isinstance(item, Stroke) and item.role == "select")
        assert selected.rect.width > 80


def test_no_layout_chip_does_not_cover_the_child() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        box = _nid(session, "box")
        ok = _nid(session, "ok")
        email = _nid(session, "email")
        static = build_static(session.document, index, view)
        assert static.unlaid == (box,)
        frame = build_frame(static, _inputs(session, view, SelectionState(), Idle()))
        chips = [item for item in frame.items if isinstance(item, Chip) and item.text == "No layout"]
        assert len(chips) == 1
        action = next(
            target.action
            for _rect, target in frame.targets
            if isinstance(target, OnChip) and isinstance(target.action, OpenLayoutPopover)
        )
        assert action.node == box
        blocked = [obstacle.rect for obstacle in static.content if obstacle.node in (ok, email)]
        assert blocked
        assert all(not chips[0].rect.intersects(rect) for rect in blocked)


def test_an_empty_root_layout_offers_the_drop_mark() -> None:
    with _opened(EMPTY) as session:
        view = _view()
        form = _nid(session, "Form")
        layout = _nid(session, "verticalLayout")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(layout, "layout", (9, 9, 382, 282), form),
            )
        )
        static = build_static(session.document, index, view)
        captions = [item for item in static.items if isinstance(item, Caption)]
        assert captions
        assert captions[0].lines[0] == "Drop a widget here"
        assert any(
            isinstance(target, OnSpace) and target.select == layout for _rect, target in static.targets
        )


def test_page_grabber_is_a_target_on_the_page_edge() -> None:
    with _opened(EMPTY) as session:
        view = _view()
        form = _nid(session, "Form")
        layout = _nid(session, "verticalLayout")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(layout, "layout", (9, 9, 382, 282), form),
            )
        )
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, SelectionState(), Idle()),
        )
        east = next(pair for pair in frame.targets if isinstance(pair[1], OnPageEdge) and pair[1].at == "e")
        hit = aim(
            CanvasPoint(east[0].x + east[0].width // 2, east[0].y + east[0].height // 2),
            frame,
            index,
            session.document,
            view,
        )
        assert isinstance(hit, OnPageEdge) and hit.at == "e"


def _segment_hits(x0: int, x1: int, y: int, rect: CanvasRect) -> bool:
    left = min(x0, x1) + 1
    right = max(x0, x1) - 1
    if right <= left:
        return False
    return left <= rect.x + rect.width and rect.x <= right and rect.y <= y <= rect.y + rect.height


def test_the_primary_chip_is_seated_and_its_leader_stays_horizontal() -> None:
    page = CanvasRect(0, 0, 400, 300)
    viewport = page.grown(240)
    target = CanvasRect(40, 80, 50, 24)
    sibling = Obstacle(NodeId(2), CanvasRect(120, 70, 80, 40))
    content = (
        Obstacle(NodeId(1), CanvasRect(10, 10, 60, 30)),
        sibling,
        Obstacle(NodeId(3), target),
    )
    request = ChipRequest("primary", target, CanvasSize(72, 18), LABEL_CORNERS, frozenset(), required=True)
    seats = place_chips((request,), content, (), page, viewport)
    assert len(seats) == 1
    seat = seats[0]
    if isinstance(seat, GutterSeat):
        assert seat.leader.start.y == seat.leader.end.y
        assert not _segment_hits(seat.leader.start.x, seat.leader.end.x, seat.leader.start.y, sibling.rect)


def test_a_packed_row_docks_the_chip_at_the_targets_x() -> None:
    """No clear seat and no clear leader: the chip goes to the dock, never away."""
    page = CanvasRect(200, 0, 400, 300)
    viewport = CanvasRect(0, 0, 900, 400)
    dock = CanvasRect(200, 0, 400, 22)
    target = CanvasRect(260, 80, 16, 14)
    neighbours = (
        Obstacle(NodeId(1), CanvasRect(260, 60, 16, 16)),
        Obstacle(NodeId(2), CanvasRect(230, 80, 20, 14)),
        Obstacle(NodeId(3), CanvasRect(260, 100, 16, 16)),
        Obstacle(NodeId(4), CanvasRect(290, 80, 20, 14)),
        Obstacle(NodeId(5), target),
    )
    request = ChipRequest("primary", target, CanvasSize(40, 18), LABEL_CORNERS, frozenset(), required=True)
    (seat,) = place_chips((request,), neighbours, (dock,), page, viewport, dock)
    assert isinstance(seat, DockSeat)
    assert seat.rect.x == target.x
    assert seat.rect.y >= dock.y and seat.rect.y + seat.rect.height <= dock.y + dock.height
    # The leader would cross the neighbour above, so there is none.
    assert seat.leader is None


def test_arrow_keys_skip_ancestors_and_widgets_that_are_not_past_the_edge() -> None:
    text = _ui(
        """
 <widget class="QWidget" name="Form">
  <widget class="QGroupBox" name="customer">
   <widget class="QLineEdit" name="emailEdit"/>
   <widget class="QLineEdit" name="addressEdit"/>
  </widget>
  <widget class="QGroupBox" name="side"/>
  <widget class="QPushButton" name="saveButton"/>
 </widget>
"""
    )
    with _opened(text) as session:
        form = _nid(session, "Form")
        customer = _nid(session, "customer")
        email = _nid(session, "emailEdit")
        address = _nid(session, "addressEdit")
        side = _nid(session, "side")
        save = _nid(session, "saveButton")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 300), None),
                _entry(customer, "widget", (0, 0, 300, 200), form),
                _entry(email, "widget", (20, 20, 80, 24), customer),
                _entry(address, "widget", (20, 60, 80, 24), customer),
                _entry(side, "widget", (50, 0, 200, 40), form),
                _entry(save, "widget", (120, 60, 40, 24), form),
            )
        )
        assert nearest_in_direction(session.document, index, email, "down") == address
        assert nearest_in_direction(session.document, index, address, "right") == save


def test_left_stays_on_the_row_when_the_next_label_is_wider() -> None:
    text = _ui(
        """
 <widget class="QWidget" name="Form">
  <widget class="QLabel" name="emailLabel"/>
  <widget class="QLineEdit" name="emailEdit"/>
  <widget class="QLabel" name="addressLabel"/>
 </widget>
"""
    )
    with _opened(text) as session:
        form = _nid(session, "Form")
        label = _nid(session, "emailLabel")
        edit = _nid(session, "emailEdit")
        wider = _nid(session, "addressLabel")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 400, 200), None),
                _entry(label, "widget", (9, 40, 40, 20), form),
                _entry(edit, "widget", (80, 40, 200, 20), form),
                _entry(wider, "widget", (9, 66, 65, 20), form),
            )
        )
        assert nearest_in_direction(session.document, index, edit, "left") == label
        assert nearest_in_direction(session.document, index, label, "down") == wider


def test_down_prefers_the_wide_widget_straight_below() -> None:
    """Cross-axis distance is the edge gap, so a full-width table below wins."""
    text = _ui(
        """
 <widget class="QWidget" name="Form">
  <widget class="QCheckBox" name="paidCheck"/>
  <widget class="QTableWidget" name="linesTable"/>
  <widget class="QLabel" name="subtotalLabel"/>
 </widget>
"""
    )
    with _opened(text) as session:
        form = _nid(session, "Form")
        paid = _nid(session, "paidCheck")
        table = _nid(session, "linesTable")
        subtotal = _nid(session, "subtotalLabel")
        index = _index(
            (
                _entry(form, "widget", (0, 0, 600, 300), None),
                _entry(paid, "widget", (16, 56, 120, 22), form),
                _entry(table, "widget", (0, 100, 600, 100), form),
                _entry(subtotal, "widget", (0, 210, 60, 20), form),
            )
        )
        assert nearest_in_direction(session.document, index, paid, "down") == table


def test_empty_space_in_a_bare_group_starts_a_band() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        box = _nid(session, "box")
        ok = _nid(session, "ok")
        email = _nid(session, "email")
        at = _canvas(view, 180, 50)
        hit = aim(at, _blank_frame(index, view, SelectionState()), index, session.document, view)
        assert isinstance(hit, OnSpace)
        assert hit.band_owner == box
        world = _world(session, index, view)
        pressed = step(Idle(), Press(at, PortPoint(0, 0), "left", Mods(), False), world)
        assert isinstance(pressed.gesture, Pressed)
        assert isinstance(pressed.gesture.on_drag, Banding)
        moved = step(
            pressed.gesture,
            Move(_canvas(view, 30, 100), PortPoint(80, 80), frozenset(("left",)), Mods()),
            world,
        )
        assert isinstance(moved.gesture, Banding)
        assert set(band_hits(moved.gesture)) == {ok, email}


def test_the_selected_form_does_not_add_an_overlay_chip() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        form = _nid(session, "Form")
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, SelectionState((form,), form), Idle()),
        )
        assert not any(isinstance(item, Chip) and item.role == "select" for item in frame.items)


def test_importing_canvas_core_does_not_import_qt() -> None:
    script = (
        "import sys\n"
        "import app.features.form_builder.qtside.canvas.core.gesture\n"
        "import app.features.form_builder.qtside.canvas.core.overlay\n"
        "banned = [\n"
        "    name for name in sys.modules\n"
        "    if name == 'app.qt' or name.startswith('app.qt.')\n"
        "    or name.startswith('PySide') or name.startswith('shiboken')\n"
        "]\n"
        "if banned:\n"
        "    raise SystemExit('imported ' + ', '.join(sorted(banned)))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
