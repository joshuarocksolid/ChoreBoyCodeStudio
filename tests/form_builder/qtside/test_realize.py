# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Live widgets stay in step with the document. A patch matches a fresh build."""

from __future__ import annotations

import gc
import importlib.abc
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pytest

from app.qt import QtGui, QtWidgets
from app.qt.QtCore import QFile, QIODevice, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtCore import QObject
from app.qt.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QWidget,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.commands.catalog import (
    AddActionRef,
    BreakLayout,
    CreateAction,
    DeleteNodes,
    InsertFragment,
    MorphLayout,
    MorphWidget,
    MoveNodes,
    Rename,
    SetProperty,
    SetZOrder,
)
from app.features.form_builder.engine.commands.placement import InActionList, InBoxLayout, InFormRow
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.qtside.realize import tree as tree_module
from app.features.form_builder.qtside.realize.tree import NODE_ID_PROPERTY
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.engine.commands._support import button_spec
from tests.form_builder.qtside.support import form, open_session, opened, run_module
from tests.support.form_builder.gen import NESTED, command_for

pytestmark = pytest.mark.usefixtures("qapp")

# Qt widget classes this offscreen platform cannot construct. Empty on the
# FreeCAD 1.1 runtime: every Qt class in the corpus built. A new name here is
# a Qt limit, recorded after a corpus run, not a realize bug.
OFFSCREEN_WIDGET_CLASSES = frozenset()

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"

_BOXES = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QHBoxLayout" name="row">
   <item>
    <widget class="QWidget" name="leftPane">
     <layout class="QVBoxLayout" name="left">
      <item><widget class="QLabel" name="stay"><property name="text"><string>a</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="rightPane">
     <layout class="QVBoxLayout" name="right">
      <item><widget class="QPushButton" name="moved"><property name="text"><string>Go</string></property></widget></item>
     </layout>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""

_MAIN = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Main</class>
 <widget class="QMainWindow" name="Main">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QWidget" name="central">
   <widget class="QLabel" name="body"><property name="text"><string>Body</string></property></widget>
  </widget>
  <widget class="QMenuBar" name="menubar">
   <widget class="QMenu" name="menuFile">
    <property name="title"><string>File</string></property>
    <addaction name="actionNew"/>
   </widget>
   <addaction name="menuFile"/>
  </widget>
  <widget class="QToolBar" name="toolBar">
   <property name="windowTitle"><string>Tools</string></property>
   <addaction name="actionNew"/>
  </widget>
  <widget class="QStatusBar" name="statusbar"/>
  <widget class="QDockWidget" name="dock">
   <property name="windowTitle"><string>Dock</string></property>
   <widget class="QLabel" name="dockLabel"><property name="text"><string>Docked</string></property></widget>
  </widget>
  <action name="actionNew"><property name="text"><string>New</string></property></action>
 </widget>
</ui>
"""


class _RecordingFinder(importlib.abc.MetaPathFinder):
    def __init__(self) -> None:
        self.names: List[str] = []

    def find_spec(self, fullname: str, path: object, target: object = None) -> None:
        self.names.append(fullname)
        return None


def _named(session: FormSession, name: str) -> NodeId:
    found = session.document.by_name(name)
    assert found, name
    return found[0]


def _layout_of(session: FormSession, widget_name: str) -> NodeId:
    node = session.document.get(_named(session, widget_name))
    assert isinstance(node, WidgetNode) and isinstance(node.layout, LayoutNode)
    return node.layout.id


def _same(realizer: Realizer, session: FormSession, label: str) -> None:
    other = Realizer(session)
    try:
        other.build()
        left = realizer.signature()
        right = other.signature()
    finally:
        other.dispose()
    if left == right:
        return
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index] != right[index]:
            raise AssertionError(
                "%s differs at %s\npatched %s\nrebuilt %s" % (label, index, left[index], right[index])
            )
    raise AssertionError("%s length %s vs %s" % (label, len(left), len(right)))


def test_dialog_button_box_keeps_the_layout_qt_created() -> None:
    path = _CORPUS / "synthetic" / "widgets" / "QDialogButtonBox.ui"
    text = path.read_text(encoding="utf-8")
    with opened(text, str(path)) as (_session, realizer):
        root = realizer.root_widget
        assert isinstance(root, QDialogButtonBox)
        assert root.layout() is not None
        assert realizer.problems() == ()


def test_move_into_an_earlier_container_keeps_the_widget() -> None:
    with opened(_BOXES) as (session, realizer):
        button = _named(session, "moved")
        live = realizer.widget_for(button)
        session.log.execute(MoveNodes((button,), InBoxLayout(_layout_of(session, "leftPane"), 0)))
        assert realizer.widget_for(button) is live
        assert realizer.last_stats.fallback_rebuilds == 0
        _same(realizer, session, "move")


def test_morph_reuses_child_widgets() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="lay">
   <item><widget class="QPushButton" name="child"><property name="text"><string>Go</string></property></widget></item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        child = _named(session, "child")
        live = realizer.widget_for(child)
        session.log.execute(MorphWidget(session.document.root.id, "QFrame"))
        assert isinstance(realizer.root_widget, QFrame)
        assert realizer.widget_for(child) is live
        assert realizer.last_stats.fallback_rebuilds == 0
        _same(realizer, session, "morph")


def test_containers_round_trip(qapp: object) -> None:
    del qapp
    cases = (
        (
            "tabs",
            form(
                'class="QTabWidget" name="tabs"',
                """
  <widget class="QWidget" name="one"><attribute name="title"><string>One</string></attribute></widget>
  <widget class="QWidget" name="two"><attribute name="title"><string>Two</string></attribute></widget>
