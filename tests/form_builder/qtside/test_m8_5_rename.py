# pyright: reportAttributeAccessIssue=false
"""Renaming a method rewrites a closed form and leaves an untouched file byte for byte."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog import SetFormSlots, SetLogic
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events_codec import call_step
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.rename_ext.methods import MethodRename, MethodSeed
from app.qt.QtWidgets import QApplication, QPlainTextEdit, QWidget
from tests.form_builder.qtside.test_m7_8b_rename import _Patch, _Plan, _Surface, _UI, _names

pytestmark = pytest.mark.unit

_CLOSED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Other</class>
 <widget class="QDialog" name="Other">
  <widget class="QPushButton" name="saveButton">
   <property name="cbcsOnClicked" stdset="0">
    <string notr="true">[{"do": "call", "method": "save_invoice"}]</string>
   </property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_UNTOUCHED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Plain</class>
 <widget class="QDialog" name="Plain">
  <widget class="QPushButton" name="okButton"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_a_closed_form_is_rewritten_and_an_untouched_file_is_not(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "notes.ui"
    window_path = str(forms / "invoice_window.py")
    ui_path.write_text(_UI, encoding="utf-8")
    session = FormSession.open(
        _UI,
        path=str(ui_path),
        scope=FormScope(kind="project", ui_path=str(ui_path), project_root=str(root), window_path=window_path),
    )
    note = session.document.by_name("noteEdit")[0]
    listed = replace(call_step("save_invoice"), when="True")
    with session.log.transaction("Build"):
        session.log.execute(SetFormSlots((), ("save_invoice()",)))
        session.log.execute(SetEventSteps("saveButton", "clicked", (call_step("save_invoice"),)))
        session.log.execute(SetEventSteps("otherButton", "clicked", (listed,)))
        session.log.execute(SetLogic(note, "cbcsValue", "window.save_invoice()"))
    surface = _Surface(session, str(ui_path), window_path)
    closed = forms / "invoice.ui"
    other = forms / "other.ui"
    untouched = forms / "plain.ui"
    closed.write_bytes(_CLOSED.replace("Other", "Invoice").encode("utf-8"))
    other.write_bytes(_CLOSED.encode("utf-8"))
    untouched.write_bytes(_UNTOUCHED.encode("utf-8"))
    before_closed = closed.read_bytes()
    before_other = other.read_bytes()
    before_plain = untouched.read_bytes()
    before_open = ui_path.read_bytes()
    source = "class InvoiceWindow(object):\n    def save_invoice(self):\n        return None\n"
    updated = source.replace("save_invoice", "save_more")
    editor = QPlainTextEdit()
    editor.setPlainText(source)
    window = QWidget()
    window._workspace_controller = type(  # type: ignore[attr-defined]
        "C",
        (),
        {"widget_for_path": lambda _self, path: editor if os.path.abspath(path) == os.path.abspath(window_path) else None},
    )()
    window._form_undo_surface = surface  # type: ignore[attr-defined]
    plan = _Plan("save_invoice", "save_more", [object()], [_Patch(window_path, updated, "invoice_window.py")])
    rename = MethodRename()
    note = rename.closed_note(window, MethodSeed("save_invoice", window_path, source, 0), plan)
    assert note == "Also changes invoice.ui (closed)"
    follow = rename.apply_paired(window, MethodSeed("save_invoice", window_path, source, 0), plan)
    assert follow.blocked is False
    assert "save_more" in closed.read_text(encoding="utf-8")
    assert "save_invoice" not in closed.read_text(encoding="utf-8")
    assert closed.read_bytes() != before_closed
    assert other.read_bytes() == before_other
    assert untouched.read_bytes() == before_plain
    assert ui_path.read_bytes() == before_open
    assert session.log.undo_label() == "Rename save_invoice to save_more"
    assert session.log.undo() is True
    assert "save_invoice" in _names(session)
    assert "save_more" not in _names(session)
    assert closed.read_bytes() == before_closed


def test_a_rename_of_open_tabs_only_leaves_the_window_file(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "notes.ui"
    window_path = forms / "invoice_window.py"
    ui_path.write_text(_UI, encoding="utf-8")
    session = FormSession.open(
        _UI,
        path=str(ui_path),
        scope=FormScope(kind="project", ui_path=str(ui_path), project_root=str(root), window_path=str(window_path)),
    )
    note = session.document.by_name("noteEdit")[0]
    with session.log.transaction("Build"):
        session.log.execute(SetFormSlots((), ("save_invoice()",)))
        session.log.execute(SetEventSteps("saveButton", "clicked", (call_step("save_invoice"),)))
        session.log.execute(SetLogic(note, "cbcsValue", "window.save_invoice()"))
    source = "class InvoiceWindow(object):\n    def save_invoice(self):\n        return None\n"
    window_path.write_text(source, encoding="utf-8")
    before = window_path.read_bytes()
    editor = QPlainTextEdit()
    editor.setPlainText(source)
    window = QWidget()
    window._workspace_controller = type(  # type: ignore[attr-defined]
        "C",
        (),
        {"widget_for_path": lambda _self, path: editor if os.path.abspath(path) == os.path.abspath(window_path) else None},
    )()
    window._form_undo_surface = _Surface(session, str(ui_path), str(window_path))  # type: ignore[attr-defined]
    updated = source.replace("save_invoice", "save_more")
    plan = _Plan("save_invoice", "save_more", [object()], [_Patch(str(window_path), updated, "invoice_window.py")])
    follow = MethodRename().apply_paired(window, MethodSeed("save_invoice", str(window_path), source, 0), plan)
    assert follow.blocked is False
    assert "save_more" in editor.toPlainText()
    assert window_path.read_bytes() == before
    assert session.log.undo() is True
    assert "save_invoice" in _names(session)
    assert "save_more" in editor.toPlainText()
    assert window_path.read_bytes() == before


def test_a_closed_tab_rename_writes_the_window_and_undo_restores_it(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "notes.ui"
    window_path = forms / "invoice_window.py"
    ui_path.write_text(_UI, encoding="utf-8")
    session = FormSession.open(
        _UI,
        path=str(ui_path),
        scope=FormScope(kind="project", ui_path=str(ui_path), project_root=str(root), window_path=str(window_path)),
    )
    note = session.document.by_name("noteEdit")[0]
    with session.log.transaction("Build"):
        session.log.execute(SetFormSlots((), ("save_invoice()",)))
        session.log.execute(SetEventSteps("saveButton", "clicked", (call_step("save_invoice"),)))
        session.log.execute(SetLogic(note, "cbcsValue", "window.save_invoice()"))
    source = "class InvoiceWindow(object):\n    def save_invoice(self):\n        return None\n"
    window_path.write_bytes(source.encode("utf-8"))
    before_window = window_path.read_bytes()
    closed = forms / "invoice.ui"
    closed.write_bytes(_CLOSED.replace("Other", "Invoice").encode("utf-8"))
    before_closed = closed.read_bytes()
    window = QWidget()
    window._workspace_controller = type("C", (), {"widget_for_path": lambda _self, _path: None})()  # type: ignore[attr-defined]
    window._form_undo_surface = _Surface(session, str(ui_path), str(window_path))  # type: ignore[attr-defined]
    updated = source.replace("save_invoice", "save_more")
    plan = _Plan("save_invoice", "save_more", [object()], [_Patch(str(window_path), updated, "invoice_window.py")])
    follow = MethodRename().apply_paired(window, MethodSeed("save_invoice", str(window_path), source, 0), plan)
    assert follow.blocked is False
    assert b"save_more" in window_path.read_bytes()
    assert b"save_more" in closed.read_bytes()
    assert session.log.undo() is True
    assert window_path.read_bytes() == before_window
    assert closed.read_bytes() == before_closed
    assert session.log.redo() is True
    assert b"save_more" in window_path.read_bytes()
    closed.write_bytes(closed.read_bytes() + b"\n")
    assert session.log.undo() is False
    assert "invoice.ui" in str(getattr(session.log, "_cbcs_rename_notice", ""))


def _closed_rename(tmp_path: Path) -> tuple:
    """An open notes form, a closed invoice.ui, and the rename that follows."""

    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    (root / "cbcs").mkdir()
    (root / "cbcs" / "project.json").write_text(
        '{"schema_version": 2, "name": "Shop", "default_entry": "main.py"}\n',
        encoding="utf-8",
    )
    (forms / "__init__.py").write_text("", encoding="utf-8")
    ui_path = forms / "notes.ui"
    window_path = forms / "invoice_window.py"
    ui_path.write_text(_UI, encoding="utf-8")
    session = FormSession.open(
        _UI,
        path=str(ui_path),
        scope=FormScope(kind="project", ui_path=str(ui_path), project_root=str(root), window_path=str(window_path)),
    )
    note = session.document.by_name("noteEdit")[0]
    with session.log.transaction("Build"):
        session.log.execute(SetFormSlots((), ("save_invoice()",)))
        session.log.execute(SetEventSteps("saveButton", "clicked", (call_step("save_invoice"),)))
        session.log.execute(SetLogic(note, "cbcsValue", "window.save_invoice()"))
    source = "class InvoiceWindow(object):\n    def save_invoice(self):\n        return None\n"
    window_path.write_bytes(source.encode("utf-8"))
    closed = forms / "invoice.ui"
    closed_text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QDialog" name="Invoice">
  <widget class="QPushButton" name="saveButton"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
    closed_session = FormSession.open(
        closed_text,
        path=str(closed),
        scope=FormScope(kind="project", ui_path=str(closed), project_root=str(root), window_path=str(window_path)),
    )
    closed_session.log.execute(SetEventSteps("saveButton", "clicked", (call_step("save_invoice"),)))
    closed.write_text(closed_session.text(), encoding="utf-8")
    from app.features.form_builder.engine.codegen.api import generate_form_module
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.project.forms import classify_form
    from app.features.form_builder.engine.ui4.reader import read_ui

    scope = classify_form(str(closed), project_root=str(root))
    document = read_ui(closed.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    generated = Path(scope.generated_path or "")
    generated.write_text(
        generate_form_module(document, scope=scope, source_bytes=closed.read_bytes()).text or "",
        encoding="utf-8",
    )
    window = QWidget()
    window._workspace_controller = type("C", (), {"widget_for_path": lambda _self, _path: None})()  # type: ignore[attr-defined]
    window._form_undo_surface = _Surface(session, str(ui_path), str(window_path))  # type: ignore[attr-defined]
    updated = source.replace("save_invoice", "save_more")
    plan = _Plan("save_invoice", "save_more", [object()], [_Patch(str(window_path), updated, "invoice_window.py")])
    return window, session, window_path, closed, generated, source, plan


def test_a_closed_rename_regenerates_the_module_and_undo_restores_every_byte(
    tmp_path: Path, qapp: QApplication
) -> None:
    import importlib.util

    from app.qt.QtWidgets import QDialog

    window, session, window_path, closed, generated, source, plan = _closed_rename(tmp_path)
    os.chmod(window_path, 0o644)
    os.chmod(closed, 0o755)
    os.chmod(generated, 0o664)
    before = (window_path.read_bytes(), closed.read_bytes(), generated.read_bytes())
    follow = MethodRename().apply_paired(window, MethodSeed("save_invoice", str(window_path), source, 0), plan)
    assert follow.blocked is False
    fresh = generated.read_text(encoding="utf-8")
    assert "clicked.connect(Invoice.save_more)" in fresh
    assert "save_invoice" not in fresh
    spec = importlib.util.spec_from_file_location("ui_invoice_disk", generated)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ui_cls = next(value for name, value in vars(module).items() if isinstance(value, type) and name.startswith("Ui_"))
    calls: list[str] = []

    class Host(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.ui = ui_cls()
            self.ui.setupUi(self)

        def save_more(self) -> None:
            calls.append("save_more")

    host = Host()
    try:
        host.ui.saveButton.click()
        qapp.processEvents()
        assert calls == ["save_more"]
    finally:
        host.close()
        host.deleteLater()
        qapp.processEvents()
    assert session.log.undo() is True
    assert (window_path.read_bytes(), closed.read_bytes(), generated.read_bytes()) == before
    assert window_path.stat().st_mode & 0o777 == 0o644
    assert closed.stat().st_mode & 0o777 == 0o755
    assert generated.stat().st_mode & 0o777 == 0o664


def test_rename_undo_names_the_window_when_it_changed_on_disk(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    window, session, window_path, _closed, _generated, source, plan = _closed_rename(tmp_path)
    follow = MethodRename().apply_paired(window, MethodSeed("save_invoice", str(window_path), source, 0), plan)
    assert follow.blocked is False
    window_path.write_bytes(window_path.read_bytes() + b"\n# on disk\n")
    assert session.log.undo() is False
    assert "invoice_window.py" in str(getattr(session.log, "_cbcs_rename_notice", ""))


def test_a_closed_rename_refuses_a_hand_edited_module(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    window, session, window_path, closed, generated, source, plan = _closed_rename(tmp_path)
    generated.write_text(generated.read_text(encoding="utf-8") + "\n# MY HAND EDIT\n", encoding="utf-8")
    before = (window_path.read_bytes(), closed.read_bytes(), generated.read_bytes())
    follow = MethodRename().apply_paired(window, MethodSeed("save_invoice", str(window_path), source, 0), plan)
    assert follow.blocked is True
    assert follow.message == "ui_invoice.py has edits made by hand. Saving the form will replace them."
    assert (window_path.read_bytes(), closed.read_bytes(), generated.read_bytes()) == before
    assert "save_invoice" in _names(session)
    assert "save_more" not in _names(session)


def test_a_closed_rename_refuses_a_dirty_generated_tab(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    window, session, window_path, closed, generated, source, plan = _closed_rename(tmp_path)
    editor = QPlainTextEdit()
    editor.setPlainText(generated.read_text(encoding="utf-8") + "\n# MY UNSAVED HAND EDIT\n")
    window._workspace_controller = type(  # type: ignore[attr-defined]
        "C",
        (),
        {
            "widget_for_path": lambda _self, path: editor
            if os.path.abspath(path) == os.path.abspath(generated)
            else None
        },
    )()
    before = generated.read_bytes()
    closed_before = closed.read_bytes()
    follow = MethodRename().apply_paired(window, MethodSeed("save_invoice", str(window_path), source, 0), plan)
    assert follow.blocked is True
    assert follow.message == "Save or discard your changes to ui_invoice.py first."
    assert generated.read_bytes() == before
    assert closed.read_bytes() == closed_before
    assert "save_invoice" in _names(session)
