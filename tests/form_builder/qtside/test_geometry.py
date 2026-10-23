"""LiveGeometrySource and HitIndexInvalidator on realized forms (CONTRACTS.md section 5.5)."""
from __future__ import annotations

from typing import Iterator, List, Optional, Tuple

import pytest

from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication, QWidget
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

NESTED = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>360</height></rect></property>
  <layout class="QVBoxLayout" name="formLayout">
   <item>
    <widget class="QGroupBox" name="group">
     <property name="title"><string>Group</string></property>
     <layout class="QVBoxLayout" name="groupLayout">
      <item><widget class="QLabel" name="label"><property name="text"><string>Name</string></property></widget></item>
      <item>
       <spacer name="gap">
        <property name="orientation"><enum>Qt::Vertical</enum></property>
        <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
       </spacer>
      </item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QTabWidget" name="tabs">
     <widget class="QWidget" name="first">
      <attribute name="title"><string>One</string></attribute>
      <layout class="QHBoxLayout" name="firstLayout">
       <item><widget class="QPushButton" name="button"><property name="text"><string>Go</string></property></widget></item>
      </layout>
     </widget>
     <widget class="QWidget" name="second">
      <attribute name="title"><string>Two</string></attribute>
      <layout class="QHBoxLayout" name="secondLayout">
       <item><widget class="QLineEdit" name="hiddenEdit"/></item>
      </layout>
     </widget>
    </widget>
   </item>
   <item>
    <widget class="QScrollArea" name="scroll">
     <property name="widgetResizable"><bool>true</bool></property>
     <widget class="QWidget" name="scrollContents">
      <layout class="QVBoxLayout" name="scrollLayout">
       <item><widget class="QCheckBox" name="check"><property name="text"><string>Check</string></property></widget></item>
      </layout>
     </widget>
    </widget>
   </item>
  </layout>
""",
)


@pytest.fixture
def shown() -> Iterator[Tuple[FormSession, Realizer, HitIndex]]:
    with opened(NESTED) as (session, realizer):
        root = realizer.root_widget
        assert root is not None
        root.show()
        QApplication.processEvents()
        index = HitIndex(LiveGeometrySource(realizer))
        try:
            yield session, realizer, index
        finally:
            root.hide()


def _id(session: FormSession, name: str) -> NodeId:
    return session.document.by_name(name)[0]


def _centre(realizer: Realizer, node: NodeId) -> Tuple[int, int]:
    widget = realizer.widget_for(node)
    root = realizer.root_widget
    assert widget is not None and root is not None
    point = widget.mapTo(root, widget.rect().center())
    return point.x(), point.y()


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("label", ("label", "groupLayout", "group", "formLayout", "Form")),
        ("button", ("button", "firstLayout", "first", "tabs", "formLayout", "Form")),
        ("check", ("check", "scrollLayout", "scrollContents", "scroll", "formLayout", "Form")),
    ],
)
def test_query_hits_the_deepest_realized_widget(
    shown: Tuple[FormSession, Realizer, HitIndex], name: str, path: Tuple[str, ...]
) -> None:
    session, realizer, index = shown
    index.ensure_fresh()
    hit = index.query(*_centre(realizer, _id(session, name)))
    assert hit is not None
    assert hit.path == tuple(_id(session, part) for part in path)


def test_a_spacer_is_hit_inside_its_layout(shown: Tuple[FormSession, Realizer, HitIndex]) -> None:
    session, realizer, index = shown
    gap = _id(session, "gap")
    spacer = realizer.spacer_for(gap)
    group = realizer.widget_for(_id(session, "group"))
    root = realizer.root_widget
    assert spacer is not None and group is not None and root is not None
    point = group.mapTo(root, spacer.geometry().center())
    index.ensure_fresh()
    hit = index.query(point.x(), point.y())
    assert hit is not None
    assert (hit.node, hit.kind) == (gap, "spacer")


def _nearest_widget(session: FormSession, path: Tuple[NodeId, ...]) -> NodeId:
    return next(node for node in path if isinstance(session.document.get(node), WidgetNode))


def _child_at(realizer: Realizer, root: QWidget, x: int, y: int) -> Optional[NodeId]:
    widget = root.childAt(x, y)
    return realizer.node_for(root if widget is None else widget)


def test_query_agrees_with_child_at_across_the_form(shown: Tuple[FormSession, Realizer, HitIndex]) -> None:
    session, realizer, index = shown
    root = realizer.root_widget
    assert root is not None
    # Realized widgets ignore the mouse, and childAt skips such widgets.
    for widget in root.findChildren(QWidget):
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    index.ensure_fresh()
    mismatches: List[Tuple[int, int, object, object]] = []
    for x in range(0, root.width(), 5):
        for y in range(0, root.height(), 5):
            hit = index.query(x, y)
            assert hit is not None
            expected = _child_at(realizer, root, x, y)
            actual = _nearest_widget(session, hit.path)
            if actual != expected:
                mismatches.append((x, y, expected, actual))
    assert mismatches == []


def test_hidden_page_is_indexed_but_never_hit(shown: Tuple[FormSession, Realizer, HitIndex]) -> None:
    session, realizer, index = shown
    second = _id(session, "second")
    index.ensure_fresh()
    tabs = _id(session, "tabs")
    pages = {entry.node: entry.visible for entry in index.children_of(tabs)}
    assert pages == {_id(session, "first"): True, second: False}


def test_a_changeset_invalidates_without_refreshing_in_the_listener(
    shown: Tuple[FormSession, Realizer, HitIndex]
) -> None:
    session, realizer, index = shown
    subscription = session.log.subscribe(HitIndexInvalidator(index).on_changeset, priority=PRIORITY_HIT_INDEX)
    try:
        index.ensure_fresh()
        label = _id(session, "label")
        session.log.execute(SetProperty(label, "text", StringValue("A much longer label text than before")))
        assert (index.is_fresh(), index.refresh_count) == (False, 1)
        index.ensure_fresh()
        settled = {entry.node: entry.rect for entry in index.children_of(_id(session, "groupLayout"))}
        QApplication.processEvents()
        index.invalidate("changeset")
        index.ensure_fresh()
        later = {entry.node: entry.rect for entry in index.children_of(_id(session, "groupLayout"))}
        assert settled == later
        assert index.refresh_count == 3
    finally:
        subscription.close()
