# pyright: reportAttributeAccessIssue=false
"""Layout gestures move the live widgets. They do not rebuild them."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, Tuple

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.layout_actions import (
    FORM,
    GRID,
    GROUP,
    HORIZONTAL,
    HSPLIT,
    TAB,
    VERTICAL,
    Adjust,
    ApplyKind,
    ChangeTo,
    Done,
    NeedsConfirm,
    PickWrap,
    RemoveLayout,
    Unwrap,
    transact,
)
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.layout_gestures import perform
from app.qt.QtCore import QPoint
from app.qt.QtWidgets import QApplication, QFormLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
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

_FREE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>200</height></rect></property>
  <widget class="QLabel" name="label">
   <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>Name</string></property>
  </widget>
  <widget class="QLineEdit" name="edit">
   <property name="geometry"><rect><x>100</x><y>10</y><width>160</width><height>24</height></rect></property>
  </widget>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>100</x><y>50</y><width>200</width><height>60</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)

_TWO_ROWS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>240</height></rect></property>
  <layout class="QVBoxLayout" name="column">
   <item>
    <widget class="QWidget" name="first">
     <layout class="QHBoxLayout" name="firstRow">
      <item><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
      <item><widget class="QLineEdit" name="nameEdit"/></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="second">
     <layout class="QHBoxLayout" name="secondRow">
      <item><widget class="QLabel" name="cityLabel"><property name="text"><string>City</string></property></widget></item>
      <item><widget class="QLineEdit" name="cityEdit"/></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QPlainTextEdit" name="notes">
     <property name="sizePolicy">
      <sizepolicy hsizetype="Expanding" vsizetype="Expanding">
       <horstretch>0</horstretch>
       <verstretch>0</verstretch>
      </sizepolicy>
     </property>
    </widget>
   </item>
  </layout>
""",
)

_NESTED = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>180</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QHBoxLayout" name="firstRow">
     <item><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
     <item><widget class="QLineEdit" name="nameEdit"/></item>
    </layout>
   </item>
   <item>
    <layout class="QHBoxLayout" name="secondRow">
     <item><widget class="QLabel" name="cityLabel"><property name="text"><string>City</string></property></widget></item>
     <item><widget class="QLineEdit" name="cityEdit"/></item>
    </layout>
   </item>
  </layout>
