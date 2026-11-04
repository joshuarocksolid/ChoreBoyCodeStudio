# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
"""Form from a table writes a bound invoice, its lines, and a customer list."""

from __future__ import annotations

import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple
from xml.sax.saxutils import escape

import pytest

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.schema import Column, Schema, Table, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader, set_schema_reader
from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file
from app.features.form_builder.engine.data.source import (
    CalcColumn,
    DataColumn,
    ListSource,
    RecordSource,
    Rows,
    read_data,
    read_lookup,
    read_rows,
    write_rows,
)
from app.features.form_builder.engine.data.sql import name_usable
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import Step
from app.features.form_builder.engine.logic.events_catalog import step_words
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.project.from_table_plan import (
    ColumnChoice,
    TableRequest,
    choice_for,
    include_column,
    plan_forms,
)
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.data_panel.column_insert_hooks import search_screen_command
from app.features.form_builder.qtside.dialogs.search_screen import install as install_search_screen
from app.features.form_builder.qtside.dialogs.table_apply import open_plan, render_plans
from tests.form_builder.engine.test_m8_2_scenario import (
    _document,
    _generate,
    _install_boxes,
    _load_module,
    _ui_class,
    _xml,
)
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit


def test_open_record_steps_name_which() -> None:
    new = EventStep("openRecord", raw=Step("openRecord", fields=(("which", "new"),)))
    selected = EventStep("openRecord", raw=Step("openRecord", fields=(("which", "selected"),)))
    assert step_words(new, "") == "Open record form (new)"
    assert step_words(selected, "") == "Open record form (selected)"


def test_search_screen_command_is_registered() -> None:
    install_search_screen()
    command = search_screen_command()
    assert command is not None
    assert command.__name__ == "open_search_screen"


def test_search_screen_writes_a_list_keyed_to_the_record_form(tmp_path: Path) -> None:
    from app.features.form_builder.engine.logic.events import read_event
    from app.features.form_builder.qtside.dialogs.search_screen import open_search_screen
    from app.qt.QtWidgets import QApplication, QWidget

    root, schema = _shop(tmp_path)
    request = TableRequest(
        "shop",
        "customers",
        _customer_request().columns,
        "record",
        "",
        "customer",
        "yyyy-MM-dd",
    )
    session = open_plan(plan_forms(request, schema).forms[0], schema, str(root))
    app = QApplication.instance() or QApplication([])

    class Project:
        project_root = str(root)

    window = QWidget()
    window._loaded_project = Project()
    window.session = session
    window.show()
    app.processEvents()
    try:
        open_search_screen("customers")
        path = root / "forms" / "customer_list.ui"
        assert path.is_file()
        document = read_ui(path.read_text(encoding="utf-8"), allocator=IdAllocator()).document
        data = read_data(_prop(document.root, "cbcsData")).value
        assert isinstance(data, ListSource) and data.open is not None and data.open.form == "customer"
        assert _prop(document.node(document.by_name("searchEdit")[0]), "placeholderText") == "Search customers"
        opened = read_event(document, "newButton", "clicked")
        selected = read_event(document, "openButton", "clicked")
        assert step_words(opened.steps[0], "") == "Open record form (new)"
        assert step_words(selected.steps[0], "") == "Open record form (selected)"
    finally:
        window.close()
        session.dispose()
        set_schema_reader(None)


def test_invoice_create_is_one_command_and_opens_clean(tmp_path: Path) -> None:
    root, schema = _shop(tmp_path)
    request = _invoice_request()
    planned = plan_forms(request, schema)
    assert planned.disabled_reason == ""
    assert planned.button_text == "Create invoice form with 5 fields and lines and a list"
    session = open_plan(planned.forms[0], schema, str(root))
    try:
        assert len(session.log.entries()) == 1
        assert session.log.undo_label() == planned.button_text
        text = write_ui(session.document).text
    finally:
        session.dispose()
    again = write_ui(read_ui(text, allocator=IdAllocator()).document).text
    assert again == text
    written = root / "forms" / "invoice.ui"
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(text, encoding="utf-8")
    from app.features.form_builder.engine.project.forms import FormScope

    scope = FormScope(
        kind="project",
        ui_path=str(written),
        project_root=str(root),
        generated_path=str(root / "forms" / "ui_invoice.py"),
        window_path=str(root / "forms" / "invoice_window.py"),
        module_name="forms.ui_invoice",
    )
    opened = FormSession.open(written.read_text(encoding="utf-8"), path=str(written), scope=scope)
    try:
        assert len(opened.log.entries()) == 0
        assert write_ui(opened.document).text == written.read_text(encoding="utf-8")
    finally:
        opened.dispose()
    assert 'class="QFormLayout"' in text
    document = read_ui(text, allocator=IdAllocator()).document
    formula = _prop(document.node(document.by_name("positionLabel")[0]), "cbcsValue")
    assert "New invoice" in formula and "text(form.position)" in formula
    source = read_data(_prop(document.root, "cbcsData")).value
    assert isinstance(source, RecordSource) and source.table == "invoices" and source.key == "id"
    lookup, lookup_error = read_lookup(_prop(document.node(document.by_name("customer_id")[0]), "cbcsLookup"))
    assert lookup_error is None and lookup is not None
    assert lookup.table == "customers" and lookup.show == "name" and lookup.blank == "(choose a customer)"
    rows, rows_error = read_rows(_prop(document.node(document.by_name("invoice_linesView")[0]), "cbcsRows"))
    assert rows_error is None and rows is not None and rows.table == "invoice_lines" and rows.link == "invoice_id"
    assert any(
        getattr(column, "column", "") == "product_id" and getattr(column, "lookup", None) is not None
        for column in rows.columns
    )
    assert document.by_name("saveButton")
    list_text = render_plans(request, schema, str(root))[1][1]
    listed = read_ui(list_text, allocator=IdAllocator()).document
    placeholder = _prop(listed.node(listed.by_name("searchEdit")[0]), "placeholderText")
    assert placeholder == "Search invoices"
    data = read_data(_prop(listed.root, "cbcsData")).value
    assert isinstance(data, ListSource) and data.open is not None and data.open.form == "invoice" and data.open.key == "id"


