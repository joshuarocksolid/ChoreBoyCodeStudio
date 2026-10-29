# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""FB033 and FB034: a sheet Qt can't read, a rule that matches nothing, and the Edit style sheet button."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form
from app.features.form_builder.qtside.style.problems import style_diagnostics
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QWidget
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]


def _form(sheet: str, button_sheet: str = "") -> str:
    inner = (
        '<property name="styleSheet"><string notr="true">%s</string></property>' % button_sheet if button_sheet else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
        ' <widget class="QWidget" name="Form">\n'
        '  <property name="styleSheet"><string notr="true">%s</string></property>\n'
        '  <layout class="QVBoxLayout" name="mainLayout">\n'
        '   <item><widget class="QPushButton" name="okButton">%s</widget></item>\n  </layout>\n </widget>\n</ui>\n'
    ) % (sheet, inner)


def _diagnostics(sheet: str, button_sheet: str = ""):  # type: ignore[no-untyped-def]
    document = read_ui(_form(sheet, button_sheet), allocator=IdAllocator()).document
    return style_diagnostics(document)


def test_a_sheet_qt_cannot_read_is_one_warning_and_a_rule_with_no_match_is_an_info() -> None:
    found = _diagnostics("QPushButton { color: red;")
    assert [(item.code, item.severity) for item in found] == [("FB033", Severity.WARNING)]
    assert found[0].message == "The style sheet of Form can't be read, so Qt ignores all of it."
    found = _diagnostics("QPushButton { color: red; }\nQProgressBar  >  QLabel { color: red; }\n")
    assert [(item.code, item.severity) for item in found] == [("FB034", Severity.INFO)]
    assert found[0].message == "This rule matches nothing on the form: QProgressBar > QLabel."
    assert found[0].location.line == 2
    assert _diagnostics("QPushButton { color: red; }") == ()
    assert _diagnostics("") == ()
    # A sheet of declarations only styles the widget and what is inside it, so it always matches.
    assert _diagnostics("color: red;") == ()


def test_each_unreadable_sheet_and_each_unmatched_rule_has_its_own_row() -> None:
    found = _diagnostics("#nobody { color: red; } #nobodyElse { color: red; }", "QLabel { color:")
    assert sorted((item.code, item.location.object_name) for item in found) == [
        ("FB033", "okButton"),
        ("FB034", "Form"),
        ("FB034", "Form"),
    ]
    assert len({item.key for item in found}) == 3
    assert {"FB033", "FB034"} <= set(CODES)


def test_the_problems_rows_offer_edit_style_sheet_and_it_opens_the_drawer_on_that_widget(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host = QWidget()
    surface = _open(host, _form("QPushButton { color: red; }"), tmp_path / "invoice.ui")
    host.show()
    surface.show()
    host.resize(1200, 800)
    surface.resize(1200, 800)
    qapp.processEvents()
    try:
        session = surface.session
        ok = session.document.by_name("okButton")[0]
        session.log.execute(SetProperty(ok, "styleSheet", StringValue("QLabel { color:", notr=True)))
        QTest.qWait(400)
        qapp.processEvents()
        rows = code_diagnostics_for_form("/work/a.ui", session.diagnostics.all())
        bad = [row for row in rows if row.code == "FB033"]
        assert len(bad) == 1 and bad[0].message.startswith("okButton: The style sheet of okButton can't be read")
        assert json.loads(bad[0].detail["fixes"]) == [["edit-style-sheet", "Edit style sheet"]]
        assert surface.run_problem_fix("edit-style-sheet", bad[0].detail)
        assert surface.workbench.under_canvas_key() == "style"
        drawer = surface.workbench._under_widget
        assert drawer.target == ok and drawer.editor.toPlainText() == "QLabel { color:"
        drawer.close_drawer()
        # Fixing the text clears the row.
        session.log.undo()
        QTest.qWait(400)
        assert not [item for item in session.diagnostics.all() if item.code == "FB033"]
    finally:
        surface.release()
        host.close()
