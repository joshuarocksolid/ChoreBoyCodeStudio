# pyright: reportAttributeAccessIssue=false
"""Direct manipulation on live widgets. Preview mutates Qt, release commits once."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Tuple

import pytest

from app.qt.QtCore import QEvent, QPoint, QPointF, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QMouseEvent  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QFormLayout, QGridLayout, QSplitter, QWidget
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.storage import splitter_sizes
from app.features.form_builder.engine.query.direct import KnobKey, survey_scope
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.controller import READOUT_LINGER_MS
from app.features.form_builder.qtside.canvas.core.frame import Chip, FocusShare, OnChip, OnKnob
from app.features.form_builder.qtside.canvas.core.gesture import ZoomAsked
from app.features.form_builder.qtside.canvas.core.space import CanvasRect, ZoomTo
from app.features.form_builder.qtside.canvas.geometry import LiveGeometrySource, survey_live
from app.features.form_builder.qtside.realize.api import Realizer
from tests.form_builder.qtside.support import form, opened
from tests.unit.features.form_builder.test_workbench import _open as _open_surface

pytestmark = pytest.mark.usefixtures("qapp")

STACK = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="ok"><property name="text"><string>OK</string></property></widget></item>
   <item><widget class="QPushButton" name="cancel"><property name="text"><string>Cancel</string></property></widget></item>
   <item><widget class="QPushButton" name="gone"><property name="text"><string>Gone</string></property></widget></item>
   <item>
    <widget class="QSplitter" name="split">
     <property name="orientation"><enum>Qt::Horizontal</enum></property>
     <widget class="QTextEdit" name="left"/>
     <widget class="QTextEdit" name="right"/>
    </widget>
   </item>
  </layout>
""",
)

MARGIN_BOX = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <property name="margin"><number>5</number></property>
   <item><widget class="QPushButton" name="a"><property name="text"><string>A</string></property></widget></item>
   <item><widget class="QPushButton" name="b"><property name="text"><string>B</string></property></widget></item>
   <item><widget class="QPushButton" name="c"><property name="text"><string>C</string></property></widget></item>
  </layout>
""",
)

SPACED_GRID = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QGridLayout" name="gridLayout">
   <property name="spacing"><number>27</number></property>
   <item row="0" column="0"><widget class="QPushButton" name="a"><property name="text"><string>A</string></property></widget></item>
   <item row="0" column="1"><widget class="QPushButton" name="b"><property name="text"><string>B</string></property></widget></item>
   <item row="1" column="0"><widget class="QPushButton" name="c"><property name="text"><string>C</string></property></widget></item>
  </layout>
""",
)

_FIXED = (
    '<property name="minimumSize"><size><width>80</width><height>24</height></size></property>'
    '<property name="maximumSize"><size><width>80</width><height>24</height></size></property>'
)

FIXED_BOX = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="a">%s</widget></item>
   <item><widget class="QPushButton" name="b">%s</widget></item>
   <item><widget class="QPushButton" name="c">%s</widget></item>
  </layout>
"""
    % (_FIXED, _FIXED, _FIXED),
)

_SHARE = (
    '<property name="sizePolicy"><sizepolicy hsizetype="Expanding" vsizetype="Expanding">'
    "<horstretch>%d</horstretch><verstretch>0</verstretch></sizepolicy></property>"
)

SHARES = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QSplitter" name="split">
     <property name="orientation"><enum>Qt::Horizontal</enum></property>
     <widget class="QTextEdit" name="left">%s</widget>
     <widget class="QTextEdit" name="right">%s</widget>
    </widget>
   </item>
  </layout>
"""
    % (_SHARE % 1, _SHARE % 3),
)

GRID = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QGridLayout" name="gridLayout" columnstretch="1,2">
   <item row="0" column="0"><widget class="QPushButton" name="a"><property name="text"><string>A</string></property></widget></item>
   <item row="0" column="1"><widget class="QPushButton" name="b"><property name="text"><string>B</string></property></widget></item>
   <item row="1" column="1"><widget class="QPushButton" name="c"><property name="text"><string>C</string></property></widget></item>
  </layout>
""",
)

SPAN = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0"><widget class="QPushButton" name="a"><property name="text"><string>A</string></property></widget></item>
   <item row="1" column="0"><widget class="QPushButton" name="b"><property name="text"><string>B</string></property></widget></item>
   <item row="1" column="1"><widget class="QPushButton" name="c"><property name="text"><string>C</string></property></widget></item>
  </layout>
""",
)

