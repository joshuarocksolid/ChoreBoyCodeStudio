# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Button groups in the form inspector (UX-MAIN-019, R3 119, 142)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog_ext.actions import MakeButtonGroup
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.writer import write_ui
from app.qt.QtWidgets import QCheckBox, QPushButton, QWidget
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane

_TWO = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
    ' <widget class="QWidget" name="Form">\n  <layout class="QVBoxLayout" name="verticalLayout">\n'
    '   <item><widget class="QRadioButton" name="a"/></item>\n   <item><widget class="QRadioButton" name="b"/></item>\n'
    '  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n'
)

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]


@pytest.mark.parity("R3-119", "R3-142")
def test_the_form_lists_its_button_groups_and_exclusive_is_written_only_when_off(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, _TWO)
    try:
        doc = session.document
        buttons = tuple(w.id for w in doc.iter_widgets() if w.class_name == "QRadioButton")[:2]
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        assert pane.findChild(QWidget, "formBuilder.formGroup.buttonGroups") is None or not pane.findChild(
            QWidget, "formBuilder.formGroup.buttonGroups"
        ).isVisibleTo(pane)
        before = write_ui(doc).text
        name = session.log.execute(MakeButtonGroup(buttons)).result
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        group = pane.findChild(QWidget, "formBuilder.formGroup.buttonGroups")
        assert group is not None and group.isVisibleTo(pane)
        box = group.findChild(QCheckBox)
        assert box.isChecked()
        box.setChecked(False)
        assert "exclusive" in write_ui(doc).text
        box.setChecked(True)
        assert "exclusive" not in write_ui(doc).text
        group.findChild(QPushButton).click()
        assert set(session.selection.state.ids) == set(buttons)
        session.log.undo()
        session.log.undo()
        session.log.undo()
        assert q.button_groups(doc) == () and write_ui(doc).text == before
        del name
    finally:
        _close(window, pane, realizer, session, qapp)
