"""Rename, move and delete keep cross-form open steps, or Problems names the form."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import parse_steps, write_steps
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.form_refs import missing_form_sentence
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.rename import apply, plan_rename
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.integration.content_source import open_document_log

pytestmark = pytest.mark.unit


def _arm(path: Path, stem: str) -> None:
    log = open_document_log(path.read_text(encoding="utf-8"))
    read = parse_steps('[{"do": "openForm", "form": "%s", "mode": "dialog"}]' % stem)
    assert read.error is None
    log.execute(SetLogic(log.document.root.id, "cbcsOnClicked", write_steps(read.steps)))
    path.write_text(write_ui_text(log), encoding="utf-8")


def write_ui_text(log: object) -> str:
    from app.features.form_builder.engine.ui4.writer import write_ui

    return write_ui(log.document).text  # type: ignore[attr-defined]


def _regenerate(root: Path, stem: str, fs: OsFileSystem) -> None:
    path = root / "forms" / ("%s.ui" % stem)
    text = path.read_text(encoding="utf-8")
    scope = scope_for(str(path), str(root), fs)
    document = read_ui(text, allocator=IdAllocator()).document
    write_generated(scope, document, text.encode("utf-8"), fs)


def test_rename_follows_an_open_form_step_and_delete_names_it(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    assert create_form(str(root), "sale", fs).refused is None
    sale = root / "forms" / "sale.ui"
    _arm(sale, "customer")
    _regenerate(root, "sale", fs)
    plan = plan_rename(str(root), str(root / "forms" / "customer.ui"), str(root / "forms" / "client.ui"), fs)
    assert plan.reason is None, plan.reason
    apply(plan, fs)
    sale_text = sale.read_text(encoding="utf-8")
    document = read_ui(sale_text, allocator=IdAllocator()).document
    entry = document.root.prop("cbcsOnClicked")
    assert entry is not None
    stored = getattr(entry.value, "text", None)
    assert isinstance(stored, str)
    opened = parse_steps(stored)
    assert opened.error is None
    assert ("form", "client") in opened.steps[0].fields
    generated = (root / "forms" / "ui_sale.py").read_text(encoding="utf-8")
    assert "from forms.client_window import ClientWindow" in generated
    assert (root / "forms" / "ui_client.py").is_file()
    assert not (root / "forms" / "ui_customer.py").exists()
    assert (root / "forms" / "__init__.py").is_file()
    for name in ("client.ui", "ui_client.py", "client_window.py"):
        os.remove(str(root / "forms" / name))
    document = read_ui(sale_text, allocator=IdAllocator()).document
    scope = scope_for(str(sale), str(root), fs)
    result = generate_form_module(document, scope=scope, source_bytes=sale.read_bytes())
    messages = [item.message for item in result.diagnostics if item.code == "FB120"]
    assert messages == [missing_form_sentence("client")]