ROWS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="name"/></item>
   <item row="1" column="0"><widget class="QLabel" name="goneLabel"><property name="text"><string>Gone</string></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="gone"/></item>
   <item row="2" column="0" colspan="2"><widget class="QCheckBox" name="wide"><property name="text"><string>A check box wider than any label</string></property></widget></item>
   <item row="3" column="0"><widget class="QLabel" name="cityLabel"><property name="text"><string>Home city</string></property></widget></item>
   <item row="3" column="1"><widget class="QLineEdit" name="city"/></item>
  </layout>
""",
)

PANES = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="%s" name="outer">
   <item>
    <widget class="QSplitter" name="split">
     <property name="orientation"><enum>%s</enum></property>
     <widget class="QListWidget" name="first"/>
     <widget class="QListWidget" name="second"/>
    </widget>
   </item>
  </layout>
""",
)


class _Host:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


@contextmanager
def _shown(text: str) -> Iterator[Tuple[FormSession, Realizer, FormCanvas]]:
    with opened(text) as (session, realizer):
        parent = QWidget()
        parent.resize(960, 720)
        canvas = FormCanvas(session, realizer, _Host(), parent)  # type: ignore[arg-type]
        canvas.resize(960, 720)
        parent.show()
        _flush()
        canvas.send(ZoomAsked(ZoomTo(1.0)))
        canvas.setFocus()
        _flush()
        try:
            yield session, realizer, canvas
        finally:
            canvas.dispose()
            parent.deleteLater()


def test_the_live_survey_skips_hidden_box_items() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        document = session.document
        gone = realizer.widget_for(_id(session, "gone"))
        assert gone is not None
        gone.hide()
        _flush()
        index = _fresh_index(realizer)
        layout = _id(session, "verticalLayout")
        ok = _id(session, "ok")
        survey = survey_live(realizer, index, document, survey_scope(document, ok, ()))
        facts = next(found for found in survey.layouts if found.layout == layout)
        expected = tuple(_id(session, name) for name in ("ok", "cancel", "split"))
        assert tuple(track.item for track in facts.rows) == expected
        for track in facts.rows:
            assert track.item is not None
            rect = index.rect_of(track.item)
            assert rect is not None and (track.start, track.end) == (rect.y, rect.y + rect.height)
        qlayout = realizer.layout_for(layout)
        assert qlayout is not None
        gaps = {after.start - before.end for before, after in zip(facts.rows, facts.rows[1:])}
        assert gaps == {qlayout.spacing()}


def test_the_live_survey_measures_grid_columns_from_their_cells() -> None:
    with _shown(GRID) as (session, realizer, canvas):
        document = session.document
        index = _fresh_index(realizer)
        grid = _id(session, "gridLayout")
        a = _id(session, "a")
        survey = survey_live(realizer, index, document, survey_scope(document, a, ()))
        facts = next(found for found in survey.layouts if found.layout == grid)
        for track, name in zip(facts.columns, ("a", "b")):
            rect = index.rect_of(_id(session, name))
            assert rect is not None and (track.start, track.end) == (rect.x, rect.x + rect.width)
        qlayout = realizer.layout_for(grid)
        assert qlayout is not None
        assert facts.columns[1].start - facts.columns[0].end == qlayout.horizontalSpacing()


def test_the_live_survey_gaps_a_form_by_its_spacing_past_hidden_rows_and_spanning_items() -> None:
    with _shown(ROWS) as (session, realizer, canvas):
        for name in ("goneLabel", "gone"):
            widget = realizer.widget_for(_id(session, name))
            assert widget is not None
            widget.hide()
        _flush()
        document = session.document
        index = _fresh_index(realizer)
        layout = _id(session, "formLayout")
        survey = survey_live(realizer, index, document, survey_scope(document, _id(session, "name"), ()))
        facts = next(found for found in survey.layouts if found.layout == layout)
        qlayout = realizer.layout_for(layout)
        assert isinstance(qlayout, QFormLayout)
        assert len(facts.columns) == 2 and len(facts.rows) == 3
        assert facts.columns[1].start - facts.columns[0].end == qlayout.horizontalSpacing()
        gaps = {after.start - before.end for before, after in zip(facts.rows, facts.rows[1:])}
        assert gaps == {qlayout.verticalSpacing()}


