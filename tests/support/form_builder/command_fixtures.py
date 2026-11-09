"""Fixtures for command-log tests. Not collected."""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.commands.log import CommandLog, SelectionSnapshot
from app.features.form_builder.engine.events import PRIORITY_SELECTION_NOTIFY
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, WidgetNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui

BOX = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="label">
     <property name="text">
      <string>Hi</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

GRID = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0">
    <widget class="QPushButton" name="a">
     <property name="text"><string>A</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QPushButton" name="b">
     <property name="text"><string>B</string></property>
    </widget>
   </item>
   <item row="1" column="0">
    <widget class="QPushButton" name="c">
     <property name="text"><string>C</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

FREE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QLabel" name="label">
   <property name="text"><string>Hi</string></property>
  </widget>
  <widget class="QPushButton" name="okButton">
   <property name="text"><string>OK</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

STACK = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QStackedWidget" name="Form">
  <property name="currentIndex">
   <number>0</number>
  </property>
  <widget class="QWidget" name="pageA"/>
  <widget class="QWidget" name="pageB"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

SHARED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QPushButton" name="same">
   <property name="text"><string>A</string></property>
  </widget>
  <widget class="QLabel" name="same">
   <property name="text"><string>B</string></property>
  </widget>
  <widget class="QLabel" name="caption">
   <property name="buddy"><cstring>same</cstring></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def open_log(text: str, *, undo_limit: int = 2000) -> CommandLog:
    """A log whose selection provider follows the log's published selection."""
    allocator = IdAllocator()
    document = read_ui(text, allocator=allocator).document
    holder = {"snap": SelectionSnapshot((), None)}

    def provider() -> SelectionSnapshot:
        return holder["snap"]

    log = CommandLog(document, allocator, selection_provider=provider, undo_limit=undo_limit)

    def remember(_change_set: object) -> None:
        holder["snap"] = log.selection

    log.subscribe(remember, priority=PRIORITY_SELECTION_NOTIFY)
    return log


def nid(doc: UiDocument, name: str) -> NodeId:
    found = doc.by_name(name)
    assert found, name
    return found[0]


def prop_text(doc: UiDocument, name: str, key: str = "text") -> Optional[str]:
    entry = doc.node(nid(doc, name)).prop(key)
    if entry is None:
        return None
    return getattr(entry.value, "text", None)


def button_spec(name: str, text: str = "Go") -> NodeSpec:
    return NodeSpec(
        "widget",
        None,
        (("class_name", "QPushButton"), ("object_name", name)),
        (PropertyEntry("property", "text", StringValue(text)),),
    )


def layout_widgets(doc: UiDocument) -> Tuple[NodeId, ...]:
    layout = doc.root.layout
    assert layout is not None
    found = []
    for item in layout.items:
        content = item.content
        if isinstance(content, WidgetNode):
            found.append(content.id)
    return tuple(found)


def cell_of(doc: UiDocument, name: str) -> Tuple[Optional[int], Optional[int]]:
    node = doc.node(nid(doc, name))
    parent = doc.parent(node.id)
    assert isinstance(parent, LayoutItemNode)
    return parent.row, parent.column


def saved(doc: UiDocument) -> str:
    return write_ui(doc).text
