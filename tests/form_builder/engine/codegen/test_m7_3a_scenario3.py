"""Invoice emailEdit: required, then an email, shown on the error label."""

from __future__ import annotations

import ast
import types
from pathlib import Path
from typing import Any

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog_ext.checks import AddErrorLabel, SetChecks
from app.features.form_builder.engine.logic.checks import Preset, Required
from app.features.form_builder.engine.project.forms import FormScope
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit

_INVOICE = Path(__file__).resolve().parents[2] / "fixtures" / "m7" / "forms" / "invoice.ui"


def test_email_edit_shows_the_first_failing_message(tmp_path: Path, qapp: Any) -> None:
    del qapp
    from PySide6.QtWidgets import QApplication, QDialog

    text = _INVOICE.read_text(encoding="utf-8")
    log = open_log(text)
    owner = nid(log.document, "emailEdit")
    log.execute(SetChecks(owner, (Required("Email is required"), Preset("email", None))))
    log.execute(AddErrorLabel(owner))
    path = tmp_path / "invoice.ui"
    path.write_text(text, encoding="utf-8")
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_invoice.py"),
        window_path=str(tmp_path / "invoice_window.py"),
        module_name="ui_invoice",
    )
    result = generate_form_module(log.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    assert not [item for item in result.diagnostics if item.code == "FB504"]
    source = result.text
    ast.parse(source, feature_version=(3, 9))
    assert "_cbcs_check_emailEdit" in source
    assert "def cbcs_validate(self):" in source
    assert "Email is required" in source
    assert "Enter an email address like name@example.com" in source
    assert "editingFinished" in source
    assert "textChanged" in source

    app = QApplication.instance()
    assert app is not None
    namespace: Any = types.ModuleType("generated_invoice")
    exec(compile(source, "ui_invoice.py", "exec"), namespace.__dict__)
    dialog = QDialog()
    ui = namespace.Ui_Invoice()
    ui.setupUi(dialog)
    dialog.show()
    app.processEvents()

    assert ui.cbcs_validate() is False
    app.processEvents()
    assert ui.emailEditError.text() == "Email is required"
    assert dialog.focusWidget() is ui.emailEdit
    assert ui.emailEdit.property("cbcsInvalid") is True

    ui.emailEdit.setText("a@b.co")
    assert ui.cbcs_validate() is True
    assert ui.emailEditError.text() == ""
    assert ui.emailEdit.property("cbcsInvalid") is False
    dialog.close()
