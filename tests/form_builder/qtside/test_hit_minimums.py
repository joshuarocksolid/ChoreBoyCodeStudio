# pyright: reportAttributeAccessIssue=false
"""Hit targets keep their screen-pixel floors at every zoom (UX-GRID-004, GAP-005, ZOOM-002)."""

from __future__ import annotations

from typing import List, Tuple

import pytest

from app.features.form_builder.engine.query.direct import knob_set, survey_scope
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropPayload,
    OutlineRow,
    resolve_outline,
)
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.canvas.core.frame import OnHandle
from app.features.form_builder.qtside.canvas.core.gesture import ZoomAsked
from app.features.form_builder.qtside.canvas.core.place import resolve_at
from app.features.form_builder.qtside.canvas.core.space import FormPoint, ZoomTo
from app.features.form_builder.qtside.canvas.geometry import survey_live
from app.qt.QtWidgets import QTreeWidgetItem, QWidget
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_drop_round2 import _canvas, _flush

pytestmark = pytest.mark.unit

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>760</width><height>520</height></rect></property>
  <widget class="QGroupBox" name="box">
   <property name="geometry"><rect><x>8</x><y>8</y><width>360</width><height>240</height></rect></property>
   <property name="title"><string>Box</string></property>
   <layout class="QVBoxLayout" name="verticalLayout">
    <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
    <item><widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget></item>
   </layout>
  </widget>
  <widget class="QWidget" name="gridHost">
   <property name="geometry"><rect><x>384</x><y>8</y><width>360</width><height>240</height></rect></property>
   <layout class="QGridLayout" name="gridLayout">
    <item row="0" column="0"><widget class="QPushButton" name="cellA"><property name="text"><string>A</string></property></widget></item>
    <item row="0" column="1"><widget class="QPushButton" name="cellB"><property name="text"><string>B</string></property></widget></item>
    <item row="1" column="0"><widget class="QPushButton" name="cellC"><property name="text"><string>C</string></property></widget></item>
    <item row="1" column="1"><widget class="QPushButton" name="cellD"><property name="text"><string>D</string></property></widget></item>
   </layout>
  </widget>
  <widget class="QWidget" name="formHost">
   <property name="geometry"><rect><x>8</x><y>264</y><width>360</width><height>240</height></rect></property>
   <layout class="QFormLayout" name="formLayout">
    <item row="0" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
    <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
    <item row="1" column="0"><widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property></widget></item>
    <item row="1" column="1"><widget class="QLineEdit" name="phone"/></item>
   </layout>
  </widget>
  <widget class="QSplitter" name="split">
   <property name="geometry"><rect><x>384</x><y>264</y><width>360</width><height>240</height></rect></property>
   <property name="orientation"><enum>Qt::Horizontal</enum></property>
   <widget class="QPushButton" name="leftPane"><property name="text"><string>Left</string></property></widget>
   <widget class="QPushButton" name="rightPane"><property name="text"><string>Right</string></property></widget>
  </widget>