def test_the_live_survey_measures_splitter_panes() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        document = session.document
        index = _fresh_index(realizer)
        split = _id(session, "split")
        survey = survey_live(realizer, index, document, survey_scope(document, None, (split,)))
        facts = survey.splitters[0]
        left, right = (index.rect_of(_id(session, name)) for name in ("left", "right"))
        assert left is not None and right is not None
        assert facts.panes == (left, right)
        handle = facts.handles[0]
        assert handle.x == left.x + left.width and handle.width == facts.handle_width
        assert sum(facts.sizes) + facts.handle_width == facts.inner


def test_a_gap_drag_is_one_undo_on_release() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        layout = _id(session, "verticalLayout")
        qlayout = realizer.layout_for(layout)
        assert qlayout is not None
        before = qlayout.spacing()
        _click(canvas, "ok")
        start = _gap_point(canvas, ("gap", layout, "v0"))
        _press(canvas, start)
        _move(canvas, start + QPoint(0, 10))
        assert qlayout.spacing() == before + 10
        assert _stored(session, layout, "spacing") is None
        _release(canvas, start + QPoint(0, 10))
        assert _stored(session, layout, "spacing") == before + 10
        assert session.log.undo_label() == "Spacing"
        assert session.log.undo()
        _flush()
        assert _stored(session, layout, "spacing") is None
        assert qlayout.spacing() == before
        assert not session.log.can_undo()


def test_escape_restores_the_live_spacing() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        layout = _id(session, "verticalLayout")
        qlayout = realizer.layout_for(layout)
        assert qlayout is not None
        before = qlayout.spacing()
        _click(canvas, "ok")
        start = _gap_point(canvas, ("gap", layout, "v0"))
        _press(canvas, start)
        _move(canvas, start + QPoint(0, 10))
        assert qlayout.spacing() == before + 10
        QTest.keyClick(canvas, _qt_key("Key_Escape"))
        _flush()
        assert qlayout.spacing() == before
        assert not session.log.can_undo()


def test_dragging_a_side_wins_over_a_stored_margin() -> None:
    with _shown(MARGIN_BOX) as (session, realizer, canvas):
        layout = _id(session, "verticalLayout")
        qlayout = realizer.layout_for(layout)
        assert qlayout is not None
        before = qlayout.contentsMargins()
        assert before.left() == before.top() == before.right() == before.bottom()
        _click(canvas, "a")
        start = _knob_point(canvas, ("margin", layout, "left"))
        _press(canvas, start)
        _move(canvas, start + QPoint(6, 0))
        during = qlayout.contentsMargins()
        assert during.left() == before.left() + 6
        assert (during.top(), during.right(), during.bottom()) == (before.top(), before.right(), before.bottom())
        _release(canvas, start + QPoint(6, 0))
        landed = qlayout.contentsMargins()
        assert (landed.left(), landed.top(), landed.right(), landed.bottom()) == (
            during.left(),
            during.top(),
            during.right(),
            during.bottom(),
        )
        assert _stored(session, layout, "leftMargin") == before.left() + 6
        saved = write_ui(session.document).text
    with _shown(saved) as (session, realizer, canvas):
        qlayout = realizer.layout_for(_id(session, "verticalLayout"))
        assert qlayout is not None
        again = qlayout.contentsMargins()
        assert again.left() == before.left() + 6
        assert (again.top(), again.right(), again.bottom()) == (before.top(), before.right(), before.bottom())


def test_dragging_one_grid_axis_wins_over_stored_spacing() -> None:
    with _shown(SPACED_GRID) as (session, realizer, canvas):
        layout = _id(session, "gridLayout")
        qlayout = realizer.layout_for(layout)
        assert isinstance(qlayout, QGridLayout)
        before_h = qlayout.horizontalSpacing()
        before_v = qlayout.verticalSpacing()
        assert before_h == before_v
        _click(canvas, "a")
        start = _knob_point(canvas, ("gap", layout, "h0"))
        _press(canvas, start)
        _move(canvas, start + QPoint(10, 0))
        assert qlayout.horizontalSpacing() == before_h + 10
        assert qlayout.verticalSpacing() == before_v
        _release(canvas, start + QPoint(10, 0))
        assert qlayout.horizontalSpacing() == before_h + 10
        assert qlayout.verticalSpacing() == before_v
        saved = write_ui(session.document).text
    with _shown(saved) as (session, realizer, canvas):
        qlayout = realizer.layout_for(_id(session, "gridLayout"))
        assert isinstance(qlayout, QGridLayout)
        assert qlayout.horizontalSpacing() == before_h + 10
        assert qlayout.verticalSpacing() == before_v


