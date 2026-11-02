"""US formats rewrite a line edit on leave. A plain form stays free of check and format code."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Format</class>
 <widget class="QDialog" name="Format">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="amountEdit">
     <property name="cbcsFormat" stdset="0"><string>money</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="rateEdit">
     <property name="cbcsFormat" stdset="0"><string>percent:1</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="whenEdit">
     <property name="cbcsFormat" stdset="0"><string>date:short</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_PLAIN = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Plain</class>
 <widget class="QDialog" name="Plain">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="nameEdit"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _load(text: str, stem: str, tmp_path: Path) -> Any:
    from PySide6.QtWidgets import QApplication, QDialog

    path = tmp_path / ("%s.ui" % stem)
    path.write_text(text, encoding="utf-8")
    document = read_ui(text, allocator=IdAllocator()).document
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / ("ui_%s.py" % stem)),
        window_path=str(tmp_path / ("%s_window.py" % stem)),
        module_name="ui_%s" % stem,
    )
    result = generate_form_module(document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    assert not [item for item in result.diagnostics if item.code == "FB504"]
    namespace: Any = types.ModuleType("generated_%s" % stem)
    exec(compile(result.text, "ui_%s.py" % stem, "exec"), namespace.__dict__)
    app = QApplication.instance()
    assert app is not None
    dialog = QDialog()
    ui = namespace.Ui_Format()
    ui.setupUi(dialog)
    dialog.show()
    app.processEvents()
    ui._source = result.text
    return dialog, ui


def test_us_money_percent_and_date_rewrite_on_leave(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _load(_FORM, "format", tmp_path)
    assert "_cbcs_write_amountEdit" in ui._source
    ui.amountEdit.setText("1234.5")
    ui.amountEdit.editingFinished.emit()
    assert ui.amountEdit.text() == "$1,234.50"
    ui.amountEdit.editingFinished.emit()
    assert ui.amountEdit.text() == "$1,234.50"

    ui.rateEdit.setText("0.125")
    ui.rateEdit.editingFinished.emit()
    assert ui.rateEdit.text() == "12.5%"
    ui.rateEdit.editingFinished.emit()
    assert ui.rateEdit.text() == "12.5%"

    ui.whenEdit.setText("2026-10-20")
    ui.whenEdit.editingFinished.emit()
    assert ui.whenEdit.text() == "10/20/2026"
    ui.whenEdit.editingFinished.emit()
    assert ui.whenEdit.text() == "10/20/2026"
    dialog.close()


def test_an_impossible_us_short_date_stays_out_of_the_field_value(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _load(_FORM, "format_us", tmp_path)
    ui.whenEdit.setText("31/01/2026")
    ui.whenEdit.editingFinished.emit()
    assert ui.whenEdit.text() == "31/01/2026"
    assert ui.whenEdit.toolTip() == "Enter a date as MM/DD/YYYY."
    dialog.close()


def test_a_day_month_short_date_keeps_the_day(tmp_path: Path, qapp: Any) -> None:
    del qapp
    meta = tmp_path / "cbcs"
    meta.mkdir()
    (meta / "project.json").write_text(
        '{"formats": {"date": "DD/MM/YYYY"}}\n',
        encoding="utf-8",
    )
    dialog, ui = _load(_FORM, "format_dmy", tmp_path)
    ui.whenEdit.setText("04/03/2026")
    ui.whenEdit.editingFinished.emit()
    assert ui.whenEdit.text() == "04/03/2026"
    ui.whenEdit.editingFinished.emit()
    assert ui.whenEdit.text() == "04/03/2026"
    ui.whenEdit.setText("31/13/2026")
    ui.whenEdit.editingFinished.emit()
    assert ui.whenEdit.text() == "31/13/2026"
    assert ui.whenEdit.toolTip() == "Enter a date as DD/MM/YYYY."
    dialog.close()


def test_a_form_with_no_format_and_no_checks_emits_neither(tmp_path: Path) -> None:
    path = tmp_path / "plain.ui"
    path.write_text(_PLAIN, encoding="utf-8")
    document = read_ui(_PLAIN, allocator=IdAllocator()).document
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_plain.py"),
        window_path=str(tmp_path / "plain_window.py"),
        module_name="ui_plain",
    )
    result = generate_form_module(document, scope=scope, source_bytes=_PLAIN.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    assert "_cbcs_format" not in result.text
    assert "_cbcs_check" not in result.text
