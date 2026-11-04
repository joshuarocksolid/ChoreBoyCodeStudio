# pyright: reportAttributeAccessIssue=false
"""An open line cell is part of the saved row before Enter or Tab."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

import pytest

from app.qt.QtCore import Qt
from app.qt.QtGui import QKeySequence
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication
from tests.form_builder.engine.test_m8_2_scenario import (
    SAVE,
    _generate,
    _install_boxes,
    _load_module,
    _ui_class,
)
from tests.form_builder.engine.test_m8_3b_lines import (
    _index,
    _invoice_schema,
    _prepare,
    _read,
    _ui,
    _value,
    record_window,
)

pytestmark = pytest.mark.unit

_TYPED = "probe line"


def test_save_button_click_keeps_the_open_cell(tmp_path: Path) -> None:
    with record_window(tmp_path, _ui(), _prepare, schema=_invoice_schema()) as (host, db):
        editor = _type_open(host)
        host.ui.saveButton.clicked.connect(host.ui.cbcs_save)
        assert host.ui.linesView.indexWidget(host.ui.linesView.currentIndex()) is editor
        host.ui.saveButton.click()
        assert _saved(db) == _TYPED


def test_ctrl_s_keeps_the_open_cell(tmp_path: Path) -> None:
    from app.qt.QtGui import QShortcut

    with record_window(tmp_path, _ui(), _prepare, schema=_invoice_schema()) as (host, db):
        _type_open(host)
        host.activateWindow()
        shortcut = QShortcut(QKeySequence("Ctrl+S"), host)
        shortcut.activated.connect(host.ui.cbcs_save)
        focus = QApplication.focusWidget()
        assert focus is not None
        QTest.keyClick(focus, _enum("Key", "Key_S"), _enum("KeyboardModifier", "ControlModifier"))
        assert _saved(db) == _TYPED


def test_toolbar_save_step_keeps_the_open_cell(tmp_path: Path) -> None:
    with record_window(tmp_path, _ui(), _prepare, schema=_invoice_schema()) as (host, db):
        _type_open(host)
        assert host.ui.cbcs_save() is True
        assert _saved(db) == _TYPED


def test_leave_prompt_save_keeps_the_open_cell(tmp_path: Path) -> None:
    seen: List[str] = []
    with record_window(
        tmp_path, _ui(), _prepare, questions=[SAVE], seen=seen, schema=_invoice_schema()
    ) as (host, db):
        _type_open(host)
        host.ui.cbcs_next()
        assert any(text.startswith("Save changes") for text in seen)
        assert _saved(db) == _TYPED


def test_a_dirty_field_still_saves_the_open_cell(tmp_path: Path) -> None:
    with record_window(tmp_path, _ui(), _prepare, schema=_invoice_schema()) as (host, db):
        host.ui.notesEdit.setText("also")
        _type_open(host)
        assert host.ui.cbcs_save() is True
        assert _saved(db) == _TYPED


def test_try_rollback_what_ran_includes_the_open_cell(tmp_path: Path) -> None:
    host, session, db = _open_try(tmp_path)
    try:
        _type_open(host)
        assert host.ui.cbcs_save() is True
        found = [note.values for note in session.notes if _TYPED in note.values]
        assert found
    finally:
        host.close()
        root = getattr(host, "_line_editor_root", None)
        if root is not None and sys.path and sys.path[0] == str(root):
            sys.path.pop(0)
        from app.features.form_builder.engine.data.schema import set_schema_reader
        from app.features.form_builder.qtside.preview.child.try_connections import end_all

        end_all()
        set_schema_reader(None)
    assert _saved(db) is None


def _type_open(host: Any) -> Any:
    ui = host.ui
    host.resize(900, 700)
    view = ui.linesView
    index = view.model().index(0, _index(ui, "description"))
    view.setCurrentIndex(index)
    view.setFocus()
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
    view.edit(index)
    app.processEvents()
    editor = view.indexWidget(index)
    assert editor is not None, "the view did not open a cell editor"
    editor.setFocus()
    app.processEvents()
    QTest.keyClicks(editor, _TYPED)
    app.processEvents()
    assert editor.text() == _TYPED
    assert view.indexWidget(index) is editor
    assert _value(ui, 0, "description") is None
    return editor


def _saved(db: Path) -> object:
    return _read(db)[0][2]


def _enum(group: str, name: str) -> object:
    return getattr(getattr(Qt, group, Qt), name)


def _open_try(tmp_path: Path) -> tuple:
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
    from app.features.form_builder.engine.data.connections_module import render_connections_module
    from app.features.form_builder.engine.data.schema import write_schema
    from app.features.form_builder.engine.data.schema_cache import install_schema_reader
    from app.features.form_builder.qtside.preview.child.try_connections import (
        activate,
        begin_try,
        bind_form_class,
    )
    from app.qt.QtWidgets import QDialog
    from tests.form_builder.qtside.test_m8_4_try_data import _message

    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "invoice.ui"
    text = _ui()
    ui_path.write_text(text, encoding="utf-8")
    db = _prepare(root)
    value = ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),))
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(
        render_connections_module(value, project_slug="line-editor"),
        encoding="utf-8",
    )
    folder = root / "cbcs" / "schema"
    folder.mkdir(parents=True)
    (folder / "shop.json").write_text(write_schema(_invoice_schema()), encoding="utf-8")
    install_schema_reader(str(root))
    source = _generate(root, ui_path, text)
    generated = forms / "ui_invoice.py"
    generated.write_text(source, encoding="utf-8")
    module = _load_module(generated, "ui_invoice_line_editor")
    _install_boxes(module, [], None, None, None)
    view = "line-editor"
    session = begin_try(_message(view, db, "rollback", project_root=str(root)))
    assert session is not None
    ui_cls = _ui_class(module)
    bind_form_class(ui_cls, view)
    sys.path.insert(0, str(root))

    class Host(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.ui = ui_cls()
            with activate(view):
                self.ui.setupUi(self)

    host = Host()
    host.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    host._line_editor_root = root  # type: ignore[attr-defined]
    return host, session, db
