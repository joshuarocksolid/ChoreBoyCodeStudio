# pyright: reportAttributeAccessIssue=false
"""Lookup combos: fill from the foreign table, keep a missing key, and read also columns."""

from __future__ import annotations

import sqlite3
import time
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table
from app.features.form_builder.engine.data.source import Lookup, RecordSource, write_data, write_lookup
from app.features.form_builder.engine.data.sql import select_lookup
from app.features.form_builder.engine.logic.formula import analyze, compile_formula
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind, WidgetFacts
from app.features.form_builder.engine.logic.formula.types import TEXT, WHOLE
from tests.form_builder.engine.test_m8_2_scenario import _xml, record_window, shop_with_three

pytestmark = pytest.mark.unit


def test_lookup_rows_come_back_ordered_by_the_shown_column(tmp_path: Path) -> None:
    path = tmp_path / "shop.db"
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        connection.executemany(
            "INSERT INTO customers (id, name, email) VALUES (?, ?, ?)",
            ((2, "Northwind", "n@example.com"), (1, "Acme", None)),
        )
        connection.commit()
        statement = select_lookup("sqlite", "customers", "id", "name", ("email",), "name")
        rows = connection.execute(statement.text).fetchall()
    finally:
        connection.close()
    assert [row[1] for row in rows] == ["Acme", "Northwind"]
    assert rows[0][2] is None
    assert rows[1][0] == 2 and rows[1][2] == "n@example.com"


def test_also_email_compiles_from_either_formula_shape() -> None:
    facts = WidgetFacts(
        "QComboBox",
        display="Customer",
        has_items_data=True,
        also=("email", "terms_days"),
        also_types=(("email", TEXT), ("terms_days", WHOLE)),
    )
    env = FormulaEnv.for_test(widgets={"customerCombo": facts}, data=object())
    for text in ("customerCombo.email", "customerCombo.also.email"):
        analysis = analyze(text, env, SlotKind("expr"))
        assert not analysis.problems
        assert analysis.type == TEXT
        emitted = compile_formula(analysis, env)
        assert emitted.source == 'self._cbcs_also(u"customerCombo", u"email")'
    whole = analyze("customerCombo.terms_days", env, SlotKind("expr"))
    assert whole.type == WHOLE
    assert "customerCombo" in whole.reads


def test_missing_show_is_fb311_and_a_long_table_is_fb312() -> None:
    lookup = write_lookup(Lookup("customers", "id", "missing", also=("email",)))
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QComboBox", "customerCombo", "customer_id", _lookup_xml(lookup)),)))
    schema = Schema(
        "shop",
        "sqlite",
        "SQLite",
        "2026-11-02T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False), Column("customer_id", "INTEGER", True, references=Reference("customers", "id"))), key="id"),
            Table("customers", (Column("id", "INTEGER", False), Column("name", "TEXT", True), Column("email", "TEXT", True)), key="id", rows=12480),
        ),
    )
    codes = [item.message for item in run_checks(doc, None, schema) if item.code == "FB311"]
    assert codes == ["missing is missing."]
    huge = Schema(
        schema.connection,
        schema.engine,
        schema.server,
        schema.read_at,
        schema.driver,
        (
            schema.tables[0],
            Table("customers", schema.tables[1].columns, key="id", rows=100001),
        ),
    )
    present = write_lookup(Lookup("customers", "id", "name", also=("email",)))
    long_doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QComboBox", "customerCombo", "customer_id", _lookup_xml(present)),)))
    info = [item.message for item in run_checks(long_doc, None, huge) if item.code == "FB312"]
    assert info == ["customers has more than 100,000 rows. A search screen opens faster than a long list. [Use a search screen instead]"]
    counted = Schema(
        schema.connection,
        schema.engine,
        schema.server,
        schema.read_at,
        schema.driver,
        (schema.tables[0], Table("customers", schema.tables[1].columns, key="id", rows=12480)),
    )
    counted_doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QComboBox", "customerCombo", "customer_id", _lookup_xml(present)),)))
    assert [item.message for item in run_checks(counted_doc, None, counted) if item.code == "FB312"] == [
        "customers has 12,480 rows. A search screen opens faster than a long list. [Use a search screen instead]"
    ]


