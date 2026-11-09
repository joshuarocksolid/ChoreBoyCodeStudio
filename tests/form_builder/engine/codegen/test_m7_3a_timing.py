"""Leave checks a dirty field. Typing updates a message only while one is showing."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Tuple

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog_ext.checks import AddErrorLabel, SetChecks
from app.features.form_builder.engine.logic.checks import FormulaCheck, Preset, Required
from app.features.form_builder.engine.project.forms import FormScope
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Timing</class>
 <widget class="QDialog" name="Timing">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="emailEdit"/>
   </item>
   <item>
    <widget class="QLineEdit" name="dueEdit"/>
   </item>
   <item>
    <widget class="QLineEdit" name="otherEdit"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _window(tmp_path: Path) -> Tuple[Any, Any]:
    from PySide6.QtWidgets import QApplication, QDialog

    log = open_log(_FORM)
    email = nid(log.document, "emailEdit")
    due = nid(log.document, "dueEdit")
    log.execute(SetChecks(email, (Required("Email is required"), Preset("email", None))))
    log.execute(AddErrorLabel(email))
    log.execute(SetChecks(due, (FormulaCheck('otherEdit == "ok"', "Pick ok"),)))
    log.execute(AddErrorLabel(due))
    path = tmp_path / "timing.ui"
    path.write_text(_FORM, encoding="utf-8")
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_timing.py"),
        window_path=str(tmp_path / "timing_window.py"),
        module_name="ui_timing",
    )
    result = generate_form_module(log.document, scope=scope, source_bytes=_FORM.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    assert not [item for item in result.diagnostics if item.code == "FB504"]
    namespace: Any = types.ModuleType("generated_timing")
    exec(compile(result.text, "ui_timing.py", "exec"), namespace.__dict__)
    app = QApplication.instance()
    assert app is not None
    dialog = QDialog()
    ui = namespace.Ui_Timing()
    ui.setupUi(dialog)
    dialog.show()
    app.processEvents()
    return dialog, ui


def test_leave_before_an_edit_does_not_show_an_error(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _window(tmp_path)
    ui.emailEdit.editingFinished.emit()
    assert ui.emailEditError.text() == ""
    assert ui.emailEditError.isVisible() is False
    dialog.close()


def test_edit_then_leave_shows_the_error(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _window(tmp_path)
    ui.emailEdit.setText("not-an-email")
    assert ui.emailEditError.text() == ""
    ui.emailEdit.editingFinished.emit()
    assert ui.emailEditError.text() == "Enter an email address like name@example.com"
    dialog.close()


def test_typing_after_a_clean_leave_does_not_show_an_error(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _window(tmp_path)
    ui.emailEdit.setText("a@b.co")
    ui.emailEdit.editingFinished.emit()
    assert ui.emailEditError.text() == ""
    ui.emailEdit.setText("nope")
    assert ui.emailEditError.text() == ""
    assert ui.emailEdit.property("cbcsInvalid") in (False, None)
    dialog.close()


def test_typing_a_valid_value_after_a_failed_leave_clears_the_label(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _window(tmp_path)
    ui.emailEdit.setText("nope")
    ui.emailEdit.editingFinished.emit()
    assert ui.emailEditError.text() == "Enter an email address like name@example.com"
    ui.emailEdit.setText("a@b.co")
    assert ui.emailEditError.text() == ""
    assert ui.emailEdit.property("cbcsInvalid") is False
    dialog.close()


def test_typing_after_a_failed_required_leave_shows_the_email_sentence(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _window(tmp_path)
    ui.emailEdit.setText("x")
    ui.emailEdit.setText("")
    ui.emailEdit.editingFinished.emit()
    assert ui.emailEditError.text() == "Email is required"
    ui.emailEdit.setText("a")
    assert ui.emailEditError.text() == "Enter an email address like name@example.com"
    dialog.close()


def test_validate_checks_a_field_that_was_never_touched(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _window(tmp_path)
    assert ui.cbcs_validate() is False
    assert ui.emailEditError.text() == "Email is required"
    assert dialog.focusWidget() is ui.emailEdit
    dialog.close()


def test_changing_another_field_updates_only_a_visible_check(tmp_path: Path, qapp: Any) -> None:
    del qapp
    dialog, ui = _window(tmp_path)
    ui.emailEdit.setText("a@b.co")
    ui.otherEdit.setText("no")
    assert ui.dueEditError.text() == ""
    assert ui.cbcs_validate() is False
    assert ui.dueEditError.text() == "Pick ok"
    ui.otherEdit.setText("ok")
    assert ui.dueEditError.text() == ""
    dialog.close()