def test_created_table_forms_have_no_diagnostics(tmp_path: Path) -> None:
    """Make both, each Make choice, and a table with no lines start with no diagnostics."""

    from app.features.form_builder.engine.data.publish import publish_session

    root, schema = _shop(tmp_path)
    cases = (
        ("invoices", "both", "invoice_lines", "invoice"),
        ("invoices", "record", "invoice_lines", "invoice"),
        ("invoices", "list", "", "invoice"),
        ("products", "both", "", "product"),
        ("products", "record", "", "product"),
        ("products", "list", "", "product"),
    )
    for table, make, lines, stem in cases:
        request = _schema_request(schema, table, make, lines, stem)
        planned = plan_forms(request, schema)
        assert planned.disabled_reason == ""
        for plan in planned.forms:
            session = open_plan(plan, schema, str(root))
            try:
                publish_session(session)
                found = [
                    (row.code, row.message, row.location.object_name)
                    for row in session.diagnostics.all()
                ]
                assert found == [], (table, make, plan.stem, found)
            finally:
                session.dispose()


def test_a_line_total_on_a_table_form_is_not_a_type_error(tmp_path: Path) -> None:
    """qty * price on a form from a table is not FB102. Blank kinds are not text."""

    from app.features.form_builder.engine.data.publish import publish_session
    from app.features.form_builder.qtside.data_panel.lines_sheet import set_lines

    root, schema = _shop(tmp_path)
    request = _schema_request(schema, "invoices", "both", "invoice_lines", "invoice")
    session = open_plan(plan_forms(request, schema).forms[0], schema, str(root))
    try:
        node = session.document.by_name("invoice_linesView")[0]
        rows, error = read_rows(_prop(session.document.node(node), "cbcsRows"))
        assert error is None and rows is not None
        set_lines(
            session,
            node,
            Rows(
                rows.table,
                rows.link,
                rows.key,
                rows.columns + (CalcColumn("line_total", "qty * price", "Line total"),),
                rows.order,
                rows.position,
            ),
        )
        publish_session(session)
        found = [(row.code, row.message, row.location.object_name) for row in session.diagnostics.all()]
        assert found == []
    finally:
        session.dispose()


def test_lines_start_checked_only_for_a_real_line_table(tmp_path: Path) -> None:
    from app.features.form_builder.engine.project.from_table_plan import child_tables, default_lines

    _root, schema = _shop(tmp_path)
    tables = {table.name: table for table in schema.tables}
    assert default_lines(schema, "invoices", tables["invoice_lines"])
    assert not any(default_lines(schema, "products", child) for child in child_tables(schema, "products"))
    assert not any(default_lines(schema, "customers", child) for child in child_tables(schema, "customers"))


def test_product_save_without_lines_leaves_invoice_lines(tmp_path: Path) -> None:
    root, schema = _shop(tmp_path)
    request = TableRequest(
        "shop",
        "products",
        (ColumnChoice("name", "QLineEdit", "Name"), ColumnChoice("price", "QDoubleSpinBox", "Price")),
        "record",
        "",
        "product",
        "yyyy-MM-dd",
    )
    _write_generated(root, _texts(root, schema, request))
    with _hosts(root, "product") as (host, db):
        before = _all(db, "SELECT id, invoice_id, line_no, product_id FROM invoice_lines ORDER BY id")
        host.ui.cbcs_open(1)
        host.ui.name.setText("Widget 2")
        assert host.ui.cbcs_save() is True
        assert _all(db, "SELECT id, invoice_id, line_no, product_id FROM invoice_lines ORDER BY id") == before


def test_a_clashing_list_module_names_the_file(tmp_path: Path) -> None:
    from app.features.form_builder.engine.project.fs import OsFileSystem
    from app.features.form_builder.engine.project.names import first_name_clash

    root, schema = _shop(tmp_path)
    forms = root / "forms"
    (forms / "invoice_list.py").write_text("# the user's own module\n", encoding="utf-8")
    made = render_plans(_invoice_request(), schema, str(root))
    reason = first_name_clash(str(forms), tuple(stem for stem, _text in made), OsFileSystem())
    assert reason is not None and "invoice_list.py" in reason
    assert not (forms / "invoice.ui").is_file()