""",
            ),
            lambda root: (root.count(), root.tabText(0), root.tabText(1)) == (2, "One", "Two"),
        ),
        (
            "stack",
            form(
                'class="QStackedWidget" name="stack"',
                """
  <widget class="QWidget" name="one"/>
  <widget class="QWidget" name="two"/>
""",
            ),
            lambda root: root.count() == 2 and root.widget(0).objectName() == "one",
        ),
        (
            "box",
            form(
                'class="QToolBox" name="box"',
                """
  <widget class="QWidget" name="one"><attribute name="label"><string>First</string></attribute></widget>
  <widget class="QWidget" name="two"><attribute name="label"><string>Second</string></attribute></widget>
""",
            ),
            lambda root: (root.count(), root.itemText(0)) == (2, "First"),
        ),
        (
            "wizard",
            form(
                'class="QWizard" name="wizard"',
                """
  <widget class="QWizardPage" name="one"><property name="title"><string>Page</string></property></widget>
  <widget class="QWizardPage" name="two"/>
""",
            ),
            lambda root: len(root.pageIds()) == 2,
        ),
        (
            "scroll",
            form(
                'class="QScrollArea" name="scroll"',
                '<widget class="QLabel" name="inner"><property name="text"><string>in</string></property></widget>',
            ),
            lambda root: root.widget() is not None and root.widget().objectName() == "inner",
        ),
        (
            "split",
            form(
                'class="QSplitter" name="split"',
                """
  <property name="cbcsSplitterSizes"><string>200,400</string></property>
  <widget class="QLabel" name="left"/>
  <widget class="QLabel" name="right"/>
""",
            ),
            lambda root: root.count() == 2 and root.sizes()[1] == root.sizes()[0] * 2,
        ),
        (
            "group",
            form(
                'class="QGroupBox" name="group"',
                """
  <property name="title"><string>Group</string></property>
  <layout class="QVBoxLayout" name="lay">
   <item><widget class="QLabel" name="inside"><property name="text"><string>in</string></property></widget></item>
  </layout>
""",
            ),
            lambda root: root.findChild(QLabel, "inside") is not None and root.title() == "Group",
        ),
        (
            "dock",
            form(
                'class="QDockWidget" name="dock"',
                '<widget class="QLabel" name="inside"><property name="text"><string>in</string></property></widget>',
            ),
            lambda root: root.widget() is not None and root.widget().objectName() == "inside",
        ),
        (
            "mdi",
            form(
                'class="QMdiArea" name="mdi"',
                """
  <widget class="QWidget" name="one"/>
  <widget class="QWidget" name="two"/>
