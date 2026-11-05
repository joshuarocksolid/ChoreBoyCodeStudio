"""Master-detail lines: the save plan, the generated grid, and the database rows."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

import pytest

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.lines import line_plan_source, plan_lines
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table, set_schema_reader
from app.features.form_builder.engine.data.source import CalcColumn, DataColumn, Lookup, RecordSource, Rows, read_rows, write_data, write_rows
from app.features.form_builder.engine.logic.codec import parse_steps
from app.features.form_builder.engine.logic.storage import signal_property
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.test_m8_2_scenario import _document, _generate, _xml, record_window

pytestmark = pytest.mark.unit

_ROWS = Rows(
    "invoice_lines",
    "invoice_id",
    "id",
    (
        DataColumn("product_id", "Product", "whole", Lookup("products", "id", "name", "name", ("price",))),
        DataColumn("description", "Description"),
        DataColumn("qty", "Qty", "whole", None, "1"),
        DataColumn("price", "Price", "money", None, "product_id.price"),
        DataColumn("needed", "Needed"),
        CalcColumn("lineTotal", "qty * price", "Line total", "money"),
    ),
    "line_no",
    "line_no",
)


def test_plan_matches_the_shipped_source() -> None:
    namespace: dict = {}
    exec(line_plan_source(), namespace)  # noqa: S102 - the generated module runs this source
    snapshot = ({"id": 1, "qty": 1, "line_no": 1}, {"id": 2, "qty": 1, "line_no": 2})
    current = ({"id": 2, "qty": 1}, {"id": 1, "qty": 4})
    args = (snapshot, current, (), "id", "line_no", ("qty",), True)
    assert namespace["_cbcs_plan_lines"](*args) == plan_lines(*args)
    assert namespace["_cbcs_lines_differ"](snapshot, current, "id", ("qty",)) is True


def test_plan_covers_edits_nulls_and_keys() -> None:
    snap = (
        {"id": "L1", "qty": Decimal("1.50"), "note": None, "line_no": 1},
        {"id": "L2", "qty": Decimal("2.00"), "note": "Gadget", "line_no": 2},
    )
    gapped = (
        {"id": "L1", "qty": Decimal("1.50"), "note": None, "line_no": 1},
        {"id": "L2", "qty": Decimal("2.00"), "note": "Gadget", "line_no": 5},
    )
    same = (
        {"id": "L1", "qty": Decimal("1.5"), "note": None},
        {"id": "L2", "qty": Decimal("2"), "note": "Gadget"},
    )
    assert plan_lines(snap, same, (), "id", "line_no", ("qty", "note"), True) == ()
    from app.features.form_builder.engine.data.lines import _cbcs_lines_differ

    assert _cbcs_lines_differ(gapped, same, "id", ("qty", "note")) is False
    edited = ({"id": "L1", "qty": Decimal("1.50"), "note": "x"}, {"id": "L2", "qty": Decimal("2.00"), "note": "Gadget"})
    assert plan_lines(snap, edited, (), "id", "line_no", ("qty", "note"), True) == (("update", "L1", (("note", "x"),)),)
    swapped = (same[1], same[0])
    ops = plan_lines(snap, swapped, (), "id", "line_no", ("qty", "note"), True)
    assert [op[0] for op in ops] == ["park", "park", "position", "position"]
    assert [op[2] for op in ops if op[0] == "park"] == [3, 4]
    plain = plan_lines(snap, swapped, (), "id", "line_no", ("qty", "note"), False)
    assert [op[0] for op in plain] == ["park", "park", "position", "position"]
    assert [op[2] for op in plain if op[0] == "park"] == [3, 4]
    removed = plan_lines(snap, (same[1],), ("L1",), "id", "line_no", ("qty", "note"), True)
    assert removed[0] == ("delete", "L1")
    added = plan_lines(snap, same + ({"id": None, "qty": Decimal("3"), "note": ""},), (), "id", "line_no", ("qty", "note"), False)
    assert added[-1][0] == "insert"
    replaced = (same[1], {"id": None, "qty": Decimal("3"), "note": ""})
    rebuilt = plan_lines(snap, replaced, ("L1",), "id", "line_no", ("qty", "note"), False)
    kinds = [op[0] for op in rebuilt]
    assert "position" in kinds and "insert" in kinds
    assert kinds.index("position") < kinds.index("insert")
    inserted = added[-1][1]
    assert isinstance(inserted, tuple) and ("note", "") in inserted
    with pytest.raises(ValueError):
        plan_lines(snap, same, (None,), "id", "line_no", ("qty", "note"), False)
    dated = ({"id": 1, "needed": date(2026, 4, 2)},)
    assert plan_lines(dated, dated, (), "id", "", ("needed",), False) == ()


def test_park_clears_decimal_and_float_positions() -> None:
    """NUMERIC and REAL positions still leave a free integer for the park."""

    def parks(first: object, second: object) -> List[object]:
        snap = (
            {"id": "L1", "qty": 1, "line_no": first},
            {"id": "L2", "qty": 1, "line_no": second},
        )
        swapped = ({"id": "L2", "qty": 1}, {"id": "L1", "qty": 1})
        ops = plan_lines(snap, swapped, (), "id", "line_no", ("qty",), True)
        return [op[2] for op in ops if op[0] == "park"]

    assert parks(Decimal("1"), Decimal("2.5")) == [3, 4]
    assert parks(1.2, 2.8) == [3, 4]


def test_a_link_that_does_not_point_here_is_fb313() -> None:
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QTableView", "linesView", "", _rows_xml(_ROWS)),)))
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False),), key="id"),
            Table(
                "invoice_lines",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference("customers", "id")),
                    Column("qty", "INTEGER", False),
                ),
                key="id",
            ),
        ),
    )
    found = [item for item in run_checks(doc, None, schema) if item.code == "FB313"]
    assert len(found) == 1
    assert found[0].message == "invoice_id in invoice_lines doesn't point to invoices."
    pointed = Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False),), key="id"),
            Table(
                "invoice_lines",
                (Column("invoice_id", "INTEGER", False, references=Reference("invoices", "id")),),
                key="id",
            ),
        ),
    )
    assert [item.code for item in run_checks(doc, None, pointed) if item.code == "FB313"] == []


def test_add_lines_is_one_undo_step(qapp, tmp_path: Path) -> None:
    del qapp
    schema = Schema(
        "office",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False),), key="id"),
            Table(
                "invoice_lines",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference("invoices", "id")),
                    Column("qty", "INTEGER", False),
                    Column("line_no", "INTEGER", False),
                ),
                key="id",
                unique_keys=(("invoice_id", "line_no"),),
            ),
        ),
    )
    set_schema_reader(lambda _doc, _name: schema)
    try:
        from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
        from app.features.form_builder.engine.project.forms import FormScope
        from app.features.form_builder.engine.session import FormSession
        from app.features.form_builder.qtside.data_panel.edits import connect_form
        from app.features.form_builder.qtside.data_panel.lines_sheet import add_lines
        from app.features.form_builder.qtside.data_panel.panel import DataPanel
        from app.qt.QtWidgets import QWidget  # type: ignore[reportAttributeAccessIssue]

        save_connections(str(tmp_path), ConnectionSet((Connection("office", "Office", "sqlite", file="shop.db"),)))
        session = FormSession.open(
            _xml(RecordSource("office", "invoices", "id"), (("QLineEdit", "notesEdit", "notes", ""),)),
            path="/tmp/cbcs-m83b.ui",
            scope=FormScope(kind="external", ui_path="/tmp/cbcs-m83b.ui", project_root=str(tmp_path)),
        )
        host = QWidget()
        host.session = session
        host.project_root = str(tmp_path)
        connect_form(session, RecordSource("office", "invoices", "id"))
        panel = DataPanel(host)
        panel.reload()
        assert panel.findChild(QWidget, "formBuilder.data.linesAdd") is not None
        before = len(session.log.entries())
        name = add_lines(session, Rows("invoice_lines", "invoice_id", "id", (DataColumn("qty", "Qty", "whole", None, "1"),), "line_no", "line_no"))
        assert name == "invoice_linesView"
        assert len(session.log.entries()) == before + 1
        assert session.log.undo_label() == "Add lines"
        node = session.document.node(session.document.by_name(name)[0])
        rows_entry = node.prop("cbcsRows")
        assert rows_entry is not None and isinstance(rows_entry.value, StringValue)
        parsed, error = read_rows(rows_entry.value.text)
        assert error is None and parsed is not None and parsed.table == "invoice_lines"
        clicked = session.document.node(session.document.by_name("addLineButton")[0]).prop(signal_property("clicked"))
        assert clicked is not None and isinstance(clicked.value, StringValue)
        steps = parse_steps(clicked.value.text).steps
        assert [step.verb for step in steps] == ["addRow"]
        assert session.log.undo()
        assert session.document.by_name("invoice_linesView") == ()
        session.dispose()
    finally:
        set_schema_reader(None)


def test_lines_round_trip_on_sqlite(tmp_path: Path) -> None:
    seen: List[str] = []

    def choose(text: str) -> str:
        if text.startswith("Delete line"):
            return "Delete"
        if text.startswith("Delete this"):
            return "Cancel"
        return "Close"

    with record_window(tmp_path, _ui(), _prepare, choose=choose, seen=seen, schema=_invoice_schema()) as (host, db):
        _story(host, lambda: _read(db))
        print("SPEED", _speed(host, db))


def test_a_text_line_key_updates_on_sqlite(tmp_path: Path) -> None:
    with record_window(tmp_path, _text_ui(), _prepare_text, schema=_text_schema(tmp_path)) as (host, db):
        assert host.ui._cbcs_is_dirty() is False
        _set(host.ui, 0, "note", "changed")
        assert host.ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            found = connection.execute("SELECT id, note FROM coded_lines").fetchall()
        finally:
            connection.close()
        assert found == [("L1", "changed")]


def test_a_record_without_lines_omits_the_line_hooks(tmp_path: Path) -> None:
    plain = _xml(
        RecordSource("shop", "invoices", "id"),
        (("QLineEdit", "invoiceNoEdit", "invoice_no", ""), ("QPushButton", "saveButton", "", "")),
    )
    kept = _xml(
        RecordSource("shop", "invoices", "id", delete_lines=False),
        (("QLineEdit", "invoiceNoEdit", "invoice_no", ""), ("QPushButton", "saveButton", "", "")),
    )
    root = tmp_path / "plain"
    forms = root / "forms"
    forms.mkdir(parents=True)
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections

    save_connections(str(root), ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),)))
    first = forms / "plain.ui"
    first.write_text(plain, encoding="utf-8")
    second = forms / "kept.ui"
    second.write_text(kept, encoding="utf-8")
    generated = _generate_text(root, first, plain)
    other = _generate_text(root, second, kept)
    assert "_cbcs_clear_lines" not in generated
    assert "_drop_lines" not in generated
    assert "_cbcs_clear_lines" not in other
    assert "_drop_lines" not in other
    lined = _generate_text(root, forms / "lines.ui", _ui())
    assert "_clear_lines" in lined
    assert "_drop_lines" in lined
    quiet = _ui().replace(escape(write_data(RecordSource("shop", "invoices", "id"))), escape(write_data(RecordSource("shop", "invoices", "id", delete_lines=False))))
    skipped = _generate_text(root, forms / "quiet.ui", quiet)
    assert "_clear_lines" in skipped
    assert "_drop_lines" not in skipped


def test_editors_keep_nulls_bools_and_dates(tmp_path: Path) -> None:
    with record_window(tmp_path, _typed_ui(), _prepare_typed, schema=_typed_schema()) as (host, db):
        ui = host.ui
        assert ui._cbcs_is_dirty() is False
        _edit(ui, 0, "due")
        assert ui._cbcs_is_dirty() is False
        assert _value(ui, 0, "due") == date(2026, 4, 2)
        _edit(ui, 0, "amount")
        assert ui._cbcs_is_dirty() is False
        assert _value(ui, 0, "amount") is None
        _edit(ui, 0, "flag", lambda editor: editor.setChecked(False))
        assert ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            flag = connection.execute("SELECT flag FROM typed_lines").fetchone()
        finally:
            connection.close()
        assert flag == (0,)
        _edit(ui, 0, "amount", lambda editor: editor.setValue(editor.minimum()))
        assert _value(ui, 0, "amount") is None
        assert ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            amount = connection.execute("SELECT amount FROM typed_lines").fetchone()
        finally:
            connection.close()
        assert amount == (None,)


def test_a_new_invoice_saves_its_lines(tmp_path: Path) -> None:
    with record_window(tmp_path, _ui(), _prepare, schema=_invoice_schema()) as (host, db):
        ui = host.ui
        ui.cbcs_new()
        ui.invoiceNoEdit.setText("INV-NEW")
        ui.customerIdSpin.setValue(1)
        ui.invoiceDateEdit.setText("2026-04-03")
        ui._cbcs_add_row()
        _edit(ui, 0, "description", lambda editor: editor.setText("fresh"))
        _edit(ui, 0, "price", lambda editor: editor.setValue(1.25))
        assert ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            parent = connection.execute("SELECT id FROM invoices WHERE invoice_no = 'INV-NEW'").fetchone()
            lines = connection.execute(
                "SELECT invoice_id, description FROM invoice_lines WHERE invoice_id = ?",
                (parent[0],),
            ).fetchall()
        finally:
            connection.close()
        assert parent is not None
        assert lines == [(parent[0], "fresh")]


def test_lookups_and_defaults_on_a_new_record(tmp_path: Path) -> None:
    with record_window(tmp_path, _ui(), _prepare, schema=_invoice_schema()) as (host, _db):
        ui = host.ui
        ui.cbcs_new()
        ui._cbcs_add_row()
        seen = {}

        def pick(editor: Any) -> None:
            seen["count"] = editor.count()
            editor.setCurrentIndex(editor.findData(1))

        _edit(ui, 0, "product_id", pick)
        assert seen["count"] > 1
        assert _value(ui, 0, "price") == Decimal("1.50")
        _edit(ui, 0, "price", lambda editor: editor.setValue(9))
        _edit(ui, 0, "product_id", lambda editor: editor.setCurrentIndex(editor.findData(2)))
        assert _value(ui, 0, "price") == Decimal("9") or _value(ui, 0, "price") == Decimal("9.00")


def test_division_by_zero_stays_in_the_cell(tmp_path: Path) -> None:
    rows = replace(
        _ROWS,
        columns=_ROWS.columns[:-1] + (CalcColumn("lineTotal", "qty / price", "Line total", "money"),),
    )
    extra = _rows_xml(rows)
    ui_text = _ui().replace(_rows_xml(_spec()), extra)
    with record_window(tmp_path, ui_text, _prepare, schema=_invoice_schema()) as (host, _db):
        ui = host.ui
        _edit(ui, 0, "price", lambda editor: editor.setValue(0))
        item = ui.linesView.model().item(0, _index(ui, "lineTotal"))
        assert item.text() == ""
        assert item.toolTip() == "Can't divide by zero"
        assert ui.cbcs_save() is True


def test_a_bad_line_formula_is_a_diagnostic() -> None:
    rows = replace(_ROWS, columns=_ROWS.columns[:-1] + (CalcColumn("lineTotal", "qty /", "Line total", "money"),))
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QTableView", "linesView", "", _rows_xml(rows)),)))
    codes = [item.code for item in run_checks(doc, None, _invoice_schema())]
    assert "FB108" in codes or "FB101" in codes


def test_add_lines_steps_follow_a_renamed_button(qapp, tmp_path: Path) -> None:
    del qapp
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.session import FormSession
    from app.features.form_builder.qtside.data_panel.edits import connect_form
    from app.features.form_builder.qtside.data_panel.lines_sheet import add_lines

    set_schema_reader(lambda _doc, _name: _invoice_schema())
    try:
        save_connections(str(tmp_path), ConnectionSet((Connection("office", "Office", "sqlite", file="shop.db"),)))
        session = FormSession.open(
            _xml(
                RecordSource("office", "invoices", "id"),
                (
                    ("QPushButton", "addLineButton", "", ""),
                    ("QPushButton", "deleteLineButton", "", ""),
                    ("QLineEdit", "notesEdit", "notes", ""),
                ),
            ),
            path=str(tmp_path / "invoice.ui"),
            scope=FormScope(kind="external", ui_path=str(tmp_path / "invoice.ui"), project_root=str(tmp_path)),
        )
        connect_form(session, RecordSource("office", "invoices", "id"))
        add_lines(session, Rows("invoice_lines", "invoice_id", "id", (DataColumn("qty", "Qty", "whole", None, "1"),), "line_no", "line_no"))
        owners = []
        for node in session.document.iter_widgets():
            clicked = node.prop(signal_property("clicked"))
            if clicked is not None and isinstance(clicked.value, StringValue) and "addRow" in clicked.value.text:
                owners.append(node.object_name)
        assert owners
        assert owners[0] != "addLineButton"
    finally:
        set_schema_reader(None)


def test_a_carried_column_is_typed_from_the_lookup_table() -> None:
    from app.features.form_builder.engine.logic.formula.check import analyze
    from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind
    from app.features.form_builder.engine.logic.formula.types import ANY, MONEY, WHOLE

    columns = {"product_id": WHOLE}
    money = FormulaEnv.for_test(row_columns=columns, row_attrs={"product_id": {"unit_cost": MONEY}})
    whole = FormulaEnv.for_test(row_columns=columns, row_attrs={"product_id": {"price": WHOLE}})
    unknown = FormulaEnv.for_test(row_columns=columns)
    assert analyze("product_id.unit_cost", money, SlotKind.value(MONEY)).type == MONEY
    assert analyze("product_id.price", whole, SlotKind.value(WHOLE)).type == WHOLE
    assert analyze("product_id.price", unknown, SlotKind.value(ANY)).type == ANY


def test_a_parent_lookup_and_a_line_lookup_both_load(tmp_path: Path) -> None:
    from app.features.form_builder.engine.data.source import write_lookup

    lookup = (
        '    <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>\n'
        % escape(write_lookup(Lookup("customers", "id", "name", "name")))
    )
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QComboBox", "customerCombo", "customer_id", lookup),
            ("QTableView", "linesView", "", _rows_xml(_ROWS)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    with record_window(tmp_path, ui_text, _prepare, schema=_invoice_schema()) as (host, _db):
        ui = host.ui
        labels = [ui.customerCombo.itemText(index) for index in range(ui.customerCombo.count())]
        assert "Acme" in labels
        ui._cbcs_add_row()
        seen = {}

        def pick(editor: Any) -> None:
            seen["count"] = editor.count()

        _edit(ui, ui.linesView.model().rowCount() - 1, "product_id", pick)
        assert seen["count"] > 1


def test_a_null_time_stays_null_and_a_set_time_saves(tmp_path: Path) -> None:
    from datetime import datetime
    from datetime import time as clock

    from app.qt.QtCore import QDate, QDateTime, QTime  # type: ignore[reportAttributeAccessIssue]

    rows = Rows(
        "xl",
        "invoice_id",
        "id",
        (DataColumn("tm", "Tm"), DataColumn("ts", "Ts")),
        "line_no",
        "line_no",
    )
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QTableView", "linesView", "", _rows_xml(rows)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False), Column("invoice_no", "TEXT", False)), key="id"),
            Table(
                "xl",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False),
                    Column("line_no", "INTEGER", False),
                    Column("tm", "TIME", True),
                    Column("ts", "TIMESTAMP", True),
                ),
                key="id",
            ),
        ),
    )

    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL)")
            connection.execute(
                "CREATE TABLE xl (id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL, line_no INTEGER NOT NULL, tm TIME, ts TIMESTAMP)"
            )
            connection.execute("INSERT INTO invoices VALUES (1, 'INV-1')")
            connection.execute("INSERT INTO xl VALUES (1, 1, 1, NULL, NULL)")
            connection.execute("INSERT INTO xl VALUES (2, 1, 2, '10:30:00', '2026-04-02 10:30:00')")
            connection.commit()
        finally:
            connection.close()
        return path

    seen: List[str] = []
    with record_window(tmp_path, ui_text, prepare, seen=seen, schema=schema) as (host, db):
        ui = host.ui
        _edit(ui, 0, "tm")
        _edit(ui, 0, "ts")
        assert _value(ui, 0, "tm") is None
        assert _value(ui, 0, "ts") is None
        assert ui.cbcs_is_dirty() is False
        _edit(ui, 1, "tm")
        _edit(ui, 1, "ts")
        assert _value(ui, 1, "tm") == clock(10, 30)
        assert _value(ui, 1, "ts") == datetime(2026, 4, 2, 10, 30)
        assert ui.cbcs_is_dirty() is False
        _edit(ui, 0, "tm", lambda editor: editor.setTime(QTime(9, 15, 0)))
        _edit(ui, 0, "ts", lambda editor: editor.setDateTime(QDateTime(QDate(2026, 4, 2), QTime(11, 0, 0))))
        assert ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            stored = connection.execute("SELECT tm, ts FROM xl WHERE id = 1").fetchone()
        finally:
            connection.close()
        assert stored == ("09:15:00", "2026-04-02 11:00:00")
        assert not seen


def test_clear_on_a_line_time_menu_saves_null(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication, QMenu

    rows = Rows(
        "xl",
        "invoice_id",
        "id",
        (DataColumn("tm", "Tm", "time"),),
        "line_no",
        "line_no",
    )
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QTableView", "linesView", "", _rows_xml(rows)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False), Column("invoice_no", "TEXT", False)), key="id"),
            Table(
                "xl",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False),
                    Column("line_no", "INTEGER", False),
                    Column("tm", "TIME", True),
                ),
                key="id",
            ),
        ),
    )

    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL)")
            connection.execute(
                "CREATE TABLE xl (id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL, line_no INTEGER NOT NULL, tm TIME)"
            )
            connection.execute("INSERT INTO invoices VALUES (1, 'INV-1')")
            connection.execute("INSERT INTO xl VALUES (1, 1, 1, '10:30:00')")
            connection.commit()
        finally:
            connection.close()
        return path

    with record_window(tmp_path, ui_text, prepare, schema=schema) as (host, db):
        ui = host.ui

        def clear(editor: Any) -> None:
            line = editor.lineEdit()
            assert line is not None
            line.customContextMenuRequested.emit(line.rect().center())
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
            found = False
            for widget in QApplication.topLevelWidgets():
                if not isinstance(widget, QMenu):
                    continue
                for action in widget.actions():
                    if action.text() == "Clear":
                        action.trigger()
                        found = True
                widget.close()
            assert found

        _edit(ui, 0, "tm", clear)
        assert _value(ui, 0, "tm") is None
        assert ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            stored = connection.execute("SELECT tm FROM xl").fetchone()
        finally:
            connection.close()
        assert stored == (None,)


@contextmanager
def _bad_line_time(tmp_path: Path) -> Iterator[Tuple[Any, Path]]:
    rows = Rows(
        "xl",
        "invoice_id",
        "id",
        (DataColumn("tm", "Tm", "time"),),
        "line_no",
        "line_no",
    )
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QTableView", "linesView", "", _rows_xml(rows)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False), Column("invoice_no", "TEXT", False)), key="id"),
            Table(
                "xl",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False),
                    Column("line_no", "INTEGER", False),
                    Column("tm", "TIME", True),
                ),
                key="id",
            ),
        ),
    )

    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL)")
            connection.execute(
                "CREATE TABLE xl (id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL, line_no INTEGER NOT NULL, tm TIME)"
            )
            connection.execute("INSERT INTO invoices VALUES (1, 'INV-1')")
            connection.execute("INSERT INTO xl VALUES (1, 1, 1, 'nope')")
            connection.commit()
        finally:
            connection.close()
        return path

    with record_window(tmp_path, ui_text, prepare, schema=schema) as opened:
        yield opened


def _stored_tm(db: Path) -> Any:
    connection = sqlite3.connect(str(db))
    try:
        return connection.execute("SELECT tm FROM xl").fetchone()
    finally:
        connection.close()


def test_a_bad_line_time_stays_when_another_column_is_saved(tmp_path: Path) -> None:
    with _bad_line_time(tmp_path) as (host, db):
        ui = host.ui
        ui.invoiceNoEdit.setText(ui.invoiceNoEdit.text() + "x")
        assert ui.cbcs_save() is True
        assert _stored_tm(db) == ("nope",)


def test_clear_on_a_bad_line_time_saves_null(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication, QMenu

    with _bad_line_time(tmp_path) as (host, db):
        ui = host.ui

        def clear(editor: Any) -> None:
            line = editor.lineEdit()
            assert line is not None
            line.customContextMenuRequested.emit(line.rect().center())
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
            found = False
            for widget in QApplication.topLevelWidgets():
                if not isinstance(widget, QMenu):
                    continue
                for action in widget.actions():
                    if action.text() == "Clear":
                        action.trigger()
                        found = True
                widget.close()
            assert found

        _edit(ui, 0, "tm", clear)
        assert ui.cbcs_save() is True
        assert _stored_tm(db) == (None,)


def test_entering_a_line_time_over_a_bad_value_saves_it(tmp_path: Path) -> None:
    from PySide6.QtCore import QTime

    with _bad_line_time(tmp_path) as (host, db):
        _edit(host.ui, 0, "tm", lambda editor: editor.setTime(QTime(9, 15, 0)))
        assert host.ui.cbcs_save() is True
        assert _stored_tm(db) == ("09:15:00",)


def test_a_failed_lookup_does_not_mark_the_other_column(tmp_path: Path) -> None:
    rows = Rows(
        "invoice_lines",
        "invoice_id",
        "id",
        (
            DataColumn("product_id", "Product", "whole", Lookup("products", "id", "name", "name")),
            DataColumn("needed", "Bin", "text", Lookup("bins", "id", "name", "name")),
        ),
        "line_no",
        "line_no",
    )
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QTableView", "linesView", "", _rows_xml(rows)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    with record_window(tmp_path, ui_text, _prepare, schema=_invoice_schema()) as (host, _db):
        ui = host.ui
        product = ui.linesView.model().item(0, _index(ui, "product_id")).text()
        missing = ui.linesView.model().item(0, _index(ui, "needed")).text()
        assert product == "Widget"
        assert "no such table" in missing
        assert "no such table" not in product


def test_a_lookup_keeps_show_and_also_when_names_repeat(tmp_path: Path) -> None:
    shown = list(_spec().columns)
    shown[0] = replace(shown[0], lookup=Lookup("products", "id", "id", "id", ("price",)))
    carried = list(_spec().columns)
    carried[0] = replace(carried[0], lookup=Lookup("products", "id", "name", "name", ("name", "price")))
    base = escape(write_rows(_spec()))

    def open_with(folder: str, columns: List[Any]) -> Any:
        text = _ui().replace(base, escape(write_rows(replace(_spec(), columns=tuple(columns)))))
        return record_window(tmp_path / folder, text, _prepare, schema=_invoice_schema())

    with open_with("shown", shown) as (host, _db):
        ui = host.ui
        assert ui.linesView.model().item(0, _index(ui, "product_id")).text() == "1"
        assert ui._cbcs_line_also("product_id", 1, "price") == Decimal("1.50")
    with open_with("carried", carried) as (host, _db):
        ui = host.ui
        assert ui.linesView.model().item(0, _index(ui, "product_id")).text() == "Widget"
        assert ui._cbcs_line_also("product_id", 1, "name") == "Widget"
        assert ui._cbcs_line_also("product_id", 1, "price") == Decimal("1.50")


def test_a_failed_line_lookup_still_saves_the_lines(tmp_path: Path) -> None:
    def prepare(root: Path) -> Path:
        path = _prepare(root)
        connection = sqlite3.connect(str(path))
        try:
            connection.execute("ALTER TABLE products RENAME TO products_old")
            connection.commit()
        finally:
            connection.close()
        return path

    seen: List[str] = []
    with record_window(tmp_path, _ui(), prepare, seen=seen, schema=_invoice_schema()) as (host, db):
        ui = host.ui
        assert any("no such table" in text for text in seen)
        told = len(seen)
        assert ui._cbcs_key == 1
        assert ui.linesView.model().rowCount() == 3
        shown = ui.linesView.model().item(0, _index(ui, "product_id")).text()
        assert "no such table" in shown
        assert not shown.startswith("(unknown #")
        assert _value(ui, 0, "product_id") == 1
        ui.cbcs_first()
        assert len(seen) == told
        _edit(ui, 0, "description", lambda editor: editor.setText("kept"))
        assert ui.cbcs_save() is True
        ui.cbcs_new()
        assert len(seen) == told
        connection = sqlite3.connect(str(db))
        try:
            connection.execute("ALTER TABLE products_old RENAME TO products")
            connection.commit()
            row = connection.execute("SELECT product_id, description FROM invoice_lines WHERE id = 1").fetchone()
        finally:
            connection.close()
        assert row == (1, "kept")
        ui.cbcs_load_lookups()
        assert len(seen) == told
        ui._cbcs_add_row()

        def pick(editor: Any) -> None:
            assert editor.count() > 1

        _edit(ui, ui.linesView.model().rowCount() - 1, "product_id", pick)


def test_a_carried_price_keeps_its_own_type(tmp_path: Path) -> None:
    rows = Rows(
        "invoice_lines",
        "invoice_id",
        "id",
        (
            DataColumn("product_id", "Product", "whole", Lookup("products", "id", "name", "name", ("price",))),
            DataColumn("qty", "Qty", "whole", None, "1"),
            DataColumn("cost", "Cost", "money", None, "product_id.price"),
        ),
        "line_no",
        "line_no",
    )
    ui_text = _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QSpinBox", "priceSpin", "price", ""),
            ("QTableView", "linesView", "", _rows_xml(rows)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    schema = _invoice_schema()
    tables = []
    for table in schema.tables:
        if table.name == "invoices":
            tables.append(replace(table, columns=table.columns + (Column("price", "INTEGER", True),)))
        elif table.name == "invoice_lines":
            tables.append(
                replace(
                    table,
                    columns=table.columns[:4] + (Column("qty", "INTEGER", False), Column("cost", "NUMERIC", True)),
                )
            )
        else:
            tables.append(table)
    schema = replace(schema, tables=tuple(tables))

    def prepare(root: Path) -> Path:
        path = root / "data" / "shop.db"
        path.parent.mkdir(parents=True)
        connection = sqlite3.connect(str(path))
        try:
            connection.executescript(
                """
                CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price NUMERIC);
                CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT, price INTEGER);
                CREATE TABLE invoice_lines (
                    id INTEGER PRIMARY KEY,
                    invoice_id INTEGER,
                    line_no INTEGER,
                    product_id INTEGER,
                    qty INTEGER,
                    cost NUMERIC
                );
                """
            )
            connection.execute("INSERT INTO products VALUES (1, 'Widget', 0.15)")
            connection.execute("INSERT INTO invoices VALUES (1, 'INV-1', 2)")
            connection.execute("INSERT INTO invoice_lines VALUES (1, 1, 1, 1, 1, 0.15)")
            connection.commit()
        finally:
            connection.close()
        return path

    with record_window(tmp_path, ui_text, prepare, schema=schema) as (host, db):
        ui = host.ui
        assert ui._cbcs_from("price", 0.15) == 0
        assert ui._cbcs_line_from("products", "price", 0.15) == Decimal("0.15")
        ui.cbcs_new()
        ui.invoiceNoEdit.setText("INV-9")
        ui._cbcs_add_row()
        _edit(ui, 0, "product_id", lambda editor: editor.setCurrentIndex(editor.findData(1)))
        assert _value(ui, 0, "cost") == Decimal("0.15")
        assert ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            stored = connection.execute(
                "SELECT product_id, cost FROM invoice_lines WHERE invoice_id <> 1"
            ).fetchone()
            parent = connection.execute("SELECT price FROM invoices WHERE invoice_no = 'INV-9'").fetchone()
        finally:
            connection.close()
        assert stored[0] == 1
        assert Decimal(str(stored[1])) == Decimal("0.15")
        assert parent == (None,) or parent == (0,)


def test_a_text_key_without_a_schema_opens(tmp_path: Path) -> None:
    with record_window(tmp_path, _text_ui(), _prepare_text, schema=None) as (host, _db):
        assert host.ui.linesView.model().rowCount() == 1
        assert host.ui.cbcs_read_lines()[0]["id"] == "L1"


def _story(host: Any, read: Callable[[], Sequence[Tuple[Any, ...]]]) -> None:
    ui = host.ui
    assert ui.linesView.model().rowCount() == 3
    assert ui._cbcs_is_dirty() is False
    assert _value(ui, 0, "description") is None
    assert _value(ui, 0, "needed") == date(2026, 4, 2)
    assert _value(ui, 0, "price") == Decimal("1.50")
    assert ui.cbcs_read_lines()[0]["id"] == 1
    total = ui.totalLabel.text()
    assert "7.00" in total
    assert ui.linesView.model().item(0, _index(ui, "price")).text() == "1.50"
    assert ui.linesView.model().item(0, _index(ui, "lineTotal")).text() == "1.50"
    assert ui.linesView.model().item(1, _index(ui, "lineTotal")).text() == "4.00"
    _set(ui, 0, "qty", 5)
    _set(ui, 0, "qty", 1)
    assert ui._cbcs_is_dirty() is False
    _set(ui, 0, "qty", 9)
    assert ui._cbcs_is_dirty() is True
    ui.cbcs_revert()
    assert _value(ui, 0, "qty") == 1
    assert ui._cbcs_is_dirty() is False
    assert read()[0][3] == 1
    _set(ui, 0, "qty", None)
    assert ui.cbcs_save() is False
    assert "Line 1: Qty is required" in ui.linesView.model().item(0, _index(ui, "qty")).toolTip()
    _set(ui, 0, "qty", 1)
    _set(ui, 0, "description", None)
    assert ui.cbcs_save() is True
    assert read()[0][2] is None
    _set(ui, 0, "needed", date(2026, 5, 1))
    _set(ui, 0, "price", Decimal("1.25"))
    assert ui.cbcs_save() is True
    saved = read()
    assert saved[0][4] == Decimal("1.25") or str(saved[0][4]) in ("1.25", "1.250")
    assert str(saved[0][5]).startswith("2026-05-01")
    _move(ui, 1, 0)
    assert ui.cbcs_save() is True
    ordered = read()
    assert [row[0] for row in ordered] == [2, 1, 3]
    assert [row[1] for row in ordered] == [1, 2, 3]
    ui.linesView.setCurrentIndex(ui.linesView.model().index(2, 0))
    ui._cbcs_delete_row()
    assert ui.cbcs_save() is True
    assert [row[0] for row in read()] == [2, 1]
    ui._cbcs_add_row()
    last = ui.linesView.model().rowCount() - 1
    _set(ui, last, "product_id", 1)
    _set(ui, last, "qty", 3)
    _set(ui, last, "price", Decimal("2.00"))
    _set(ui, last, "description", "Added")
    assert ui.cbcs_save() is True
    added = read()
    assert added[-1][2] == "Added"
    assert added[-1][3] == 3
    assert added[-1][1] == 3


def _speed(host: Any, db: Path) -> Tuple[Tuple[float, ...], Tuple[float, ...], Tuple[float, ...]]:
    import cbcs_connections  # type: ignore[reportMissingImports]

    key = host.ui.cbcs_current_key()
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("DELETE FROM invoice_lines")
        connection.executemany(
            "INSERT INTO invoice_lines (invoice_id, line_no, product_id, description, qty, price, needed) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, index, 1, "Row %d" % index, 1, "1.50", None) for index in range(1, 21)],
        )
        connection.commit()
    finally:
        connection.close()
    with cbcs_connections.work("shop") as conn:
        host.ui._cbcs_load_lines(conn, key)
    small: List[float] = []
    for _ in range(3):
        started = time.perf_counter()
        assert host.ui._cbcs_is_dirty() is False
        small.append(time.perf_counter() - started)
    assert max(small) < 0.001
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("DELETE FROM invoice_lines")
        connection.executemany(
            "INSERT INTO invoice_lines (invoice_id, line_no, product_id, description, qty, price, needed) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, index, 1, "Row %d" % index, 1, "1.50", None) for index in range(1, 201)],
        )
        connection.commit()
    finally:
        connection.close()
    samples: List[float] = []
    for _ in range(3):
        started = time.perf_counter()
        with cbcs_connections.work("shop") as conn:
            host.ui._cbcs_load_lines(conn, key)
        samples.append(time.perf_counter() - started)
    assert host.ui.linesView.model().rowCount() == 200
    host.ui._cbcs_line_snapshot = host.ui._cbcs_line_rows()
    assert host.ui._cbcs_is_dirty() is False
    saves: List[float] = []
    for sample in range(3):
        for row in range(20):
            _set(host.ui, row, "description", "S%d-%d" % (sample, row))
        started = time.perf_counter()
        assert host.ui.cbcs_save() is True
        saves.append(time.perf_counter() - started)
    with cbcs_connections.work("shop") as conn:
        host.ui._cbcs_delete_lines(conn, key)
    connection = sqlite3.connect(str(db))
    try:
        left = connection.execute("SELECT COUNT(*) FROM invoice_lines").fetchone()[0]
    finally:
        connection.close()
    assert left == 0
    return (tuple(small), tuple(samples), tuple(saves))


def _prepare(root: Path) -> Path:
    path = root / "data" / "shop.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, price NUMERIC NOT NULL);
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                invoice_no TEXT NOT NULL UNIQUE,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                invoice_date TEXT,
                notes TEXT,
                total NUMERIC
            );
            CREATE TABLE invoice_lines (
                id INTEGER PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                line_no INTEGER NOT NULL,
                product_id INTEGER REFERENCES products(id),
                description TEXT,
                qty INTEGER NOT NULL,
                price NUMERIC NOT NULL,
                needed DATE,
                UNIQUE (invoice_id, line_no)
            );
            """
        )
        connection.execute("INSERT INTO customers (id, name) VALUES (1, 'Acme')")
        connection.executemany(
            "INSERT INTO products (id, name, price) VALUES (?, ?, ?)",
            ((1, "Widget", "1.50"), (2, "Gadget", "2.00")),
        )
        connection.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (1, 'INV-1', 1, '2026-04-02', '', '7.00')"
        )
        connection.executemany(
            "INSERT INTO invoice_lines (id, invoice_id, line_no, product_id, description, qty, price, needed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (1, 1, 1, 1, None, 1, "1.50", "2026-04-02"),
                (2, 1, 2, 2, "Gadget", 2, "2.00", None),
                (3, 1, 3, 1, "Extra", 1, "1.50", None),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _prepare_text(root: Path) -> Path:
    path = root / "data" / "shop.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL, customer_id INTEGER NOT NULL, invoice_date TEXT, notes TEXT);
            CREATE TABLE coded_lines (
                id TEXT PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                line_no INTEGER NOT NULL,
                note TEXT,
                UNIQUE (invoice_id, line_no)
            );
            """
        )
        connection.execute("INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes) VALUES (1, 'INV-1', 1, '2026-04-02', '')")
        connection.execute("INSERT INTO coded_lines (id, invoice_id, line_no, note) VALUES ('L1', 1, 1, 'hello')")
        connection.commit()
    finally:
        connection.close()
    return path


def _invoice_schema(parent: str = "invoices", lines: str = "invoice_lines") -> Schema:
    return Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table(
                parent,
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_no", "TEXT", False),
                    Column("customer_id", "INTEGER", False, references=Reference("customers", "id")),
                    Column("invoice_date", "TEXT", True),
                    Column("notes", "TEXT", True),
                    Column("total", "NUMERIC", True),
                ),
                key="id",
            ),
            Table(
                "products",
                (
                    Column("id", "INTEGER", False),
                    Column("name", "TEXT", False),
                    Column("price", "NUMERIC", False),
                ),
                key="id",
            ),
            Table(
                lines,
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference(parent, "id")),
                    Column("line_no", "INTEGER", False),
                    Column("product_id", "INTEGER", True, references=Reference("products", "id")),
                    Column("description", "TEXT", True),
                    Column("qty", "INTEGER", False),
                    Column("price", "NUMERIC", False),
                    Column("needed", "DATE", True),
                ),
                key="id",
                unique_keys=(("invoice_id", "line_no"),),
            ),
        ),
    )


def _text_schema(tmp_path: Path) -> Schema:
    del tmp_path
    path_holder: List[Schema] = []
    del path_holder
    return Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table(
                "invoices",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_no", "TEXT", False),
                    Column("customer_id", "INTEGER", False),
                    Column("invoice_date", "TEXT", True),
                    Column("notes", "TEXT", True),
                ),
                key="id",
            ),
            Table(
                "coded_lines",
                (
                    Column("id", "TEXT", False),
                    Column("invoice_id", "INTEGER", False, references=Reference("invoices", "id")),
                    Column("line_no", "INTEGER", False),
                    Column("note", "TEXT", True),
                ),
                key="id",
                unique_keys=(("invoice_id", "line_no"),),
            ),
        ),
    )


def _spec(lines: str = "invoice_lines", products: str = "products") -> Rows:
    columns = []
    for column in _ROWS.columns:
        if isinstance(column, DataColumn) and column.lookup is not None:
            columns.append(replace(column, lookup=replace(column.lookup, table=products)))
        else:
            columns.append(column)
    return replace(_ROWS, table=lines, columns=tuple(columns))


def _ui(parent: str = "invoices", lines: str = "invoice_lines", products: str = "products") -> str:
    rows = '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n' % escape(
        write_rows(_spec(lines, products))
    )
    total = (
        '    <property name="cbcsValue" stdset="0"><string notr="true">sum(linesView.lineTotal)</string></property>\n'
        '    <property name="cbcsFormat" stdset="0"><string notr="true">number:2</string></property>\n'
        '    <property name="alignment"><set>Qt::AlignRight|Qt::AlignVCenter</set></property>\n'
    )
    fields = (
        ("Number", "QLineEdit", "invoiceNoEdit", "invoice_no", ""),
        ("Customer", "QSpinBox", "customerIdSpin", "customer_id", ""),
        ("Date", "QLineEdit", "invoiceDateEdit", "invoice_date", ""),
        ("Notes", "QLineEdit", "notesEdit", "notes", ""),
    )
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Invoice</class>\n',
        ' <widget class="QDialog" name="Invoice">\n',
        '  <property name="cbcsData" stdset="0"><string notr="true">%s</string></property>\n' % escape(write_data(RecordSource("shop", parent, "id"))),
        '  <layout class="QFormLayout" name="formLayout">\n',
    ]
    for row, (label, class_name, name, column, extra) in enumerate(fields):
        bind = '    <property name="cbcsBind" stdset="0"><string notr="true">%s</string></property>\n' % escape(column)
        parts.append(
            '   <item row="%d" column="0"><widget class="QLabel" name="%sLabel"><property name="text"><string>%s</string></property></widget></item>\n'
            % (row, name, label)
        )
        parts.append(
            '   <item row="%d" column="1"><widget class="%s" name="%s">\n%s%s    </widget></item>\n'
            % (row, class_name, name, bind, extra)
        )
    parts.append(
        '   <item row="4" column="0" colspan="2"><widget class="QTableView" name="linesView">\n%s    </widget></item>\n' % rows
    )
    parts.append(
        '   <item row="5" column="0" colspan="2"><layout class="QHBoxLayout" name="lineButtons">\n'
        '    <item><widget class="QPushButton" name="addLineButton"><property name="text"><string>Add line</string></property></widget></item>\n'
        '    <item><widget class="QPushButton" name="deleteLineButton"><property name="text"><string>Delete line</string></property></widget></item>\n'
        '    <item><spacer name="lineSpacer"><property name="orientation"><enum>Qt::Horizontal</enum></property></spacer></item>\n'
        "   </layout></item>\n"
    )
    parts.append(
        '   <item row="6" column="0" colspan="2"><layout class="QHBoxLayout" name="totalRow">\n'
        '    <item><widget class="QLabel" name="totalCaption"><property name="text"><string>Total</string></property></widget></item>\n'
        '    <item><spacer name="totalSpacer"><property name="orientation"><enum>Qt::Horizontal</enum></property></spacer></item>\n'
        '    <item><widget class="QLabel" name="totalLabel">\n%s    </widget></item>\n'
        "   </layout></item>\n" % total
    )
    bar = (
        ("firstButton", "First"),
        ("previousButton", "Previous"),
        ("nextButton", "Next"),
        ("lastButton", "Last"),
        ("newButton", "New"),
        ("saveButton", "Save"),
        ("revertButton", "Revert"),
        ("deleteButton", "Delete"),
        ("findButton", "Find"),
    )
    buttons = "".join(
        '    <item><widget class="QPushButton" name="%s"><property name="text"><string>%s</string></property></widget></item>\n' % item
        for item in bar
    )
    parts.append(
        '   <item row="7" column="0" colspan="2"><layout class="QHBoxLayout" name="recordBar">\n%s   </layout></item>\n' % buttons
    )
    parts.append("  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n")
    return "".join(parts)


def _text_ui() -> str:
    rows = Rows(
        "coded_lines",
        "invoice_id",
        "id",
        (DataColumn("note", "Note"),),
        "line_no",
        "line_no",
    )
    extra = '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n' % escape(write_rows(rows))
    return _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QSpinBox", "customerIdSpin", "customer_id", ""),
            ("QLineEdit", "notesEdit", "notes", ""),
            ("QTableView", "linesView", "", extra),
        ),
    )


def _rows_xml(rows: Rows) -> str:
    return '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n' % escape(write_rows(rows))


def _read(db: Path) -> List[Tuple[Any, ...]]:
    connection = sqlite3.connect(str(db))
    try:
        found = connection.execute(
            "SELECT id, line_no, description, qty, price, needed FROM invoice_lines WHERE invoice_id = 1 ORDER BY line_no"
        ).fetchall()
    finally:
        connection.close()
    return list(found)


def _index(ui: Any, name: str) -> int:
    return ui._cbcs_line_names.index(name)


def _value(ui: Any, row: int, name: str) -> Any:
    item = ui.linesView.model().item(row, _index(ui, name))
    return None if item is None else item.data(ui._cbcs_line_role)


def _set(ui: Any, row: int, name: str, value: Any) -> None:
    item = ui.linesView.model().item(row, _index(ui, name))
    item.setData(value, ui._cbcs_line_role)
    item.setText("" if value is None else str(value))


def _generate_text(root: Path, ui_path: Path, ui_text: str) -> str:
    ui_path.parent.mkdir(parents=True, exist_ok=True)
    ui_path.write_text(ui_text, encoding="utf-8")
    return _generate(root, ui_path, ui_text)


def _edit(ui: Any, row: int, name: str, change: Optional[Callable[[Any], None]] = None) -> None:
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

    index = ui.linesView.model().index(row, _index(ui, name))
    ui.linesView.setCurrentIndex(index)
    ui.linesView.edit(index)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    editor = ui.linesView.indexWidget(index)
    delegate = ui.linesView.itemDelegate()
    opened = editor is not None
    if editor is None:
        editor = delegate.createEditor(ui.linesView.viewport(), QStyleOptionViewItem(), index)
        delegate.setEditorData(editor, index)
    assert editor is not None
    if change is not None:
        change(editor)
    if opened:
        delegate.commitData.emit(editor)
        delegate.closeEditor.emit(editor, 0)
    else:
        delegate.setModelData(editor, ui.linesView.model(), index)
    if app is not None:
        app.processEvents()


def _typed_schema() -> Schema:
    return Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table(
                "invoices",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_no", "TEXT", False),
                ),
                key="id",
            ),
            Table(
                "typed_lines",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference("invoices", "id")),
                    Column("line_no", "INTEGER", False),
                    Column("flag", "BOOLEAN", True),
                    Column("due", "DATE", True),
                    Column("amount", "NUMERIC", True),
                ),
                key="id",
            ),
        ),
    )


def _typed_ui() -> str:
    rows = Rows(
        "typed_lines",
        "invoice_id",
        "id",
        (
            DataColumn("flag", "Flag", "yesno"),
            DataColumn("due", "When"),
            DataColumn("amount", "Amount", "money"),
        ),
        "line_no",
        "line_no",
    )
    return _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QTableView", "linesView", "", _rows_xml(rows)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )


def _prepare_typed(root: Path) -> Path:
    path = root / "data" / "shop.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL);
            CREATE TABLE typed_lines (
                id INTEGER PRIMARY KEY,
                invoice_id INTEGER NOT NULL,
                line_no INTEGER NOT NULL,
                flag BOOLEAN,
                due DATE,
                amount NUMERIC
            );
            """
        )
        connection.execute("INSERT INTO invoices (id, invoice_no) VALUES (1, 'INV-1')")
        connection.execute(
            "INSERT INTO typed_lines (id, invoice_id, line_no, flag, due, amount) VALUES (1, 1, 1, 1, '2026-04-02', NULL)"
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _move(ui: Any, source: int, target: int) -> None:
    model = ui.linesView.model()
    row = model.takeRow(source)
    model.insertRow(target, row)


def test_a_bad_line_date_opens_blank_and_stays_unsaved(tmp_path: Path) -> None:
    def prepare(root: Path) -> Path:
        path = _prepare(root)
        connection = sqlite3.connect(str(path))
        connection.execute("UPDATE invoice_lines SET needed = '4/2/2026' WHERE id = 1")
        connection.commit()
        connection.close()
        return path

    with record_window(tmp_path, _ui(), prepare, schema=_invoice_schema()) as (host, db):
        assert host.ui._cbcs_is_dirty() is False
        assert _value(host.ui, 0, "needed") is None
        assert "needed has a value that isn't a date ('4/2/2026')" in host.ui._cbcs_status_line
        _set(host.ui, 0, "description", "kept")
        assert host.ui.cbcs_save() is True
    connection = sqlite3.connect(str(db))
    try:
        stored = connection.execute("SELECT needed FROM invoice_lines WHERE id = 1").fetchone()[0]
    finally:
        connection.close()
    assert stored == "4/2/2026"

