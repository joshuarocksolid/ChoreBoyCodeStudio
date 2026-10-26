# pyright: reportAttributeAccessIssue=false
"""Layout gestures move the live widgets. They do not rebuild them."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.layout_actions import (
    FORM,
    GRID,
    GROUP,
    HORIZONTAL,
    HSPLIT,
    TAB,
    VERTICAL,
    Adjust,
    ApplyKind,
    ChangeTo,
    Done,
    NeedsConfirm,
    PickWrap,
    RemoveLayout,
    Unwrap,
    transact,
)
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.layout_gestures import perform
from app.qt.QtWidgets import QApplication, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_UI = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
   <item><widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget></item>
   <item>
    <widget class="QGroupBox" name="box">
     <layout class="QVBoxLayout" name="inner">
      <item><widget class="QPushButton" name="three"><property name="text"><string>Three</string></property></widget></item>
     </layout>
    </widget>
   </item>
  </layout>
""",
)
_LEAVES = ("one", "two", "three")

_FREE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>200</height></rect></property>
  <widget class="QLabel" name="label">
   <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>Name</string></property>
  </widget>
  <widget class="QLineEdit" name="edit">
   <property name="geometry"><rect><x>100</x><y>10</y><width>160</width><height>24</height></rect></property>
  </widget>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>100</x><y>50</y><width>200</width><height>60</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)

_TWO_ROWS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>160</height></rect></property>
  <layout class="QVBoxLayout" name="column">
   <item>
    <widget class="QWidget" name="first">
     <layout class="QHBoxLayout" name="firstRow">
      <item><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
      <item><widget class="QLineEdit" name="nameEdit"/></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="second">
     <layout class="QHBoxLayout" name="secondRow">
      <item><widget class="QLabel" name="cityLabel"><property name="text"><string>City</string></property></widget></item>
      <item><widget class="QLineEdit" name="cityEdit"/></item>
     </layout>
    </widget>
   </item>
  </layout>