""",
)

_SIZE = (420, 240)
_BIG = (640, 420)
_FIRST_ROW = ("nameLabel", "nameEdit")


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


@pytest.mark.parametrize(
    ("kind_id", "layout_type"),
    [
        pytest.param(HORIZONTAL, QHBoxLayout, marks=pytest.mark.parity("R3-35")),
        pytest.param(VERTICAL, QVBoxLayout, marks=pytest.mark.parity("R3-36")),
        pytest.param(GRID, QGridLayout, marks=pytest.mark.parity("R3-37")),
        pytest.param(FORM, QFormLayout, marks=pytest.mark.parity("R3-38")),
    ],
)
def test_laying_out_free_widgets_puts_the_same_widgets_in_that_layout(kind_id: str, layout_type: type) -> None:
    with opened(_FREE) as (session, realizer):
        doc = session.document
        before = {name: realizer.widget_for(doc.by_name(name)[0]) for name in ("label", "edit", "ok")}
        entries = len(session.log.entries())

        outcome = perform(doc, (), realizer.widget_for, transact(session.log), ApplyKind(kind_id), _never)

        assert isinstance(outcome, Done), outcome
        assert len(session.log.entries()) == entries + 1
        root = realizer.widget_for(doc.root.id)
        assert root is not None and isinstance(root.layout(), layout_type)
        for name, widget in before.items():
            assert widget is not None
            assert realizer.widget_for(doc.by_name(name)[0]) is widget, name
            assert root.layout().indexOf(widget) >= 0, name


@pytest.mark.parity("R3-42")
def test_adjust_size_fits_a_free_widget_to_its_content_in_one_step() -> None:
    with opened(_FREE) as (session, realizer):
        doc = session.document
        ok = doc.by_name("ok")[0]
        widget = realizer.widget_for(ok)
        assert widget is not None
        stored = widget.size()
        hint = widget.sizeHint()
        assert stored != hint
        entries = len(session.log.entries())

        outcome = perform(doc, (ok,), realizer.widget_for, transact(session.log), Adjust(), _never)

        assert outcome == Done("Resized ok to fit its content")
        assert len(session.log.entries()) == entries + 1
        resized = realizer.widget_for(ok)
        assert resized is not None
        assert resized.size() == hint
        session.log.undo()
        restored_size = realizer.widget_for(ok)
        assert restored_size is not None
        assert restored_size.size() == stored


@pytest.mark.pain("P-5")
def test_removing_one_row_layout_keeps_every_rectangle_after_reload(tmp_path: Path) -> None:
    bigger = _placed_in(_TWO_ROWS, _BIG)
    with opened(_TWO_ROWS) as (session, realizer):
        doc = session.document
        first = doc.by_name("first")[0]
        root = realizer.widget_for(doc.root.id)
        assert root is not None
        _settle(root, _SIZE)
        before = _placed(root)
        asked: list = []

        def accept(prompt: NeedsConfirm) -> bool:
            asked.append(prompt.text)
            return prompt.accept == "Remove layout"

        outcome = perform(
            doc, (first,), realizer.widget_for, transact(session.log), RemoveLayout(), accept, realizer.layout_for
        )
        _settle(root, _SIZE)

        assert asked and "first keeps its current size as its smallest size." in asked[0]
        assert outcome == Done("Removed the layout")
        assert _same(before, _placed(root))
        block = write_ui(doc).text.split('name="first"', 1)[1].split("</widget>", 1)[0]
        assert "minimumSize" in block
        saved = write_ui(doc).text
        assert "maximumSize" not in saved
        _settle(root, _BIG)
        assert _same(_siblings(bigger, _FIRST_ROW), _placed(root))
        root.hide()

    _reopen_matches(saved, before)
    _reopen_matches(saved, _siblings(bigger, _FIRST_ROW), _BIG)
    _generated_matches(saved, before, tmp_path)


@pytest.mark.parity("R3-55")
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


def _layout_pass() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _settle(root: QWidget, size: Tuple[int, int]) -> None:
    root.resize(*size)
    root.show()
    _layout_pass()


def _placed(root: QWidget) -> Dict[str, Tuple[int, int, int, int]]:
    placed = {}
    for widget in root.findChildren(QWidget):
        name = widget.objectName()
        if not name:
            continue
        origin = widget.mapTo(root, QPoint(0, 0))
        placed[name] = (origin.x(), origin.y(), widget.width(), widget.height())
    return placed


def _same(before: Dict[str, Tuple[int, int, int, int]], after: Dict[str, Tuple[int, int, int, int]]) -> bool:
    shared = set(before) & set(after)
    assert shared
    for name in sorted(shared):
        assert after[name] == before[name], name
    return True


def _reopen_matches(
    text: str, before: Dict[str, Tuple[int, int, int, int]], size: Tuple[int, int] = _SIZE
) -> None:
    assert _same(before, _placed_in(text, size))


def _placed_in(text: str, size: Tuple[int, int]) -> Dict[str, Tuple[int, int, int, int]]:
    with opened(text, "/tmp/cbcs-form-reopen.ui") as (session, realizer):
        root = realizer.widget_for(session.document.root.id)
        assert root is not None
        _settle(root, size)
        placed = _placed(root)
        root.hide()
    return placed


def _siblings(
    placed: Dict[str, Tuple[int, int, int, int]], removed: Tuple[str, ...]
) -> Dict[str, Tuple[int, int, int, int]]:
    """Every rectangle outside the removed layout. Its own widgets stop following the window."""
    return {name: rect for name, rect in placed.items() if name not in removed}


def _generated_matches(text: str, before: Dict[str, Tuple[int, int, int, int]], directory: Path) -> None:
    """setupUi keeps every named widget's height and the top-to-bottom order.

    uic's default margins are not the canvas realizer's, so this does not
    compare absolute coordinates with the live form.
    """
    code = _python_ui(text, directory)
    namespace: Dict[str, object] = {}
    exec(compile(code, "ui_sample.py", "exec"), namespace)
    ui_cls = next(value for value in namespace.values() if isinstance(value, type) and hasattr(value, "setupUi"))
    host = QWidget()
    ui_cls().setupUi(host)  # type: ignore[operator]
    _settle(host, _SIZE)
    placed = _placed(host)
    for name, rect in before.items():
        assert name in placed, name
        assert placed[name][2] > 0 and placed[name][3] > 0, (name, placed[name], rect)
    order = [name for name in ("nameLabel", "cityLabel", "notes") if name in placed]
    tops = [placed[name][1] for name in order]
    assert tops == sorted(tops)
    host.hide()
    host.deleteLater()
    _layout_pass()


def _python_ui(text: str, directory: Path) -> str:
    uic = os.environ.get("CBCS_FB_UIC", "")
    if uic and os.path.isfile(uic):
        source = directory / "sample.ui"
        source.write_text(text, encoding="utf-8")
        completed = subprocess.run([uic, "-g", "python", str(source)], check=True, capture_output=True, text=True)
        lines = completed.stdout.splitlines()
        start = 0
        for index, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                start = index
                break
        return "\n".join(lines[start:]) + "\n"
    forms = directory / "forms"
    forms.mkdir(parents=True, exist_ok=True)
    path = forms / "sample.ui"
    path.write_text(text, encoding="utf-8")
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(directory),
        generated_path=str(forms / "ui_sample.py"),
    )
    document = read_ui(text, allocator=IdAllocator()).document
    result = generate_form_module(document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text
    return result.text


@pytest.mark.pain("P-5")
@pytest.mark.parity("R3-41")
def test_removing_a_nested_layout_keeps_every_rectangle(tmp_path: Path) -> None:
    bigger = _placed_in(_NESTED, _BIG)
    with opened(_NESTED) as (session, realizer):
        doc = session.document
        row = doc.by_name("firstRow")[0]
        root = realizer.widget_for(doc.root.id)
        assert root is not None
        _settle(root, _SIZE)
        before = _placed(root)
        entries = len(session.log.entries())
        asked: list = []

        def accept(prompt: NeedsConfirm) -> bool:
            asked.append(prompt.text)
            return True

        outcome = perform(
            doc, (row,), realizer.widget_for, transact(session.log), RemoveLayout(), accept, realizer.layout_for
        )
        _settle(root, _SIZE)

        assert asked and "firstRow keeps its current size as its smallest size." in asked[0]
        assert outcome == Done("Removed the layout")
        assert len(session.log.entries()) == entries + 1
        assert _same(before, _placed(root))
        assert doc.by_name("firstRowWidget")
        saved = write_ui(doc).text
        assert "maximumSize" not in saved
        _settle(root, _BIG)
        assert _same(_siblings(bigger, _FIRST_ROW), _placed(root))
        holder = realizer.widget_for(doc.by_name("firstRowWidget")[0])
        second = realizer.layout_for(doc.by_name("secondRow")[0])
        assert holder is not None and second is not None
        assert holder.width() == second.geometry().width()
        _settle(root, _SIZE)
        bytes_before = write_ui(doc).text
        session.log.undo()
        assert write_ui(doc).text != bytes_before
        session.log.redo()
        assert write_ui(doc).text == saved
        root.hide()

    _reopen_matches(saved, before)
    _reopen_matches(saved, _siblings(bigger, _FIRST_ROW), _BIG)
    _generated_matches(saved, before, tmp_path)


@pytest.mark.parametrize(
    ("inner", "target", "dropped"),
    [
        (
            '<widget class="QLineEdit" name="edit"><property name="echoMode"><enum>QLineEdit::Password</enum></property></widget>',
            "QPlainTextEdit",
            ("echoMode",),
        ),
        (
            '<widget class="QSpinBox" name="edit"><property name="maximum"><number>10</number></property><property name="value"><number>3</number></property></widget>',
            "QDateEdit",
            ("maximum", "value"),
        ),
        (
            '<widget class="QPushButton" name="edit"><property name="default"><bool>true</bool></property></widget>',
            "QCheckBox",
            ("default",),
        ),
        (
            '<widget class="QGroupBox" name="edit"><property name="title"><string>Group</string></property><property name="checkable"><bool>true</bool></property></widget>',
            "QFrame",
            ("title", "checkable"),
        ),
    ],
)
def test_change_to_drops_properties_the_new_class_rejects(inner: str, target: str, dropped: Tuple[str, ...], tmp_path: Path) -> None:
    text = form('class="QWidget" name="Form"', "  " + inner)
    with opened(text) as (session, realizer):
        doc = session.document
        node = doc.by_name("edit")[0]
        before = write_ui(doc).text
        entries = len(session.log.entries())
        asked: list = []

        def accept(prompt: NeedsConfirm) -> bool:
            asked.append(prompt.text)
            return True

        outcome = perform(
            doc, (node,), realizer.widget_for, transact(session.log), ChangeTo(target), accept, realizer.layout_for
        )

        assert asked
        for name in dropped:
            assert name in asked[0]
            assert name in outcome.sentence
            assert '<property name="%s">' % name not in write_ui(doc).text
        assert isinstance(outcome, Done)
        assert len(session.log.entries()) == entries + 1
        saved = write_ui(doc).text
        session.log.undo()
        assert write_ui(doc).text == before
        _generated_runs(saved, tmp_path)


def _generated_runs(text: str, directory: Path) -> None:
    code = _python_ui(text, directory)
    namespace: Dict[str, object] = {}
    exec(compile(code, "ui_sample.py", "exec"), namespace)
    ui_cls = next(value for value in namespace.values() if isinstance(value, type) and hasattr(value, "setupUi"))
    host = QWidget()
    ui_cls().setupUi(host)  # type: ignore[operator]
    host.deleteLater()
    _layout_pass()