def test_scenario_five_fills_the_combo_and_round_trips_the_key(tmp_path: Path) -> None:
    with record_window(tmp_path, _story_ui(), shop_with_three, choose=lambda text: "Close") as (host, db):
        ui = host.ui
        assert "self.cbcs_load_lookups()" in (tmp_path / "proj" / "forms" / "ui_invoice.py").read_text(encoding="utf-8")
        assert ui.customerCombo.currentData() == 1
        assert ui.customerCombo.currentText() == "Acme"
        assert ui.customerCombo.itemText(0) == "(choose a customer)"
        assert ui._cbcs_also("customerCombo", "email") == "acme@example.com"
        assert ui.emailLabel.text() == "acme@example.com"
        assert ui.cbcs_is_dirty() is False
        completer = ui.customerCombo.completer()
        assert completer is not None
        from PySide6.QtCore import Qt

        assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive
        assert completer.filterMode() == Qt.MatchFlag.MatchContains
        completer.setCompletionPrefix("nor")
        assert completer.completionCount() == 1
        ui.customerCombo.setCurrentIndex(_index(ui.customerCombo, 2))
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        assert app is not None
        app.processEvents()
        assert ui._cbcs_also("customerCombo", "email") == "northwind@example.com"
        assert ui.emailLabel.text() == "northwind@example.com"
        assert ui.cbcs_save() is True
        assert _invoice(db, "INV-1")[2] == 2
        _insert_missing(db)
        ui.cbcs_open(9)
        app.processEvents()
        assert ui.customerCombo.currentText() == "(unknown #99)"
        assert ui.customerCombo.currentData() == 99
        assert ui.cbcs_is_dirty() is False
        ui.notesEdit.setText("kept")
        assert ui.cbcs_save() is True
        row = _invoice(db, "OLD")
        assert row[2] == 99
        assert row[4] == "kept"
        connection = sqlite3.connect(str(db))
        try:
            connection.execute("UPDATE customers SET email = NULL WHERE id = 2")
            connection.commit()
        finally:
            connection.close()
        ui.cbcs_load_lookups()
        ui.customerCombo.setCurrentIndex(_index(ui.customerCombo, 2))
        assert ui._cbcs_also("customerCombo", "email") is None


def test_a_text_key_a_null_and_a_date_round_trip(tmp_path: Path) -> None:
    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("CREATE TABLE people (code TEXT PRIMARY KEY, name TEXT, email TEXT, started TEXT, balance NUMERIC)")
            connection.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, person_code TEXT, title TEXT)")
            connection.execute(
                "INSERT INTO people (code, name, email, started, balance) VALUES ('west', 'West', 'west@example.com', '2020-04-01', '3.25')"
            )
            connection.execute("INSERT INTO people (code, name, email, started, balance) VALUES ('east', 'East', NULL, NULL, NULL)")
            connection.execute("INSERT INTO jobs (id, person_code, title) VALUES (1, 'west', 'Route')")
            connection.execute("INSERT INTO jobs (id, person_code, title) VALUES (2, NULL, 'Open')")
            connection.execute("INSERT INTO jobs (id, person_code, title) VALUES (3, 'gone', 'Old')")
            connection.commit()
        finally:
            connection.close()
        return path

    with record_window(tmp_path, _jobs_ui(), prepare, choose=lambda text: "Close", filename="jobs.ui") as (host, db):
        ui = host.ui
        assert ui.personCombo.currentData() == "west"
        assert ui.personCombo.currentText() == "West"
        assert ui._cbcs_also("personCombo", "email") == "west@example.com"
        assert ui._cbcs_also("personCombo", "started") == "2020-04-01"
        stored = sqlite3.connect(str(db)).execute("SELECT balance FROM people WHERE code = 'west'").fetchone()[0]
        assert ui._cbcs_also("personCombo", "balance") == stored
        assert isinstance(stored, str) or isinstance(stored, Decimal) or isinstance(stored, float)
        ui.cbcs_open(2)
        assert ui.personCombo.currentData() is None
        assert ui.personCombo.currentText() == "(choose a person)"
        assert ui.cbcs_is_dirty() is False
        ui.cbcs_open(3)
        assert ui.personCombo.currentText() == "(unknown #gone)"
        assert ui.personCombo.currentData() == "gone"
        assert ui.cbcs_is_dirty() is False
        ui.titleEdit.setText("Still old")
        assert ui.cbcs_save() is True
        row = sqlite3.connect(str(db)).execute("SELECT person_code, title FROM jobs WHERE id = 3").fetchone()
        assert row == ("gone", "Still old")


