# pyright: reportAttributeAccessIssue=false
"""Rename a method used three ways. One form undo. Cancel and close write nothing."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog import SetFormSlots, SetLogic  # noqa: E402
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps  # noqa: E402
from app.features.form_builder.engine.logic.compat import split_signature  # noqa: E402
from app.features.form_builder.engine.logic.events import declared_methods, read_events  # noqa: E402
from app.features.form_builder.engine.logic.events_codec import call_step  # noqa: E402
from app.features.form_builder.engine.project.handler_checks import shadow_sentence  # noqa: E402
from app.features.form_builder.engine.project.forms import FormScope  # noqa: E402
from app.features.form_builder.engine.session import FormSession  # noqa: E402
from app.features.form_builder.integration.rename_ext.methods import MethodRename, MethodSeed  # noqa: E402
from app.qt.QtWidgets import QApplication, QPlainTextEdit, QWidget  # noqa: E402
from app.shell.semantic_rename_workflow import SemanticRenameWorkflow  # noqa: E402

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QDialog" name="Invoice">
  <widget class="QPushButton" name="saveButton">
   <property name="text"><string>Save</string></property>
  </widget>
  <widget class="QPushButton" name="otherButton">
   <property name="text"><string>Other</string></property>
  </widget>
  <widget class="QLineEdit" name="noteEdit"/>
 </widget>
</ui>
"""


class _Surface:
    def __init__(self, session: FormSession, ui_path: str, window_path: str) -> None:
        self.session = session
        self._ui = ui_path
        self._py = window_path

    def form_path(self) -> str:
        return self._ui

    def logic_window_file(self) -> str:
        return os.path.basename(self._py)


def _open(tmp_path: Path) -> tuple:
    ui_path = tmp_path / "invoice.ui"
    window_path = tmp_path / "invoice_window.py"
    ui_path.write_text(_UI, encoding="utf-8")
    session = FormSession.open(
        _UI,
        path=str(ui_path),
        scope=FormScope(kind="external", ui_path=str(ui_path)),
    )
    note = session.document.by_name("noteEdit")[0]
    listed = replace(call_step("save_invoice"), when="True")
    with session.log.transaction("Build"):
        session.log.execute(SetFormSlots((), ("save_invoice()",)))
        session.log.execute(SetEventSteps("saveButton", "clicked", (call_step("save_invoice"),)))
        session.log.execute(SetEventSteps("otherButton", "clicked", (listed,)))
        session.log.execute(SetLogic(note, "cbcsValue", "window.save_invoice()"))
    return session, _Surface(session, str(ui_path), str(window_path)), str(window_path)


def _names(session: FormSession) -> set:
    found = set(declared_methods(session.document))
    for state in read_events(session.document):
        for step in state.steps:
            if step.method:
                found.add(step.method)
            if step.slot:
                found.add(split_signature(step.slot)[0])
    return found


@dataclass
class _Patch:
    file_path: str
    updated_content: str
    relative_path: str = ""
    diff_text: str = ""
    changed_line_numbers: tuple = ()


@dataclass
class _Plan:
    old_symbol: str
    new_symbol: str
    hits: list
    preview_patches: list
    metadata: object = None

    @property
    def touched_files(self) -> list:
        return [patch.file_path for patch in self.preview_patches]


def test_rename_is_one_form_undo(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    session, surface, window_path = _open(tmp_path)
    before = session.text()
    source = "class InvoiceWindow(object):\n    def save_invoice(self):\n        return None\n"
    updated = source.replace("save_invoice", "save_more")
    editor = QPlainTextEdit()
    editor.setPlainText(source)
    window = QWidget()
    window._workspace_controller = type("C", (), {"widget_for_path": lambda _self, path: editor if os.path.abspath(path) == os.path.abspath(window_path) else None})()  # type: ignore[attr-defined]
    window._form_undo_surface = surface  # type: ignore[attr-defined]
    plan = _Plan("save_invoice", "save_more", [object()], [_Patch(window_path, updated, "invoice_window.py")])
    follow = MethodRename().apply_paired(window, MethodSeed("save_invoice", window_path, source, 0), plan)
    assert follow.blocked is False
    assert "save_more" in _names(session)
    assert "save_invoice" not in _names(session)
    assert "window.save_more()" in session.text()
    assert session.log.undo_label() == "Rename save_invoice to save_more"
    assert editor.toPlainText() == updated
    editor.undo()
    assert editor.toPlainText() == source
    assert session.log.undo()
    assert session.text() == before
    assert "save_invoice" in _names(session)
    assert "save_more" not in _names(session)


class _Controller:
    def __init__(self, plan: _Plan) -> None:
        self.plan = plan
        self.plans = 0
        self.applies = 0

    def request_rename_plan(self, **kwargs: object) -> None:
        self.plans += 1
        kwargs["on_success"](self.plan)  # type: ignore[operator]

    def request_apply_rename(self, **_kwargs: object) -> None:
        self.applies += 1


class _Host:
    def __init__(self, window: QWidget, controller: _Controller, root: Path) -> None:
        self._window = window
        self._controller = controller
        self._root = root
        self.saved = False

    def dialog_parent(self) -> QWidget:
        return self._window

    def loaded_project(self) -> object:
        return type("P", (), {"project_root": str(self._root)})()

    def save_all_files(self) -> bool:
        self.saved = True
        return True

    def intelligence_metrics_logging_enabled(self) -> bool:
        return False

    def intelligence_controller(self) -> _Controller:
        return self._controller


def _run(tmp_path: Path, new_name: str, question: object, monkeypatch: pytest.MonkeyPatch) -> tuple:
    session, surface, window_path = _open(tmp_path)
    before = session.text()
    window = QWidget()
    window._form_undo_surface = surface  # type: ignore[attr-defined]
    hook = MethodRename()
    hook.arm(surface, "save_invoice")
    window._form_builder_method_rename = hook  # type: ignore[attr-defined]
    plan = _Plan("save_invoice", new_name, [object()], [_Patch(window_path, "x", "invoice_window.py", "diff")])
    controller = _Controller(plan)
    import app.shell.semantic_rename_workflow as workflow

    monkeypatch.setattr(workflow.QInputDialog, "getText", lambda *_args, **_kwargs: (new_name, True))
    monkeypatch.setattr(workflow.QMessageBox, "question", lambda *_args, **_kwargs: question)
    warnings: list = []
    monkeypatch.setattr(workflow.QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))
    monkeypatch.setattr(workflow.QMessageBox, "information", lambda *_args, **_kwargs: None)
    host: Any = _Host(window, controller, tmp_path)
    SemanticRenameWorkflow(host).handle_rename_symbol_action()
    return session, before, controller, warnings


def test_cancel_leaves_the_form_unchanged(tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    del qapp
    from app.qt.QtWidgets import QMessageBox

    session, before, controller, warnings = _run(tmp_path, "save_more", QMessageBox.No, monkeypatch)
    assert controller.plans == 1
    assert controller.applies == 0
    assert session.text() == before
    assert warnings == []


def test_close_is_refused_before_any_write(tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    del qapp
    from app.qt.QtWidgets import QMessageBox

    session, before, controller, warnings = _run(tmp_path, "close", QMessageBox.Yes, monkeypatch)
    assert warnings == [shadow_sentence("close", "QDialog")]
    assert controller.plans == 0
    assert controller.applies == 0
    assert session.text() == before