""",
            ),
            lambda root: len(root.subWindowList()) == 2,
        ),
    )
    for name, text, check in cases:
        with opened(text) as (session, realizer):
            root = realizer.root_widget
            assert root is not None, name
            assert check(root), name
            assert realizer.problems() == (), (name, realizer.problems())
            _same(realizer, session, name)
            if name == "tabs":
                page = _named(session, "one")
                identity = root
                session.log.execute(SetProperty(page, "title", StringValue("Renamed"), kind="attribute"))
                assert realizer.root_widget is identity
                assert root.tabText(0) == "Renamed"
                assert realizer.last_stats.fallback_rebuilds == 0
                assert realizer.last_stats.created_widgets == 0


def test_main_window_chrome_patches_per_container() -> None:
    with opened(_MAIN) as (session, realizer):
        window = realizer.root_widget
        assert isinstance(window, QMainWindow)
        menu_bar = window.menuBar()
        central = window.centralWidget()
        dock = window.findChild(QDockWidget, "dock")
        toolbar = window.findChild(QToolBar, "toolBar")
        assert isinstance(menu_bar, QMenuBar)
        assert central is not None and central.objectName() == "central"
        assert dock is not None and toolbar is not None
        menu = _named(session, "menuFile")
        session.log.execute(SetProperty(menu, "title", StringValue("Document")))
        assert realizer.root_widget is window
        assert window.menuBar() is menu_bar
        assert window.centralWidget() is central
        assert window.findChild(QDockWidget, "dock") is dock
        assert realizer.last_stats.fallback_rebuilds == 0
        assert realizer.last_stats.created_widgets == 0
        file_menu = realizer.widget_for(menu)
        assert file_menu is not None and file_menu.title() == "Document"
        session.log.execute(AddActionRef(InActionList(menu, 1), "separator"))
        assert window.menuBar() is menu_bar
        assert window.centralWidget() is central
        assert realizer.last_stats.fallback_rebuilds == 0
        assert realizer.last_stats.created_widgets == 0
        _same(realizer, session, "chrome")


def test_widgets_ignore_input_and_carry_their_node_id() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="lay">
   <item><widget class="QSpinBox" name="spin"/></item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        root = realizer.root_widget
        spin_id = _named(session, "spin")
        spin = realizer.widget_for(spin_id)
        assert isinstance(root, QWidget) and isinstance(spin, QSpinBox)
        for widget in (root, spin):
            assert widget.focusPolicy() == Qt.NoFocus
            assert widget.testAttribute(Qt.WA_TransparentForMouseEvents)
            assert widget.property("_cbcsNodeId") == int(realizer.node_for(widget))  # type: ignore[arg-type]
        edit = spin.findChild(QLineEdit)
        assert edit is not None
        assert realizer.node_for(edit) == spin_id
        layout = session.document.root.layout
        assert layout is not None
        assert realizer.layout_for(layout.id) is not None
        assert realizer.object_for(layout.id) is realizer.layout_for(layout.id)


def test_rename_reresolves_buddies_and_zorder_restacks() -> None:
    with opened(NESTED) as (session, realizer):
        label = realizer.widget_for(_named(session, "fl"))
        assert isinstance(label, QLabel)
        assert label.buddy() is not None
        assert label.buddy().objectName() == "fe"
        session.log.execute(Rename(_named(session, "fe"), "fieldTwo"))
        assert label.buddy() is not None
        assert label.buddy().objectName() == "fieldTwo"
        assert realizer.last_stats.fallback_rebuilds == 0
    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QPushButton" name="a"><property name="geometry"><rect><x>0</x><y>0</y><width>40</width><height>20</height></rect></property></widget>
  <widget class="QPushButton" name="b"><property name="geometry"><rect><x>10</x><y>10</y><width>40</width><height>20</height></rect></property></widget>
""",
    )
    with opened(text) as (session, realizer):
        root = realizer.root_widget
        assert isinstance(root, QWidget)
        session.log.execute(SetZOrder(session.document.root.id, ("b", "a")))
        names = [child.objectName() for child in root.children() if child.objectName() in ("a", "b")]
        assert names[-1] == "a"
        assert realizer.last_stats.fallback_rebuilds == 0
        _same(realizer, session, "zorder")


def test_promoted_widgets_do_not_import_user_or_resource_modules(tmp_path: Path) -> None:
    (tmp_path / "my_button.py").write_text("IMPORTED = True\n", encoding="utf-8")
    (tmp_path / "resources_rc.py").write_text("IMPORTED = True\n", encoding="utf-8")
    text = form(
        'class="QWidget" name="Form"',
        '<widget class="MyButton" name="mine"/>',
        """
 <customwidgets>
  <customwidget>
   <class>MyButton</class>
   <extends>QPushButton</extends>
   <header>my_button</header>
  </customwidget>
 </customwidgets>
""",
    )
    sys.path.insert(0, str(tmp_path))
    finder = _RecordingFinder()
    sys.meta_path.insert(0, finder)
    try:
        with opened(text, str(tmp_path / "form.ui")) as (session, realizer):
            mine = realizer.widget_for(_named(session, "mine"))
            assert isinstance(mine, QPushButton)
            assert type(mine) is QPushButton
    finally:
        sys.meta_path.remove(finder)
        sys.path.remove(str(tmp_path))
    loaded = [name for name in finder.names if name == "my_button" or name.endswith("_rc") or name.endswith("_rc.py")]
    assert loaded == []
    assert "my_button" not in sys.modules
    assert "resources_rc" not in sys.modules


def test_resources_register_without_an_rc_module(tmp_path: Path) -> None:
    (tmp_path / "dot.bin").write_bytes(b"HELLO")
    (tmp_path / "demo.qrc").write_text(
        '<!DOCTYPE RCC><RCC version="1.0"><qresource prefix="/cbcs"><file>dot.bin</file></qresource></RCC>\n',
        encoding="utf-8",
    )
    text = form('class="QWidget" name="Form"', "", '<resources><include location="demo.qrc"/></resources>\n')
    with opened(text, str(tmp_path / "form.ui")) as (_session, realizer):
        assert realizer.problems() == ()
        handle = QFile(":/cbcs/dot.bin")
        assert handle.open(QIODevice.ReadOnly)
        assert bytes(handle.readAll()) == b"HELLO"
        handle.close()


FAST_STEPS = 30
FAST_SEEDS = 200
SOAK_STEPS = 50
SOAK_SEEDS = 5000
PINNED_SEEDS = (2, 4, 6, 7, 14, 15, 19, 28, 49, 653, 805, 1219)
PINNED_HASH_SEEDS = ("0", "1")
# Allocator settings that overwrite freed memory, so a use-after-free crashes.
SCRIBBLE_ENV = {"MallocScribble": "1", "MallocPreScribble": "1", "MALLOC_PERTURB_": "165"}


