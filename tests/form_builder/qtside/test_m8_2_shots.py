# pyright: reportAttributeAccessIssue=false
"""M8.2 Data tab shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set.

The record window and the two prompts are grabbed from code ``record.py``
generates. A shot is written only when that window actually shows the text.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import save_project_connections
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table, set_schema_reader, write_schema
from app.features.form_builder.engine.data.source import RecordSource
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.data_panel.chrome import apply_chrome, chrome_qss
from app.features.form_builder.qtside.data_panel.edits import bind_field, connect_form, insert_record_toolbar
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.features.form_builder.qtside.data_panel.sheets import ConnectSheet, SqlDialog
from app.features.form_builder.qtside.inspector.data_page import DataPage
from app.qt.QtCore import QTimer
from app.qt.QtGui import QColor, QPalette
from app.qt.QtWidgets import QApplication, QLabel, QMessageBox, QWidget
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="1">
    <widget class="QLineEdit" name="invoiceDateEdit"/>
   </item>
   <item row="1" column="1">
    <widget class="QLineEdit" name="notesEdit"/>
   </item>
   <item row="2" column="1">
    <widget class="QCheckBox" name="paidCheck"><property name="text"><string>Paid</string></property></widget>
   </item>
  </layout>
 </widget>
</ui>
"""

_SCHEMA = Schema(
    "office",
    "sqlite",
    "SQLite",
    "2026-11-02T16:00:00",
    "sqlite3",
    (
        Table(
            "invoices",
            (
                Column("id", "integer", False, unique=True),
                Column("invoice_date", "date", True),
                Column("notes", "text", True),
                Column("customer_id", "integer", True, references=Reference("customers", "id")),
            ),
            key="id",
        ),
        Table("audit_log", (Column("message", "text", True),), key=None),
    ),
)

_RUNTIME_SCHEMA = Schema(
    "office",
    "sqlite",
    "SQLite",
    "2026-11-02T16:00:00",
    "sqlite3",
    (
        Table(
            "invoices",
            (
                Column("id", "INTEGER", False),
                Column("invoice_no", "TEXT", False, unique=True),
                Column("customer_id", "INTEGER", True),
                Column("invoice_date", "date", True),
                Column("notes", "TEXT", True),
                Column("total", "NUMERIC", True),
            ),
            key="id",
        ),
    ),
)


def test_data_tab_shots(qapp, tmp_path: Path) -> None:
    directory = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not directory:
        pytest.skip("set CBCS_FB_SCREENSHOT_DIR to grab form-builder screenshots")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    _cache(tmp_path)
    set_schema_reader(lambda _doc, _name: _SCHEMA)
    save_connections(
        str(tmp_path),
        ConnectionSet((Connection("office", "Office", "sqlite", file="shop.db"),)),
    )
    try:
        session, host = _open(_FORM, tmp_path)
        try:
            empty = DataPanel(host)
            _shoot(empty, qapp, root, "empty-data", 420, 280)
            sheet = ConnectSheet(host, session)
            sheet._form._select_table("invoices")
            _shoot(sheet, qapp, root, "connect-sheet", 520, 640)
            connect_form(session, RecordSource("office", "invoices", "id"))
            set_schema_reader(lambda _doc, _name: _SCHEMA)
            bind_field(session, session.document.by_name("notesEdit")[0], "notes")
            connected = DataPanel(host)
            connected.reload()
            _shoot(connected, qapp, root, "connected-data", 640, 420)
            _shoot(connected, qapp, root, "connected-data-184", 184, 420)
            sql_dialog = SqlDialog(host, session)
            _shoot(sql_dialog, qapp, root, "show-sql", 680, 520)
            notes = session.document.by_name("notesEdit")[0]
            session.selection.set((notes,), source=SelectionSource.PROGRAM)
            bound = DataPage(host)
            bound.show()
            bound.paint("QLineEdit")
            _shoot(bound, qapp, root, "inspector-bound", 360, 240)
            _shoot(bound, qapp, root, "inspector-bound-236", 236, 480)
            paid = session.document.by_name("paidCheck")[0]
            bind_field(session, paid, "invoice_date")
            session.selection.set((paid,), source=SelectionSource.PROGRAM)
            problem = DataPage(host)
            problem.show()
            problem.paint("QCheckBox")
            _shoot(problem, qapp, root, "inspector-problem", 360, 320)
        finally:
            session.dispose()
        _runtime(qapp, tmp_path, root)
    finally:
        set_schema_reader(None)