def test_a_gap_drag_starts_from_spacing_when_fixed_widgets_leave_spare_room() -> None:
    with _shown(FIXED_BOX) as (session, realizer, canvas):
        layout = _id(session, "verticalLayout")
        qlayout = realizer.layout_for(layout)
        assert qlayout is not None
        before = qlayout.spacing()
        _click(canvas, "a")
        index = _fresh_index(realizer)
        survey = survey_live(realizer, index, session.document, survey_scope(session.document, layout, ()))
        facts = next(found for found in survey.layouts if found.layout == layout)
        visual = facts.rows[1].start - facts.rows[0].end
        assert visual > before + 10
        start = _gap_point(canvas, ("gap", layout, "v0"))
        _press(canvas, start)
        _move(canvas, start + QPoint(0, 10))
        assert qlayout.spacing() == before + 10
        _release(canvas, start + QPoint(0, 10))
        assert _stored(session, layout, "spacing") == before + 10


def test_escape_and_undo_restore_splitter_sizes_when_panes_have_unequal_shares() -> None:
    with _shown(SHARES) as (session, realizer, canvas):
        split = _id(session, "split")
        before = _sizes(session, realizer, "split")
        assert before[1] > before[0] + 30
        fresh = _fresh_splitter_sizes(session)
        assert fresh == before
        start = _knob_point(canvas, ("grip", split, "0"))
        _press(canvas, start)
        _move(canvas, start + QPoint(30, 0))
        assert _sizes(session, realizer, "split") == (before[0] + 30, before[1] - 30)
        QTest.keyClick(canvas, _qt_key("Key_Escape"))
        _flush()
        assert _sizes(session, realizer, "split") == before
        assert not session.log.can_undo()
        _press(canvas, start)
        _move(canvas, start + QPoint(30, 0))
        _release(canvas, start + QPoint(30, 0))
        assert _stored_sizes(session, split) == (before[0] + 30, before[1] - 30)
        assert session.log.undo()
        _flush()
        assert _stored_sizes(session, split) is None
        assert _sizes(session, realizer, "split") == fresh


def test_ctrl_arrow_resizes_by_one_pixel() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        ok = _id(session, "ok")
        _click(canvas, "ok")
        button = realizer.widget_for(ok)
        assert button is not None
        width = button.width()
        _key(canvas, "Key_Left", "ControlModifier")
        assert button.width() == width - 1
        _key(canvas, "Key_Left", "ControlModifier", "ShiftModifier", "AltModifier")
        assert button.width() == width - 1


def test_a_grip_drag_is_one_undo_on_release() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        split = _id(session, "split")
        splitter = realizer.widget_for(split)
        assert isinstance(splitter, QSplitter)
        before = tuple(splitter.sizes())
        start = _knob_point(canvas, ("grip", split, "0"))
        _press(canvas, start)
        _move(canvas, start + QPoint(30, 0))
        assert tuple(splitter.sizes()) == (before[0] + 30, before[1] - 30)
        assert _stored_sizes(session, split) is None
        _release(canvas, start + QPoint(30, 0))
        assert _stored_sizes(session, split) == (before[0] + 30, before[1] - 30)
        assert session.log.undo()
        _flush()
        assert _stored_sizes(session, split) is None
        assert not session.log.can_undo()


def test_a_size_readout_lingers_after_release() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        _click(canvas, "ok")
        start = _knob_point(canvas, ("size", _id(session, "ok"), "e"))
        end = start + QPoint(-40, 0)
        _press(canvas, start)
        _move(canvas, end)
        during = _readout(canvas)
        assert during is not None and during.startswith("Fixed ")
        _release(canvas, end)
        assert _readout(canvas) == during
        QTest.qWait(READOUT_LINGER_MS + 200)
        _flush()
        assert _readout(canvas) is None


def test_repeated_ctrl_shift_arrows_are_one_undo() -> None:
    with _shown(STACK) as (session, realizer, canvas):
        ok = _id(session, "ok")
        _click(canvas, "ok")
        button = realizer.widget_for(ok)
        assert button is not None
        width = button.width()
        _key(canvas, "Key_Left", "ControlModifier", "ShiftModifier")
        _key(canvas, "Key_Left", "ControlModifier", "ShiftModifier")
        assert button.width() == width - 16
        assert len(session.log.entries()) == 1
        assert session.log.undo()
        _flush()
        node = session.document.get(ok)
        assert isinstance(node, WidgetNode) and node.prop("sizePolicy") is None


