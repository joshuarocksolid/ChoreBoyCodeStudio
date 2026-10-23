"""Built-in templates round-trip and build a module the loader can show."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.names import (
    NAME_PATTERN_MESSAGE,
    name_row_reason,
    unique_form_stem,
)
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.templates import (
    build_template_ui,
    template_for,
    template_keys,
)
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_NAMED = {
    "data_entry": ("nameLabel", "nameEdit", "emailEdit", "notesEdit"),
    "list_detail": ("itemList", "nameEdit", "emailEdit"),
    "table_search": ("searchEdit", "resultTable"),
    "dialog_ok_cancel": ("nameEdit", "emailEdit", "buttonBox"),
    "widget": (),
    "main_window": ("centralwidget",),
    "dialog": (),
}


def _load(text: str, qapp: object):
    del qapp
    from app.qt.QtCore import QBuffer, QIODevice
    from app.qt.QtUiTools import QUiLoader

    buffer = QBuffer()
    buffer.setData(text.encode("utf-8"))
    buffer.open(QIODevice.ReadOnly)
    loader = QUiLoader()
    widget = loader.load(buffer)
    return widget, loader.errorString()


@pytest.mark.parametrize("key", template_keys())
def test_template_round_trips_and_loads(key: str, tmp_path: Path, qapp: object) -> None:
    text = build_template_ui(key, "Invoice")
    assert "label_2" not in text
    document = read_ui(text, allocator=IdAllocator()).document
    assert write_ui(document).text == text

    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    ui_path.write_text(text, encoding="utf-8")
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(tmp_path),
        generated_path=str(forms / "ui_invoice.py"),
        window_path=str(forms / "invoice_window.py"),
        module_name="forms.ui_invoice",
    )
    generated = generate_form_module(document, scope=scope, source_bytes=text.encode("utf-8"))
    assert generated.text
    ast.parse(generated.text)

    widget, error = _load(text, qapp)
    assert widget is not None, error
    assert error == ""
    spec = template_for(key)
    assert spec is not None
    assert widget.metaObject().className() == spec.root_class
    from app.qt.QtWidgets import QWidget

    for name in _NAMED[key]:
        assert widget.findChild(QWidget, name) is not None, name
    layout = widget.layout()
    if layout is None and hasattr(widget, "centralWidget"):
        central = widget.centralWidget()
        layout = None if central is None else central.layout()
    assert layout is not None


def test_the_name_row_uses_the_start_sentence_for_bad_characters(tmp_path: Path) -> None:
    folder = str(tmp_path)
    fs = OsFileSystem()
    assert name_row_reason("9invoice", folder=folder, fs=fs) == NAME_PATTERN_MESSAGE
    assert name_row_reason("invoice", folder=folder, fs=fs) is None
    keyword = name_row_reason("class", folder=folder, fs=fs)
    assert keyword is not None
    assert "keyword" in keyword


def test_the_default_name_skips_a_form_already_in_the_folder(tmp_path: Path) -> None:
    (tmp_path / "new_form.ui").write_text("<ui/>\n", encoding="utf-8")
    assert unique_form_stem(str(tmp_path), OsFileSystem()) == "new_form_2"