def test_morph_in_a_grid_keeps_the_cell() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0"><widget class="QPushButton" name="a"/></item>
   <item row="0" column="1"><widget class="QPushButton" name="b"/></item>
   <item row="1" column="0" colspan="2"><widget class="QLineEdit" name="c"/></item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        session.log.execute(MorphWidget(_named(session, "b"), "QLabel"))
        assert realizer.last_stats.fallback_rebuilds == 0
        grid = realizer.root_widget.layout()
        assert isinstance(grid, QGridLayout)
        placed = _grid_ids(grid)
        assert placed[_named(session, "b")] == (0, 1, 1, 1)
        _same(realizer, session, "grid morph")


def test_morph_in_a_form_keeps_the_role() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QFormLayout" name="form">
   <item row="0" column="0"><widget class="QLabel" name="lab"><property name="buddy"><cstring>edit</cstring></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="edit"/></item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        session.log.execute(MorphWidget(_named(session, "edit"), "QPushButton"))
        assert realizer.last_stats.fallback_rebuilds == 0
        form_layout = realizer.root_widget.layout()
        assert isinstance(form_layout, QFormLayout)
        role = getattr(getattr(QFormLayout, "ItemRole", QFormLayout), "FieldRole")
        field = form_layout.itemAt(0, role)
        assert field is not None and field.widget() is not None
        assert field.widget().objectName() == "edit"
        label = realizer.widget_for(_named(session, "lab"))
        assert isinstance(label, QLabel)
        assert label.buddy() is not None
        assert label.buddy().objectName() == "edit"
        _same(realizer, session, "form morph")


def test_morph_in_a_box_keeps_the_widget() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="box">
   <item><widget class="QPushButton" name="a"/></item>
   <item><widget class="QPushButton" name="b"/></item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        session.log.execute(MorphWidget(_named(session, "a"), "QLabel"))
        assert realizer.last_stats.fallback_rebuilds == 0
        names = [realizer.root_widget.layout().itemAt(index).widget().objectName() for index in range(2)]
        assert names == ["a", "b"]
        _same(realizer, session, "box morph")


def test_morph_of_a_tab_page_keeps_the_tab() -> None:
    text = form(
        'class="QTabWidget" name="tabs"',
        """
  <widget class="QWidget" name="one"><attribute name="title"><string>One</string></attribute></widget>
  <widget class="QWidget" name="two"><attribute name="title"><string>Two</string></attribute></widget>
""",
    )
    with opened(text) as (session, realizer):
        session.log.execute(MorphWidget(_named(session, "one"), "QFrame"))
        assert realizer.last_stats.fallback_rebuilds == 0
        tabs = realizer.root_widget
        assert isinstance(tabs, QTabWidget)
        assert tabs.count() == 2
        assert tabs.tabText(0) == "One"
        assert tabs.widget(0).objectName() == "one"
        assert isinstance(tabs.widget(0), QFrame)
        _same(realizer, session, "tab morph")


def test_morph_of_a_nested_layout_keeps_children_parented() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="outer">
   <item>
    <layout class="QHBoxLayout" name="inner">
     <item><widget class="QPushButton" name="a"/></item>
     <item><widget class="QPushButton" name="b"/></item>
    </layout>
   </item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        session.log.execute(MorphLayout(_named(session, "inner"), "QGridLayout"))
        assert realizer.last_stats.fallback_rebuilds == 0
        button = realizer.widget_for(_named(session, "a"))
        assert isinstance(button, QPushButton)
        assert button.parentWidget() is not None
        _same(realizer, session, "nested layout morph")


def test_break_layout_can_take_another_layout() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="box">
   <item><widget class="QPushButton" name="a"/></item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        session.log.execute(BreakLayout(_layout_of(session, "Form"), ()))
        assert realizer.last_stats.fallback_rebuilds == 0
        assert realizer.widget_for(_named(session, "a")) is not None
        _same(realizer, session, "break layout")


def test_create_action_on_a_main_window() -> None:
    with opened(_MAIN) as (session, realizer):
        toolbar = _named(session, "toolBar")
        session.log.execute(
            CreateAction(
                NodeSpec("action", None, (("name", "actionExtra"),)),
                ref_at=InActionList(toolbar, 0),
            )
        )
        assert realizer.last_stats.fallback_rebuilds == 0
        bar = realizer.widget_for(toolbar)
        assert isinstance(bar, QToolBar)
        assert "actionExtra" in [action.objectName() for action in bar.actions()]
        _same(realizer, session, "create action")


def test_signature_records_layout_items_and_container_state() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="1" rowspan="1" colspan="2"><widget class="QPushButton" name="a"/></item>
   <item row="1" column="0">
    <spacer name="gap"><property name="sizeHint"><size><width>8</width><height>12</height></size></property></spacer>
   </item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        part = _part_for(realizer.signature(), _named(session, "grid"))
        assert part[0] == "QGridLayout"
        items = part[3]
        assert isinstance(items, tuple)
        positions = [item[5] if item[0] == "spacer" else item[3] for item in items]
        assert (0, 1, 1, 2) in positions
        spacer = next(item for item in items if item[0] == "spacer")
        assert spacer[1] == int(_named(session, "gap"))
        assert spacer[2:4] == (8, 12)
        assert part[4]  # stretch and minimum-size rows and columns
    combo = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="box">
   <item>
    <widget class="QComboBox" name="combo">
     <item><property name="text"><string>Alpha</string></property></item>
     <item><property name="text"><string>Beta</string></property></item>
    </widget>
   </item>
   <item>
    <widget class="QStackedWidget" name="stack">
     <property name="currentIndex"><number>1</number></property>
     <widget class="QWidget" name="one"/>
     <widget class="QWidget" name="two"/>
    </widget>
   </item>
  </layout>