@pytest.mark.parametrize(
    "text, select, key, delta, read, moved",
    (
        pytest.param(
            STACK, "ok", ("gap", "verticalLayout", "v0"),
            lambda session, realizer: (0, 10),
            lambda session, realizer: _qlayout(session, realizer, "verticalLayout").spacing(),
            lambda before: before + 10,
            id="spacing",
            marks=pytest.mark.parity("R3-48"),
        ),
        pytest.param(
            STACK, "ok", ("margin", "verticalLayout", "left"),
            lambda session, realizer: (6, 0),
            lambda session, realizer: _qlayout(session, realizer, "verticalLayout").contentsMargins().left(),
            lambda before: before + 6,
            id="margin",
            marks=pytest.mark.parity("R3-47"),
        ),
        pytest.param(
            SPAN, "a", ("size", "a", "e"),
            lambda session, realizer: (_right(session, realizer, "c") - _right(session, realizer, "a"), 0),
            lambda session, realizer: _cell(session, realizer, "gridLayout", "a"),
            lambda before: before[:3] + (2,),
            id="span",
            marks=pytest.mark.parity("R3-52"),
        ),
        pytest.param(
            PANES % ("QVBoxLayout", "Qt::Horizontal"), None, ("grip", "split", "0"),
            lambda session, realizer: (30, 0),
            lambda session, realizer: _sizes(session, realizer, "split"),
            lambda before: (before[0] + 30, before[1] - 30),
            id="splitter-h",
            marks=pytest.mark.parity("R3-39"),
        ),
        pytest.param(
            PANES % ("QHBoxLayout", "Qt::Vertical"), None, ("grip", "split", "0"),
            lambda session, realizer: (0, 30),
            lambda session, realizer: _sizes(session, realizer, "split"),
            lambda before: (before[0] + 30, before[1] - 30),
            id="splitter-v",
            marks=(pytest.mark.parity("R3-40"), pytest.mark.pain("P-19")),
        ),
    ),
)
def test_a_knob_drop_survives_save_and_reload(text, select, key, delta, read, moved) -> None:
    with _shown(text) as (session, realizer, canvas):
        before = read(session, realizer)
        if select is not None:
            _click(canvas, select)
        kind, owner, detail = key
        knob: KnobKey = (kind, _id(session, owner), detail)
        start = _gap_point(canvas, knob) if kind == "gap" else _knob_point(canvas, knob)
        dx, dy = delta(session, realizer)
        _press(canvas, start)
        _move(canvas, start + QPoint(dx, dy))
        _release(canvas, start + QPoint(dx, dy))
        dropped = read(session, realizer)
        assert dropped == moved(before)
        saved = write_ui(session.document).text
    with _shown(saved) as (session, realizer, canvas):
        assert read(session, realizer) == dropped