def test_two_thousand_row_lookup_loads_three_times(tmp_path: Path) -> None:
    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
            connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id INTEGER, notes TEXT)")
            connection.executemany(
                "INSERT INTO customers (id, name, email) VALUES (?, ?, ?)",
                ((index, "Customer %04d" % index, "c%d@example.com" % index) for index in range(1, 2001)),
            )
            connection.execute("INSERT INTO invoices (id, customer_id, notes) VALUES (1, 1, '')")
            connection.commit()
        finally:
            connection.close()
        return path

    with record_window(tmp_path, _story_ui(), prepare, choose=lambda text: "Close") as (host, _db):
        ui = host.ui
        samples = []
        for _sample in range(3):
            started = time.perf_counter()
            ui.cbcs_load_lookups()
            samples.append((time.perf_counter() - started) * 1000)
        assert ui.customerCombo.count() == 2001
        print("LOOKUP_MS %0.2f %0.2f %0.2f" % (samples[0], samples[1], samples[2]))


def test_a_record_form_without_a_lookup_matches_m82(tmp_path: Path) -> None:
    from app.features.form_builder.engine.codegen.api import generate_form_module
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.ui4.reader import read_ui

    source = write_data(RecordSource("shop", "invoices", "id"))
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QDialog" name="Invoice">
  <property name="cbcsData" stdset="0"><string notr="true">%s</string></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="notesEdit">
     <property name="cbcsBind" stdset="0"><string notr="true">notes</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
