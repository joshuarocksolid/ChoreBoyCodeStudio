"""A nullable time can be blank and can be midnight."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.features.form_builder.engine.data.schema import Column
from app.features.form_builder.engine.data.source import RecordSource
from tests.form_builder.engine.test_m8_2_followup import _sqlite, _table_schema
from tests.form_builder.engine.test_m8_2_scenario import _xml, record_window

pytestmark = pytest.mark.unit


def test_a_nullable_time_keeps_midnight_and_blank_apart(tmp_path: Path) -> None:
    schema = _table_schema(
        "clocks",
        (Column("id", "INTEGER", False), Column("at_time", "time", True)),
        "id",
    )
    ui = _xml(RecordSource("shop", "clocks", "id"), (("QTimeEdit", "timeEdit", "at_time", ""),))

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE clocks (id INTEGER PRIMARY KEY, at_time TEXT)",),
            (
                ("INSERT INTO clocks (id, at_time) VALUES (?, ?)", (1, None)),
                ("INSERT INTO clocks (id, at_time) VALUES (?, ?)", (2, "00:00:00")),
            ),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        from PySide6.QtCore import QTime

        assert host.ui.timeEdit.property("cbcsTimeBlank") is True
        assert host.ui.timeEdit.text().strip() == ""
        assert host.ui.cbcs_save() is True
        host.ui.cbcs_next()
        assert host.ui.timeEdit.property("cbcsTimeBlank") is False
        assert host.ui.timeEdit.time() == QTime(0, 0, 0)
        host.ui.timeEdit.setTime(QTime(0, 0, 0))
        assert host.ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            rows = connection.execute("SELECT id, at_time FROM clocks ORDER BY id").fetchall()
        finally:
            connection.close()
        assert rows == [(1, None), (2, "00:00:00")]


def test_delete_on_a_selected_time_clears_a_nullable_field(tmp_path: Path) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    schema = _table_schema(
        "clocks",
        (Column("id", "INTEGER", False), Column("at_time", "time", True)),
        "id",
    )
    ui = _xml(RecordSource("shop", "clocks", "id"), (("QTimeEdit", "timeEdit", "at_time", ""),))

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE clocks (id INTEGER PRIMARY KEY, at_time TEXT)",),
            (("INSERT INTO clocks (id, at_time) VALUES (?, ?)", (1, "08:30:00")),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        edit = host.ui.timeEdit
        line = edit.lineEdit()
        assert line is not None
        line.selectAll()
        QApplication.sendEvent(
            line,
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier),
        )
        assert edit.property("cbcsTimeBlank") is True
        assert edit.text().strip() == ""
        assert host.ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            stored = connection.execute("SELECT at_time FROM clocks").fetchone()
        finally:
            connection.close()
        assert stored == (None,)


def test_a_bad_stored_time_saves_null(tmp_path: Path) -> None:
    schema = _table_schema(
        "clocks",
        (Column("id", "INTEGER", False), Column("at_time", "time", True)),
        "id",
    )
    ui = _xml(RecordSource("shop", "clocks", "id"), (("QTimeEdit", "timeEdit", "at_time", ""),))

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE clocks (id INTEGER PRIMARY KEY, at_time TEXT)",),
            (("INSERT INTO clocks (id, at_time) VALUES (?, ?)", (1, "nope")),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        assert host.ui.timeEdit.property("cbcsTimeBlank") is True
        saved = dict(host.ui._cbcs_saved_fields)
        saved["at_time"] = "nope"
        host.ui._cbcs_saved_fields = saved
        assert host.ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            stored = connection.execute("SELECT at_time FROM clocks").fetchone()
        finally:
            connection.close()
        assert stored == (None,)
