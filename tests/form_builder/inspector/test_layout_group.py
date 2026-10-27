# pyright: reportAttributeAccessIssue=false
"""The inspector's Layout group: Kind, size constraint, form policies, and a spacer's size type."""

from __future__ import annotations

from typing import List, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import LayoutNode
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.qt.QtCore import QTimer
from app.qt.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_UI = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>420</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QWidget" name="column">
     <layout class="QVBoxLayout" name="columnLayout">
      <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
      <item><widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="fields">
     <layout class="QFormLayout" name="fieldsLayout">
      <item row="0" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
      <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="cells">
     <layout class="QGridLayout" name="cellsLayout">
      <item row="0" column="0" colspan="2"><widget class="QPushButton" name="wide"><property name="text"><string>Wide</string></property></widget></item>
      <item row="1" column="0"><widget class="QPushButton" name="left"><property name="text"><string>Left</string></property></widget></item>
      <item row="1" column="1"><widget class="QPushButton" name="right"><property name="text"><string>Right</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QGroupBox" name="bare">
     <property name="title"><string>Bare</string></property>
     <property name="minimumSize"><size><width>0</width><height>90</height></size></property>
     <widget class="QPushButton" name="upper">
      <property name="geometry"><rect><x>10</x><y>20</y><width>80</width><height>24</height></rect></property>
      <property name="text"><string>Upper</string></property>
     </widget>
     <widget class="QPushButton" name="lower">
      <property name="geometry"><rect><x>10</x><y>54</y><width>80</width><height>24</height></rect></property>
      <property name="text"><string>Lower</string></property>
     </widget>
    </widget>
   </item>
   <item>
    <spacer name="gap">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
    </spacer>
   </item>
  </layout>
