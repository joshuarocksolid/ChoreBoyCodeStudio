
from __future__ import annotations

from typing import Dict, Optional, Tuple, Type

import pytest

from app.features.form_builder.engine.commands.catalog import (
    SetGeometry,
    SetProperty,
    SetPropertyMany,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode
from app.features.form_builder.engine.ui4.values import RectValue, SetValue, StringValue
from app.features.form_builder.qtside.inspector.api import (
    EnumSpec,
    GroupId,
    LockedRow,
    Mixed,
    OpenRow,
    Row,
    RowValue,
    Unset,
    Written,
)
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.model import (
    FormBody,
    LiveClass,
    LiveProperty,
    NodeBody,
    OneHeader,
    project,
    project_header,
)

pytestmark = pytest.mark.unit

_UI_PATH = "/tmp/proj/forms/invoice.ui"

_WIDGET = (
    LiveProperty("objectName", "QObject", "string"),
    LiveProperty("geometry", "QWidget", "rect"),
    LiveProperty("toolTip", "QWidget", "string"),
)
_LIVE: Dict[str, LiveClass] = {
    "QLineEdit": LiveClass(
        chain=("QLineEdit", "QWidget", "QObject"),
        properties=_WIDGET
        + (
            LiveProperty("text", "QLineEdit", "string"),
            LiveProperty("maxLength", "QLineEdit", "number"),
            LiveProperty(
                "echoMode",
                "QLineEdit",
                "enum",
                EnumSpec("QLineEdit", "EchoMode", ("Normal", "NoEcho", "Password"), False),
            ),
        ),
        signals=("textChanged(QString)",),
        slots=(),
    ),
    "QPushButton": LiveClass(
        chain=("QPushButton", "QAbstractButton", "QWidget", "QObject"),
        properties=_WIDGET + (LiveProperty("text", "QAbstractButton", "string"),),
        signals=("clicked()",),
        slots=(),
    ),
}

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>640</width><height>480</height></rect>
  </property>
  <property name="windowTitle">
   <string>Invoice form</string>
  </property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLineEdit" name="email">
     <property name="text">
      <string>Pay</string>
     </property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="phone"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_FREE_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <widget class="QLineEdit" name="nameEdit">
   <property name="geometry">
    <rect><x>10</x><y>10</y><width>100</width><height>24</height></rect>
   </property>
  </widget>
  <widget class="QPushButton" name="okButton">
   <property name="geometry">
    <rect><x>10</x><y>40</y><width>80</width><height>24</height></rect>
   </property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_GRID_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0">
    <widget class="QLabel" name="caption"/>
   </item>
   <item row="1" column="2" colspan="2">
    <widget class="QLabel" name="total"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_PAIR_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  %s
  %s
 </widget>
 <resources/>
 <connections/>
</ui>
"""

def _tooltip(name: str, text: Optional[str]) -> str:
    if text is None:
        return '<widget class="QLineEdit" name="%s"/>' % name
    return (
        '<widget class="QLineEdit" name="%s"><property name="toolTip"><string>%s</string></property></widget>'
        % (name, text)
    )

def _two_line_edits(first: Optional[str], second: Optional[str]) -> str:
    return _PAIR_FORM % (_tooltip("first", first), _tooltip("second", second))

def _open(xml: str) -> FormSession:
    return FormSession.open(xml, path=_UI_PATH, scope=classify_form(_UI_PATH, project_root="/tmp/proj"))

def _select(session: FormSession, *names: str) -> Tuple[NodeId, ...]:
    ids = tuple(session.document.by_name(name)[0] for name in names)
    session.selection.set(ids, source=SelectionSource.PROGRAM)
    return ids

def _body(session: FormSession, search: str = "") -> NodeBody:
    live = {
        node.id: _LIVE[node.class_name]
        for node in session.document.iter_widgets()
        if node.class_name in _LIVE
    }
    body = project(session, default_catalog(), search=search, live=live).body
    assert isinstance(body, NodeBody)
    return body

def _row(body: NodeBody, key: str, group: Optional[GroupId] = None) -> Row:
    found = body.find(key) if group is None else body.group(group).find(key)
    assert found is not None, key
    return found

def _open_row(body: NodeBody, key: str, group: Optional[GroupId] = None) -> OpenRow:
    found = _row(body, key, group)
    assert isinstance(found, OpenRow), found
    return found

def test_one_edit_is_one_undoable_set_property() -> None:
    session = _open(_FORM)
    (email,) = _select(session, "email")

    command = _open_row(_body(session), "text").write.edit(StringValue("Paid"), None)
    session.log.execute(command)

    assert isinstance(command, SetProperty)
    assert session.document.node(email).value("text") == StringValue("Paid")
    assert session.log.undo()
    assert session.document.node(email).value("text") == StringValue("Pay")

def test_reset_removes_the_entry() -> None:
    session = _open(_FORM)
    (email,) = _select(session, "email")

    command = _open_row(_body(session), "text").write.reset()
    session.log.execute(command)

    assert command == SetProperty(email, "text", None)
    assert session.document.node(email).prop("text") is None
    assert isinstance(_row(_body(session), "text").value, Unset)

def test_multi_select_edit_is_one_set_property_many_step() -> None:
    session = _open(_FORM)
    email, phone = _select(session, "email", "phone")
    before = len(session.log.entries())

    command = _open_row(_body(session), "text").write.edit(StringValue("Same"), None)
    session.log.execute(command)

    assert isinstance(command, SetPropertyMany)
    assert len(session.log.entries()) == before + 1
    assert session.document.node(phone).value("text") == StringValue("Same")
    assert session.log.undo()
    assert session.document.node(email).value("text") == StringValue("Pay")
    assert session.document.node(phone).prop("text") is None

@pytest.mark.parametrize(
    "first, second, expected",
    [("a", "a", Written), ("a", "b", Mixed), ("a", None, Mixed), (None, None, Unset)],
)
def test_row_value_follows_the_owners_entries(
    first: Optional[str], second: Optional[str], expected: Type[RowValue]
) -> None:
    session = _open(_two_line_edits(first, second))
    _select(session, "first", "second")

    assert type(_row(_body(session), "toolTip").value) is expected

@pytest.mark.parametrize(
    "search, group, key, where",
    [
        ("echo", GroupId.INPUT, "echoMode", "label"),
        ("maxLength", GroupId.INPUT, "maxLength", "qt_name"),
        ("Pay", GroupId.CONTENT, "text", "value"),
    ],
)
def test_search_keeps_only_matching_rows(search: str, group: GroupId, key: str, where: str) -> None:
    session = _open(_FORM)
    _select(session, "email")

    body = _body(session, search)

    match = _row(body, key, group).match
    assert match is not None and match.where == where
    assert all(row.match is not None for view in body.groups for row in view.rows())
    assert GroupId.ACCESSIBILITY not in [view.group for view in body.groups]

def test_empty_selection_shows_the_form_section() -> None:
    session = _open(_FORM)

    header = project_header(session)
    body = project(session, default_catalog()).body

    assert isinstance(header, OneHeader)
    assert (header.name, header.crumbs) == ("Invoice", ())
    assert isinstance(body, FormBody)
    assert isinstance(body.window, OpenRow)
    assert body.window.value == Written(StringValue("Invoice form"))
    assert (body.design_size, body.root_layout, body.tab_order, body.problems, body.files) == (
        "640 \u00d7 480",
        "Vertical layout",
        ("email", "phone", "okButton"),
        "No problems.",
        "Saves invoice.ui and ui_invoice.py in forms/.",
    )

def test_layout_child_geometry_is_set_by_the_layout() -> None:
    session = _open(_FORM)
    _select(session, "email")

    body = _body(session)

    assert [view.group for view in body.groups if view.find("geometry") is not None] == [GroupId.ALL]
    geometry = _row(body, "geometry", GroupId.ALL)
    assert isinstance(geometry, LockedRow)
    assert geometry.reason == "Set by the layout."

def test_one_free_widget_geometry_edit_is_set_geometry() -> None:
    session = _open(_FREE_FORM)
    (name,) = _select(session, "nameEdit")
    rect = RectValue(20, 30, 120, 24)

    write = _open_row(_body(session), "geometry", GroupId.PLACEMENT).write

    assert write.edit(rect, "gesture") == SetGeometry(name, rect, merge_token="gesture")
    assert write.reset() == SetProperty(name, "geometry", None)

def test_several_free_widgets_lock_geometry() -> None:
    session = _open(_FREE_FORM)
    _select(session, "nameEdit", "okButton")

    geometry = _row(_body(session), "geometry", GroupId.PLACEMENT)

    assert isinstance(geometry, LockedRow)
    assert geometry.reason == "Select one widget to edit its position."

def test_cell_alignment_edit_keeps_the_cell() -> None:
    session = _open(_GRID_FORM)
    (total,) = _select(session, "total")
    item = session.document.containing_layout_item(total)
    assert item is not None

    session.log.execute(_open_row(_body(session), "cell.alignment").write.edit(SetValue("Qt::AlignRight"), None))

    cell = session.document.node(item)
    assert isinstance(cell, LayoutItemNode)
    assert (cell.row, cell.column, cell.colspan, cell.alignment) == (1, 2, 2, "Qt::AlignRight")
    assert session.log.undo()
    undone = session.document.node(item)
    assert isinstance(undone, LayoutItemNode)
    assert (undone.row, undone.column, undone.colspan, undone.alignment) == (1, 2, 2, None)
