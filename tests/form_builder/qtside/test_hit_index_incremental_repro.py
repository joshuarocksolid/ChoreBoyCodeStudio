# pyright: reportAttributeAccessIssue=false
"""Review repro (M3.7a gate): the ChangeSet-scoped hit index must equal a full rebuild."""
from __future__ import annotations

import random
from typing import Callable, Iterator, List, Tuple

import pytest

from app.qt.QtWidgets import QApplication, QScrollArea, QWidget
from app.features.form_builder.engine.commands.catalog import DeleteNodes, SetLayoutStretch, SetProperty
from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import NumberValue, SizeValue, StringValue
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_geometry import NESTED

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def live() -> Iterator[Tuple[FormSession, Realizer, HitIndex]]:
    with opened(NESTED) as (session, realizer):
        root = realizer.root_widget
        assert root is not None
        root.show()
        QApplication.processEvents()
        index = HitIndex(LiveGeometrySource(realizer))
        subscription = session.log.subscribe(HitIndexInvalidator(index).on_changeset, priority=PRIORITY_HIT_INDEX)
        try:
            index.ensure_fresh()
            yield session, realizer, index
        finally:
            subscription.close()
            root.hide()


def _id(session: FormSession, name: str) -> NodeId:
    return session.document.by_name(name)[0]


def _table(entries) -> List[Tuple[object, str, object, bool]]:
    return sorted(
        ((entry.node, entry.kind, entry.rect, entry.visible) for entry in entries),
        key=repr,
    )


def _assert_matches_full(realizer: Realizer, index: HitIndex) -> None:
    index.ensure_fresh()
    full = HitIndex(LiveGeometrySource(realizer))
    full.ensure_fresh()
    assert _table(index._entries) == _table(full._entries)


EDITS: List[Tuple[str, Callable[[FormSession], object]]] = [
    ("label text", lambda s: s.log.execute(SetProperty(_id(s, "label"), "text", StringValue("A much longer label text")))),
    ("layout spacing", lambda s: s.log.execute(SetProperty(_id(s, "formLayout"), "spacing", NumberValue(40)))),
    ("layout margin", lambda s: s.log.execute(SetProperty(_id(s, "groupLayout"), "topMargin", NumberValue(40)))),
    ("layout stretch", lambda s: s.log.execute(SetLayoutStretch(_id(s, "formLayout"), "stretch", "0,4,1"))),
    ("delete laid label", lambda s: s.log.execute(DeleteNodes((_id(s, "label"),)))),
    ("tab currentIndex", lambda s: s.log.execute(SetProperty(_id(s, "tabs"), "currentIndex", NumberValue(1)))),
]


@pytest.mark.parametrize(("name", "edit"), EDITS, ids=[name for name, _ in EDITS])
def test_incremental_index_equals_full_rebuild(live: Tuple[FormSession, Realizer, HitIndex], name: str, edit) -> None:
    session, realizer, index = live
    edit(session)
    _assert_matches_full(realizer, index)


@pytest.mark.parametrize(("name", "edit"), EDITS, ids=[name for name, _ in EDITS])
def test_incremental_index_equals_full_rebuild_after_undo(
    live: Tuple[FormSession, Realizer, HitIndex], name: str, edit
) -> None:
    session, realizer, index = live
    edit(session)
    index.ensure_fresh()
    session.log.undo()
    _assert_matches_full(realizer, index)


def test_random_edits_and_undo_match_a_full_rebuild(live: Tuple[FormSession, Realizer, HitIndex]) -> None:
    session, realizer, index = live
    rng = random.Random(37)
    for _step in range(24):
        kind = rng.randrange(5)
        if kind == 0:
            session.log.execute(SetProperty(_id(session, "label"), "text", StringValue("n%d" % rng.randrange(50))))
        elif kind == 1:
            session.log.execute(SetProperty(_id(session, "formLayout"), "spacing", NumberValue(rng.randrange(2, 24))))
        elif kind == 2:
            session.log.execute(
                SetProperty(_id(session, "groupLayout"), "topMargin", NumberValue(rng.randrange(0, 20)))
            )
        elif kind == 3:
            session.log.execute(SetProperty(_id(session, "tabs"), "currentIndex", NumberValue(rng.randrange(2))))
        elif not session.log.undo():
            session.log.redo()
        _assert_matches_full(realizer, index)