""",
    )
    with opened(combo) as (session, realizer):
        combo_part = _part_for(realizer.signature(), _named(session, "combo"))
        assert combo_part[9] == ("Alpha", "Beta")
        stack_part = _part_for(realizer.signature(), _named(session, "stack"))
        assert stack_part[8] == 1
        assert isinstance(realizer.widget_for(_named(session, "stack")), QStackedWidget)
    with opened(_MAIN) as (session, realizer):
        menu = _part_for(realizer.signature(), _named(session, "menuFile"))
        names = menu[10]
        assert isinstance(names, tuple)
        assert "actionNew" in names


def test_rename_reads_the_document_not_the_event_value() -> None:
    text = form(
        'class="QWidget" name="Form"',
        '<layout class="QVBoxLayout" name="box"><item><widget class="QPushButton" name="before"></widget></item></layout>',
    )
    with opened(text) as (session, realizer):
        button = _named(session, "before")
        session.log.execute(Rename(button, "after"))
        widget = realizer.widget_for(button)
        assert isinstance(widget, QPushButton)
        assert widget.objectName() == "after"
        realizer._rename(button, "stale-event-value")
        assert widget.objectName() == "after"


def test_dispose_closes_the_realizer_and_selection_listeners() -> None:
    text = form(
        'class="QWidget" name="Form"',
        '<layout class="QVBoxLayout" name="box"><item><widget class="QPushButton" name="a"></widget></item></layout>',
    )
    session = open_session(text)
    realizer = Realizer(session)
    realizer.build()
    button = _named(session, "a")
    widget = realizer.widget_for(button)
    seen: List[object] = []
    selection = session.selection
    log = session.log
    selection.set((button,), source=SelectionSource.PROGRAM)
    selection.subscribe(lambda change: seen.append(change))
    session.dispose()
    seen.clear()
    selection.set((), source=SelectionSource.PROGRAM)
    assert seen == []
    log.execute(Rename(button, "renamed"))
    assert isinstance(widget, QPushButton)
    assert widget.objectName() == "a"
    realizer.dispose()


@pytest.mark.parametrize("hash_seed", PINNED_HASH_SEEDS)
@pytest.mark.timeout(120)
def test_pinned_realize_seeds_under_malloc_scribble(hash_seed: str) -> None:
    # A child process with the allocator scribble env: a stale layout item
    # then crashes on every run instead of reading memory that still looks
    # valid. 653 and 805 freed a widget that a parked layout still named.
    _run_seed_batches(PINNED_SEEDS, FAST_STEPS, len(PINNED_SEEDS), hash_seed=hash_seed)


@pytest.mark.timeout(60)
def test_a_crashing_seed_reports_how_to_replay_it() -> None:
    with pytest.raises(AssertionError) as caught:
        _run_seed_batches(
            (0, 1),
            1,
            2,
            hash_seed="77",
            extra_env={"CBCS_FB_REALIZE_ABORT_SEED": "1"},
        )
    message = str(caught.value)
    assert "seed 1" in message
    assert "PYTHONHASHSEED=77" in message
    assert "MallocScribble=1" in message and "MALLOC_PERTURB_=" in message
    assert "--seeds 1 " in message


@pytest.mark.timeout(240)
def test_patch_matches_a_fresh_build() -> None:
    chosen = os.environ.get("FB_SEED")
    if chosen:
        run_realize_seeds((int(chosen),), FAST_STEPS)
        return
    _run_seed_batches(range(FAST_SEEDS), FAST_STEPS, 40)


@pytest.mark.soak
@pytest.mark.timeout(0)
def test_patch_matches_a_fresh_build_soak() -> None:
    chosen = os.environ.get("FB_SEED")
    if chosen:
        run_realize_seeds((int(chosen),), SOAK_STEPS)
        return
    _run_seed_batches(range(SOAK_SEEDS), SOAK_STEPS, 40)


def test_insert_delete_cycles_do_not_grow_memory() -> None:
    text = form(
        'class="QWidget" name="Form"',
        '<layout class="QVBoxLayout" name="lay"/>',
    )
    with opened(text) as (session, realizer):
        box = _layout_of(session, "Form")
        gc.collect()
        tagged_before = _tagged_count(realizer)
        midpoint = 0
        tagged_mid = 0
        for index in range(200):
            outcome = session.log.execute(
                InsertFragment(InBoxLayout(box, 0), Fragment(nodes=(button_spec("b%d" % index),)))
            )
            added = outcome.result.ids[0]
            assert realizer.widget_for(added) is not None
            session.log.execute(DeleteNodes((added,)))
            assert realizer.widget_for(added) is None
            assert realizer.last_stats.destroyed_widgets == 1
            assert realizer.last_stats.fallback_rebuilds == 0
            if index == 99:
                gc.collect()
                midpoint = _rss_bytes()
                tagged_mid = _tagged_count(realizer)
        gc.collect()
        growth = _rss_bytes() - midpoint
        tagged_after = _tagged_count(realizer)
    assert tagged_mid == tagged_before
    assert tagged_after == tagged_mid
    assert growth < 2 * 1024 * 1024, "rss grew %s bytes between cycles 100 and 200" % growth


def test_realize_package_does_not_call_delete_later() -> None:
    root = Path(__file__).resolve().parents[3] / "app" / "features" / "form_builder" / "qtside" / "realize"
    hits = [path.name for path in root.glob("*.py") if "deleteLater" in path.read_text(encoding="utf-8")]
    assert hits == []


@pytest.mark.timeout(180)
def test_corpus_builds_offscreen() -> None:
    class_failures: Set[str] = set()
    property_failures: List[str] = []
    raised: List[str] = []
    built = 0
    for path in sorted(_CORPUS.rglob("*.ui")):
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            read_ui(text, allocator=IdAllocator())
        except UiReadError:
            continue
        session = open_session(text, str(path))
        realizer = Realizer(session)
        try:
            realizer.build()
        except Exception as exc:
            raised.append("%s: %s" % (path.name, exc))
        else:
            built += 1
            for problem in realizer.problems():
                kind = _offscreen_class(problem)
                if kind is not None:
                    class_failures.add(kind)
                elif _expected_corpus_gap(problem):
                    continue
                else:
                    property_failures.append("%s: %s" % (path.name, problem))
        finally:
            realizer.dispose()
            session.dispose()
    assert built > 0
    assert raised == []
    assert class_failures == OFFSCREEN_WIDGET_CLASSES
    assert property_failures == [], property_failures[:30]


def test_a_structural_patch_reapplies_geometry_only_near_the_change(monkeypatch: pytest.MonkeyPatch) -> None:
    loose = "\n".join(
        '<widget class="QLabel" name="l%d"><property name="geometry"><rect><x>%d</x><y>0</y>'
        "<width>10</width><height>10</height></rect></property></widget>" % (index, index)
        for index in range(40)
    )
    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QWidget" name="pane">
   <property name="geometry"><rect><x>0</x><y>40</y><width>100</width><height>40</height></rect></property>
   <layout class="QVBoxLayout" name="paneLay"><item><widget class="QPushButton" name="a"/></item></layout>
  </widget>
  %s
"""
        % loose,
    )
    with opened(text) as (session, realizer):
        calls: List[object] = []
        original = tree_module.apply_geometry

        def counting(widget: object, value: object, is_root: bool) -> None:
            calls.append(widget)
            original(widget, value, is_root)

        monkeypatch.setattr(tree_module, "apply_geometry", counting)
        box = _layout_of(session, "pane")
        session.log.execute(InsertFragment(InBoxLayout(box, 0), Fragment(nodes=(button_spec("added"),))))
        assert realizer.last_stats.fallback_rebuilds == 0
        assert len(calls) <= 2, "a box insert re-applied %d geometries" % len(calls)
        monkeypatch.setattr(tree_module, "apply_geometry", original)
        _same(realizer, session, "insert")


