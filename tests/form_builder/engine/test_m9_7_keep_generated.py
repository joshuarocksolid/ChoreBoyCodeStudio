"""A missing connection must not replace a good generated module."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.source import RecordSource, write_data
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.unit

_KEPT = "The form has a data error, so the previous generated Python file was left unchanged."
_NONE = "The form has a data error, so no Python file was written."


def _invoice_ui() -> str:
    data = escape(write_data(RecordSource("shop", "invoices", "id")))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>Invoice</class>\n"
        ' <widget class="QWidget" name="Invoice">\n'
        '  <property name="windowTitle"><string>Hello</string></property>\n'
        '  <property name="cbcsData" stdset="0"><string notr="true">%s</string></property>\n'
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "   <item>\n"
        '    <widget class="QLineEdit" name="notesEdit">\n'
        '     <property name="cbcsBind" stdset="0"><string notr="true">notes</string></property>\n'
        "    </widget>\n"
        "   </item>\n"
        "  </layout>\n"
        " </widget>\n"
        "</ui>\n"
    ) % data


def _load(path: Path):
    return read_ui(path.read_text(encoding="utf-8"), allocator=IdAllocator()).document


def _project(tmp_path: Path):
    root = tmp_path / "proj"
    fs = OsFileSystem()
    created = create_form(str(root), "invoice", fs)
    assert created.refused is None
    save_connections(
        str(root),
        ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),)),
    )
    ui_path = root / "forms" / "invoice.ui"
    ui_path.write_text(_invoice_ui(), encoding="utf-8")
    scope = scope_for(str(ui_path), str(root), fs)
    document = _load(ui_path)
    first = write_generated(scope, document, ui_path.read_bytes(), fs)
    assert first.text_written is True
    generated = root / "forms" / "ui_invoice.py"
    assert b"def cbcs_save" in generated.read_bytes()
    return fs, scope, document, ui_path, generated, root


def test_a_missing_connection_keeps_the_previous_python_file(tmp_path: Path) -> None:
    fs, scope, document, ui_path, generated, root = _project(tmp_path)
    before = generated.read_bytes()
    save_connections(str(root), ConnectionSet())
    result = write_generated(scope, document, ui_path.read_bytes(), fs)
    assert generated.read_bytes() == before
    assert result.text_written is False
    assert result.files == ()
    codes = {item.code for item in result.diagnostics}
    assert "FB301" in codes
    assert "FB510" in codes
    kept = next(item for item in result.diagnostics if item.code == "FB510")
    assert kept.message == _KEPT


def test_a_missing_connection_writes_nothing_when_no_python_file_exists(tmp_path: Path) -> None:
    fs, scope, document, ui_path, generated, root = _project(tmp_path)
    generated.unlink()
    save_connections(str(root), ConnectionSet())
    result = write_generated(scope, document, ui_path.read_bytes(), fs)
    assert not generated.exists()
    assert result.text_written is False
    assert result.files == ()
    codes = {item.code for item in result.diagnostics}
    assert "FB301" in codes
    assert "FB510" in codes
    missing = next(item for item in result.diagnostics if item.code == "FB510")
    assert missing.message == _NONE