""" % escape(source)
    forms = tmp_path / "forms"
    forms.mkdir()
    path = forms / "invoice.ui"
    path.write_text(text, encoding="utf-8")
    save_connections(str(tmp_path), ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),)))
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(forms / "ui_invoice.py"),
        window_path=str(forms / "invoice_window.py"),
        module_name="forms.ui_invoice",
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    expected = (Path(__file__).parent / "fixtures" / "m82_plain_record.out").read_text(encoding="utf-8")
    assert result.text == expected


def test_a_mistyped_lookup_does_not_save_null(tmp_path: Path) -> None:
    with record_window(tmp_path, _story_ui(), shop_with_three, choose=lambda text: "Close") as (host, db):
        ui = host.ui
        edit = ui.customerCombo.lineEdit()
        assert edit is not None
        edit.setText("Acmx")
        edit.editingFinished.emit()
        assert ui.customerCombo.currentData() == 1
        assert ui.cbcs_save() is True
        assert _invoice(db, "INV-1")[2] == 1


def test_unknown_items_do_not_pile_up_or_move_to_another_record(tmp_path: Path) -> None:
    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
            connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id INTEGER, notes TEXT)")
            connection.execute("INSERT INTO customers (id, name, email) VALUES (1, 'Acme', 'acme@example.com')")
            connection.executemany(
                "INSERT INTO invoices (id, customer_id, notes) VALUES (?, ?, '')",
                ((1, 1), (2, 92), (3, 93), (4, 94)),
            )
            connection.commit()
        finally:
            connection.close()
        return path

    lookup = write_lookup(Lookup("customers", "id", "name", order="name", blank="(choose a customer)"))
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QComboBox", "customerCombo", "customer_id", _lookup_xml(lookup)),
            ("QLineEdit", "notesEdit", "notes", ""),
        ),
    )
    with record_window(tmp_path, ui_text, prepare, choose=lambda text: "Close") as (host, db):
        ui = host.ui
        for key, dead in ((2, 92), (3, 93), (4, 94)):
            ui.cbcs_open(key)
            assert _unknown_keys(ui.customerCombo) == [dead]
        ui.cbcs_open(1)
        assert _unknown_keys(ui.customerCombo) == []
        assert ui.customerCombo.currentData() == 1
        ui.notesEdit.setText("still acme")
        assert ui.cbcs_save() is True
        row = sqlite3.connect(str(db)).execute("SELECT customer_id, notes FROM invoices WHERE id = 1").fetchone()
        assert row == (1, "still acme")


def test_carried_date_and_money_match_record_values(tmp_path: Path) -> None:
    from datetime import date

    from app.features.form_builder.engine.data.schema import Column, Schema, Table

    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, since TEXT, fee NUMERIC)")
            connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id INTEGER, notes TEXT, amount NUMERIC)")
            connection.execute(
                "INSERT INTO customers (id, name, since, fee) VALUES (1, 'Acme', '2019-06-15', 10.5)"
            )
            connection.execute("INSERT INTO invoices (id, customer_id, notes, amount) VALUES (1, 1, '', 2.25)")
            connection.commit()
        finally:
            connection.close()
        return path

    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-11-02T00:00:00",
        "sqlite3",
        (
            Table(
                "invoices",
                (
                    Column("id", "integer", False),
                    Column("customer_id", "integer", True),
                    Column("notes", "text", True),
                    Column("amount", "numeric", True),
                ),
                key="id",
            ),
            Table(
                "customers",
                (
                    Column("id", "integer", False),
                    Column("name", "text", True),
                    Column("since", "date", True),
                    Column("fee", "numeric", True),
                ),
                key="id",
            ),
        ),
    )
    lookup = write_lookup(Lookup("customers", "id", "name", order="name", also=("since", "fee"), blank="(choose a customer)"))
    year = '    <property name="cbcsValue" stdset="0"><string notr="true">year(customerCombo.also.since)</string></property>\n'
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QComboBox", "customerCombo", "customer_id", _lookup_xml(lookup)),
            ("QLineEdit", "amountEdit", "amount", ""),
            ("QLineEdit", "notesEdit", "notes", ""),
            ("QLabel", "yearLabel", "", year),
        ),
    )
    with record_window(tmp_path, ui_text, prepare, choose=lambda text: "Close", schema=schema) as (host, _db):
        ui = host.ui
        assert ui._cbcs_also("customerCombo", "since") == date(2019, 6, 15)
        assert ui.yearLabel.text() == "2019"
        assert ui._cbcs_also("customerCombo", "fee") + ui._cbcs_record["amount"] == Decimal("12.75")


def test_refresh_lookups_shows_the_new_email_and_stays_clean(tmp_path: Path) -> None:
    with record_window(tmp_path, _story_ui(), shop_with_three, choose=lambda text: "Close") as (host, db):
        ui = host.ui
        assert ui.emailLabel.text() == "acme@example.com"
        assert ui.cbcs_is_dirty() is False
        connection = sqlite3.connect(str(db))
        try:
            connection.execute("UPDATE customers SET email = 'fresh@example.com' WHERE id = 1")
            connection.commit()
        finally:
            connection.close()
        ui.reloadButton.click()
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        assert app is not None
        app.processEvents()
        assert ui.emailLabel.text() == "fresh@example.com"
        assert ui.cbcs_is_dirty() is False


def test_the_completer_is_kept_across_reloads(tmp_path: Path) -> None:
    with record_window(tmp_path, _story_ui(), shop_with_three, choose=lambda text: "Close") as (host, _db):
        ui = host.ui
        first = ui.customerCombo.completer()
        assert first is not None
        ui.cbcs_load_lookups()
        assert ui.customerCombo.completer() is first


def test_fb311_includes_the_order_column() -> None:
    lookup = write_lookup(Lookup("customers", "id", "name", order="missing_order"))
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QComboBox", "customerCombo", "customer_id", _lookup_xml(lookup)),)))
    schema = Schema(
        "shop",
        "sqlite",
        "SQLite",
        "2026-11-02T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False), Column("customer_id", "INTEGER", True)), key="id"),
            Table("customers", (Column("id", "INTEGER", False), Column("name", "TEXT", True)), key="id"),
        ),
    )
    codes = [item.message for item in run_checks(doc, None, schema) if item.code == "FB311"]
    assert codes == ["missing_order is missing."]


def _story_ui() -> str:
    lookup = write_lookup(Lookup("customers", "id", "name", order="name", also=("email",), blank="(choose a customer)"))
    source = escape(write_data(RecordSource("shop", "invoices", "id")))
    combo = escape(lookup)
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QDialog" name="Invoice">
  <property name="cbcsData" stdset="0"><string notr="true">%s</string></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QFormLayout" name="formLayout">
     <item row="0" column="0">
      <widget class="QLabel" name="customerLabel">
       <property name="text"><string>Customer</string></property>
      </widget>
     </item>
     <item row="0" column="1">
      <widget class="QComboBox" name="customerCombo">
       <property name="cbcsBind" stdset="0"><string notr="true">customer_id</string></property>
       <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>
       <property name="editable"><bool>true</bool></property>
      </widget>
     </item>
     <item row="1" column="0">
      <widget class="QLabel" name="emailCaption">
       <property name="text"><string>Email</string></property>
      </widget>
     </item>
     <item row="1" column="1">
      <widget class="QLineEdit" name="emailLabel">
       <property name="readOnly"><bool>true</bool></property>
       <property name="cbcsValue" stdset="0"><string notr="true">customerCombo.also.email</string></property>
      </widget>
     </item>
     <item row="2" column="0">
      <widget class="QLabel" name="notesLabel">
       <property name="text"><string>Notes</string></property>
      </widget>
     </item>
     <item row="2" column="1">
      <widget class="QLineEdit" name="notesEdit">
       <property name="cbcsBind" stdset="0"><string notr="true">notes</string></property>
      </widget>
     </item>
    </layout>
   </item>
   <item>
    <layout class="QHBoxLayout" name="recordBar">
     <item><widget class="QPushButton" name="firstButton"><property name="text"><string>First</string></property></widget></item>
     <item><widget class="QPushButton" name="previousButton"><property name="text"><string>Previous</string></property></widget></item>
     <item><widget class="QLabel" name="positionLabel"><property name="text"><string>Record 1 of 1</string></property></widget></item>
     <item><widget class="QPushButton" name="nextButton"><property name="text"><string>Next</string></property></widget></item>
     <item><widget class="QPushButton" name="lastButton"><property name="text"><string>Last</string></property></widget></item>
     <item><widget class="QPushButton" name="newButton"><property name="text"><string>New</string></property></widget></item>
     <item><widget class="QPushButton" name="saveButton"><property name="text"><string>Save</string></property></widget></item>
     <item><widget class="QPushButton" name="revertButton"><property name="text"><string>Revert</string></property></widget></item>
     <item><widget class="QPushButton" name="deleteButton"><property name="text"><string>Delete</string></property></widget></item>
     <item><widget class="QPushButton" name="findButton"><property name="text"><string>Find</string></property></widget></item>
     <item><widget class="QPushButton" name="reloadButton"><property name="text"><string>Reload</string></property><property name="cbcsOnClicked" stdset="0"><string notr="true">[{"do": "refreshLookups"}]</string></property></widget></item>
  </layout>
 </item>
 <item>
  <spacer name="verticalSpacer">
   <property name="orientation"><enum>Qt::Vertical</enum></property>
   <property name="sizeType"><enum>QSizePolicy::Expanding</enum></property>
   <property name="sizeHint" stdset="0"><size><width>20</width><height>0</height></size></property>
  </spacer>
 </item>
</layout>
 </widget>
 <resources/>
 <connections/>
</ui>
""" % (source, combo)