def test_a_toolbar_edit_leaves_the_central_subtree_alone() -> None:
    rows = "\n".join(
        '<item><widget class="QLabel" name="row%d"><property name="text"><string>r%d</string></property>'
        '<property name="toolTip"><string>t%d</string></property></widget></item>' % (index, index, index)
        for index in range(30)
    )
    text = _MAIN.replace(
        '<widget class="QLabel" name="body"><property name="text"><string>Body</string></property></widget>',
        '<layout class="QVBoxLayout" name="bodyLay">%s</layout>' % rows,
    )
    with opened(text) as (session, realizer):
        window = realizer.root_widget
        assert isinstance(window, QMainWindow)
        central = window.centralWidget()
        first = realizer.widget_for(_named(session, "row0"))
        toolbar = _named(session, "toolBar")
        session.log.execute(
            CreateAction(
                NodeSpec("action", None, (("name", "actionSpeed"),)),
                ref_at=InActionList(toolbar, 0),
            )
        )
        stats = realizer.last_stats
        assert stats.fallback_rebuilds == 0
        assert window.centralWidget() is central
        assert realizer.widget_for(_named(session, "row0")) is first
        # Only the new action's properties. The 30 rows are not touched.
        assert stats.patched_properties <= 2, stats
        _same(realizer, session, "toolbar edit")
        session.log.undo()
        assert realizer.last_stats.patched_properties <= 2, realizer.last_stats
        _same(realizer, session, "toolbar edit undo")


def test_a_form_cell_that_is_taken_is_reported() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QFormLayout" name="form">
   <item row="0" column="1"><widget class="QLineEdit" name="first"/></item>
   <item row="0" column="1"><widget class="QLineEdit" name="second"/></item>
  </layout>
