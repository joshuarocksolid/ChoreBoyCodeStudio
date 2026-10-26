# pyright: reportAttributeAccessIssue=false
"""A deleted spacing, margin or splitter size leaves the live object as a fresh build would."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.qt.QtWidgets import QApplication, QFormLayout, QGridLayout, QLayout, QSplitter
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.live import LiveProp
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.qtside.support import form, opened

_GRID_ITEMS = """
   <item row="0" column="0"><widget class="QPushButton" name="a"/></item>
   <item row="0" column="1"><widget class="QPushButton" name="b"/></item>
   <item row="1" column="0"><widget class="QPushButton" name="c"/></item>
"""
_BOX_ITEMS = """
   <item><widget class="QPushButton" name="a"/></item>
   <item><widget class="QPushButton" name="b"/></item>
"""


def _number(name: str, value: int) -> str:
    return '<property name="%s"><number>%d</number></property>' % (name, value)


def _top(kind: str, props: str) -> str:
    items = _GRID_ITEMS if kind == "QGridLayout" else _BOX_ITEMS
    return form('class="QWidget" name="Form"', '<layout class="%s" name="lay">%s%s</layout>' % (kind, props, items))


def _nested(props: str) -> str:
    inner = '<item><layout class="QHBoxLayout" name="lay">%s%s</layout></item>' % (props, _BOX_ITEMS)
    return form('class="QWidget" name="Form"', '<layout class="QVBoxLayout" name="outer">%s</layout>' % inner)


def _facts(layout: QLayout) -> Tuple[int, ...]:
    margins = layout.contentsMargins()
    sides = (margins.left(), margins.top(), margins.right(), margins.bottom())
    if isinstance(layout, (QGridLayout, QFormLayout)):
        return sides + (layout.horizontalSpacing(), layout.verticalSpacing())
    return sides + (layout.spacing(),)


def _built(session: FormSession, name: str) -> Tuple[int, ...]:
    other = Realizer(session)
    try:
        other.build()
        layout = other.layout_for(session.document.by_name(name)[0])
        assert layout is not None
        return _facts(layout)
    finally:
        other.dispose()


_CASES = (
    ("grid spacing falls back to spacing", _top("QGridLayout", _number("spacing", 13) + _number("horizontalSpacing", 4)), "horizontalSpacing"),
    ("grid row spacing falls back to the default", _top("QGridLayout", _number("horizontalSpacing", 4) + _number("verticalSpacing", 17)), "verticalSpacing"),
    ("grid spacing keeps the stored row spacing", _top("QGridLayout", _number("spacing", 13) + _number("verticalSpacing", 17)), "spacing"),
    ("box spacing", _top("QVBoxLayout", _number("spacing", 23)), "spacing"),
    ("a side keeps the other stored sides", _top("QVBoxLayout", _number("leftMargin", 20) + _number("topMargin", 2)), "leftMargin"),
    ("a side falls back to the legacy margin", _top("QVBoxLayout", _number("margin", 5) + _number("leftMargin", 20)), "leftMargin"),
    ("the legacy margin keeps a later side", _top("QVBoxLayout", _number("margin", 5) + _number("leftMargin", 20)), "margin"),
    ("a nested side falls back to the nested default", _nested(_number("rightMargin", 21)), "rightMargin"),
)


@pytest.mark.parametrize(("label", "text", "name"), _CASES, ids=[case[0] for case in _CASES])
def test_deleting_a_layout_number_matches_a_fresh_build(qapp: object, label: str, text: str, name: str) -> None:
    del qapp
    with opened(text) as (session, realizer):
        layout_id = session.document.by_name("lay")[0]
        live = realizer.layout_for(layout_id)
        assert live is not None
        before = _facts(live)
        session.log.execute(SetProperty(layout_id, name, None))
        assert _facts(live) == _built(session, "lay"), label
        assert _facts(live) != before, label
        assert session.log.undo()
        assert _facts(live) == before, label


@pytest.mark.parametrize("name", ("leftMargin", "spacing"))
def test_preview_end_puts_back_what_the_file_holds(qapp: object, name: str) -> None:
    del qapp
    text = _top("QVBoxLayout", _number("margin", 5) + _number("spacing", 23))
    with opened(text) as (session, realizer):
        layout_id = session.document.by_name("lay")[0]
        live = realizer.layout_for(layout_id)
        assert live is not None
        before = _facts(live)
        realizer.apply_live((LiveProp(layout_id, name, NumberValue(31)),))
        assert 31 in _facts(live)
        realizer.reapply(((layout_id, name),))
        assert _facts(live) == before


def _splitter_form(sizes: str) -> str:
    stored = '<property name="cbcsSplitterSizes" stdset="0"><string>%s</string></property>' % sizes
    return form(
        'class="QWidget" name="Form"',
        """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="box">
   <item>
    <widget class="QSplitter" name="splitter">%s
     <widget class="QTextEdit" name="left"/>
     <widget class="QTextEdit" name="right"/>
    </widget>
   </item>
  </layout>"""
        % stored,
    )


def _shown_sizes(realizer: Realizer, session: FormSession) -> Tuple[int, ...]:
    root = realizer.root_widget
    assert root is not None
    root.show()
    QApplication.processEvents()
    splitter = realizer.widget_for(session.document.by_name("splitter")[0])
    assert isinstance(splitter, QSplitter)
    return tuple(splitter.sizes())


def test_deleting_splitter_sizes_splits_the_panes_by_their_size_hints(qapp: object) -> None:
    del qapp
    with opened(_splitter_form("90,280")) as (session, realizer):
        first, second = _shown_sizes(realizer, session)
        assert second > first
        splitter_id = session.document.by_name("splitter")[0]
        session.log.execute(SetProperty(splitter_id, "cbcsSplitterSizes", None))
        left, right = _shown_sizes(realizer, session)
        assert abs(left - right) <= 1
        fresh = Realizer(session)
        try:
            fresh.build()
            assert _shown_sizes(fresh, session) == (left, right)
        finally:
            fresh.dispose()
        assert session.log.undo()
        assert _shown_sizes(realizer, session) == (first, second)