def _jobs_ui() -> str:
    lookup = write_lookup(
        Lookup("people", "code", "name", order="name", also=("email", "started", "balance"), blank="(choose a person)")
    )
    return _xml(
        RecordSource("shop", "jobs", "id"),
        (
            ("QComboBox", "personCombo", "person_code", _lookup_xml(lookup)),
            ("QLineEdit", "titleEdit", "title", ""),
        ),
    )


def _lookup_xml(text: str) -> str:
    return '    <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>\n' % escape(text)


def _document(text: str):
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.ui4.reader import read_ui

    return read_ui(text, allocator=IdAllocator()).document


def _unknown_keys(combo: object) -> list:
    found = []
    index = 0
    while index < combo.count():
        if str(combo.itemText(index)).startswith("(unknown #"):
            found.append(combo.itemData(index))
        index += 1
    return found


def _index(combo: object, key: object) -> int:
    index = 0
    while index < combo.count():
        if combo.itemData(index) == key:
            return index
        index += 1
    raise AssertionError(key)


def _invoice(db: Path, invoice_no: str):
    connection = sqlite3.connect(str(db))
    try:
        return connection.execute(
            "SELECT id, invoice_no, customer_id, invoice_date, notes FROM invoices WHERE invoice_no = ?",
            (invoice_no,),
        ).fetchone()
    finally:
        connection.close()


def _insert_missing(db: Path) -> None:
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (9, 'OLD', 99, '2026-04-01', '', '0')"
        )
        connection.commit()
    finally:
        connection.close()