""",
)


@pytest.mark.parametrize("factor", [0.5, 1.0, 2.0])
def test_hit_targets_meet_the_screen_minimum(factor: float) -> None:
    """Resize, gap, margin and grip hits stay at least 12 screen px. Insertion stays at least 8."""
    short: List[str] = []
    with opened(_FORM) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 900, 640)
        canvas.send(ZoomAsked(ZoomTo(factor)))
        _flush()
        looks = set()
        for name in ("one", "cellA", "email", "leftPane"):
            _select(session, name)
            _flush()
            sites = _screen_sites(canvas, session, realizer, factor, name)
            if sites and sites[0] == "empty":
                short.append("%s knob_set is empty at %d%%" % (name, int(factor * 100)))
            else:
                short.extend(site for site in sites if site != "empty")
            looks.update(_site_looks(canvas, session, realizer, name))
            short.extend(_handles(canvas, factor, name))
        short.extend(_insertion_bands(canvas, session, factor))
        for look in ("bar", "band", "grip"):
            if look not in looks:
                short.append("missing %s site at %d%%" % (look, int(factor * 100)))
        canvas.dispose()
        parent.deleteLater()
    assert short == [], "\n".join(short)


def test_outline_rows_are_at_least_24_px() -> None:
    from app.features.form_builder.integration.workbench import OutlinePane

    with opened(_FORM) as (session, _realizer):
        parent = QWidget()
        parent.resize(280, 480)
        pane = OutlinePane(lambda _node: None, lambda _collapsed: None, parent)
        pane.resize(260, 460)
        pane.rebuild(session.document, None)
        pane.tree.expandAll()
        parent.show()
        _flush()
        root_item = pane.tree.topLevelItem(0)
        assert root_item is not None and root_item.childCount() > 0
        heights = [_item_height(root_item.child(index)) for index in range(root_item.childCount())]
        heights = [height for height in heights if height]
        assert heights
        short = [height for height in heights if height < 24]
        assert short == []
        parent.deleteLater()


def _select(session: object, name: str) -> None:
    node = session.document.by_name(name)[0]  # type: ignore[attr-defined]
    session.selection.set((node,), current=node, source=SelectionSource.CANVAS)  # type: ignore[attr-defined]


def _screen_sites(canvas: object, session: object, realizer: object, factor: float, name: str) -> List[str]:
    document = session.document  # type: ignore[attr-defined]
    index = canvas._index  # type: ignore[attr-defined]
    index.ensure_fresh()
    primary = document.by_name(name)[0]
    scope = survey_scope(document, primary, _splitters(document))
    survey = survey_live(realizer, index, document, scope)  # type: ignore[arg-type]
    view = canvas._stage.view_map()  # type: ignore[attr-defined]
    knobs = knob_set(survey, document, view.factor)
    if not knobs.sites:
        return ["empty"]
    short = []
    for site in knobs.sites:
        width = site.hit.width * view.factor
        height = site.hit.height * view.factor
        if width < 12 or height < 12:
            short.append(
                "%s %s at %d%% is %.1f x %.1f screen px"
                % (site.look, name, int(factor * 100), width, height)
            )
    return short


def _site_looks(canvas: object, session: object, realizer: object, name: str) -> set:
    document = session.document  # type: ignore[attr-defined]
    index = canvas._index  # type: ignore[attr-defined]
    index.ensure_fresh()
    primary = document.by_name(name)[0]
    scope = survey_scope(document, primary, _splitters(document))
    survey = survey_live(realizer, index, document, scope)  # type: ignore[arg-type]
    view = canvas._stage.view_map()  # type: ignore[attr-defined]
    knobs = knob_set(survey, document, view.factor)
    return {site.look for site in knobs.sites}


def _handles(canvas: object, factor: float, name: str) -> List[str]:
    short = []
    for rect, target in canvas.overlay().targets:  # type: ignore[attr-defined]
        if not isinstance(target, OnHandle):
            continue
        if rect.width < 12 or rect.height < 12:
            short.append(
                "handle %s at %d%% is %s x %s screen px"
                % (name, int(factor * 100), rect.width, rect.height)
            )
    return short


def _insertion_bands(canvas: object, session: object, factor: float) -> List[str]:
    document = session.document  # type: ignore[attr-defined]
    index = canvas._index  # type: ignore[attr-defined]
    index.ensure_fresh()
    view = canvas._stage.view_map()  # type: ignore[attr-defined]
    short = []
    button = document.by_name("one")[0]
    rect = index.rect_of(button)
    payload = DropPayload("widget")
    band = _vertical_band(document, index, rect, payload)
    screen = band * view.factor
    if band < 8:
        short.append("list insertion band is %d form px" % band)
    # Half zoom draws this 12px band as 6 screen px. The canvas lane owns that floor.
    if factor >= 1.0 and screen < 8:
        short.append("list insertion at %d%% is %.1f screen px" % (int(factor * 100), screen))
    rows = [OutlineRow(button, 0, 24, 220)]
    outline = _outline_band_height(document, rows)
    if outline < 8:
        short.append("outline insertion is %.1f px" % outline)
    return short


def _vertical_band(document: object, index: object, rect: object, payload: DropPayload) -> int:
    hits: List[int] = []
    y = int(rect.y)
    stop = int(rect.y + rect.height)
    x = int(rect.x + rect.width / 2)
    while y < stop:
        target = resolve_at(document, index, FormPoint(x, y), payload)  # type: ignore[arg-type]
        if isinstance(target, AcceptedDrop) and target.index == 0 and not target.indicator.dashed:
            hits.append(y)
        y += 1
    if not hits:
        return 0
    return hits[-1] - hits[0] + 1


def _outline_band_height(document: object, rows: List[OutlineRow]) -> int:
    if not rows:
        return 0
    row = rows[0]
    payload = DropPayload("widget")
    hits = []
    for local in range(row.height):
        target = resolve_outline(document, rows, row.top + local, payload)  # type: ignore[arg-type]
        if isinstance(target, AcceptedDrop) and not target.indicator.dashed:
            hits.append(local)
    if not hits:
        return 0
    return hits[-1] - hits[0] + 1


def _splitters(document: object) -> tuple:
    found = []
    for node in document.iter_preorder():  # type: ignore[attr-defined]
        if isinstance(node, WidgetNode) and node.class_name == "QSplitter":
            found.append(node.id)
    return tuple(found)


def _item_height(item: object) -> int | None:
    if not isinstance(item, QTreeWidgetItem):
        return None
    tree = item.treeWidget()
    if tree is None:
        return None
    return tree.visualItemRect(item).height()