def _runtime(qapp: QApplication, tmp_path: Path, root: Path) -> None:
    """Run the generated record window. Missing shots stay missing."""

    project = tmp_path / "app"
    forms = project / "forms"
    forms.mkdir(parents=True)
    data = project / "data"
    data.mkdir()
    database = data / "office.sqlite"
    connection = sqlite3.connect(str(database))
    connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL UNIQUE, customer_id INTEGER, invoice_date TEXT, notes TEXT, total NUMERIC)")
    connection.executemany(
        "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (?, ?, ?, ?, ?, ?)",
        (
            (1, "INV-1", 1, "2026-01-15", "First", 10),
            (2, "INV-2", 1, "2026-02-15", "Second", 20),
            (3, "INV-3", 1, None, "Third", 30),
        ),
    )
    connection.commit()
    connection.close()
    save_project_connections(
        str(project),
        ConnectionSet((Connection("office", "Office", "sqlite", file="data/office.sqlite"),)),
        slug="shots",
    )
    _cache(project)
    set_schema_reader(lambda _doc, _name: _RUNTIME_SCHEMA)
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>InvoiceForm</class>
 <widget class="QWidget" name="InvoiceForm">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLabel" name="invoiceNoLabel"><property name="text"><string>Invoice number</string></property><property name="buddy"><cstring>invoiceNoEdit</cstring></property></widget></item>
   <item><widget class="QLineEdit" name="invoiceNoEdit"><property name="cbcsErrorLabel" stdset="0"><string notr="true">invoiceNoError</string></property></widget></item>
   <item><widget class="QLabel" name="invoiceNoError"><property name="text"><string></string></property></widget></item>
   <item><widget class="QLabel" name="customerLabel"><property name="text"><string>Customer</string></property><property name="buddy"><cstring>customerIdSpin</cstring></property></widget></item>
   <item><widget class="QSpinBox" name="customerIdSpin"/></item>
   <item><widget class="QLabel" name="dateLabel"><property name="text"><string>Invoice date</string></property><property name="buddy"><cstring>invoiceDateEdit</cstring></property></widget></item>
   <item><widget class="QDateEdit" name="invoiceDateEdit"/></item>
   <item><widget class="QLabel" name="notesLabel"><property name="text"><string>Notes</string></property><property name="buddy"><cstring>notesEdit</cstring></property></widget></item>
   <item><widget class="QLineEdit" name="notesEdit"/></item>
   <item><widget class="QLabel" name="totalLabel"><property name="text"><string>Total</string></property><property name="buddy"><cstring>totalSpin</cstring></property></widget></item>
   <item><widget class="QDoubleSpinBox" name="totalSpin"/></item>
  </layout>
 </widget>
