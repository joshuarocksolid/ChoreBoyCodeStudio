# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
"""Form from a table writes a bound invoice, its lines, and a customer list."""

from __future__ import annotations

import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.schema import Schema, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader, set_schema_reader
from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file
from app.features.form_builder.engine.data.source import (
    ListSource,
    RecordSource,
    read_data,
    read_lookup,
    read_rows,
)
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import Step
from app.features.form_builder.engine.logic.events_catalog import step_words
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.project.from_table_plan import ColumnChoice, TableRequest, plan_forms
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.data_panel.column_insert_hooks import search_screen_command
from app.features.form_builder.qtside.dialogs.search_screen import install as install_search_screen
from app.features.form_builder.qtside.dialogs.table_apply import open_plan, render_plans
from tests.form_builder.engine.test_m8_2_scenario import _generate, _install_boxes, _load_module, _ui_class
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