# --- Review round 2: structural fuzz, several seeds, container compared too. ---

from app.features.form_builder.engine.commands.catalog import InsertFragment, MoveNodes, SetGeometry  # noqa: E402
from app.features.form_builder.engine.commands.placement import InBoxLayout, InContainer  # noqa: E402
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode  # noqa: E402
from app.features.form_builder.engine.ui4.spec import Fragment  # noqa: E402
from app.features.form_builder.engine.ui4.values import RectValue  # noqa: E402
from tests.form_builder.engine.commands._support import button_spec  # noqa: E402


def _full_table(entries):
    return sorted(
        ((entry.node, entry.kind, entry.rect, entry.visible, entry.container) for entry in entries),
        key=repr,
    )


def _step(session: FormSession, rng: random.Random, counter: List[int]) -> None:
    doc = session.document
    widgets = [w for w in doc.iter_widgets() if w.id != doc.root.id]
    layouts = [n for n in doc.iter_preorder() if isinstance(n, LayoutNode)]
    kind = rng.randrange(10)
    counter[0] += 1
    if kind == 0 and widgets:
        target = rng.choice(widgets)
        session.log.execute(SetProperty(target.id, "text", StringValue("t" * rng.randrange(1, 30))))
    elif kind == 1 and layouts:
        layout = rng.choice(layouts)
        name = rng.choice(["spacing", "topMargin", "leftMargin", "bottomMargin"])
        session.log.execute(SetProperty(layout.id, name, NumberValue(rng.randrange(0, 30))))
    elif kind == 2:
        tabs = [w for w in widgets if w.class_name == "QTabWidget"]
        if tabs:
            session.log.execute(SetProperty(tabs[0].id, "currentIndex", NumberValue(rng.randrange(2))))
    elif kind == 3 and widgets:
        session.log.execute(DeleteNodes((rng.choice(widgets).id,)))
    elif kind == 4 and layouts:
        layout = rng.choice(layouts)
        index = rng.randrange(len(layout.items) + 1)
        session.log.execute(
            InsertFragment(InBoxLayout(layout.id, index), Fragment(nodes=(button_spec("fz%d" % counter[0]),)))
        )
    elif kind == 5 and widgets and layouts:
        layout = rng.choice(layouts)
        mover = rng.choice(widgets)
        session.log.execute(MoveNodes((mover.id,), InBoxLayout(layout.id, rng.randrange(len(layout.items) + 1))))
    elif kind == 6 and layouts:
        layout = rng.choice(layouts)
        session.log.execute(SetLayoutStretch(layout.id, "stretch", ",".join(str(rng.randrange(3)) for _ in layout.items) or None))
    elif kind == 7:
        if not session.log.undo():
            session.log.redo()
    elif kind == 8:
        if not session.log.redo():
            session.log.undo()
    else:
        free_host = _id(session, "scrollContents") if session.document.by_name("scrollContents") else None
        if free_host is not None:
            session.log.execute(
                InsertFragment(
                    InContainer(session.document.root.id, 0, RectValue(rng.randrange(200), rng.randrange(300), 60, 24)),
                    Fragment(nodes=(button_spec("fr%d" % counter[0]),)),
                )
            )


@pytest.fixture
def embedded() -> Iterator[Tuple[FormSession, Realizer, HitIndex]]:
    """The root under a plain host, as on the canvas: a top-level root resizes asynchronously offscreen."""
    from app.qt.QtWidgets import QWidget

    with opened(NESTED) as (session, realizer):
        root = realizer.root_widget
        assert root is not None
        host = QWidget()
        host.resize(1200, 1200)
        root.setParent(host)
        host.show()
        root.show()
        QApplication.processEvents()
        index = HitIndex(LiveGeometrySource(realizer))
        subscription = session.log.subscribe(HitIndexInvalidator(index).on_changeset, priority=PRIORITY_HIT_INDEX)
        try:
            index.ensure_fresh()
            yield session, realizer, index
        finally:
            subscription.close()
            root.setParent(None)
            host.hide()
            host.deleteLater()


