# pyright: reportAttributeAccessIssue=false
"""Settings › Connections writes the files, refuses a used connection, and renames forms."""

from __future__ import annotations

import os
import threading
import time

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QEvent, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QDialog, QPushButton, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.data.source import Hooks, RecordSource, write_data
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.data.tester import connection_tester, set_connection_tester
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.settings_ext import connections_page
from app.features.form_builder.integration.settings_ext.connections_page import (
    POSTGRES_PLACEHOLDER,
    ConnectionsPage,
)
from app.features.form_builder.integration.workbench_ext.data import _build
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.features.form_builder.qtside.data_panel.sections_ext.empty import _create
from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import SETTINGS_SCOPE_PROJECT, EditorSettingsSnapshot
from app.shell.settings_pages import SettingsRefusal, unregister_settings_page
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit


def _form(connection: str, *, hooks: str = "") -> str:
    source = RecordSource(
        connection,
        "invoices",
        "id",
        hooks=Hooks(connection=hooks) if hooks else None,
    )
    payload = write_data(source)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<ui version=\"4.0\">\n"
        " <class>Form</class>\n"
        " <widget class=\"QWidget\" name=\"Form\">\n"
        "  <property name=\"cbcsData\" stdset=\"0\">"
        "<string notr=\"true\">%s</string></property>\n"
        " </widget>\n"
        " <resources/>\n"
        " <connections/>\n"
        "</ui>\n"
    ) % payload


def _until(qapp, predicate, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for the connection test")


def test_apply_writes_the_connection_files(qapp, tmp_path) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    page.findChild(QPushButton, "formBuilder.connections.addSqlite").click()
    page._file.setText("data/shop.db")
    page._title.setText("Shop database")
    assert page.commit(str(tmp_path)) is None
    written = (tmp_path / "connections.json").read_text(encoding="utf-8")
    module = (tmp_path / "cbcs_connections.py").read_text(encoding="utf-8")
    assert "Shop database" in written
    assert "data/shop.db" in written
    assert "def open_connection" in module
    assert "data/shop.db" in module


def test_remove_of_a_used_connection_is_refused(qapp, tmp_path) -> None:
    del qapp
    forms = tmp_path / "forms"
    forms.mkdir()
    (forms / "invoice.ui").write_text(_form("shop"), encoding="utf-8")
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
    from app.features.form_builder.engine.data.connections_module import save_project_connections

    save_project_connections(
        str(tmp_path),
        ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),)),
        slug="shop",
    )
    page = ConnectionsPage(None, str(tmp_path))
    page.findChild(QPushButton, "formBuilder.connections.remove").click()
    sentence = "shop is used by invoice. Remove it from that form first."
    label = page.findChild(QWidget, "formBuilder.connections.refusal")
    assert label.text() == sentence
    refusal = page.commit(str(tmp_path))
    assert isinstance(refusal, SettingsRefusal)
    assert refusal.sentence == sentence
    assert '"name": "shop"' in (tmp_path / "connections.json").read_text(encoding="utf-8") or (
        "shop" in (tmp_path / "connections.json").read_text(encoding="utf-8")
    )


def test_rename_updates_an_open_form_and_a_closed_form(qapp, tmp_path, monkeypatch) -> None:
    forms = tmp_path / "forms"
    forms.mkdir()
    open_path = forms / "open.ui"
    closed_path = forms / "closed.ui"
    other_path = forms / "other.ui"
    open_path.write_text(_form("office"), encoding="utf-8")
    closed_path.write_text(_form("office", hooks="office"), encoding="utf-8")
    other_path.write_text(_form("other"), encoding="utf-8")
    other_bytes = other_path.read_bytes()
    open_bytes = open_path.read_bytes()
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
    from app.features.form_builder.engine.data.connections_module import save_project_connections

    save_project_connections(
        str(tmp_path),
        ConnectionSet(
            (Connection("office", "Office", "postgres", host="127.0.0.1", database="shop", user="clerk", password="none"),)
        ),
        slug="shop",
    )
    open_abs = os.path.abspath(str(open_path))
    session = FormSession.open(
        open_path.read_text(encoding="utf-8"),
        path=open_abs,
        scope=FormScope(kind="external", ui_path=open_abs),
    )
    monkeypatch.setattr(
        connections_page,
        "open_sessions",
        lambda _root: {open_abs: session},
    )
    page = ConnectionsPage(None, str(tmp_path))
    accepted = enum_value(QDialog.DialogCode.Accepted)
    monkeypatch.setattr(connections_page, "exec_qt", lambda dialog: accepted)
    page._code.setText("ledger")
    page._on_code_finished()
    qapp.processEvents()
    assert session.log.undo_label() == "Update connection name"
    assert len(session.log.entries()) == 1
    assert session.log.can_undo()
    entry = session.document.root.prop("cbcsData")
    assert entry is not None
    value = entry.value
    assert isinstance(value, StringValue)
    assert "ledger" in value.text
    assert "office" not in value.text
    closed = closed_path.read_text(encoding="utf-8")
    assert "ledger" in closed
    assert "office" not in closed
    assert other_path.read_bytes() == other_bytes
    assert open_path.read_bytes() == open_bytes
    session.log.undo()
    assert session.log.can_undo() is False