def test_keyword_column_names_still_generate(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    database = root / "data" / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        'CREATE TABLE "order" (id INTEGER PRIMARY KEY, "class" TEXT, "from" TEXT, "first name" TEXT);'
        "INSERT INTO \"order\" VALUES (1, 'a', 'b', 'Ann');"
        'CREATE TABLE "order line" (id INTEGER PRIMARY KEY, "order" INTEGER NOT NULL REFERENCES "order"(id), "select" TEXT);'
        'INSERT INTO "order line" VALUES (1, 1, \'x\');'
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    _save_schema(root, schema)
    _save_connection(root)
    table = next(item for item in schema.tables if item.name == "order")
    from app.features.form_builder.engine.project.from_table_plan import choice_for, include_column

    columns = tuple(
        choice_for(column, "sqlite")
        for column in table.columns
        if include_column(column, "id", "sqlite")
    )
    request = TableRequest("shop", "order", columns, "both", "order line", "orders", "yyyy-MM-dd")
    texts = _texts(root, schema, request)
    _write_generated(root, texts)
    with _hosts(root, "orders") as (host, db):
        host.ui.cbcs_open(1)
        assert host.ui.cbcs_save() is True
        assert _all(db, 'SELECT "class", "from", "first name" FROM "order"') == [("a", "b", "Ann")]


def test_text_on_a_foreign_key_drops_the_lookup(tmp_path: Path) -> None:
    root, schema = _shop(tmp_path)
    request = TableRequest(
        "shop",
        "invoices",
        (ColumnChoice("customer_id", "QLineEdit", "Customer"), ColumnChoice("invoice_no", "QLineEdit", "Invoice No")),
        "record",
        "",
        "invoice",
        "yyyy-MM-dd",
    )
    text = _texts(root, schema, request)[0][1]
    document = read_ui(text, allocator=IdAllocator()).document
    node = document.node(document.by_name("customer_id")[0])
    assert node.class_name == "QLineEdit"
    assert _prop(node, "cbcsLookup") == ""


def test_invoice_story_saves_lines_and_a_customer_edit(tmp_path: Path) -> None:
    root, schema = _shop(tmp_path)
    invoice = _texts(root, schema, _invoice_request())
    customer = _texts(root, schema, _customer_request())
    _write_generated(root, invoice + customer)
    samples: List[float] = []
    with _hosts(root, "invoice") as (invoice_host, db):
        ui = invoice_host.ui
        ui.cbcs_new()
        ui.cbcs_load_lookups()
        ui.invoice_no.setText("INV-9")
        _pick(ui.customer_id, 2)
        ui._cbcs_add_row()
        ui._cbcs_add_row()
        _line(ui, 0, "qty", 2)
        _line(ui, 0, "price", Decimal("1.50"))
        _line(ui, 0, "product_id", 1)
        _line(ui, 1, "qty", 1)
        _line(ui, 1, "price", Decimal("2.00"))
        _line(ui, 1, "description", None)
        started = time.perf_counter()
        assert ui.cbcs_save() is True
        samples.append(time.perf_counter() - started)
        row = _one(db, "SELECT invoice_no, customer_id, notes FROM invoices WHERE invoice_no = 'INV-9'")
        assert row[0] == "INV-9" and row[1] == 2 and row[2] in (None, "")
        lines = _all(
            db,
            "SELECT qty, price, description FROM invoice_lines WHERE invoice_id = "
            "(SELECT id FROM invoices WHERE invoice_no = 'INV-9') ORDER BY line_no",
        )
        assert len(lines) == 2
        assert lines[0][0] == 2
        assert Decimal(str(lines[0][1])) == Decimal("1.50")
        assert lines[1][2] in (None, "")
        for _index in range(2):
            ui.notes.setText("edited")
            started = time.perf_counter()
            assert ui.cbcs_save() is True
            samples.append(time.perf_counter() - started)
        assert _one(db, "SELECT notes FROM invoices WHERE invoice_no = 'INV-9'")[0] == "edited"
    print("SAVE_MS=%s" % ",".join("%.3f" % (sample * 1000) for sample in samples))
    assert max(samples) < 2.0
    open_samples: List[float] = []
    with _hosts(root, "invoice") as (host, db):
        key = _one(db, "SELECT id FROM invoices WHERE invoice_no = 'INV-9'")[0]
        for _index in range(3):
            started = time.perf_counter()
            host.ui.cbcs_open(key)
            open_samples.append(time.perf_counter() - started)
        assert host.ui.invoice_no.text() == "INV-9"
    print("OPEN_MS=%s" % ",".join("%.3f" % (sample * 1000) for sample in open_samples))
    assert max(open_samples) < 2.0
    list_samples: List[float] = []
    with _hosts(root, "invoice_list") as (list_host, db):
        for _index in range(3):
            list_host.ui.searchEdit.setText("INV-9")
            started = time.perf_counter()
            list_host.ui.cbcs_refresh_list()
            list_samples.append(time.perf_counter() - started)
        opened = _open_selected(list_host, "INV-9", "invoice")
        opened.ui.notes.setText("from the list")
        assert opened.ui.cbcs_save() is True
        opened.close()
        assert _one(db, "SELECT notes FROM invoices WHERE invoice_no = 'INV-9'")[0] == "from the list"
    print("LIST_MS=%s" % ",".join("%.3f" % (sample * 1000) for sample in list_samples))
    assert max(list_samples) < 2.0
    with _hosts(root, "customer_list") as (list_host, db):
        list_host.ui.cbcs_refresh_list()
        opened = _open_selected(list_host, "Acme", "customer")
        opened.ui.name.setText("Acme Goods")
        assert opened.ui.cbcs_save() is True
        opened.close()
        assert _one(db, "SELECT name FROM customers WHERE id = 1")[0] == "Acme Goods"


def test_a_text_key_keeps_null_decimal_and_date(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    db = root / "data" / "shop.db"
    connection = sqlite3.connect(str(db))
    connection.execute(
        "CREATE TABLE jobs (code TEXT PRIMARY KEY, title TEXT, due TEXT, amount NUMERIC, note TEXT)"
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(db), "shop", read_at="2026-11-03T00:00:00Z")
    _save_schema(root, schema)
    _save_connection(root)
    columns = (
        ColumnChoice("code", "QLineEdit", "Code"),
        ColumnChoice("title", "QLineEdit", "Title"),
        ColumnChoice("due", "QDateEdit", "Due"),
        ColumnChoice("amount", "QDoubleSpinBox", "Amount"),
        ColumnChoice("note", "QLineEdit", "Note"),
    )
    request = TableRequest("shop", "jobs", columns, "record", "", "job", "yyyy-MM-dd")
    _write_generated(root, _texts(root, schema, request))
    with _hosts(root, "job") as (host, database):
        ui = host.ui
        ui.cbcs_new()
        ui.code.setText("J-1")
        ui.title.setText("Roof")
        from app.qt.QtCore import QDate

        ui.due.setDate(QDate(2026, 4, 5))
        ui.amount.setValue(3.25)
        ui.note.clear()
        assert ui.cbcs_save() is True
        row = _one(database, "SELECT code, title, due, amount, note FROM jobs")
        assert row[0] == "J-1"
        assert row[1] == "Roof"
        assert "2026" in str(row[2])
        assert Decimal(str(row[3])) == Decimal("3.25")
        assert row[4] in (None, "")


def _shop(tmp_path: Path) -> Tuple[Path, Schema]:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    database = root / "data" / "shop.db"
    build(str(database))
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    _save_schema(root, schema)
    _save_connection(root)
    return root, schema


def _schema_request(schema: Schema, table_name: str, make: str, lines: str, stem: str) -> TableRequest:
    table = next(item for item in schema.tables if item.name == table_name)
    engine = schema.engine or "sqlite"
    columns = tuple(
        choice_for(column, engine)
        for column in table.columns
        if include_column(column, table.key or "", engine)
    )
    return TableRequest("shop", table_name, columns, make, lines, stem, "yyyy-MM-dd")


def _invoice_request() -> TableRequest:
    columns = (
        ColumnChoice("invoice_no", "QLineEdit", "Invoice No"),
        ColumnChoice("customer_id", "QComboBox", "Customer"),
        ColumnChoice("invoice_date", "QDateEdit", "Invoice Date"),
        ColumnChoice("notes", "QLineEdit", "Notes"),
        ColumnChoice("total", "QDoubleSpinBox", "Total"),
    )
    return TableRequest("shop", "invoices", columns, "both", "invoice_lines", "invoice", "yyyy-MM-dd")


def _customer_request() -> TableRequest:
    columns = (
        ColumnChoice("name", "QLineEdit", "Name"),
        ColumnChoice("phone", "QLineEdit", "Phone"),
        ColumnChoice("city", "QLineEdit", "City"),
        ColumnChoice("email", "QLineEdit", "Email"),
    )
    return TableRequest("shop", "customers", columns, "both", "", "customer", "yyyy-MM-dd")


def _texts(root: Path, schema: Schema, request: TableRequest) -> Tuple[Tuple[str, str], ...]:
    install_schema_reader(str(root))
    return render_plans(request, schema, str(root))


def _save_schema(root: Path, schema: Schema) -> None:
    folder = root / "cbcs" / "schema"
    folder.mkdir(parents=True)
    (folder / "shop.json").write_text(write_schema(schema), encoding="utf-8")
    install_schema_reader(str(root))


def _save_connection(root: Path) -> None:
    value = ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db"),))
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(
        render_connections_module(value, project_slug="m83d"),
        encoding="utf-8",
    )


def _write_generated(root: Path, texts: Tuple[Tuple[str, str], ...]) -> None:
    from app.features.form_builder.engine.codegen.window_template import render_window_class
    from app.features.form_builder.engine.project.forms import FormScope

    forms = root / "forms"
    (forms / "__init__.py").write_text("", encoding="utf-8")
    for stem, text in texts:
        ui_path = forms / ("%s.ui" % stem)
        ui_path.write_text(text, encoding="utf-8")
        (forms / ("ui_%s.py" % stem)).write_text(_generate(root, ui_path, text), encoding="utf-8")
        document = read_ui(text, allocator=IdAllocator()).document
        scope = FormScope(
            kind="project",
            ui_path=str(ui_path),
            project_root=str(root),
            generated_path=str(forms / ("ui_%s.py" % stem)),
            window_path=str(forms / ("%s_window.py" % stem)),
            module_name="forms.ui_%s" % stem,
        )
        (forms / ("%s_window.py" % stem)).write_text(
            render_window_class(document, scope=scope),
            encoding="utf-8",
        )


class _hosts:
    def __init__(self, root: Path, stem: str) -> None:
        self._root = root
        self._stem = stem
        self._restore: Optional[Callable[[], None]] = None

    def __enter__(self) -> Tuple[Any, Path]:
        stashed = _stash_forms()
        forms = self._root / "forms"
        ui_path = forms / ("%s.ui" % self._stem)
        text = ui_path.read_text(encoding="utf-8")
        module = _load_module(forms / ("ui_%s.py" % self._stem), "ui_%s_m83d" % self._stem)
        seen: List[str] = []
        _install_boxes(module, seen, None, lambda message: "Save" if message.startswith("Save") else "Cancel", None)
        previous = sys.modules.get("cbcs_connections")
        connections = _load_module(self._root / "cbcs_connections.py", "cbcs_connections")
        sys.modules["cbcs_connections"] = connections
        if str(self._root) not in sys.path:
            sys.path.insert(0, str(self._root))
        from app.qt.QtWidgets import QApplication, QDialog

        app = QApplication.instance() or QApplication([])

        class Host(QDialog):
            def __init__(self) -> None:
                super().__init__()
                self.ui = _ui_class(module)()
                self.ui.setupUi(self)

        host = Host()
        host.show()
        app.processEvents()

        def restore() -> None:
            set_schema_reader(None)
            closer = getattr(connections, "close_all", None)
            if closer is not None:
                closer()
            if previous is None:
                sys.modules.pop("cbcs_connections", None)
            else:
                sys.modules["cbcs_connections"] = previous
            if sys.path and sys.path[0] == str(self._root):
                sys.path.pop(0)
            _restore_forms(stashed)

        self._restore = restore
        return host, self._root / "data" / "shop.db"

    def __exit__(self, *_exc: object) -> None:
        if self._restore is not None:
            self._restore()


def _stash_forms() -> dict:
    saved = {}
    for name in list(sys.modules):
        if name == "forms" or name.startswith("forms."):
            saved[name] = sys.modules.pop(name)
    return saved


def _restore_forms(saved: dict) -> None:
    for name in list(sys.modules):
        if name == "forms" or name.startswith("forms."):
            sys.modules.pop(name, None)
    sys.modules.update(saved)


def _pick(combo: Any, key: int) -> None:
    from app.qt.QtCore import Qt

    for index in range(combo.count()):
        if combo.itemData(index) == key or combo.itemData(index, Qt.ItemDataRole.UserRole) == key:
            combo.setCurrentIndex(index)
            return
    raise AssertionError(key)


def _line(ui: Any, row: int, name: str, value: object, view_name: str = "invoice_linesView") -> None:
    view = getattr(ui, view_name)
    column = ui._cbcs_line_names.index(name)
    item = view.model().item(row, column)
    item.setData(value, ui._cbcs_line_role)
    item.setText("" if value is None else str(value))


def _open_selected(host: Any, name: str, stem: str) -> Any:
    model = host.ui.resultTable.model()
    row = None
    for index in range(model.rowCount()):
        if model.item(index, 0).text() == name:
            row = index
            break
    assert row is not None
    host.ui.resultTable.selectRow(row)
    host.ui.cbcs_open_record("selected")
    opened = host.ui._cbcs_open_windows.get(stem)
    label = getattr(getattr(host.ui, "_cbcs_limit_label", None), "text", lambda: "")()
    assert opened is not None, (host.ui._cbcs_selected_key(), label)
    return opened


def test_the_form_tab_shows_record_sections_or_list_sections(tmp_path: Path, qapp) -> None:
    from app.features.form_builder.integration.provider import FormTabProvider
    from app.features.form_builder.qtside.inspector.pane import TabId
    from app.qt.QtWidgets import QLabel, QPlainTextEdit, QWidget
    from app.shell.tab_content_providers import TabSurfaceRequest
    from app.shell.theme_tokens import tokens_from_palette

    root, schema = _shop(tmp_path)
    texts = _texts(root, schema, _invoice_request()) + _texts(root, schema, _customer_request())
    _write_generated(root, texts)
    record = _form_tab(root, qapp, "invoice", QWidget, QPlainTextEdit, TabSurfaceRequest, tokens_from_palette, FormTabProvider)
    listing = _form_tab(root, qapp, "customer_list", QWidget, QPlainTextEdit, TabSurfaceRequest, tokens_from_palette, FormTabProvider)
    try:
        for _pass in range(2):
            record.workbench.focus_inspector_tab(TabId.DATA)
            record.workbench.inspector.data.paint("@form")
            qapp.processEvents()
        assert _shown(record, "formBuilder.inspectorData.formSource")
        assert not _shown(record, "formBuilder.data.listing")
        panel = record.workbench.section_widget("data")
        lines = panel.findChild(QLabel, "formBuilder.data.linesText")
        assert lines is not None and not lines.isHidden() and "invoice_lines" in lines.text()
        for _pass in range(2):
            listing.workbench.focus_inspector_tab(TabId.DATA)
            listing.workbench.inspector.data.paint("@form")
            qapp.processEvents()
        assert _shown(listing, "formBuilder.data.listing")
        assert not _shown(listing, "formBuilder.inspectorData.formSource")
    finally:
        for surface in (record, listing):
            parent = surface.parent()
            surface.release()
            if parent is not None:
                parent.close()
        set_schema_reader(None)


def _form_tab(root, qapp, stem, widget_type, editor_type, request_type, tokens_from_palette, provider):
    parent = widget_type()
    path = root / "forms" / ("%s.ui" % stem)
    text = path.read_text(encoding="utf-8")

    def create_source_editor():
        editor = editor_type(parent)
        editor.setObjectName("shell.editorTabs.textEditor")
        return editor

    surface = provider().create_surface(
        request_type(
            file_path=str(path),
            initial_text=text,
            parent=parent,
            theme=tokens_from_palette(qapp.palette(), force_mode="light"),
            create_source_editor=create_source_editor,
            open_linked_file=lambda _linked: None,
            project_root=str(root),
        )
    )
    parent.resize(1200, 800)
    parent.show()
    surface.resize(1200, 800)
    surface.show()
    qapp.processEvents()
    surface.workbench.focus_section("data")
    qapp.processEvents()
    return surface


def _shown(surface, name: str) -> bool:
    from app.qt.QtWidgets import QWidget

    found = surface.findChildren(QWidget, name)
    return any(not widget.isHidden() for widget in found)


def _prop(node: Any, name: str) -> str:
    entry = node.prop(name) if hasattr(node, "prop") else None
    value = getattr(entry, "value", None)
    text = getattr(value, "text", "")
    return text if isinstance(text, str) else ""


def _one(database: Path, sql: str) -> Tuple[object, ...]:
    connection = sqlite3.connect(str(database))
    try:
        row = connection.execute(sql).fetchone()
    finally:
        connection.close()
    assert row is not None
    return tuple(row)


def _all(database: Path, sql: str) -> List[Tuple[object, ...]]:
    connection = sqlite3.connect(str(database))
    try:
        return [tuple(row) for row in connection.execute(sql)]
    finally:
        connection.close()


def test_spaced_names_keep_the_lookup_and_skip_fb307(tmp_path: Path) -> None:
    from app.features.form_builder.engine.data.check import run_checks
    from app.features.form_builder.engine.project.from_table_plan import choice_for, include_column

    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    database = root / "data" / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        'CREATE TABLE "the products" (id INTEGER PRIMARY KEY, "display name" TEXT NOT NULL);'
        "INSERT INTO \"the products\" VALUES (1, 'Widget');"
        'CREATE TABLE "first name" ('
        "id INTEGER PRIMARY KEY, "
        '"product id" INTEGER REFERENCES "the products"(id), '
        '"given name" TEXT);'
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    _save_schema(root, schema)
    _save_connection(root)
    table = next(item for item in schema.tables if item.name == "first name")
    columns = tuple(
        choice_for(column, "sqlite")
        for column in table.columns
        if include_column(column, table.key or "", "sqlite")
    )
    request = TableRequest("shop", "first name", columns, "record", "", "person", "yyyy-MM-dd")
    text = _texts(root, schema, request)[0][1]
    document = read_ui(text, allocator=IdAllocator()).document
    assert [item.code for item in run_checks(document, None, schema) if item.code == "FB307"] == []
    lookup, lookup_error = read_lookup(_prop(document.node(document.by_name("product_id")[0]), "cbcsLookup"))
    assert lookup_error is None and lookup is not None
    assert lookup.table == "the products" and lookup.show == "display name"


def test_a_line_without_a_unique_position_writes_the_next_number(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    database = root / "data" / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT);"
        "INSERT INTO jobs VALUES (1, 'Roof');"
        "CREATE TABLE job_lines ("
        "id INTEGER PRIMARY KEY, "
        "job_id INTEGER NOT NULL REFERENCES jobs(id), "
        "line_no INTEGER NOT NULL, "
        "note TEXT);"
        "INSERT INTO job_lines VALUES (1, 1, 5, 'a');"
        "INSERT INTO job_lines VALUES (2, 1, 9, 'b');"
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    _save_schema(root, schema)
    _save_connection(root)
    request = TableRequest(
        "shop",
        "jobs",
        (ColumnChoice("title", "QLineEdit", "Title"),),
        "record",
        "job_lines",
        "job",
        "yyyy-MM-dd",
        lines_link="job_id",
    )
    _write_generated(root, _texts(root, schema, request))
    with _hosts(root, "job") as (host, db):
        host.ui.cbcs_open(1)
        host.ui._cbcs_add_row()
        _line(host.ui, 2, "note", "c", "job_linesView")
        assert host.ui.cbcs_save() is True
        host.close()
    assert _all(database, "SELECT line_no, note FROM job_lines ORDER BY line_no") == [(5, "a"), (9, "b"), (10, "c")]
    with _hosts(root, "job") as (host, db):
        host.ui.cbcs_open(1)
        _line(host.ui, 0, "note", "a2", "job_linesView")
        assert host.ui.cbcs_save() is True
        host.close()
    assert _all(database, "SELECT line_no, note FROM job_lines ORDER BY line_no") == [(5, "a2"), (9, "b"), (10, "c")]


def test_an_earlier_numbered_list_is_reopened(tmp_path: Path) -> None:
    from app.features.form_builder.qtside.dialogs.search_screen import open_search_screen
    from app.qt.QtWidgets import QApplication, QWidget

    root, schema = _shop(tmp_path)
    record = TableRequest("shop", "customers", _customer_request().columns, "record", "", "customer", "yyyy-MM-dd")
    session = open_plan(plan_forms(record, schema).forms[0], schema, str(root))
    listed = TableRequest(
        "shop",
        "customers",
        _customer_request().columns,
        "list",
        "",
        "customer_list_2",
        "yyyy-MM-dd",
        open_form="customer",
    )
    (root / "forms" / "customer_list_2.ui").write_text(render_plans(listed, schema, str(root))[0][1], encoding="utf-8")
    app = QApplication.instance() or QApplication([])

    class Project:
        project_root = str(root)

    window = QWidget()
    window._loaded_project = Project()
    window.session = session
    window.show()
    app.processEvents()
    try:
        open_search_screen("customers")
        assert not (root / "forms" / "customer_list.ui").is_file()
        assert (root / "forms" / "customer_list_2.ui").is_file()
    finally:
        window.close()
        session.dispose()
        set_schema_reader(None)


def test_a_list_module_without_a_screen_gets_a_free_name(tmp_path: Path) -> None:
    from app.features.form_builder.qtside.dialogs.search_screen import open_search_screen
    from app.qt.QtWidgets import QApplication, QWidget

    root, schema = _shop(tmp_path)
    record = TableRequest("shop", "customers", _customer_request().columns, "record", "", "customer", "yyyy-MM-dd")
    session = open_plan(plan_forms(record, schema).forms[0], schema, str(root))
    (root / "forms" / "customer_list.py").write_text("# kept\n", encoding="utf-8")
    app = QApplication.instance() or QApplication([])

    class Project:
        project_root = str(root)

    window = QWidget()
    window._loaded_project = Project()
    window.session = session
    window.show()
    app.processEvents()
    try:
        open_search_screen("customers")
        assert (root / "forms" / "customer_list.py").read_text(encoding="utf-8") == "# kept\n"
        assert not (root / "forms" / "customer_list.ui").is_file()
        assert (root / "forms" / "customer_list_2.ui").is_file()
    finally:
        window.close()
        session.dispose()
        set_schema_reader(None)


def test_a_text_column_named_position_saves_what_you_type(tmp_path: Path) -> None:
    root, schema = _staff_shop(tmp_path, "position TEXT NOT NULL")
    request = _team_request()
    planned = plan_forms(request, schema)
    assert planned.forms and planned.forms[0].lines is not None
    assert [column.column for column in planned.forms[0].lines.columns] == ["name", "position"]
    _write_generated(root, _texts(root, schema, request))
    with _hosts(root, "team") as (host, database):
        host.ui.cbcs_open(1)
        assert host.ui._cbcs_line_names == ("name", "position")
        assert _grid_text(host.ui, 0, "position", "staffView") == "Manager"
        host.ui._cbcs_add_row()
        _line(host.ui, 1, "name", "Bob", "staffView")
        _line(host.ui, 1, "position", "Clerk", "staffView")
        assert host.ui.cbcs_save() is True
        host.close()
    assert _all(database, "SELECT id, team_id, name, position FROM staff ORDER BY id") == [
        (1, 1, "Ann", "Manager"),
        (2, 1, "Bob", "Clerk"),
    ]


def test_a_refused_line_column_is_left_out_and_the_note_still_saves(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    database = root / "data" / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT);"
        "INSERT INTO jobs VALUES (1, 'Roof');"
        "CREATE TABLE job_lines ("
        "id INTEGER PRIMARY KEY, "
        "job_id INTEGER NOT NULL REFERENCES jobs(id), "
        'note TEXT, "a""b" TEXT);'
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    _save_schema(root, schema)
    _save_connection(root)
    request = TableRequest(
        "shop",
        "jobs",
        (ColumnChoice("title", "QLineEdit", "Title"),),
        "record",
        "job_lines",
        "job",
        "yyyy-MM-dd",
    )
    planned = plan_forms(request, schema)
    assert planned.disabled_reason == ""
    assert planned.forms and planned.forms[0].lines is not None
    assert [column.column for column in planned.forms[0].lines.columns] == ["note"]
    _write_generated(root, _texts(root, schema, request))
    with _hosts(root, "job") as (host, db):
        host.ui.cbcs_open(1)
        assert 'a"b' not in host.ui._cbcs_line_names
        host.ui._cbcs_add_row()
        _line(host.ui, 0, "note", "n", "job_linesView")
        assert host.ui.cbcs_save() is True
        host.close()
    assert _all(db, "SELECT note FROM job_lines") == [("n",)]


def test_a_hand_edited_refused_line_name_is_fb307() -> None:
    rows = Rows("job_lines", "job_id", "id", (DataColumn('a"b'), DataColumn("note")))
    extra = (
        '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n'
        % escape(write_rows(rows))
    )
    document = _document(
        _xml(RecordSource("shop", "jobs", "id"), (("QTableView", "job_linesView", "", extra),))
    )
    found = [item.message for item in run_checks(document, None, None) if item.code == "FB307"]
    assert any('a"b' in message for message in found)


def test_a_refused_line_link_is_not_planned(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    database = root / "data" / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT);"
        "CREATE TABLE job_lines ("
        "id INTEGER PRIMARY KEY, "
        '"a""b" INTEGER NOT NULL REFERENCES jobs(id), '
        "note TEXT);"
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    request = TableRequest(
        "shop",
        "jobs",
        (ColumnChoice("title", "QLineEdit", "Title"),),
        "record",
        "job_lines",
        "job",
        "yyyy-MM-dd",
    )
    planned = plan_forms(request, schema)
    assert planned.forms == ()
    assert 'a"b' in planned.disabled_reason


def test_a_whitespace_only_name_is_refused() -> None:
    assert name_usable(" ") is False
    assert name_usable("   ") is False
    assert name_usable(" first name ") is True
    assert name_usable("first name") is True
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-11-03T00:00:00",
        "sqlite3",
        (
            Table(
                "things",
                (
                    Column("id", "INTEGER", False),
                    Column(" ", "TEXT", True),
                    Column(" first name ", "TEXT", True),
                ),
                key="id",
            ),
        ),
    )
    document = _document(_xml(RecordSource("shop", "things", "id"), ()))
    messages = [item.message for item in run_checks(document, None, schema) if item.code == "FB307"]
    assert messages == ["  can't be used as a table or column name."]


def test_a_nullable_position_sorts_after_reload(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    database = root / "data" / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT);"
        "INSERT INTO jobs VALUES (1, 'Roof');"
        "CREATE TABLE job_lines ("
        "id INTEGER PRIMARY KEY, "
        "job_id INTEGER NOT NULL REFERENCES jobs(id), "
        "line_no INTEGER, "
        "note TEXT);"
        "INSERT INTO job_lines VALUES (1, 1, 5, 'a');"
        "INSERT INTO job_lines VALUES (2, 1, 9, 'b');"
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    _save_schema(root, schema)
    _save_connection(root)
    request = TableRequest(
        "shop",
        "jobs",
        (ColumnChoice("title", "QLineEdit", "Title"),),
        "record",
        "job_lines",
        "job",
        "yyyy-MM-dd",
        lines_link="job_id",
    )
    _write_generated(root, _texts(root, schema, request))
    with _hosts(root, "job") as (host, db):
        host.ui.cbcs_open(1)
        host.ui._cbcs_add_row()
        _line(host.ui, 2, "note", "c", "job_linesView")
        assert host.ui.cbcs_save() is True
        host.close()
    with _hosts(root, "job") as (host, db):
        host.ui.cbcs_open(1)
        assert _grid_notes(host.ui, "job_linesView") == ["a", "b", "c"]
        host.close()
    assert _all(database, "SELECT line_no, note FROM job_lines ORDER BY line_no") == [(5, "a"), (9, "b"), (10, "c")]


def test_a_missing_surface_writes_the_rendered_form(tmp_path: Path) -> None:
    from app.features.form_builder.integration.new_form import NewFormSurface
    from app.qt.QtWidgets import QApplication, QWidget
    from app.shell.tab_content_providers import TabSurfaceRequest
    from app.shell.theme_tokens import tokens_from_palette

    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "cbcs").mkdir()
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-11-03T00:00:00",
        "sqlite3",
        (Table("teams", (Column("id", "INTEGER", False), Column("title", "TEXT", True)), key="id"),),
    )
    request = TableRequest(
        "shop",
        "teams",
        (ColumnChoice("title", "QLineEdit", "Title"),),
        "record",
        "",
        "team",
        "yyyy-MM-dd",
    )
    text = render_plans(request, schema, str(root))[0][1]
    planned = plan_forms(request, schema)
    app = QApplication.instance() or QApplication([])
    window = QWidget()

    class Project:
        def __init__(self, path: str) -> None:
            self.project_root = path

    class Registry:
        def surface_for_path(self, path: str) -> None:
            del path
            return None

    window._loaded_project = Project(str(root))  # type: ignore[attr-defined]
    window._tab_content_registry = Registry()  # type: ignore[attr-defined]
    surface = NewFormSurface(
        TabSurfaceRequest(
            file_path=str(root / "cbcs" / "new-form.cbcs-tab"),
            initial_text="",
            parent=window,
            theme=tokens_from_palette(app.palette(), force_mode="light"),
            create_source_editor=lambda: None,  # type: ignore[arg-type]
            open_linked_file=lambda _path: None,
            project_root=str(root),
        ),
        window,
    )
    try:
        result = surface._create_planned("team", text, "record", planned, schema)  # noqa: SLF001
        assert result.refused is None
        written = (root / "forms" / "team.ui").read_text(encoding="utf-8")
        assert "cbcsData" in written
        assert "title" in written
    finally:
        window.close()