@pytest.mark.parametrize("seed", list(range(1, 121)))
def test_review_structural_fuzz_matches_a_full_rebuild(embedded: Tuple[FormSession, Realizer, HitIndex], seed: int) -> None:
    session, realizer, index = embedded
    rng = random.Random(seed)
    counter = [0]
    trail: List[str] = []
    for step in range(60):
        try:
            _step(session, rng, counter)
        except Exception as exc:  # refused command: not what this test checks
            trail.append("refused %s" % type(exc).__name__)
            continue
        trail.append(session.log.undo_label() or "")
        # The canvas refreshes from its paint request, after posted events ran.
        QApplication.processEvents()
        index.ensure_fresh()
        full = HitIndex(LiveGeometrySource(realizer))
        full.ensure_fresh()
        assert _full_table(index._entries) == _full_table(full._entries), (seed, step, trail[-6:])


# Minimum heights are fixed pixels, so the scrollbar threshold does not depend on the font.
DEFERRED_SCROLL = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="formLayout">
   <item>
    <widget class="QTabWidget" name="tabs">
     <widget class="QWidget" name="first">
      <attribute name="title"><string>One</string></attribute>
     </widget>
     <widget class="QWidget" name="second">
      <attribute name="title"><string>Two</string></attribute>
     </widget>
    </widget>
   </item>
   <item>
    <widget class="QScrollArea" name="scroll">
     <property name="widgetResizable"><bool>true</bool></property>
     <widget class="QWidget" name="scrollContents">
      <property name="minimumSize"><size><width>40</width><height>100</height></size></property>
      <layout class="QVBoxLayout" name="scrollLayout">
       <item><widget class="QPushButton" name="inside"><property name="text"><string>Go</string></property></widget></item>
      </layout>
     </widget>
    </widget>
   </item>
  </layout>
""",
)


def test_deferred_scrollbar_on_a_sibling_scroll_area_matches_a_full_rebuild() -> None:
    """Growing a sibling can leave the scrollbar pending until the next layout.

    The scroll area's rect stays put. The contents width changes by the bar.
    """
    with opened(DEFERRED_SCROLL) as (session, realizer):
        root = realizer.root_widget
        assert root is not None
        host = QWidget()
        host.resize(800, 800)
        root.setParent(host)
        host.show()
        root.show()
        QApplication.processEvents()
        index = HitIndex(LiveGeometrySource(realizer))
        subscription = session.log.subscribe(
            HitIndexInvalidator(index).on_changeset, priority=PRIORITY_HIT_INDEX
        )
        try:
            index.ensure_fresh()
            session.log.execute(
                SetProperty(session.document.by_name("tabs")[0], "minimumSize", SizeValue(10, 200))
            )
            QApplication.processEvents()
            index.ensure_fresh()
            scroll = realizer.widget_for(session.document.by_name("scroll")[0])
            contents = realizer.widget_for(session.document.by_name("scrollContents")[0])
            assert isinstance(scroll, QScrollArea)
            assert contents is not None
            assert not scroll.verticalScrollBar().isVisible()
            assert contents.height() > scroll.viewport().height()
            assert contents.width() == scroll.viewport().width()
            session.log.execute(
                SetProperty(session.document.by_name("tabs")[0], "currentIndex", NumberValue(1))
            )
            QApplication.processEvents()
            assert scroll.verticalScrollBar().isVisible()
            index.ensure_fresh()
            _assert_full(realizer, index)
        finally:
            subscription.close()
            root.setParent(None)
            host.hide()
            host.deleteLater()


def _assert_full(realizer: Realizer, index: HitIndex) -> None:
    full = HitIndex(LiveGeometrySource(realizer))
    full.ensure_fresh()
    assert _full_table(index._entries) == _full_table(full._entries)