</ui>
"""
    ui_path = forms / "invoice.ui"
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(project),
        generated_path=str(forms / "ui_invoice.py"),
    )
    session = FormSession.open(text, path=str(ui_path), scope=scope)
    host = QWidget()
    host.session = session
    try:
        connect_form(
            session,
            RecordSource("office", "invoices", "id", allow_overwrite=True),
        )
        for widget_name, column in (
            ("invoiceNoEdit", "invoice_no"),
            ("customerIdSpin", "customer_id"),
            ("invoiceDateEdit", "invoice_date"),
            ("notesEdit", "notes"),
            ("totalSpin", "total"),
        ):
            bind_field(session, session.document.by_name(widget_name)[0], column)
        insert_record_toolbar(session)
        written = write_ui(session.document).text
        ui_path.write_text(written, encoding="utf-8")
        made = generate_form_module(session.document, scope=scope, source_bytes=written.encode("utf-8"))
        if not made.text:
            print("runtime shots missing: generate returned no text", [item.code for item in made.diagnostics])
            return
        sys.path.insert(0, str(project))
        namespace = {}
        exec(compile(made.text, "ui_invoice.py", "exec"), namespace)
        ui_cls = next(value for value in namespace.values() if isinstance(value, type) and hasattr(value, "setupUi"))
        window = QWidget()
        window.setObjectName("formBuilder.recordWindow")
        ui = ui_cls()
        ui.setupUi(window)
        window.ui = ui  # type: ignore[attr-defined]
        if hasattr(ui, "cbcs_next"):
            ui.cbcs_next()
        label = getattr(ui, "positionLabel", None)
        shown = label.text() if label is not None and hasattr(label, "text") else ""
        print("record label:", repr(shown))
        if shown == "Record 2 of 3":
            _shoot(window, qapp, root, "record-window", 420, 480)
        else:
            print("runtime shot missing: record window did not show Record 2 of 3")
        if hasattr(ui, "cbcs_next") and hasattr(ui, "invoiceDateEdit"):
            ui.cbcs_next()
            if ui.invoiceDateEdit.text().strip() == "":
                _shoot(window, qapp, root, "null-date", 420, 480)
            else:
                print("runtime shot missing: null date showed", repr(ui.invoiceDateEdit.text()))
        if hasattr(ui, "cbcs_save") and hasattr(ui, "invoiceNoEdit") and hasattr(ui, "invoiceNoError"):
            ui.invoiceNoEdit.setText("INV-1")
            ui.cbcs_save()
            if ui.invoiceNoError.isVisible() and "already uses" in ui.invoiceNoError.text():
                _shoot(window, qapp, root, "db-error", 420, 480)
            else:
                print("runtime shot missing: database error label", repr(getattr(ui.invoiceNoError, "text", lambda: "")()))
        if hasattr(ui, "_cbcs_confirm_leave") and hasattr(ui, "notesEdit"):
            ui.notesEdit.setText("Changed")
            _grab_modal(ui._cbcs_confirm_leave, qapp, root, "unsaved-prompt")
        else:
            print("runtime shot missing: unsaved prompt")
        if hasattr(ui, "_cbcs_conflict"):
            _grab_modal(ui._cbcs_conflict, qapp, root, "conflict-prompt")
        else:
            print("runtime shot missing: conflict prompt")
    except Exception as exc:
        print("runtime shots missing:", type(exc).__name__, exc)
    finally:
        if str(project) in sys.path:
            sys.path.remove(str(project))
        session.dispose()
        host.deleteLater()


def _grab_modal(call: Callable[[], object], qapp: QApplication, root: Path, name: str) -> None:
    saved = {"ok": False}

    def shoot() -> None:
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            return
        for mode in _MODES:
            tokens = tokens_from_palette(box.palette(), force_mode=mode)
            box.setObjectName("formBuilder.dataChrome")
            ink = QColor(tokens.text_primary)
            palette = box.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor(tokens.panel_bg))
            palette.setColor(QPalette.ColorRole.WindowText, ink)
            palette.setColor(QPalette.ColorRole.Text, ink)
            palette.setColor(QPalette.ColorRole.ButtonText, ink)
            box.setPalette(palette)
            box.setStyleSheet(chrome_qss(tokens, "formBuilder.dataChrome"))
            for label in box.findChildren(QLabel):
                label.setStyleSheet("color: %s; background: transparent;" % tokens.text_primary)
            qapp.processEvents()
            path = root / ("%s-%s.png" % (name, mode))
            box.grab().save(str(path))
            saved["ok"] = True
        cancel = None
        button = getattr(box, "button", None)
        if callable(button):
            cancel = button(QMessageBox.StandardButton.Cancel)
        if cancel is None:
            for item in box.buttons():
                if item.text().replace("&", "") == "Cancel":
                    cancel = item
                    break
        if cancel is not None:
            cancel.click()
        else:
            box.reject()

    QTimer.singleShot(80, shoot)
    QTimer.singleShot(1500, lambda: _close_modal())
    call()
    if not saved["ok"]:
        print("runtime shot missing:", name)


def _close_modal() -> None:
    box = QApplication.activeModalWidget()
    if box is not None:
        box.reject()


def _cache(folder: Path) -> None:
    path = folder / "cbcs" / "schema" / "office.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(write_schema(_SCHEMA), encoding="utf-8", newline="\n")


def _open(text: str, folder: Path):
    scope = FormScope(kind="external", ui_path=str(folder / "form.ui"), project_root=str(folder))
    session = FormSession.open(text, path=str(folder / "form.ui"), scope=scope)
    host = QWidget()
    host.session = session
    host.project_root = str(folder)
    return session, host


def _shoot(widget: QWidget, qapp: QApplication, root: Path, name: str, width: int, height: int) -> None:
    for mode in _MODES:
        tokens = tokens_from_palette(widget.palette(), force_mode=mode)
        if hasattr(widget, "apply_theme"):
            widget.apply_theme(tokens)
        elif hasattr(widget, "apply_colors"):
            widget.apply_colors(
                tokens.panel_bg,
                tokens.text_primary,
                tokens.text_muted,
                tokens.diag_warning_color,
                tokens.diag_error_color,
                tokens.accent,
                tokens.input_bg,
                tokens.border,
                int(tokens.focus_border_width or 1),
            )
        else:
            if hasattr(widget, "ui"):
                from app.features.form_builder.qtside.theme.runtime import pin_runtime_look

                pin_runtime_look(widget)
            else:
                apply_chrome(widget, tokens)
        fit = getattr(widget, "fit_to_contents", None)
        if callable(fit):
            fit()
        else:
            widget.resize(width, height)
        widget.show()
        for _ in range(4):
            qapp.processEvents()
            time.sleep(0.01)
        widget.grab().save(str(root / ("%s-%s.png" % (name, mode))))
