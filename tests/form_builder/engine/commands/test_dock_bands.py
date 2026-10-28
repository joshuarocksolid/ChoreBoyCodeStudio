"""Dock bands in a main window (UX-CONT-012): nearest band, central refusal, the side as a number."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import MoveNodes
from app.features.form_builder.engine.commands.drop_plan import commands_for
from app.features.form_builder.engine.query.drop_target import (
    DOCK_REFUSAL,
    AcceptedDrop,
    DropPayload,
    RefusedDrop,
    _widget_host,
    resolve_drop,
)
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit

MAIN = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Main</class>
 <widget class="QMainWindow" name="Main">
  <widget class="QWidget" name="centralwidget"/>
  <widget class="QDockWidget" name="dock">
   <attribute name="dockWidgetArea"><number>1</number></attribute>
   <widget class="QWidget" name="dockContents"/>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

MAIN_RECT = Rect(0, 0, 400, 300)


def _host(doc):  # type: ignore[no-untyped-def]
    rects = {nid(doc, "Main"): MAIN_RECT, nid(doc, "centralwidget"): Rect(32, 32, 336, 236)}
    host = _widget_host(doc, rects, nid(doc, "Main"), "Main")
    assert host is not None
    return host


def _dock_payload(doc):  # type: ignore[no-untyped-def]
    return DropPayload("widget", (nid(doc, "dock"),), dock=True)


@pytest.mark.parametrize(
    ("pointer", "side"),
    [((4, 150), "Left"), ((396, 150), "Right"), ((200, 4), "Top"), ((200, 296), "Bottom")],
)
def test_the_nearest_band_picks_the_side(pointer, side) -> None:  # type: ignore[no-untyped-def]
    log = open_log(MAIN)
    doc = log.document
    target = resolve_drop(_host(doc), pointer, _dock_payload(doc))
    assert isinstance(target, AcceptedDrop)
    assert target.action == "dock_side"
    assert target.dock_side == side


def test_the_central_area_refuses_a_dock_with_the_spec_sentence() -> None:
    log = open_log(MAIN)
    doc = log.document
    target = resolve_drop(_host(doc), (200, 150), _dock_payload(doc))
    assert isinstance(target, RefusedDrop)
    assert target.sentence == DOCK_REFUSAL == "In a main window, a dock widget goes on one of its sides."


def test_dropping_on_a_band_writes_the_side_as_the_attribute_number() -> None:
    log = open_log(MAIN)
    doc = log.document
    target = resolve_drop(_host(doc), (396, 150), _dock_payload(doc))
    assert isinstance(target, AcceptedDrop)
    for command in commands_for(doc, target, _dock_payload(doc), None):
        assert isinstance(command, MoveNodes)
        log.execute(command)
    dock = doc.node(nid(doc, "dock"))
    assert isinstance(dock, WidgetNode)
    entry = dock.attr("dockWidgetArea")
    assert entry is not None and getattr(entry.value, "value", None) == 2
    assert log.undo()
    assert getattr(doc.node(nid(doc, "dock")).attr("dockWidgetArea").value, "value", None) == 1  # type: ignore[union-attr]


def test_a_new_dock_from_insert_lands_on_the_band_side() -> None:
    """Dragging the Dock widget tile (a fragment, no source ids) onto the bottom band."""
    from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec

    log = open_log(MAIN)
    doc = log.document
    payload = DropPayload("widget", dock=True)
    target = resolve_drop(_host(doc), (200, 296), payload)
    assert isinstance(target, AcceptedDrop) and target.dock_side == "Bottom"
    fragment = Fragment((NodeSpec("widget", None, (("class_name", "QDockWidget"), ("object_name", "dockWidget"))),))
    commands = commands_for(doc, target, payload, fragment)
    assert commands
    for command in commands:
        log.execute(command)
    docks = [
        child
        for child in doc.node(nid(doc, "Main")).child_widgets  # type: ignore[attr-defined]
        if child.class_name == "QDockWidget" and child.object_name != "dock"
    ]
    assert len(docks) == 1
    entry = docks[0].attr("dockWidgetArea")
    assert entry is not None and getattr(entry.value, "value", None) == 8
