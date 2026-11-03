# pyright: reportAttributeAccessIssue=false
"""PostgreSQL 9.3 lookup story. Skipped unless CBCS_PG93_DSN is set.

Tables are prefixed ``m83a_`` and dropped in ``finally`` so this file can run
beside the other lanes' PostgreSQL tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.source import Lookup, RecordSource, write_data, write_lookup
from app.features.form_builder.engine.data.sql import select_lookup
from tests.form_builder.engine.test_m8_2_pg93 import _driver, _fields
from tests.form_builder.engine.test_m8_2_scenario import _generate, _install_boxes, _load_module, _ui_class

pytestmark = pytest.mark.pg93

_PEOPLE = "m83a_people"
_JOBS = "m83a_jobs"


def test_lookup_story_on_postgres(tmp_path: Path) -> None:
    dsn, connect = _driver()
    fields = _fields(dsn)
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "jobs.ui"
    ui_text = _jobs_ui()
    ui_path.write_text(ui_text, encoding="utf-8")
    value = _connection(fields)
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="m83a"), encoding="utf-8")
    module = _load_module(root / "cbcs_connections.py", "cbcs_connections_m83a")
    module.set_password("shop", fields["password"])
    side = connect(dsn, fields)
    try:
        _create(side)
        statement = select_lookup("postgres", _PEOPLE, "code", "name", ("email", "started", "balance"), "name")
        cursor = side.cursor()
        cursor.execute(statement.text)
        loaded = cursor.fetchall()
        side.commit()
        assert [row[1] for row in loaded] == ["East", "West"]
        assert loaded[0][2] is None
        source = _generate(root, ui_path, ui_text)
        generated = forms / "ui_jobs.py"
        generated.write_text(source, encoding="utf-8")
        ui_module = _load_module(generated, "ui_jobs_m83a")
        _install_boxes(ui_module, [], None, lambda text: "Close", lambda: ("", False))
        previous = sys.modules.get("cbcs_connections")
        sys.modules["cbcs_connections"] = module
        sys.path.insert(0, str(root))
        try:
            from PySide6.QtWidgets import QApplication, QDialog

            app = QApplication.instance() or QApplication([])

            class Host(QDialog):
                def __init__(self) -> None:
                    super().__init__()
                    self.ui = _ui_class(ui_module)()
                    self.ui.setupUi(self)

            host = Host()
            host.show()
            app.processEvents()
            ui = host.ui
            assert ui.personCombo.currentText() == "West"
            assert ui.personCombo.currentData() == "west"
            direct = _person(side, "west")
            assert ui._cbcs_also("personCombo", "email") == direct[0]
            assert ui._cbcs_also("personCombo", "started") == direct[1]
            assert ui._cbcs_also("personCombo", "balance") == direct[2]
            assert direct[1] is not None and hasattr(direct[1], "isoformat")
            from decimal import Decimal

            assert isinstance(direct[2], Decimal)
            ui.cbcs_open(2)
            app.processEvents()
            assert ui.personCombo.currentData() is None
            assert ui.personCombo.currentText() == "(choose a person)"
            assert ui.cbcs_is_dirty() is False
            ui.cbcs_open(3)
            app.processEvents()
            assert ui.personCombo.currentText() == "(unknown #gone)"
            assert ui.personCombo.currentData() == "gone"
            assert ui.cbcs_is_dirty() is False
            ui.titleEdit.setText("Still old")
            assert ui.cbcs_save() is True
            cursor = side.cursor()
            cursor.execute("SELECT person_code, title FROM %s WHERE id = 3" % _JOBS)
            assert cursor.fetchone() == ("gone", "Still old")
            side.commit()
            host.close()
            host.deleteLater()
            app.processEvents()
        finally:
            if previous is None:
                sys.modules.pop("cbcs_connections", None)
            else:
                sys.modules["cbcs_connections"] = previous
            if sys.path and sys.path[0] == str(root):
                sys.path.pop(0)
            module.close_all()
    finally:
        _drop(side)
        closer = getattr(side, "close", None)
        if closer is not None:
            closer()


def _jobs_ui() -> str:
    source = write_data(RecordSource("shop", _JOBS, "id"))
    lookup = write_lookup(
        Lookup(_PEOPLE, "code", "name", order="name", also=("email", "started", "balance"), blank="(choose a person)")
    )
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Jobs</class>
 <widget class="QDialog" name="Jobs">
  <property name="cbcsData" stdset="0"><string notr="true">%s</string></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QComboBox" name="personCombo">
     <property name="cbcsBind" stdset="0"><string notr="true">person_code</string></property>
     <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="titleEdit">
     <property name="cbcsBind" stdset="0"><string notr="true">title</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
""" % (escape(source), escape(lookup))


def _connection(fields: dict) -> ConnectionSet:
    port = int(fields.get("port") or "5432")
    return ConnectionSet(
        (
            Connection(
                "shop",
                "Shop",
                "postgres",
                host=fields.get("host") or "127.0.0.1",
                port=None if port == 5432 else port,
                database=fields.get("dbname") or fields.get("database") or "cbcs",
                user=fields["user"],
                password="none",
            ),
        )
    )


def _create(side: object) -> None:
    cursor = side.cursor()
    cursor.execute("DROP TABLE IF EXISTS %s" % _JOBS)
    cursor.execute("DROP TABLE IF EXISTS %s" % _PEOPLE)
    cursor.execute(
        "CREATE TABLE %s (code text PRIMARY KEY, name text, email text, started date, balance numeric)" % _PEOPLE
    )
    cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, person_code text, title text)" % _JOBS)
    cursor.execute(
        "INSERT INTO %s (code, name, email, started, balance) VALUES ('west', 'West', 'west@example.com', '2020-04-01', 3.25)"
        % _PEOPLE
    )
    cursor.execute("INSERT INTO %s (code, name, email, started, balance) VALUES ('east', 'East', NULL, NULL, NULL)" % _PEOPLE)
    cursor.execute("INSERT INTO %s (id, person_code, title) VALUES (1, 'west', 'Route')" % _JOBS)
    cursor.execute("INSERT INTO %s (id, person_code, title) VALUES (2, NULL, 'Open')" % _JOBS)
    cursor.execute("INSERT INTO %s (id, person_code, title) VALUES (3, 'gone', 'Old')" % _JOBS)
    cursor.execute("SELECT setval(pg_get_serial_sequence('%s', 'id'), 3)" % _JOBS)
    side.commit()


def _drop(side: object) -> None:
    try:
        cursor = side.cursor()
        cursor.execute("DROP TABLE IF EXISTS %s" % _JOBS)
        cursor.execute("DROP TABLE IF EXISTS %s" % _PEOPLE)
        side.commit()
    except Exception:
        return None
    return None


def _person(side: object, code: str):
    cursor = side.cursor()
    cursor.execute("SELECT email, started, balance FROM %s WHERE code = %%s" % _PEOPLE, (code,))
    row = cursor.fetchone()
    side.commit()
    return row