""",
    )
    with opened(text) as (session, realizer):
        assert any("second" in problem and "form" in problem for problem in realizer.problems()), realizer.problems()
        session.log.execute(SetProperty(_named(session, "first"), "toolTip", StringValue("x")))
        layout = _layout_of(session, "Form")
        session.log.execute(InsertFragment(InFormRow(layout, 1, "field"), Fragment(nodes=(button_spec("third"),))))
        assert realizer.last_stats.fallback_rebuilds == 0
        reported = [problem for problem in realizer.problems() if "second" in problem]
        assert len(reported) == 1, realizer.problems()
        _same(realizer, session, "taken cell")


def opened_pair(text: str) -> Tuple[FormSession, Realizer]:
    session = open_session(text)
    realizer = Realizer(session)
    realizer.build()
    return session, realizer


def _widget_ids(session: FormSession, realizer: Realizer) -> Set[NodeId]:
    found = set()
    for node in session.document.iter_preorder():
        if isinstance(node, WidgetNode) and realizer.widget_for(node.id) is not None:
            found.add(node.id)
    return found


def _check_step(
    session: FormSession,
    realizer: Realizer,
    realized: Set[NodeId],
    captured: Dict[str, object],
    noop: bool,
    label: str,
) -> None:
    assert realizer.last_stats.fallback_rebuilds == 0, label
    if not noop and "cs" in captured:
        removed = captured["cs"].removed  # type: ignore[attr-defined]
        destroyed = len([node_id for node_id in removed if node_id in realized])
        assert realizer.last_stats.destroyed_widgets == destroyed, label
    _assert_no_loaded_orphan_layouts(session, realizer, label)
    _same(realizer, session, label)


def _assert_no_loaded_orphan_layouts(session: FormSession, realizer: Realizer, label: str) -> None:
    """A layout outside the live tree must hold no items.

    Its items would keep pointers to widgets that later move or die, and the
    next read of such an item is a use-after-free.
    """
    for node in session.document.iter_preorder():
        if not isinstance(node, LayoutNode):
            continue
        layout = realizer.layout_for(node.id)
        if layout is not None and layout.parent() is None:
            assert layout.count() == 0, "%s: detached layout %s holds %d items" % (
                label,
                node.object_name,
                layout.count(),
            )


def _offscreen_class(problem: str) -> Optional[str]:
    """A Qt class that exists but could not be constructed. Unknown names are not that."""
    if not problem.startswith("class ") or ": " not in problem:
        return None
    name = problem[len("class ") :].split(": ", 1)[0]
    short = name.split("::")[-1]
    if getattr(QtWidgets, short, None) is None and getattr(QtGui, short, None) is None:
        return None
    return short


def _expected_corpus_gap(problem: str) -> bool:
    """Adversarial class names and .qrc files the corpus does not ship."""
    if problem.startswith("class ") and " is not a Qt widget" in problem:
        return True
    return problem.startswith("resource ") and "No such file or directory" in problem


def sequence_forms() -> Tuple[str, ...]:
    """NESTED, the main window, and the page containers the fast lane must cover."""
    tab = form(
        'class="QTabWidget" name="tabs"',
        """
  <widget class="QWidget" name="one"><attribute name="title"><string>One</string></attribute>
   <layout class="QVBoxLayout" name="oneLay"><item><widget class="QPushButton" name="go"></widget></item></layout>
  </widget>
  <widget class="QWidget" name="two"><attribute name="title"><string>Two</string></attribute></widget>
""",
    )
    stack = form(
        'class="QStackedWidget" name="stack"',
        """
  <property name="currentIndex"><number>1</number></property>
  <widget class="QWidget" name="one"/>
  <widget class="QWidget" name="two">
   <layout class="QHBoxLayout" name="row"><item><widget class="QLabel" name="lab"><property name="text"><string>L</string></property></widget></item></layout>
  </widget>
""",
    )
    toolbox = form(
        'class="QToolBox" name="tools"',
        """
  <widget class="QWidget" name="pageA"><attribute name="label"><string>A</string></attribute></widget>
  <widget class="QWidget" name="pageB"><attribute name="label"><string>B</string></attribute></widget>
""",
    )
    wizard = form(
        'class="QWizard" name="wizard"',
        """
  <widget class="QWizardPage" name="page1"><attribute name="title"><string>First</string></attribute></widget>
  <widget class="QWizardPage" name="page2"><attribute name="title"><string>Second</string></attribute></widget>
""",
    )
    splitter = form(
        'class="QSplitter" name="split"',
        """
  <widget class="QWidget" name="left"/>
  <widget class="QWidget" name="right">
   <layout class="QVBoxLayout" name="rv"><item><widget class="QLineEdit" name="edit"></widget></item></layout>
  </widget>
