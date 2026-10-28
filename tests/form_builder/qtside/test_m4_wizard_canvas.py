# pyright: reportAttributeAccessIssue=false
"""Wizard on the canvas: the shown step changes, the file does not (UX-CONT-006, UX-CONT-013)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple

import pytest

from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget, QWizard
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.canvas import FormCanvas
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_m4_scroll_area import _Host, _flush

pytestmark = pytest.mark.usefixtures("qapp")

WIZARD = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>600</width><height>400</height></rect></property>
  <widget class="QWizard" name="wizard">
   <property name="geometry"><rect><x>20</x><y>20</y><width>500</width><height>300</height></rect></property>
   <widget class="QWizardPage" name="wizardPage_1">
    <property name="title"><string>Details</string></property>
    <widget class="QLabel" name="inside_one"><property name="text"><string>One</string></property></widget>
   </widget>
   <widget class="QWizardPage" name="wizardPage_2">
    <property name="title"><string>Payment</string></property>
    <widget class="QLabel" name="inside_two"><property name="text"><string>Two</string></property></widget>
   </widget>
   <widget class="QWizardPage" name="wizardPage_3">
    <property name="title"><string>Done</string></property>
   </widget>
  </widget>
""",
)


@contextmanager
def _canvas(text: str) -> Iterator[Tuple[FormSession, FormCanvas, _Host]]:
    host = _Host()
    with opened(text) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(640, 480)
        parent.show()
        canvas.setFocus()
        _flush()
        try:
            yield session, canvas, host
        finally:
            canvas.dispose()
            parent.deleteLater()


def test_ctrl_page_down_shows_the_next_step_and_the_file_stays_the_same() -> None:
    with _canvas(WIZARD) as (session, canvas, host):
        root = canvas.page_widget()
        wizard = root.findChild(QWizard, "wizard")  # type: ignore[union-attr]
        assert wizard is not None
        ids = list(wizard.pageIds())
        assert wizard.currentId() in (-1, ids[0])  # an unshown wizard has no current page yet
        inside = session.document.by_name("inside_one")[0]
        session.selection.set((inside,), current=inside, source=SelectionSource.CANVAS)
        _flush()
        before = write_ui(session.document).text
        QTest.keyClick(canvas, Qt.Key.Key_PageDown, Qt.KeyboardModifier.ControlModifier)
        _flush()
        assert wizard.currentId() == ids[1]
        assert host.sentences[-1] == "Showing step 2 of 3: Payment"
        assert write_ui(session.document).text == before
        assert not session.log.is_dirty()


def test_previous_step_wraps_to_the_last_step() -> None:
    with _canvas(WIZARD) as (session, canvas, host):
        root = canvas.page_widget()
        wizard = root.findChild(QWizard, "wizard")  # type: ignore[union-attr]
        ids = list(wizard.pageIds())
        inside = session.document.by_name("inside_one")[0]
        session.selection.set((inside,), current=inside, source=SelectionSource.CANVAS)
        _flush()
        QTest.keyClick(canvas, Qt.Key.Key_PageUp, Qt.KeyboardModifier.ControlModifier)
        _flush()
        assert wizard.currentId() == ids[2]
        assert host.sentences[-1] == "Showing step 3 of 3: Done"
