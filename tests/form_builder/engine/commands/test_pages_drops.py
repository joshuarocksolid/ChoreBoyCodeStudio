"""Drops into page containers and dock sides (UX-CONT-009, UX-CONT-012)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import MoveNodes
from app.features.form_builder.engine.commands.drop_plan import commands_for
from app.features.form_builder.engine.commands.placement import AsMainWindowPart
from app.features.form_builder.engine.commands.planning import dock_area_number
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, DropPayload, _widget_host, resolve_drop
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from tests.form_builder.engine.commands._support import nid, open_log, saved

pytestmark = pytest.mark.unit

EMPTY_TABS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QTabWidget" name="tabs"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

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


def _button(name: str) -> Fragment:
    spec = NodeSpec(
        "widget",
        None,
        (("class_name", "QPushButton"), ("object_name", name)),
        (PropertyEntry("property", "text", StringValue(name)),),
    )
    return Fragment((spec,))


def test_a_drop_on_an_empty_tab_widget_makes_the_first_page() -> None:
    log = open_log(EMPTY_TABS)
    doc = log.document
    tabs = nid(doc, "tabs")
    rect = Rect(0, 0, 200, 120)
    host = _widget_host(doc, {tabs: rect}, tabs, "tabs")
    assert host is not None
    target = resolve_drop(host, (50, 40), DropPayload("widget"))
    assert isinstance(target, AcceptedDrop)
    assert target.action == "new_page"
    assert target.host == tabs
    for command in commands_for(doc, target, DropPayload("widget"), _button("okButton")):
        log.execute(command)
    widget = doc.node(tabs)
    assert isinstance(widget, WidgetNode)
    assert len(widget.child_widgets) == 1
    assert widget.child_widgets[0].attr("title") is not None
    page = widget.child_widgets[0]
    assert page.object_name == "tab"
    content = page.layout.items[0].content  # type: ignore[union-attr]
    assert isinstance(content, WidgetNode) and content.object_name == "okButton"
    assert log.undo()
    assert len(doc.node(tabs).child_widgets) == 0  # type: ignore[attr-defined]


def test_dock_side_is_the_dock_area_number() -> None:
    assert dock_area_number("Left") == 1
    assert dock_area_number("RightDockWidgetArea") == 2
    assert dock_area_number("Top") == 4
    assert dock_area_number("Bottom") == 8
    with pytest.raises(CommandRejected):
        dock_area_number("Centre")


def test_moving_a_dock_into_a_main_window_writes_its_side_as_a_number() -> None:
    log = open_log(MAIN)
    doc = log.document
    main = nid(doc, "Main")
    dock = nid(doc, "dock")
    log.execute(MoveNodes((dock,), AsMainWindowPart(main, "dock", "Bottom")))
    dock_node = doc.node(dock)
    attr = dock_node.attr("dockWidgetArea")  # type: ignore[union-attr]
    assert attr is not None and isinstance(attr.value, NumberValue) and attr.value.value == 8
    assert attr.kind == "attribute"
    assert "dockWidgetArea" not in [entry.name for entry in dock_node.properties()]  # type: ignore[union-attr]
    assert "<number>8</number>" in saved(doc)