""",
    )
    return (NESTED, _MAIN, tab, stack, toolbox, wizard, splitter)


def run_realize_seeds(seeds: Sequence[int], steps: int, hash_seed: str = "") -> None:
    """One process. Prints the seed before each step so a crash names it."""
    forms = sequence_forms()
    abort_at = os.environ.get("CBCS_FB_REALIZE_ABORT_SEED")
    for seed in seeds:
        print("SEED %d PYTHONHASHSEED=%s" % (seed, hash_seed), file=sys.stderr, flush=True)
        if abort_at is not None and int(abort_at) == seed:
            os.abort()
        session, realizer = opened_pair(forms[seed % len(forms)])
        try:
            rng = random.Random(seed)
            captured: Dict[str, object] = {}

            def grab(changeset: object) -> None:
                captured["cs"] = changeset

            session.log.subscribe(grab, priority=200)
            for step in range(steps):
                command = command_for(session.document, rng, step)
                if command is None:
                    continue
                print(
                    "STEP seed %d step %d %s" % (seed, step, type(command).__name__),
                    file=sys.stderr,
                    flush=True,
                )
                realized = _widget_ids(session, realizer)
                try:
                    outcome = session.log.execute(command)
                except CommandRejected:
                    continue
                label = "%s seed %s step %s %s" % (type(command).__name__, seed, step, command.label)
                _check_step(session, realizer, realized, captured, outcome.noop, label)
                if session.log.can_undo():
                    realized = _widget_ids(session, realizer)
                    session.log.undo()
                    _check_step(session, realizer, realized, captured, False, label + " undo")
                    realized = _widget_ids(session, realizer)
                    session.log.redo()
                    _check_step(session, realizer, realized, captured, False, label + " redo")
        finally:
            realizer.dispose()
            session.dispose()


def _run_seed_batches(
    seeds: Sequence[int],
    steps: int,
    batch_size: int,
    *,
    hash_seed: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> None:
    """Children run under ``SCRIBBLE_ENV`` and a known ``PYTHONHASHSEED``."""
    seed_list = list(seeds)
    if hash_seed is None:
        hash_seed = os.environ.get("PYTHONHASHSEED") or str(random.randrange(1, 2 ** 31))
    env = dict(SCRIBBLE_ENV)
    env["PYTHONHASHSEED"] = hash_seed
    env.update(extra_env or {})
    for start in range(0, len(seed_list), batch_size):
        chunk = seed_list[start : start + batch_size]
        proc = run_module(
            "tests.form_builder.qtside.tools.realize_sequence",
            ["--steps", str(steps), "--seeds", ",".join(str(item) for item in chunk)],
            extra_env=env,
        )
        if proc.returncode != 0:
            stderr = proc.stderr or ""
            raise AssertionError(
                "realize seeds %s..%s exited %s at %s\nreplay: %s\n%s"
                % (
                    chunk[0],
                    chunk[-1],
                    proc.returncode,
                    _last_step(stderr),
                    _replay_command(_failing_seed(stderr, chunk[0]), steps, env),
                    stderr[-4000:],
                )
            )


def _failing_seed(stderr: str, default: int) -> int:
    seed = default
    for line in stderr.splitlines():
        if line.startswith("SEED "):
            seed = int(line.split()[1])
    return seed


def _last_step(stderr: str) -> str:
    found = "start"
    for line in stderr.splitlines():
        if line.startswith("SEED "):
            found = "seed %s start" % line.split()[1]
        elif line.startswith("STEP "):
            found = line[len("STEP ") :]
    return found


def _replay_command(seed: int, steps: int, env: Dict[str, str]) -> str:
    names = ("PYTHONHASHSEED",) + tuple(sorted(SCRIBBLE_ENV))
    settings = " ".join("%s=%s" % (name, env[name]) for name in names if name in env)
    return "%s QT_QPA_PLATFORM=offscreen python -m tests.form_builder.qtside.tools.realize_sequence --seeds %d --steps %d" % (
        settings,
        seed,
        steps,
    )


def _part_for(signature: Tuple[object, ...], node_id: NodeId) -> Tuple[object, ...]:
    target = int(node_id)
    for part in signature:
        if isinstance(part, tuple) and len(part) >= 3 and part[2] == target:
            return part
    raise AssertionError("no signature entry for %s" % node_id)


def _grid_ids(grid: QGridLayout) -> Dict[NodeId, Tuple[int, int, int, int]]:
    found: Dict[NodeId, Tuple[int, int, int, int]] = {}
    for index in range(grid.count()):
        item = grid.itemAt(index)
        widget = None if item is None else item.widget()
        if widget is None:
            continue
        raw = widget.property(NODE_ID_PROPERTY)
        row, column, rowspan, colspan = grid.getItemPosition(index)
        found[NodeId(int(raw))] = (int(row), int(column), int(rowspan), int(colspan))
    return found


def _tagged_count(realizer: Realizer) -> int:
    root = realizer.root_widget
    if root is None:
        return 0
    count = 1 if _has_node_id(root) else 0
    for child in root.findChildren(QObject):
        if _has_node_id(child):
            count += 1
    return count


def _has_node_id(obj: object) -> bool:
    raw = obj.property(NODE_ID_PROPERTY) if hasattr(obj, "property") else None
    return raw not in (None, "")


def _rss_bytes() -> int:
    """Current RSS from /proc on Linux; elsewhere the peak RSS, which still
    grows when memory leaks."""
    try:
        status = Path("/proc/self/status").read_text(encoding="ascii")
    except OSError:
        import resource
        import sys

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak if sys.platform == "darwin" else peak * 1024
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return 0