""",
)


def _never(prompt: NeedsConfirm) -> bool:
    raise AssertionError("unexpected confirm: %s" % prompt.text)


@pytest.mark.parametrize(
    ("selected", "request_"),
    [
        (("one", "two"), PickWrap(GROUP)),
        (("one", "two"), PickWrap(HSPLIT)),
        (("one", "two"), PickWrap(TAB)),
        (("one", "two"), ApplyKind(HORIZONTAL)),
        (("box",), Unwrap()),
        ((), ApplyKind(HORIZONTAL)),
    ],
)
def test_wrap_unwrap_and_a_layout_morph_keep_every_live_widget(selected: Tuple[str, ...], request_: object) -> None:
    with opened(_UI) as (session, realizer):
        doc = session.document
        ids = tuple(doc.by_name(name)[0] for name in selected)
        before = {name: realizer.widget_for(doc.by_name(name)[0]) for name in _LEAVES}
        entries = len(session.log.entries())

        outcome = perform(doc, ids, realizer.widget_for, transact(session.log), request_, _never)

        assert isinstance(outcome, Done), outcome
        assert len(session.log.entries()) == entries + 1
        assert realizer.last_stats.fallback_rebuilds == 0
        for name, widget in before.items():
            assert widget is not None
            assert realizer.widget_for(doc.by_name(name)[0]) is widget, name


@pytest.mark.parametrize(
    ("kind_id", "layout_type"),
    [
        pytest.param(HORIZONTAL, QHBoxLayout, marks=pytest.mark.parity("R3-35")),
        pytest.param(VERTICAL, QVBoxLayout, marks=pytest.mark.parity("R3-36")),
        pytest.param(GRID, QGridLayout, marks=pytest.mark.parity("R3-37")),
        pytest.param(FORM, QFormLayout, marks=pytest.mark.parity("R3-38")),
    ],
)
def test_laying_out_free_widgets_puts_the_same_widgets_in_that_layout(kind_id: str, layout_type: type) -> None:
    with opened(_FREE) as (session, realizer):
        doc = session.document
        before = {name: realizer.widget_for(doc.by_name(name)[0]) for name in ("label", "edit", "ok")}
        entries = len(session.log.entries())

        outcome = perform(doc, (), realizer.widget_for, transact(session.log), ApplyKind(kind_id), _never)

        assert isinstance(outcome, Done), outcome
        assert len(session.log.entries()) == entries + 1
        root = realizer.widget_for(doc.root.id)
        assert root is not None and isinstance(root.layout(), layout_type)
        for name, widget in before.items():
            assert widget is not None
            assert realizer.widget_for(doc.by_name(name)[0]) is widget, name
            assert root.layout().indexOf(widget) >= 0, name


@pytest.mark.parity("R3-42")
def test_adjust_size_fits_a_free_widget_to_its_content_in_one_step() -> None:
    with opened(_FREE) as (session, realizer):
        doc = session.document
        ok = doc.by_name("ok")[0]
        widget = realizer.widget_for(ok)
        assert widget is not None
        stored = widget.size()
        hint = widget.sizeHint()
        assert stored != hint
        entries = len(session.log.entries())

        outcome = perform(doc, (ok,), realizer.widget_for, transact(session.log), Adjust(), _never)

        assert outcome == Done("Resized ok to fit its content")
        assert len(session.log.entries()) == entries + 1
        resized = realizer.widget_for(ok)
        assert resized is not None
        assert resized.size() == hint
        session.log.undo()
        restored_size = realizer.widget_for(ok)
        assert restored_size is not None
        assert restored_size.size() == stored


@pytest.mark.pain("P-5")
def test_removing_one_row_layout_keeps_the_next_rows_width() -> None:
    with opened(_TWO_ROWS) as (session, realizer):
        doc = session.document
        first = doc.by_name("first")[0]
        root = realizer.widget_for(doc.root.id)
        second = realizer.widget_for(doc.by_name("second")[0])
        assert root is not None and second is not None
        root.show()
        _layout_pass()
        width = second.width()
        asked = []

        def accept(prompt: NeedsConfirm) -> bool:
            asked.append(prompt.accept)
            return True

        outcome = perform(doc, (first,), realizer.widget_for, transact(session.log), RemoveLayout(), accept)
        _layout_pass()

        assert asked == ["Remove layout"]
        assert outcome == Done("Removed the layout")
        broken = realizer.widget_for(first)
        kept = realizer.widget_for(doc.by_name("second")[0])
        assert broken is not None and kept is not None
        assert broken.layout() is None
        assert kept.width() == width
        session.log.undo()
        _layout_pass()
        brought_back = realizer.widget_for(first)
        assert brought_back is not None
        restored = brought_back.layout()
        assert isinstance(restored, QHBoxLayout)
        assert restored.indexOf(realizer.widget_for(doc.by_name("nameEdit")[0])) >= 0
        root.hide()


@pytest.mark.parity("R3-55")
def test_changing_a_container_class_replaces_it_and_keeps_its_children() -> None:
    with opened(_UI) as (session, realizer):
        doc = session.document
        box = doc.by_name("box")[0]
        three = doc.by_name("three")[0]
        old_box = realizer.widget_for(box)
        old_three = realizer.widget_for(three)

        outcome = perform(doc, (box,), realizer.widget_for, transact(session.log), ChangeTo("QFrame"), _never)

        assert outcome == Done("Changed to a frame.")
        node = doc.node(box)
        assert isinstance(node, WidgetNode) and node.class_name == "QFrame" and node.object_name == "box"
        new_box = realizer.widget_for(box)
        assert new_box is not None and new_box is not old_box
        assert type(new_box).__name__ == "QFrame"
        assert realizer.widget_for(three) is old_three
        assert old_three is not None and new_box.isAncestorOf(old_three)
        assert realizer.last_stats.fallback_rebuilds == 0


def _layout_pass() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()