def test_postgres_tester_result_is_shown_and_the_placeholder_does_not_need_one(qapp, tmp_path) -> None:
    page = ConnectionsPage(None, str(tmp_path))
    page.findChild(QPushButton, "formBuilder.connections.addPostgres").click()
    page._host.setText("192.168.1.20")
    page._database.setText("shop")
    page._user.setText("clerk")
    seen = []

    def fake(connection, password):
        seen.append((connection.name, password()))
        return {"ok": True, "server": "PostgreSQL 9.3", "driver": "pg8000", "tables": 4}

    set_connection_tester(fake)
    try:
        page._test_button.click()
        _until(qapp, lambda: "PostgreSQL 9.3" in page._result.text())
        assert "pg8000" in page._result.text()
        assert "4" in page._result.text()
        assert seen and seen[0][1] == ""
        set_connection_tester(None)
        assert connection_tester() is None
        page._test_button.click()
        assert page._result.text() == POSTGRES_PLACEHOLDER
        assert page._test_button.isEnabled()
        assert page._test_button.text() == "Test"
    finally:
        set_connection_tester(None)


def test_sqlite_probe_reports_success_and_a_missing_file(qapp, tmp_path) -> None:
    build(str(tmp_path / "data" / "shop.db"))
    page = ConnectionsPage(None, str(tmp_path))
    page.findChild(QPushButton, "formBuilder.connections.addSqlite").click()
    page._file.setText("data/shop.db")
    set_connection_tester(None)
    page._test_button.click()
    _until(qapp, lambda: "Connected" in page._result.text())
    assert page._result.text() == "\u2713 Connected · SQLite · 4 tables"
    page._file.setText("data/missing.db")
    page._test_button.click()
    _until(qapp, lambda: page._test_button.isEnabled() and not page._result.text().startswith("Testing"))
    assert "Connected" not in page._result.text()
    assert page._result.text()


def test_escape_cancels_a_sqlite_test_and_leaves_the_page_open(qapp, tmp_path, monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow(_path: str) -> str:
        started.set()
        release.wait(2)
        return "late"

    monkeypatch.setattr(connections_page, "probe_sqlite", slow)
    page = ConnectionsPage(None, str(tmp_path))
    page.show()
    qapp.processEvents()
    page.findChild(QPushButton, "formBuilder.connections.addSqlite").click()
    page._file.setText("data/shop.db")
    page._test_button.click()
    try:
        _until(qapp, lambda: page._test_button.text().startswith("Testing"))
        assert started.wait(2)
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(page.window(), event)
        qapp.processEvents()
        assert page._test_button.text() == "Test"
        assert page._test_button.isEnabled()
        assert page._result.text() == ""
        assert page.isVisible()
        release.set()
        _until(qapp, lambda: not page._workers)
    finally:
        release.set()


def test_add_connection_opens_the_connections_page(qapp, tmp_path) -> None:
    class _Workflow:
        def __init__(self) -> None:
            self.pages = []

        def _open_settings_dialog(self, page_key=None, focus_completion_mode=False) -> None:
            del focus_completion_mode
            self.pages.append(page_key)

    bench = QWidget()
    bench._file_project_commands_workflow = _Workflow()
    panel = _build(bench)
    panel.add_connection_requested.emit()
    qapp.processEvents()
    assert bench._file_project_commands_workflow.pages == ["connections"]
    body = _create(DataPanel(bench))
    add = body.findChild(QPushButton, "formBuilder.data.addConnection")
    connect = body.findChild(QPushButton, "formBuilder.data.connect")
    assert add.isEnabled()
    assert add.toolTip() == ""
    assert connect.isEnabled() is False
    connections_page.install()
    dialog = None
    try:
        dialog = SettingsDialog(
            EditorSettingsSnapshot(),
            project_snapshot=EditorSettingsSnapshot(),
            project_scope_available=True,
            global_settings_payload={},
            project_root=str(tmp_path),
            initial_page_key="connections",
        )
        current = getattr(dialog._tabs_widget, "currentWidget")()
        assert current is not None
        assert current.objectName() == "formBuilder.connections.page"
        assert dialog._active_scope == SETTINGS_SCOPE_PROJECT
    finally:
        unregister_settings_page("connections")
        if dialog is not None:
            dialog.close()
