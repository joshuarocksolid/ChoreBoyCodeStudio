# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Live widgets stay in step with the document. A patch matches a fresh build."""

from __future__ import annotations

import gc
import importlib.abc
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pytest

from app.qt import QtGui, QtWidgets
from app.qt.QtCore import QFile, QIODevice, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import (
    QDialogButtonBox,
    QDockWidget,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QPushButton,
    QSpinBox,
    QToolBar,
    QWidget,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import (
    AddActionRef,
    DeleteNodes,
    InsertFragment,
    MorphWidget,
    MoveNodes,
    Rename,
    SetProperty,
    SetZOrder,
)
from app.features.form_builder.engine.commands.placement import InActionList, InBoxLayout
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.engine.commands._support import button_spec
from tests.form_builder.qtside.support import form, open_session, opened
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


@pytest.mark.timeout(90)
def test_patch_matches_a_fresh_build() -> None:
    seed_text = os.environ.get("FB_SEED")
    seeds = [int(seed_text)] if seed_text else [1, 2, 3, 4]
    for seed in seeds:
        session, realizer = opened_pair(NESTED)
        try:
            rng = random.Random(seed)
            captured: Dict[str, object] = {}

            def grab(changeset: object) -> None:
                captured["cs"] = changeset

            session.log.subscribe(grab, priority=200)
            for step in range(10):
                command = command_for(session.document, rng, step)
                if command is None:
                    continue
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


def test_insert_delete_cycles_do_not_grow_memory() -> None:
    text = form(
        'class="QWidget" name="Form"',
        '<layout class="QVBoxLayout" name="lay"/>',
    )
    with opened(text) as (session, realizer):
        box = _layout_of(session, "Form")
        gc.collect()
        before = _rss_bytes()
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
        gc.collect()
        growth = _rss_bytes() - before
    assert growth < 30 * 1024 * 1024, "rss grew %s bytes over 200 insert/delete cycles" % growth


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
    _same(realizer, session, label)


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