def test_a_share_chip_focuses_the_share_spin(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(1280, 800)
    surface = _open_surface(parent, GRID, tmp_path / "grid.ui")
    surface.resize(1280, 800)
    parent.show()
    surface.show()
    app = QApplication.instance()
    assert app is not None
    app.setActiveWindow(parent)
    _flush()
    try:
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        assert isinstance(canvas, FormCanvas)
        session = surface.session
        b = _id(session, "b")
        session.selection.set((b,), current=b, source=SelectionSource.PROGRAM)
        _flush()
        rect, action = next(
            (rect, target.action)
            for rect, target in canvas.overlay().targets
            if isinstance(target, OnChip) and isinstance(target.action, FocusShare) and target.action.node == b
        )
        assert action.axis == "h"
        at = _from_rect(canvas, rect)
        _press(canvas, at)
        _release(canvas, at)
        focused = QApplication.focusWidget()
        assert focused is not None
        owner: Optional[QWidget] = focused
        while owner is not None and owner.objectName() != "formBuilder.size.share.h.value":
            owner = owner.parentWidget()
        assert owner is not None
        assert session.selection.state.current == b
    finally:
        surface.release()
        parent.deleteLater()


def _fresh_index(realizer: Realizer) -> HitIndex:
    index = HitIndex(LiveGeometrySource(realizer))
    index.ensure_fresh()
    return index


def _knob_point(canvas: FormCanvas, key: KnobKey) -> QPoint:
    for rect, target in canvas.overlay().targets:
        if isinstance(target, OnKnob) and target.knob.key == key:
            return _from_rect(canvas, rect)
    raise AssertionError(key)


def _gap_point(canvas: FormCanvas, key: KnobKey) -> QPoint:
    """Near the gap's left end, clear of the selection's south handle."""
    for rect, target in canvas.overlay().targets:
        if isinstance(target, OnKnob) and target.knob.key == key:
            return canvas.mapFromScene(QPointF(rect.x + 20, rect.y + rect.height / 2.0))
    raise AssertionError(key)


def _readout(canvas: FormCanvas) -> Optional[str]:
    for item in canvas.overlay().items:
        if isinstance(item, Chip) and item.text.startswith("Fixed "):
            return item.text
    return None


def _stored(session: FormSession, node: NodeId, name: str) -> Optional[int]:
    found = session.document.get(node)
    assert isinstance(found, LayoutNode)
    value = found.value(name)
    return None if value is None else int(getattr(value, "value"))


def _stored_sizes(session: FormSession, node: NodeId) -> Optional[Tuple[int, ...]]:
    found = session.document.get(node)
    assert isinstance(found, WidgetNode)
    value = found.value("cbcsSplitterSizes")
    return None if value is None else splitter_sizes(value)


def _qlayout(session: FormSession, realizer: Realizer, name: str):
    found = realizer.layout_for(_id(session, name))
    assert found is not None
    return found


def _right(session: FormSession, realizer: Realizer, name: str) -> int:
    widget = realizer.widget_for(_id(session, name))
    assert widget is not None
    return widget.geometry().right()


def _cell(session: FormSession, realizer: Realizer, layout: str, name: str) -> Tuple[int, ...]:
    grid = _qlayout(session, realizer, layout)
    widget = realizer.widget_for(_id(session, name))
    return tuple(grid.getItemPosition(grid.indexOf(widget)))


def _fresh_splitter_sizes(session: FormSession) -> Tuple[int, ...]:
    fresh = Realizer(session)
    try:
        fresh.build()
        root = fresh.root_widget
        assert root is not None
        root.resize(400, 300)
        root.show()
        _flush()
        return _sizes(session, fresh, "split")
    finally:
        fresh.dispose()


def _sizes(session: FormSession, realizer: Realizer, name: str) -> Tuple[int, ...]:
    splitter = realizer.widget_for(_id(session, name))
    assert isinstance(splitter, QSplitter) and splitter.count() == 2
    return tuple(splitter.sizes())


def _id(session: FormSession, name: str) -> NodeId:
    found = session.document.by_name(name)
    assert len(found) == 1
    return found[0]


def _click(canvas: FormCanvas, name: str) -> None:
    at = _center(canvas, name)
    _press(canvas, at)
    _release(canvas, at)


def _center(canvas: FormCanvas, name: str) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(widget.mapTo(root, widget.rect().center())))


def _from_rect(canvas: FormCanvas, rect: CanvasRect) -> QPoint:
    return canvas.mapFromScene(QPointF(rect.x + rect.width / 2.0, rect.y + rect.height / 2.0))


def _press(canvas: FormCanvas, pos: QPoint) -> None:
    _send(canvas, "MouseButtonPress", pos, "LeftButton", "LeftButton")


def _move(canvas: FormCanvas, pos: QPoint) -> None:
    _send(canvas, "MouseMove", pos, "NoButton", "LeftButton")


def _release(canvas: FormCanvas, pos: QPoint) -> None:
    _send(canvas, "MouseButtonRelease", pos, "LeftButton", "NoButton")


def _send(canvas: FormCanvas, kind_name: str, pos: QPoint, button_name: str, buttons_name: str) -> None:
    viewport = canvas.viewport()
    kind = getattr(getattr(QEvent, "Type", QEvent), kind_name)
    event = QMouseEvent(
        kind,
        QPointF(pos),
        QPointF(viewport.mapToGlobal(pos)),
        _mouse(button_name),
        _mouse(buttons_name),
        _mods("NoModifier"),
    )
    QApplication.sendEvent(viewport, event)
    _flush()


def _key(canvas: FormCanvas, name: str, *modifiers: str) -> None:
    mods = _mods("NoModifier")
    for modifier in modifiers:
        mods = mods | _mods(modifier)
    QTest.keyClick(canvas, _qt_key(name), mods)
    _flush()


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _qt_key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)
