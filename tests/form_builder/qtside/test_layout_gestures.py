# pyright: reportAttributeAccessIssue=false
"""Layout gestures move the live widgets. They do not rebuild them."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.layout_actions import (
    GROUP,
    HORIZONTAL,
    HSPLIT,
    TAB,
    ApplyKind,
    ChangeTo,
    Done,
    NeedsConfirm,
    PickWrap,
    Unwrap,
    transact,
)
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.layout_gestures import perform
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
