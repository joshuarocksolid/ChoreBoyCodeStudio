"""Jedi, through CBCS's completion service, offers the form's widget names."""

from __future__ import annotations

from pathlib import Path

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import read_ui
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_service import CompletionRequest, CompletionService

_BUTTON = (
    '<widget class="QPushButton" name="%(name)s">'
    '<property name="text"><string>%(name)s</string></property>'
    "</widget>"
)


def _labels(root: Path, service: CompletionService) -> set[str]:
    window = root / "forms" / "invoice_window.py"
    source = window.read_text(encoding="utf-8")
    marker = "self.ui."
    cursor = source.index(marker) + len(marker)
    request = CompletionRequest(
        source_text=source,
        cursor_position=cursor,
        current_file_path=str(window.resolve()),
        project_root=str(root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=1,
        max_results=200,
        trigger_kind="trigger_character",
        trigger_character=".",
    )
    envelope = service.complete(request)
    return {item.label for item in envelope.items if isinstance(item, CompletionItem)}


def test_completion_follows_a_widget_rename(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    ui = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>Invoice</class>\n"
        ' <widget class="QWidget" name="Invoice">\n'
        '  <property name="windowTitle"><string>Hello</string></property>\n'
        "  %s\n"
        " </widget>\n"
        "</ui>\n"
    )
    create_form(str(root), "invoice", fs)
    ui_path = root / "forms" / "invoice.ui"
    ui_path.write_text(ui % (_BUTTON % {"name": "okButton"}), encoding="utf-8")
    scope = scope_for(str(ui_path), str(root), fs)
    document = read_ui(ui_path.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    write_generated(scope, document, ui_path.read_bytes(), fs)
    service = CompletionService(cache_db_path=str(tmp_path / "symbols.sqlite3"))
    offered = _labels(root, service)
    assert "okButton" in offered

    ui_path.write_text(ui % (_BUTTON % {"name": "saveButton"}), encoding="utf-8")
    document = read_ui(ui_path.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    write_generated(scope, document, ui_path.read_bytes(), fs)
    renamed = _labels(root, service)
    assert "saveButton" in renamed
    assert "okButton" not in renamed
