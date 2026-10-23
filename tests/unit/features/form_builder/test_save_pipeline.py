"""Codegen after the .ui bytes are on disk does not undo the save."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.integration.save_pipeline import finish_save

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
 <resources/>
 <connections/>
</ui>
"""

_BAD = _FORM.replace('name="Form"', 'name="class"', 1)


def test_generating_save_writes_the_module_bytes(tmp_path: Path) -> None:
    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    ui_path.write_text(_FORM, encoding="utf-8")
    scope = classify_form(str(ui_path), project_root=str(tmp_path))
    document = read_ui(_FORM, allocator=IdAllocator()).document
    notice = finish_save(scope, document, _FORM, OsFileSystem())

    assert notice.error is False
    assert notice.text == "Saved · ui_invoice.py updated"
    written = Path(scope.generated_path or "").read_bytes()
    expected = generate_form_module(document, scope=scope, source_bytes=_FORM.encode("utf-8")).text
    assert expected is not None
    assert written == expected.encode("utf-8")


def test_codegen_refusal_is_a_notice(tmp_path: Path) -> None:
    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    ui_path.write_text(_BAD, encoding="utf-8")
    scope = classify_form(str(ui_path), project_root=str(tmp_path))
    document = read_ui(_BAD, allocator=IdAllocator()).document
    notice = finish_save(scope, document, _BAD, OsFileSystem())

    assert notice.error is True
    assert "ui_invoice.py not written" in notice.text
    assert not (forms / "ui_invoice.py").exists()