def test_a_failed_rendered_write_removes_the_blank_form(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.engine.project.fs import OsFileSystem
    from app.features.form_builder.integration.new_form import NewFormSurface
    from app.qt.QtWidgets import QApplication, QLabel, QWidget
    from app.shell.tab_content_providers import TabSurfaceRequest
    from app.shell.theme_tokens import tokens_from_palette

    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "cbcs").mkdir()
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-11-03T00:00:00",
        "sqlite3",
        (Table("teams", (Column("id", "INTEGER", False), Column("title", "TEXT", True)), key="id"),),
    )
    request = TableRequest(
        "shop",
        "teams",
        (ColumnChoice("title", "QLineEdit", "Title"),),
        "record",
        "",
        "team",
        "yyyy-MM-dd",
    )
    text = render_plans(request, schema, str(root))[0][1]
    planned = plan_forms(request, schema)
    original = OsFileSystem.write_bytes

    def fail_rendered(self: OsFileSystem, path: str, data: bytes) -> None:
        if path.endswith(".ui") and b"cbcsData" in data:
            raise OSError("disk full")
        original(self, path, data)

    monkeypatch.setattr(OsFileSystem, "write_bytes", fail_rendered)
    app = QApplication.instance() or QApplication([])
    window = QWidget()

    class Project:
        def __init__(self, path: str) -> None:
            self.project_root = path

    class Registry:
        def surface_for_path(self, path: str) -> None:
            del path
            return None

    window._loaded_project = Project(str(root))  # type: ignore[attr-defined]
    window._tab_content_registry = Registry()  # type: ignore[attr-defined]
    surface = NewFormSurface(
        TabSurfaceRequest(
            file_path=str(root / "cbcs" / "new-form.cbcs-tab"),
            initial_text="",
            parent=window,
            theme=tokens_from_palette(app.palette(), force_mode="light"),
            create_source_editor=lambda: None,  # type: ignore[arg-type]
            open_linked_file=lambda _path: None,
            project_root=str(root),
        ),
        window,
    )
    try:
        result = surface._create_planned("team", text, "record", planned, schema)  # noqa: SLF001
        assert result.refused is not None and "disk full" in result.refused
        assert not (root / "forms" / "team.ui").exists()
        status = surface.widget().findChild(QLabel, "formBuilder.newForm.status")
        assert status is not None and "disk full" in status.text()
    finally:
        window.close()