""",
    " <resources/>\n <connections/>",
)

_CHROME = chrome_from_values(
    window="#f3f3f3",
    panel="#ffffff",
    text="#1f1f1f",
    muted="#5c5c5c",
    faint="#6b6b6b",
    border="#c8c8c8",
    accent="#0060c0",
    row_hover="#eef3fb",
    input_bg="#ffffff",
    error="#b00020",
    focus_width=1,
)


@pytest.mark.parity("R3-49")
def test_size_constraint_is_written_on_the_layout() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "column")
        combo = _combo(pane, "layout.sizeConstraint")
        _choose(combo, "SetFixedSize")
        assert combo.currentText() == "Fixed"
        assert combo.currentData() == "SetFixedSize"

        layout = _node(session, "columnLayout")
        assert isinstance(layout, LayoutNode)
        assert _enum_name(layout, "sizeConstraint") == "SetFixedSize"
        block = write_ui(session.document).text.split('name="columnLayout"', 1)[1].split("<item>", 1)[0]
        assert "<enum>QLayout::SetFixedSize</enum>" in block
        live = realizer.layout_for(layout.id)
        assert live is not None and live.sizeConstraint() == QLayout.SizeConstraint.SetFixedSize
        session.log.undo()
        assert _node(session, "columnLayout").prop("sizeConstraint") is None
        _close(window, pane)


@pytest.mark.parity("R3-53")
@pytest.mark.parametrize(("container", "shown"), (("fields", True), ("column", False), ("cells", False)))
def test_form_policies_are_rows_only_for_a_form_layout(container: str, shown: bool) -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, container)
        for key in ("fieldGrowthPolicy", "rowWrapPolicy", "labelAlignment", "formAlignment"):
            row = pane.findChild(QWidget, "formBuilder.row.layout.%s" % key)
            assert (row is not None and row.isVisible()) is shown, key
        _close(window, pane)


@pytest.mark.parity("R3-53")
def test_field_growth_is_written_on_the_form_layout() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "fields")
        _choose(_combo(pane, "layout.fieldGrowthPolicy"), "FieldsStayAtSizeHint")

        layout = _node(session, "fieldsLayout")
        assert _enum_name(layout, "fieldGrowthPolicy") == "FieldsStayAtSizeHint"
        live = realizer.layout_for(layout.id)
        assert isinstance(live, QFormLayout)
        assert live.fieldGrowthPolicy() == QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        _close(window, pane)


@pytest.mark.parity("R3-46")
def test_a_spacer_size_type_is_one_undoable_write() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "gap")
        steps = len(session.log.entries())
        _choose(_combo(pane, "sizeType"), "Fixed")

        assert len(session.log.entries()) == steps + 1
        assert _enum_name(_node(session, "gap"), "sizeType") == "Fixed"
        assert "<enum>QSizePolicy::Fixed</enum>" in write_ui(session.document).text
        session.log.undo()
        assert _node(session, "gap").prop("sizeType") is None
        _close(window, pane)


def test_the_kind_segment_morphs_the_layout_and_keeps_its_widgets() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "column")
        container = realizer.widget_for(_node(session, "column").id)
        assert container is not None
        one = _named(container, "one")
        assert _segment(pane, "vertical").isChecked()

        _segment(pane, "grid").click()
        _events()

        assert isinstance(container.layout(), QGridLayout)
        assert _named(container, "one") is one
        assert realizer.last_stats.fallback_rebuilds == 0
        assert _segment(pane, "grid").isChecked()
        assert not _segment(pane, "vertical").isChecked()
        assert session.log.undo_label()
        _close(window, pane)


def test_a_bare_container_gets_a_layout_from_a_kind_segment() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "bare")
        bare = realizer.widget_for(_node(session, "bare").id)
        assert bare is not None and bare.layout() is None
        assert not any(_segment(pane, kind).isChecked() for kind in ("vertical", "horizontal", "grid", "form"))

        _segment(pane, "vertical").click()
        _events()

        layout = bare.layout()
        assert isinstance(layout, QVBoxLayout)
        assert layout.indexOf(_named(bare, "upper")) == 0
        assert layout.indexOf(_named(bare, "lower")) == 1
        assert _segment(pane, "vertical").isChecked()
        _close(window, pane)


@pytest.mark.parametrize(("answer", "kept"), (("Cancel", True), ("Change layout", False)))
def test_a_morph_that_drops_a_span_asks_first(answer: str, kept: bool) -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "cells")
        before = write_ui(session.document).text
        asked = _answer(pane, answer)

        _segment(pane, "vertical").click()
        _events()

        assert asked and "span" in asked[0].lower()
        container = realizer.widget_for(_node(session, "cells").id)
        assert container is not None
        if kept:
            assert isinstance(container.layout(), QGridLayout)
            assert write_ui(session.document).text == before
        else:
            assert isinstance(container.layout(), QVBoxLayout)
        _close(window, pane)


def test_a_picked_layout_shows_its_rows_and_the_kind_control() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "fieldsLayout")
        assert _segment(pane, "form").isChecked()
        assert pane.findChild(QWidget, "formBuilder.row.layout.fieldGrowthPolicy") is not None

        _segment(pane, "grid").click()
        _events()

        assert isinstance(_node(session, "fieldsLayout"), LayoutNode)
        assert _node(session, "fieldsLayout").class_name == "QGridLayout"
        _close(window, pane)


def test_the_layout_group_fits_at_236_px() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer, width=236, height=640)
        _select(session, pane, "fields")
        scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
        body = pane.findChild(QWidget, "formBuilder.layoutBody")
        assert scroll is not None and body is not None and body.isVisible()
        assert scroll.horizontalScrollBar().maximum() == 0
        _no_overlap(body)
        growth = [ _combo(pane, "layout.fieldGrowthPolicy").itemText(index) for index in range(_combo(pane, "layout.fieldGrowthPolicy").count()) ]
        wrap = [ _combo(pane, "layout.rowWrapPolicy").itemText(index) for index in range(_combo(pane, "layout.rowWrapPolicy").count()) ]
        assert "All grow" in growth
        assert "Don't wrap" in wrap
        assert "AllNonFixedFieldsGrow" not in growth
        assert "DontWrapRows" not in wrap
        _close(window, pane)


def test_the_layout_group_keeps_spacing_rows_beside_the_kind_control() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        _select(session, pane, "cells")
        body = pane.findChild(QWidget, "formBuilder.layoutBody")
        assert body is not None
        order = [
            child.objectName()
            for child in sorted(
                (item for item in body.children() if isinstance(item, QWidget) and item.isVisible()),
                key=lambda item: item.geometry().top(),
            )
        ]
        assert "formBuilder.row.layout.spacing" in order
        assert order.index("formBuilder.row.layout.spacing") < order.index("formBuilder.layout.kind")
        assert order.index("formBuilder.layout.kind") < order.index("formBuilder.row.layout.sizeConstraint")
        _close(window, pane)


def _pane(session: FormSession, realizer: Realizer, width: int = 420, height: int = 900) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(width, height)
    window.show()
    _events()
    pane.flush()
    return window, pane


def _close(window: QWidget, pane: InspectorPane) -> None:
    pane.dispose()
    window.close()
    window.deleteLater()
    _events()


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    session.selection.set((_node(session, name).id,), source=SelectionSource.PROGRAM)
    pane.flush()
    _events()


def _node(session: FormSession, name: str):  # type: ignore[no-untyped-def]
    found = session.document.by_name(name)
    assert found, name
    return session.document.node(found[0])


def _enum_name(node: object, name: str) -> str:
    entry = node.prop(name)  # type: ignore[attr-defined]
    assert entry is not None, name
    return entry.value.key()[1]


def _named(parent: QWidget, name: str) -> QWidget:
    found = parent.findChild(QWidget, name)
    assert found is not None, name
    return found


def _combo(pane: QWidget, key: str) -> QComboBox:
    row = pane.findChild(QWidget, "formBuilder.row.%s" % key)
    assert row is not None and row.isVisible(), key
    combo = row.findChild(QComboBox)
    assert combo is not None, key
    return combo


def _no_overlap(body: QWidget) -> None:
    for parent in [body] + body.findChildren(QWidget):
        shown = [item for item in parent.children() if isinstance(item, QWidget) and item.isVisible()]
        for index, first in enumerate(shown):
            for second in shown[index + 1 :]:
                both = first.geometry().intersected(second.geometry())
                assert both.isEmpty(), (first.objectName(), second.objectName())


def _choose(combo: QComboBox, name: str) -> None:
    index = -1
    for candidate in range(combo.count()):
        if combo.itemData(candidate) == name or combo.itemText(candidate) == name:
            index = candidate
            break
    assert index >= 0, name
    combo.setCurrentIndex(index)
    _events()


def _segment(pane: QWidget, kind_id: str) -> QToolButton:
    found = pane.findChild(QToolButton, "formBuilder.layout.kind.%s" % kind_id)
    assert isinstance(found, QToolButton), kind_id
    return found


def _answer(pane: QWidget, button: str) -> List[str]:
    """Click ``button`` on the next layout confirm. Returns the question it asked."""
    asked: List[str] = []

    def click() -> None:
        question = pane.findChild(QFrame, "formBuilder.layoutConfirm")
        if question is None or not question.isVisible():
            QTimer.singleShot(10, click)
            return
        text = question.findChild(QLabel, "formBuilder.layoutConfirmText")
        asked.append(text.text() if text is not None else "")
        for candidate in question.findChildren(QPushButton):
            if candidate.text() == button:
                candidate.click()
                return
        raise AssertionError("no %r button" % button)

    QTimer.singleShot(0, click)
    return asked


def _events() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
