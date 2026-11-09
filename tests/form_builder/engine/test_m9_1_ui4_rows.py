# pyright: reportAttributeAccessIssue=false
"""ui4 catalog rows the ledger still had open.

Each element is read into the document, kept through a second save, and still
present after a window-title edit. QUiLoader and uic are checked for the
facts they actually apply.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import ItemNode, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.engine.ui4.writer import write_ui

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="windowTitle">
   <string>Hello</string>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <spacer name="verticalSpacer">
     <property name="orientation">
      <enum>Qt::Vertical</enum>
     </property>
     <property name="sizeHint" stdset="0">
      <size>
       <width>20</width>
       <height>40</height>
      </size>
     </property>
    </spacer>
   </item>
  </layout>
  <widget class="QLabel" name="nameLabel">
   <class>CompatLabel</class>
   <property name="text">
    <string>Name</string>
   </property>
   <script>keep</script>
   <widgetdata>keep</widgetdata>
  </widget>
  <widget class="QListWidget" name="listWidget">
   <item>
    <property name="text">
     <string>Alpha</string>
    </property>
   </item>
  </widget>
  <widget class="QTreeWidget" name="treeWidget">
   <item>
    <property name="text">
     <string>Parent</string>
    </property>
    <item>
     <property name="text">
      <string>Child</string>
     </property>
    </item>
   </item>
  </widget>
  <widget class="QTableWidget" name="tableWidget">
   <row>
    <property name="text">
     <string>Row</string>
    </property>
   </row>
   <column>
    <property name="text">
     <string>Column</string>
    </property>
   </column>
   <item row="0" column="0">
    <property name="text">
     <string>cell</string>
    </property>
   </item>
  </widget>
  <widget class="QWidget" name="stackHost">
   <property name="geometry">
    <rect>
     <x>0</x>
     <y>0</y>
     <width>80</width>
     <height>40</height>
    </rect>
   </property>
   <widget class="QLabel" name="backLabel">
    <property name="geometry">
     <rect>
      <x>0</x>
      <y>0</y>
      <width>40</width>
      <height>20</height>
     </rect>
    </property>
    <property name="text">
     <string>Back</string>
    </property>
   </widget>
   <widget class="QLabel" name="frontLabel">
    <property name="geometry">
     <rect>
      <x>0</x>
      <y>0</y>
      <width>40</width>
      <height>20</height>
     </rect>
    </property>
    <property name="text">
     <string>Front</string>
    </property>
   </widget>
   <zorder>frontLabel</zorder>
   <zorder>backLabel</zorder>
  </widget>
  <widget class="QTabWidget" name="tabs">
   <widget class="QWidget" name="tab">
    <attribute name="title">
     <string>One</string>
    </attribute>
   </widget>
  </widget>
  <widget class="QSpinBox" name="countBox">
   <property name="value">
    <number>7</number>
   </property>
  </widget>
  <action name="actionNew">
   <property name="text">
    <string>New</string>
   </property>
   <attribute name="cbcsActionRole" stdset="0">
    <string>file</string>
   </attribute>
  </action>
  <actiongroup name="tools">
   <attribute name="cbcsGroupNote" stdset="0">
    <string>outer</string>
   </attribute>
  </actiongroup>
 </widget>
 <buttongroups>
  <buttongroup name="choice">
   <attribute name="cbcsGroupId" stdset="0">
    <string>choice</string>
   </attribute>
  </buttongroup>
 </buttongroups>
 <resources/>
 <connections/>
</ui>
"""

_KEPT = (
    "<class>CompatLabel</class>",
    "<script>keep</script>",
    "<widgetdata>keep</widgetdata>",
    '<zorder>frontLabel</zorder>',
    '<zorder>backLabel</zorder>',
    '<spacer name="verticalSpacer">',
    "<number>7</number>",
    "<string>Alpha</string>",
    "<string>Parent</string>",
    "<string>Child</string>",
    "<string>Row</string>",
    "<string>Column</string>",
    "<string>cell</string>",
    'name="title"',
    'name="cbcsActionRole"',
    'name="cbcsGroupNote"',
    'name="cbcsGroupId"',
)


