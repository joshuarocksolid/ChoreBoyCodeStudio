"""Qt-free canvas core. Gesture, snap, chips, and the overlay frame."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Iterator, Optional, Sequence, Tuple
from contextlib import contextmanager

import pytest

from app.features.form_builder.engine.commands.catalog import SetGeometry
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.chips import (
    LABEL_CORNERS,
    ChipRequest,
    GutterSeat,
    Obstacle,
    place_chips,
)
from app.features.form_builder.qtside.canvas.core.frame import (
    Caption,
    Chip,
    FrameBasis,
    Handle,
    OnChip,
    OnHandle,
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
    Idle,
    Inert,
    Key,
    Mods,
    MovedItem,
    Move,
    Moving,
    PageResizing,
    Press,
    Pressed,
    Release,
    Resizing,
    Reveal,
    Select,
    Toggle,
    World,
    aim,
    previewing,
    step,
)
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
    gesture: Idle,
) -> FrameInputs:
    return FrameInputs(
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
    assert zoom_factor(Fit(), Size(1000, 1000), CanvasSize(300, 300)) == 0.5


def test_layout_page_centres_inside_the_gutters() -> None:
    centred = layout_page(Size(100, 80), 1.0, CanvasSize(400, 400), 0)
    assert centred.page_origin == CanvasPoint(150, 160)
    parked = layout_page(Size(400, 300), 1.0, CanvasSize(200, 200), 0)
    assert parked.page_origin == CanvasPoint(96, 64)


def test_a_blocked_chip_sits_in_the_gutter_and_still_gets_a_seat() -> None:
    page = CanvasRect(0, 0, 200, 100)
    target = CanvasRect(10, 10, 40, 20)
    blocker = Obstacle(NodeId(1), page)
    requests = tuple(
        ChipRequest(index, target, CanvasSize(30, 18), LABEL_CORNERS, frozenset())
        for index in range(8)
    )
    seats = place_chips(requests, (blocker,), (), page)
    assert len(seats) == 8
    for seat in seats:
        assert isinstance(seat, GutterSeat)
        assert seat.rect.x + seat.rect.width <= page.x or seat.rect.x >= page.x + page.width
        assert not seat.rect.intersects(page)


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


def test_dragging_a_laid_out_widget_writes_nothing() -> None:
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
        assert isinstance(dragged.gesture, Inert)
        released = step(
            dragged.gesture,
            Release(_canvas(view, 50, 30), PortPoint(20, 0), "left", Mods()),
            world,
        )
        assert not any(isinstance(effect, Commit) for effect in released.effects)


def test_every_drag_state_consumes_release_without_an_empty_commit() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        form = _nid(session, "Form")
        item = MovedItem(ok, RectValue(8, 16, 80, 24), Rect(30, 46, 80, 24))
        origin = FormPoint(0, 0)
        states = (
            Moving("t", ok, (item,), origin, origin, True),
            Resizing("t", item, "e", origin, origin, True),
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
        assert isinstance(parent, OnWidget) and parent.node == box
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


def test_free_handles_write_and_laid_out_handles_do_not() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        selection = SelectionState((ok,), ok)
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, selection, Idle()),
        )
        handles = [target for _rect, target in frame.targets if isinstance(target, OnHandle)]
        assert len(handles) == 8
        assert all(target.writes for target in handles)
        east = next(pair for pair in frame.targets if isinstance(pair[1], OnHandle) and pair[1].at == "e")
        hit = aim(
            CanvasPoint(east[0].x + east[0].width // 2, east[0].y + east[0].height // 2),
            frame,
            index,
            session.document,
            view,
        )
        assert isinstance(hit, OnHandle) and hit.writes and hit.at == "e"

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
            _inputs(session, view, selection, Idle()),
        )
        handles = [target for _rect, target in frame.targets if isinstance(target, OnHandle)]
        assert {target.at for target in handles} == {"e", "s", "se"}
        assert all(not target.writes for target in handles)


def test_handles_stay_a_fixed_screen_size_when_the_page_is_zoomed() -> None:
    with _opened(BARE) as session:
        view = _view(factor=2.0)
        index = _bare_index(session)
        ok = _nid(session, "ok")
        frame = build_frame(
            build_static(session.document, index, view),
            _inputs(session, view, SelectionState((ok,), ok), Idle()),
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
