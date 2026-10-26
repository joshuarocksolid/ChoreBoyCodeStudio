"""Knob sites on the overlay and the gestures that turn them. Qt-free."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from typing import Iterator, List, Optional, Tuple

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.catalog_ext.sizing import ApplySizing
from app.features.form_builder.engine.commands.live import live_props
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.direct import (
    KnobKey,
    LayoutFacts,
    PrimaryFacts,
    Readout,
    SplitterFacts,
    Survey,
    Track,
    knob_set,
    survey_scope,
)
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.qtside.canvas.core.frame import (
    Chip,
    Fill,
    FocusShare,
    Glyph,
    OnChip,
    OnHandle,
    OnKnob,
    OnPageEdge,
    OverlayFrame,
    Stroke,
    Target,
)
from app.features.form_builder.qtside.canvas.core.gesture import (
    Commit,
    EndPreview,
    Gesture,
    Idle,
    Key,
    Mods,
    Move,
    Press,
    Preview,
    Release,
    RunChipAction,
    Select,
    Step,
    World,
    step,
)
from app.features.form_builder.qtside.canvas.core.overlay import FrameInputs, build_frame, build_static
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, PortPoint, Size, ViewMap

pytestmark = pytest.mark.unit

FORM = Rect(0, 0, 400, 300)
MARGINS = (9, 9, 9, 9)
COLUMN = Track(9, 391)
OK = Rect(9, 9, 382, 30)
CANCEL = Rect(9, 45, 382, 30)
SPLIT = Rect(9, 81, 382, 210)
LEFT = Rect(9, 81, 188, 210)
HANDLE = Rect(197, 81, 6, 210)
RIGHT = Rect(203, 81, 188, 210)


def _stack(spacing: Optional[int] = None, stretch: str = "") -> str:
    attributes = ' stretch="%s"' % stretch if stretch else ""
    stored = "<property name=\"spacing\"><number>%d</number></property>" % spacing if spacing is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
        ' <widget class="QWidget" name="Form">\n'
        '  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>\n'
        '  <layout class="QVBoxLayout" name="verticalLayout"%s>%s\n'
        '   <item><widget class="QPushButton" name="ok"/></item>\n'
        '   <item><widget class="QPushButton" name="cancel"/></item>\n'
        "   <item>\n"
        '    <widget class="QSplitter" name="split">\n'
        '     <property name="orientation"><enum>Qt::Horizontal</enum></property>\n'
        '     <widget class="QTextEdit" name="left"/>\n'
        '     <widget class="QTextEdit" name="right"/>\n'
        "    </widget>\n"
        "   </item>\n"
        "  </layout>\n"
        " </widget>\n</ui>\n"
    ) % (attributes, stored)


class _Source:
    def __init__(self, rows: Tuple[GeoEntry, ...]) -> None:
        self.rows = rows

    def settle(self) -> None:
        return None

    def entries(self) -> Tuple[GeoEntry, ...]:
        return self.rows


@contextmanager
def _opened(text: str) -> Iterator[FormSession]:
    session = FormSession.open(
        text,
        path="/tmp/cbcs-m33b-knobs.ui",
        scope=FormScope(kind="external", ui_path="/tmp/cbcs-m33b-knobs.ui"),
    )
    try:
        yield session
    finally:
        session.dispose()


def _nid(session: FormSession, name: str) -> NodeId:
    found = session.document.by_name(name)
    assert len(found) == 1
    return found[0]


def _index(session: FormSession) -> HitIndex:
    form = _nid(session, "Form")
    layout = _nid(session, "verticalLayout")
    split = _nid(session, "split")
    rows = (
        GeoEntry(form, "widget", FORM, None, True, 0),
        GeoEntry(layout, "layout", FORM, form, True, -1),
        GeoEntry(_nid(session, "ok"), "widget", OK, layout, True, 0),
        GeoEntry(_nid(session, "cancel"), "widget", CANCEL, layout, True, 1),
        GeoEntry(split, "widget", SPLIT, layout, True, 2),
        GeoEntry(_nid(session, "left"), "widget", LEFT, split, True, 0),
        GeoEntry(_nid(session, "right"), "widget", RIGHT, split, True, 1),
    )
    index = HitIndex(_Source(rows))
    index.ensure_fresh()
    return index


def _view(factor: float = 1.0) -> ViewMap:
    return ViewMap(factor, CanvasPoint(96, 64), Size(400, 300))


def _survey(session: FormSession, index: HitIndex, primary: NodeId) -> Survey:
    """What the live surveyor measures for this form."""
    document = session.document
    layout = _nid(session, "verticalLayout")
    split = _nid(session, "split")
    scope = survey_scope(document, primary, (split,))
    rows = (
        Track(OK.y, OK.y + OK.height, _nid(session, "ok")),
        Track(CANCEL.y, CANCEL.y + CANCEL.height, _nid(session, "cancel")),
        Track(SPLIT.y, SPLIT.y + SPLIT.height, split),
    )
    layouts = tuple(LayoutFacts(layout, FORM, MARGINS, (COLUMN,), rows) for found in scope.layouts if found == layout)
    splitter = SplitterFacts(split, "h", SPLIT, SPLIT.width, HANDLE.width, (HANDLE,), (LEFT, RIGHT), (188, 188), (20, 20))
    rect = index.rect_of(primary)
    widget = isinstance(document.get(primary), WidgetNode) and primary != document.root.id
    facts = PrimaryFacts(primary, rect, ("Minimum", "Fixed")) if widget and rect is not None else None
    return Survey(index.epoch, scope, facts, layouts, (splitter,))


def _frame(
    session: FormSession,
    index: HitIndex,
    view: ViewMap,
    selection: SelectionState,
    gesture: Gesture = Idle(),
    readout: Optional[Readout] = None,
) -> OverlayFrame:
    document = session.document
    primary = selection.current if selection.current is not None else document.root.id
    knobs = knob_set(_survey(session, index, primary), document, view.factor)
    inputs = FrameInputs(
        document,
        selection,
        gesture,
        view,
        False,
        {},
        0,
        None,
        (),
        lambda text: len(text) * 6,
        knobs=knobs,
        readout=readout,
    )
    return build_frame(build_static(document, index, view), inputs)


def _world(session: FormSession, index: HitIndex, view: ViewMap, selection: SelectionState, frame: OverlayFrame) -> World:
    return World(session.document, selection, index, view, frame, Size(80, 60), "token")


def _knob_rect(frame: OverlayFrame, key: KnobKey) -> CanvasRect:
    for rect, target in frame.targets:
        if isinstance(target, OnKnob) and target.knob.key == key:
            return rect
    raise AssertionError(key)


def _centre(rect: CanvasRect) -> CanvasPoint:
    return CanvasPoint(rect.x + rect.width // 2, rect.y + rect.height // 2)


def _on_first_gap(frame: OverlayFrame, view: ViewMap, layout: NodeId) -> CanvasPoint:
    """Mid-gap, clear of ``ok``'s south handle, which ranks above the gap."""
    at = _at(view, OK.x + 40, (OK.y + OK.height + CANCEL.y) // 2)
    assert _knob_rect(frame, ("gap", layout, "v0")).contains(at)
    return at


def _at(view: ViewMap, x: int, y: int) -> CanvasPoint:
    return CanvasPoint(view.page_origin.x + x, view.page_origin.y + y)


def _press(world: World, at: CanvasPoint, double: bool = False) -> Step:
    return step(Idle(), Press(at, PortPoint(0, 0), "left", Mods(), double), world)


def _move(world: World, gesture: Gesture, start: CanvasPoint, dx: int, dy: int) -> Step:
    end = CanvasPoint(start.x + dx, start.y + dy)
    return step(gesture, Move(end, PortPoint(dx, dy), frozenset(("left",)), Mods()), world)


_RANK = {"chip": 0, "pill": 1, "size": 2, "grip": 3, "gap": 4, "margin": 5, "inert": 6, "body": 7}


def _kind(target: Target) -> str:
    if isinstance(target, OnChip):
        return "chip"
    if isinstance(target, OnPageEdge):
        return "pill"
    if isinstance(target, OnKnob):
        return target.knob.key[0]
    if isinstance(target, OnHandle):
        return "inert"
    return "body"


@pytest.mark.parametrize(
    ("selected", "expected"),
    [
        ("ok", {"pill", "size", "grip", "gap", "margin"}),
        ("verticalLayout", {"pill", "grip", "gap", "margin", "inert"}),
    ],
)
def test_knob_targets_follow_the_hit_order(selected: str, expected: set) -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        node = _nid(session, selected)
        frame = _frame(session, index, view, SelectionState((node,), node))
        kinds = [_kind(target) for _rect, target in frame.targets]
        assert expected <= set(kinds)
        ranks = [_RANK[kind] for kind in kinds]
        assert ranks == sorted(ranks)


@pytest.mark.parametrize("factor", [0.5, 1.0, 2.0])
def test_gap_bars_keep_their_screen_size_at_every_zoom(factor: float) -> None:
    with _opened(_stack()) as session:
        view = _view(factor)
        index = _index(session)
        ok = _nid(session, "ok")
        frame = _frame(session, index, view, SelectionState((ok,), ok))
        bars = [item.rect for item in frame.items if isinstance(item, Fill) and item.role == "gap"]
        hits = [rect for rect, target in frame.targets if isinstance(target, OnKnob) and target.knob.key[0] == "gap"]
        assert len(bars) == 2 and len(hits) == 2
        assert all(min(rect.width, rect.height) == 2 for rect in bars)
        assert all(min(rect.width, rect.height) >= 12 for rect in hits)


def test_a_hovered_grip_draws_its_glyph() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        grip: KnobKey = ("grip", _nid(session, "split"), "0")
        hovered = _frame(session, index, view, SelectionState(), Idle(None, grip))
        resting = _frame(session, index, view, SelectionState())
        assert [item for item in hovered.items if isinstance(item, Glyph) and item.name == "grip"]
        assert not [item for item in resting.items if isinstance(item, Glyph) and item.name == "grip"]


def test_root_layout_margin_numbers_sit_in_the_gutter() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        layout = _nid(session, "verticalLayout")
        frame = _frame(session, index, view, SelectionState((layout,), layout))
        numbers = [item.rect for item in frame.items if isinstance(item, Chip) and item.text == str(MARGINS[0])]
        ticks = [item for item in frame.items if isinstance(item, Stroke) and item.caps and item.role == "layout"]
        assert len(numbers) == 4 and len(ticks) == 4
        assert not any(rect.intersects(view.page_rect()) for rect in numbers)


def test_a_share_chip_click_asks_for_the_share_spin() -> None:
    with _opened(_stack(stretch="1,2,0")) as session:
        view = _view()
        index = _index(session)
        layout = _nid(session, "verticalLayout")
        selection = SelectionState((layout,), layout)
        frame = _frame(session, index, view, selection)
        chips = [
            (rect, target.action)
            for rect, target in frame.targets
            if isinstance(target, OnChip) and isinstance(target.action, FocusShare)
        ]
        assert chips
        assert {action.node for _rect, action in chips} <= {_nid(session, "ok"), _nid(session, "cancel")}
        rect, action = chips[0]
        world = _world(session, index, view, selection, frame)
        pressed = _press(world, _centre(rect))
        released = step(pressed.gesture, Release(_centre(rect), PortPoint(0, 0), "left", Mods()), world)
        assert RunChipAction(action) in released.effects
        assert action.axis == "v"


def test_a_gap_drag_previews_exactly_what_it_commits() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        layout = _nid(session, "verticalLayout")
        selection = SelectionState((ok,), ok)
        frame = _frame(session, index, view, selection)
        world = _world(session, index, view, selection, frame)
        start = _on_first_gap(frame, view, layout)
        pressed = _press(world, start)
        moved = _move(world, pressed.gesture, start, 0, 10)
        preview = next(effect for effect in moved.effects if isinstance(effect, Preview))
        released = step(moved.gesture, Release(CanvasPoint(start.x, start.y + 10), PortPoint(0, 10), "left", Mods()), world)
        commits = [effect for effect in released.effects if isinstance(effect, Commit)]
        gap = CANCEL.y - (OK.y + OK.height)
        assert len(commits) == 1
        assert commits[0].commands == (SetProperty(layout, "spacing", NumberValue(gap + 10)),)
        assert preview.props == live_props(commits[0].commands)
        assert commits[0].merge is None
        assert EndPreview() in released.effects


def test_a_gap_drag_reads_its_number_beside_the_gap() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        layout = _nid(session, "verticalLayout")
        selection = SelectionState((ok,), ok)
        frame = _frame(session, index, view, selection)
        world = _world(session, index, view, selection, frame)
        start = _on_first_gap(frame, view, layout)
        moved = _move(world, _press(world, start).gesture, start, 0, 10)
        dragging = _frame(session, index, view, selection, moved.gesture)
        gap = CANCEL.y - (OK.y + OK.height)
        assert [item for item in dragging.items if isinstance(item, Chip) and item.text == "Spacing %d px" % (gap + 10)]


def test_escape_ends_a_knob_drag_without_a_commit() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        layout = _nid(session, "verticalLayout")
        selection = SelectionState((ok,), ok)
        frame = _frame(session, index, view, selection)
        world = _world(session, index, view, selection, frame)
        start = _centre(_knob_rect(frame, ("margin", layout, "top")))
        moved = _move(world, _press(world, start).gesture, start, 0, 6)
        escaped = step(moved.gesture, Key("escape", Mods()), world)
        assert isinstance(escaped.gesture, Idle)
        assert EndPreview() in escaped.effects
        assert not any(isinstance(effect, Commit) for effect in escaped.effects)


def test_a_click_on_a_grip_selects_the_pane_beneath() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        left = _nid(session, "left")
        frame = _frame(session, index, view, SelectionState())
        world = _world(session, index, view, SelectionState(), frame)
        grip = _knob_rect(frame, ("grip", _nid(session, "split"), "0"))
        # Inside the widened grip, one pixel left of the handle, over the left pane.
        at = _at(view, HANDLE.x - 1, HANDLE.y + HANDLE.height // 2)
        assert grip.contains(at)
        pressed = _press(world, at)
        released = step(pressed.gesture, Release(at, PortPoint(0, 0), "left", Mods()), world)
        assert Select((left,), left) in released.effects


def test_a_double_click_on_a_stored_gap_deletes_the_spacing() -> None:
    with _opened(_stack(spacing=6)) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        layout = _nid(session, "verticalLayout")
        selection = SelectionState((ok,), ok)
        frame = _frame(session, index, view, selection)
        world = _world(session, index, view, selection, frame)
        result = _press(world, _centre(_knob_rect(frame, ("gap", layout, "v1"))), double=True)
        commits = [effect for effect in result.effects if isinstance(effect, Commit)]
        assert [commit.commands for commit in commits] == [(SetProperty(layout, "spacing", None),)]


@pytest.mark.parametrize(("shift", "pixels"), [(True, 8), (False, 1)])
def test_ctrl_arrow_turns_the_primary_east_handle(shift: bool, pixels: int) -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        selection = SelectionState((ok,), ok)
        frame = _frame(session, index, view, selection)
        world = _world(session, index, view, selection, frame)
        result = step(Idle(), Key("right", Mods(shift=shift, ctrl=True)), world)
        commits: List[Commit] = [effect for effect in result.effects if isinstance(effect, Commit)]
        assert len(commits) == 1
        sizing = commits[0].commands[0]
        assert isinstance(sizing, ApplySizing) and sizing.owner == ok
        assert commits[0].readout is not None
        assert commits[0].readout.text.startswith("Fixed %d × " % (OK.width + pixels))
        assert commits[0].merge == "resize:%s" % ok


def test_ctrl_arrow_resizes_when_no_handle_is_drawn() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        selection = SelectionState((ok,), ok)
        frame = replace(_frame(session, index, view, selection), targets=())
        world = _world(session, index, view, selection, frame)
        result = step(Idle(), Key("right", Mods(ctrl=True)), world)
        commits: List[Commit] = [effect for effect in result.effects if isinstance(effect, Commit)]
        assert len(commits) == 1
        assert commits[0].readout is not None
        assert commits[0].readout.text.startswith("Fixed %d × " % (OK.width + 1))
        held = step(Idle(), Key("right", Mods(ctrl=True, shift=True, alt=True)), world)
        assert not any(
            isinstance(effect, Commit) and any(isinstance(command, ApplySizing) for command in effect.commands)
            for effect in held.effects
        )


def test_a_direct_child_draws_gap_bars_and_margin_bands_as_a_hint() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        layout = _nid(session, "verticalLayout")
        form = _nid(session, "Form")
        child = _frame(session, index, view, SelectionState((ok,), ok))
        chosen = _frame(session, index, view, SelectionState((layout,), layout))
        container = _frame(session, index, view, SelectionState((form,), form))

        def _bars(frame: OverlayFrame) -> List[Fill]:
            return [item for item in frame.items if isinstance(item, Fill) and item.role in ("gap", "gap_fill")]

        faint = _bars(child)
        assert faint
        assert all(item.alpha == 0.35 for item in faint)
        assert all(item.alpha == 1.0 for item in _bars(chosen))
        assert all(item.alpha == 1.0 for item in _bars(container))
        assert any(isinstance(target, OnKnob) and target.knob.key[0] == "gap" for _rect, target in child.targets)
        assert not any(isinstance(item, Chip) and item.text.endswith(" px") for item in child.items)


def test_a_landed_size_readout_replaces_the_selection_chip_text() -> None:
    with _opened(_stack()) as session:
        view = _view()
        index = _index(session)
        ok = _nid(session, "ok")
        selection = SelectionState((ok,), ok)
        landed = Readout(("size", ok, "e"), "Fixed 240 × Hug", OK)
        frame = _frame(session, index, view, selection, readout=landed)
        resting = _frame(session, index, view, selection, readout=replace(landed, key=("size", _nid(session, "cancel"), "e")))
        assert [item for item in frame.items if isinstance(item, Chip) and item.text == landed.text]
        assert not [item for item in resting.items if isinstance(item, Chip) and item.text == landed.text]