def _stable(text: str) -> str:
    saved = write_ui(read_ui(text, allocator=IdAllocator()).document).text
    assert write_ui(read_ui(saved, allocator=IdAllocator()).document).text == saved
    return saved


def _opaque_text(node: WidgetNode, tag: str) -> str:
    for child in node.children("opaque"):
        element = child.field("element")
        if isinstance(element, OpaqueElement) and element.tag == tag:
            return "".join(part for part in element.children if isinstance(part, str))
    raise AssertionError(tag)


def _string_attr(node: object, name: str) -> str:
    entries = node.attributes()  # type: ignore[attr-defined]
    found = next(entry for entry in entries if entry.name == name)
    assert isinstance(found.value, StringValue)
    return found.value.text


def _uic_body(uic: Path, text: str, directory: Path, name: str) -> str:
    source = directory / name
    source.write_text(text, encoding="utf-8")
    completed = subprocess.run(
        [str(uic), "-g", "python", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [
        line
        for line in completed.stdout.splitlines()
        if not line.startswith("## Form generated from reading UI file")
    ]
    return "\n".join(lines)


def _uic_path() -> Optional[Path]:
    raw = os.environ.get("CBCS_FB_UIC", "")
    candidates = [Path(raw)] if raw else []
    candidates.extend(
        (
            Path("/usr/local/bin/cbcs-fb-uic"),
            Path("/opt/freecad-1.1/usr/lib/qt6/libexec/uic"),
            Path("/opt/freecad-1.1/usr/lib/qt6/bin/uic"),
            Path("/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"),
        )
    )
    for path in candidates:
        if path.is_file() and os.access(str(path), os.X_OK):
            return path
    return None


def _loaded(text: str) -> dict:
    from app.qt.QtCore import QBuffer, QIODevice, QPoint
    from app.qt.QtUiTools import QUiLoader
    from app.qt.QtWidgets import (
        QLabel,
        QListWidget,
        QSpinBox,
        QTabWidget,
        QTableWidget,
        QTreeWidget,
        QVBoxLayout,
        QWidget,
    )

    buffer = QBuffer()
    buffer.setData(text.encode("utf-8"))
    buffer.open(QIODevice.ReadOnly)
    window = QUiLoader().load(buffer)
    assert isinstance(window, QWidget)
    window.show()
    label = window.findChild(QLabel, "nameLabel")
    listed = window.findChild(QListWidget, "listWidget")
    tree = window.findChild(QTreeWidget, "treeWidget")
    table = window.findChild(QTableWidget, "tableWidget")
    host = window.findChild(QWidget, "stackHost")
    tabs = window.findChild(QTabWidget, "tabs")
    spin = window.findChild(QSpinBox, "countBox")
    layout = window.findChild(QVBoxLayout, "verticalLayout")
    assert label is not None and listed is not None and tree is not None
    assert table is not None and host is not None and tabs is not None
    assert spin is not None and layout is not None
    parent = tree.topLevelItem(0)
    nested = None if parent is None else parent.child(0)
    top = host.childAt(QPoint(10, 10))
    row = table.verticalHeaderItem(0)
    column = table.horizontalHeaderItem(0)
    cell = table.item(0, 0)
    spacer = layout.itemAt(0).spacerItem() if layout.count() else None
    facts = {
        "label": type(label).__name__,
        "list": listed.item(0).text() if listed.item(0) is not None else "",
        "tree": "" if parent is None else parent.text(0),
        "nested": "" if nested is None else nested.text(0),
        "row": "" if row is None else row.text(),
        "column": "" if column is None else column.text(),
        "cell": "" if cell is None else cell.text(),
        "top": "" if top is None else top.objectName(),
        "tab": tabs.tabText(0),
        "number": spin.value(),
        "spacer": spacer is not None,
    }
    window.hide()
    window.deleteLater()
    return facts


@pytest.mark.parity("R3-257")
@pytest.mark.parity("R3-259")
@pytest.mark.parity("R3-260")
@pytest.mark.parity("R3-261")
@pytest.mark.parity("R3-262")
@pytest.mark.parity("R3-263")
@pytest.mark.parity("R3-264")
@pytest.mark.parity("R3-270")
@pytest.mark.parity("R3-273")
@pytest.mark.parity("R3-301")
def test_catalog_elements_survive_an_edit_and_loader_agrees(qapp: object, tmp_path: Path) -> None:
    del qapp
    document = read_ui(_FORM, allocator=IdAllocator()).document
    label = document.node(document.by_name("nameLabel")[0])
    assert isinstance(label, WidgetNode)
    assert label.class_name == "QLabel"
    assert _opaque_text(label, "class") == "CompatLabel"
    assert _opaque_text(label, "script") == "keep"
    assert _opaque_text(label, "widgetdata") == "keep"
    host = document.node(document.by_name("stackHost")[0])
    assert isinstance(host, WidgetNode)
    assert host.zorder == ("frontLabel", "backLabel")
    table = document.node(document.by_name("tableWidget")[0])
    assert isinstance(table, WidgetNode)
    assert table.children("rows")[0].field("axis") == "row"
    assert table.children("columns")[0].field("axis") == "column"
    cell = table.children("items")[0]
    assert isinstance(cell, ItemNode)
    assert cell.row == 0 and cell.column == 0
    tree = document.node(document.by_name("treeWidget")[0])
    assert isinstance(tree, WidgetNode)
    parent = tree.children("items")[0]
    assert isinstance(parent, ItemNode)
    assert parent.children("subitems")[0].kind == "item"
    spacer = next(node for node in document.iter_preorder() if isinstance(node, SpacerNode))
    assert spacer.name == "verticalSpacer"
    count = document.node(document.by_name("countBox")[0])
    number = count.prop("value")
    assert number is not None and number.value == NumberValue(7)
    tab = document.node(document.by_name("tab")[0])
    assert _string_attr(tab, "title") == "One"
    action = next(node for node in document.root.children("actions") if node.field("name") == "actionNew")
    assert _string_attr(action, "cbcsActionRole") == "file"
    group = document.root.children("action_groups")[0]
    assert _string_attr(group, "cbcsGroupNote") == "outer"
    buttons = document.ui.children("buttongroups")[0]
    assert _string_attr(buttons, "cbcsGroupId") == "choice"

    saved = _stable(_FORM)
    for piece in _KEPT:
        assert piece in saved
    before = _loaded(saved)
    scope = FormScope(kind="external", ui_path=str(tmp_path / "form.ui"))
    session = FormSession.open(saved, path=scope.ui_path, scope=scope)
    session.log.execute(SetProperty(session.document.root.id, "windowTitle", StringValue("Edited")))
    edited = write_ui(session.document).text
    assert write_ui(read_ui(edited, allocator=IdAllocator()).document).text == edited
    assert "<string>Edited</string>" in edited
    for piece in _KEPT:
        assert piece in edited
    after = _loaded(edited)
    assert before == after
    assert before == {
        "label": "QLabel",
        "list": "Alpha",
        "tree": "Parent",
        "nested": "Child",
        "row": "Row",
        "column": "Column",
        "cell": "cell",
        "top": "backLabel",
        "tab": "One",
        "number": 7,
        "spacer": True,
    }
    uic = _uic_path()
    if uic is None:
        return
    original = _uic_body(uic, saved, tmp_path, "before.ui")
    rewritten = _uic_body(uic, edited, tmp_path, "after.ui")
    assert original.replace("Hello", "TITLE").replace("before.ui", "FILE") == rewritten.replace(
        "Edited", "TITLE"
    ).replace("after.ui", "FILE")