def _staff_shop(tmp_path: Path, position_sql: str) -> Tuple[Path, Schema]:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "data").mkdir()
    database = root / "data" / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        "CREATE TABLE teams (id INTEGER PRIMARY KEY, title TEXT);"
        "INSERT INTO teams VALUES (1, 'A');"
        "CREATE TABLE staff ("
        "id INTEGER PRIMARY KEY, "
        "team_id INTEGER NOT NULL REFERENCES teams(id), "
        "name TEXT, "
        + position_sql
        + ");"
        "INSERT INTO staff VALUES (1, 1, 'Ann', 'Manager');"
    )
    connection.commit()
    connection.close()
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    _save_schema(root, schema)
    _save_connection(root)
    return root, schema


def _team_request() -> TableRequest:
    return TableRequest(
        "shop",
        "teams",
        (ColumnChoice("title", "QLineEdit", "Title"),),
        "record",
        "staff",
        "team",
        "yyyy-MM-dd",
    )


def _grid_text(ui: Any, row: int, name: str, view_name: str) -> str:
    view = getattr(ui, view_name)
    column = ui._cbcs_line_names.index(name)
    return str(view.model().item(row, column).text())


def _grid_notes(ui: Any, view_name: str) -> List[str]:
    view = getattr(ui, view_name)
    column = ui._cbcs_line_names.index("note")
    model = view.model()
    return [str(model.item(row, column).text()) for row in range(model.rowCount())]
