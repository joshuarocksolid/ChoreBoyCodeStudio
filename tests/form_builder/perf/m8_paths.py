# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""UX-M8-003 speed rows.

CPU p95, 20 samples, the first dropped, Hyndman-Fan, load on every row, and
the M6.R idle loop. PostgreSQL rows and the schema helper are recorded.
A budget miss is profiled beside the summary.

``python -m tests.form_builder.perf.m8_paths``

The reference database is ``make_shop.py --reference``. Invoices 1 and 2 are
given 20 lines each, still inside the 400,000 line total.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sqlite3
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from tests.form_builder.perf.stats import percentile

RUNS = 20
IDLE_LOOPS = 116000
LOAD_LIMIT = 4.0
LOAD_WAIT_S = 15 * 60
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS = ROOT / "docs" / "form_builder" / "orch" / "probe_m8r_vm" / "results"


@dataclass(frozen=True)
class BudgetRow:
    key: str
    title: str
    mac_ms: float
    vm_ms: float


MAC_ROWS: Tuple[BudgetRow, ...] = (
    BudgetRow("data_tab", "Data tab fill for a 40-column table, cached schema", 16.0, 60.0),
    BudgetRow(
        "open_form",
        "Open a bound form, SQLite, 100,000 keys, both lookups, record 1 with 20 lines",
        200.0,
        800.0,
    ),
    BudgetRow("show_record", "Show another record with 20 lines", 16.0, 60.0),
    BudgetRow("dirty_check", "Dirty check on a keystroke", 1.0, 4.0),
    BudgetRow("save_record", "Save a record with 20 lines, SQLite", 40.0, 160.0),
    BudgetRow("load_lookup", "Load a 2,000-row lookup", 30.0, 120.0),
    BudgetRow("list_search", "List search, 2,000 customers, limit 500", 50.0, 200.0),
)


def budgets_for(machine: str) -> Dict[str, float]:
    field = "mac_ms" if machine == "mac" else "vm_ms"
    return {row.key: float(getattr(row, field)) for row in MAC_ROWS}


def _load() -> List[float]:
    try:
        return [round(float(value), 2) for value in os.getloadavg()]
    except OSError:
        return []


def _p(samples: Sequence[float], fraction: float) -> float:
    return percentile(list(samples), fraction)


def _idle() -> str:
    total = 0
    for index in range(IDLE_LOOPS):
        total += index
    if total < 0:
        raise RuntimeError("idle")
    return "The loop added the integers from 0 through 115999."


def _wait_for_load() -> Dict[str, Any]:
    started = time.monotonic()
    waits = 0
    while True:
        load = _load()
        elapsed = time.monotonic() - started
        if not load or load[0] <= LOAD_LIMIT or elapsed >= LOAD_WAIT_S:
            return {
                "waited_s": round(elapsed, 1),
                "waits": waits,
                "load": load,
                "gave_up": bool(load) and load[0] > LOAD_LIMIT,
            }
        time.sleep(30)
        waits += 1


def _row_from_samples(
    cpu_s: Sequence[float],
    wall_s: Sequence[float],
    *,
    evidence: str,
    error: str = "",
) -> Dict[str, Any]:
    judged_cpu = list(cpu_s)[1:] if len(cpu_s) > 1 else list(cpu_s)
    judged_wall = list(wall_s)[1:] if len(wall_s) > 1 else list(wall_s)
    return {
        "n": len(cpu_s),
        "judged": len(judged_cpu),
        "warmup_dropped": 1 if len(cpu_s) > 1 else 0,
        "clock": "cpu",
        "p50_ms": round(_p(judged_cpu, 0.50) * 1000.0, 3) if judged_cpu else None,
        "p95_ms": round(_p(judged_cpu, 0.95) * 1000.0, 3) if judged_cpu else None,
        "wall_p50_ms": round(_p(judged_wall, 0.50) * 1000.0, 3) if judged_wall else None,
        "wall_p95_ms": round(_p(judged_wall, 0.95) * 1000.0, 3) if judged_wall else None,
        "load": _load(),
        "samples_ms": [round(value * 1000.0, 3) for value in cpu_s],
        "wall_samples_ms": [round(value * 1000.0, 3) for value in wall_s],
        "evidence": evidence,
        "error": error,
    }


def _time(fn: Callable[[], str], prepare: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
    cpu: List[float] = []
    wall: List[float] = []
    evidence = ""
    error = ""
    for _index in range(RUNS):
        if prepare is not None:
            prepare()
        gc.collect()
        cpu0 = time.process_time()
        wall0 = time.perf_counter()
        try:
            evidence = fn() or evidence
        except Exception:
            cpu.append(max(0.0, time.process_time() - cpu0))
            wall.append(max(0.0, time.perf_counter() - wall0))
            error = traceback.format_exc()
            break
        cpu.append(max(0.0, time.process_time() - cpu0))
        wall.append(max(0.0, time.perf_counter() - wall0))
    return _row_from_samples(cpu, wall, evidence=evidence, error=error)


def _judge(row: Dict[str, Any], budget_ms: Optional[float]) -> None:
    row["budget_ms"] = budget_ms
    if budget_ms is None:
        row["pass"] = None
        return
    if row.get("error") or row.get("p95_ms") is None:
        row["pass"] = False
        return
    row["pass"] = bool(float(row["p95_ms"]) <= budget_ms)


def _profile(results: Path, name: str, fn: Callable[[], str], prepare: Optional[Callable[[], None]] = None) -> str:
    import cProfile
    import io
    import pstats

    profiler = cProfile.Profile()
    for _index in range(8):
        if prepare is not None:
            prepare()
        gc.collect()
        profiler.enable()
        try:
            fn()
        finally:
            profiler.disable()
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer)
    stats.sort_stats("cumulative").print_stats(40)
    text = buffer.getvalue()
    results.mkdir(parents=True, exist_ok=True)
    (results / ("profile_%s.txt" % name)).write_text(text, encoding="utf-8")
    return _top_frame(text)


def _top_frame(text: str) -> str:
    seen = False
    first = ""
    app_frame = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("ncalls"):
            seen = True
            continue
        if not seen or not stripped:
            continue
        if not first:
            first = stripped
        if "/app/" in stripped or stripped.startswith("app/"):
            app_frame = stripped
            break
    return app_frame or first


def give_twenty_lines(path: str) -> None:
    """Move 16 lines onto invoice 1 and 16 onto invoice 2.

    The reference build stores 4 lines on every invoice. The speed rows time
    a record with 20 lines. The table still holds 400,000 lines.
    """

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        stolen = [int(row[0]) for row in connection.execute("SELECT id FROM invoice_lines ORDER BY id DESC LIMIT 32")]
        if len(stolen) != 32:
            raise RuntimeError("the reference database has %d lines to move" % len(stolen))
        assignments = []
        for offset, line_id in enumerate(stolen):
            invoice_id = 1 if offset < 16 else 2
            line_no = 5 + (offset % 16)
            assignments.append((invoice_id, line_no, line_id))
        connection.executemany(
            "UPDATE invoice_lines SET invoice_id = ?, line_no = ? WHERE id = ?",
            assignments,
        )
        connection.commit()
        counts = {
            int(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT invoice_id, count(*) FROM invoice_lines WHERE invoice_id IN (1, 2) GROUP BY invoice_id"
            )
        }
        total = int(connection.execute("SELECT count(*) FROM invoice_lines").fetchone()[0])
    finally:
        connection.close()
    if counts.get(1) != 20 or counts.get(2) != 20 or total != 400000:
        raise RuntimeError("line counts after the move: %s total %s" % (counts, total))


def reference_counts(path: str) -> Dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        def one(sql: str) -> int:
            row = connection.execute(sql).fetchone()
            return 0 if row is None or row[0] is None else int(row[0])

        return {
            "customers": one("SELECT count(*) FROM customers"),
            "products": one("SELECT count(*) FROM products"),
            "invoices": one("SELECT count(*) FROM invoices"),
            "lines": one("SELECT count(*) FROM invoice_lines"),
            "invoice_1_lines": one("SELECT count(*) FROM invoice_lines WHERE invoice_id = 1"),
            "invoice_2_lines": one("SELECT count(*) FROM invoice_lines WHERE invoice_id = 2"),
        }
    finally:
        connection.close()


def ensure_reference(path: Path) -> Dict[str, int]:
    from tests.form_builder.fixtures.m8.make_shop import build

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        build(str(path), reference=True)
        give_twenty_lines(str(path))
    counts = reference_counts(str(path))
    expected = {
        "customers": 2000,
        "products": 5000,
        "invoices": 100000,
        "lines": 400000,
        "invoice_1_lines": 20,
        "invoice_2_lines": 20,
    }
    if counts != expected:
        path.unlink()
        build(str(path), reference=True)
        give_twenty_lines(str(path))
        counts = reference_counts(str(path))
    if counts != expected:
        raise RuntimeError("reference counts %s" % counts)
    return counts


def parse_dsn(text: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for part in text.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        found[key] = value
    return found


LAST_DRIVER = ""


def _connect_postgres(fields: Dict[str, str]) -> Any:
    global LAST_DRIVER
    password = fields.get("password") or ""
    host = fields.get("host") or "127.0.0.1"
    port = int(fields.get("port") or "5432")
    database = fields.get("dbname") or fields.get("database") or "shop"
    user = fields.get("user") or "postgres"
    try:
        import psycopg  # pyright: ignore[reportMissingImports]
    except ImportError:
        psycopg = None
    if psycopg is not None:
        connection = psycopg.connect(host=host, port=port, dbname=database, user=user, password=password)
        connection.autocommit = False
        LAST_DRIVER = "psycopg"
        return connection
    import pg8000.dbapi as pg8000  # pyright: ignore[reportMissingImports]

    LAST_DRIVER = "pg8000"
    return pg8000.connect(user=user, host=host, database=database, port=port, password=password)


def load_postgres(sqlite_path: str, fields: Dict[str, str]) -> Dict[str, Any]:
    """Copy the reference rows into PostgreSQL and add empty tables through 30."""

    connection = _connect_postgres(fields)
    cursor = connection.cursor()
    try:
        ready = _postgres_ready(cursor)
        if ready is not None:
            return ready
        connection.rollback()
        cursor = connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS invoice_lines")
        cursor.execute("DROP TABLE IF EXISTS invoices")
        cursor.execute("DROP TABLE IF EXISTS products")
        cursor.execute("DROP TABLE IF EXISTS customers")
        for index in range(26):
            cursor.execute("DROP TABLE IF EXISTS extra_%02d" % index)
        cursor.execute(
            "CREATE TABLE customers ("
            "id serial PRIMARY KEY, name text NOT NULL, phone text, city text, email text UNIQUE)"
        )
        cursor.execute(
            "CREATE TABLE products (id serial PRIMARY KEY, name text NOT NULL, price numeric NOT NULL)"
        )
        cursor.execute(
            "CREATE TABLE invoices ("
            "id serial PRIMARY KEY, invoice_no text NOT NULL UNIQUE, "
            "customer_id integer NOT NULL REFERENCES customers(id), "
            "invoice_date text, notes text, total numeric)"
        )
        cursor.execute(
            "CREATE TABLE invoice_lines ("
            "id serial PRIMARY KEY, invoice_id integer NOT NULL REFERENCES invoices(id), "
            "line_no integer NOT NULL, product_id integer REFERENCES products(id), "
            "description text, qty integer NOT NULL, price numeric NOT NULL, "
            "UNIQUE (invoice_id, line_no))"
        )
        for index in range(26):
            cursor.execute("CREATE TABLE extra_%02d (id integer PRIMARY KEY, name text)" % index)
        source = sqlite3.connect(sqlite_path)
        try:
            _copy_table(
                source,
                cursor,
                "SELECT id, name, phone, city, email FROM customers ORDER BY id",
                "INSERT INTO customers (id, name, phone, city, email) VALUES (%s, %s, %s, %s, %s)",
            )
            _copy_table(
                source,
                cursor,
                "SELECT id, name, price FROM products ORDER BY id",
                "INSERT INTO products (id, name, price) VALUES (%s, %s, %s)",
            )
            _copy_table(
                source,
                cursor,
                "SELECT id, invoice_no, customer_id, invoice_date, notes, total FROM invoices ORDER BY id",
                "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
            )
            _copy_table(
                source,
                cursor,
                "SELECT id, invoice_id, line_no, product_id, description, qty, price FROM invoice_lines ORDER BY id",
                "INSERT INTO invoice_lines (id, invoice_id, line_no, product_id, description, qty, price) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            )
        finally:
            source.close()
        for table in ("customers", "products", "invoices", "invoice_lines"):
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('%s', 'id'), (SELECT max(id) FROM %s))" % (table, table)
            )
        connection.commit()
        cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
        tables = int(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM invoice_lines WHERE invoice_id = 1")
        lines = int(cursor.fetchone()[0])
    finally:
        connection.close()
    return {"tables": tables, "invoice_1_lines": lines, "driver": LAST_DRIVER}


def _postgres_ready(cursor: Any) -> Optional[Dict[str, Any]]:
    try:
        counts = {}
        for name in ("customers", "products", "invoices", "invoice_lines"):
            cursor.execute("SELECT count(*) FROM %s" % name)
            counts[name] = int(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM invoice_lines WHERE invoice_id = 1")
        lines = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
        tables = int(cursor.fetchone()[0])
    except Exception:
        return None
    if counts != {"customers": 2000, "products": 5000, "invoices": 100000, "invoice_lines": 400000}:
        return None
    if lines != 20 or tables < 30:
        return None
    return {"tables": tables, "invoice_1_lines": lines, "driver": LAST_DRIVER, "reused": True}


def _copy_table(source: sqlite3.Connection, cursor: Any, select: str, insert: str) -> None:
    batch: List[Tuple[Any, ...]] = []
    for row in source.execute(select):
        batch.append(tuple(row))
        if len(batch) >= 5000:
            cursor.executemany(insert, batch)
            batch = []
    if batch:
        cursor.executemany(insert, batch)


def _postgres_schema(sqlite_schema: Any) -> Any:
    from app.features.form_builder.engine.data.schema import Schema

    return Schema(
        sqlite_schema.connection,
        "postgres",
        "PostgreSQL 9.3",
        sqlite_schema.read_at,
        "pg8000",
        tuple(sqlite_schema.tables),
    )


def _save_schema(root: Path, schema: Any) -> None:
    from app.features.form_builder.engine.data.schema import write_schema
    from app.features.form_builder.engine.data.schema_cache import install_schema_reader

    folder = root / "cbcs" / "schema"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "shop.json").write_text(write_schema(schema), encoding="utf-8")
    install_schema_reader(str(root))


def _project(root: Path, connection: Any, schema: Any) -> None:
    from app.features.form_builder.engine.data.connections import ConnectionSet, save_connections
    from app.features.form_builder.engine.data.connections_module import render_connections_module
    from app.features.form_builder.engine.project.from_table_plan import (
        TableRequest,
        choice_for,
        include_column,
    )
    from app.features.form_builder.engine.project.start_screen import screen_for, write_start_entry
    from app.features.form_builder.engine.ui4.reader import read_ui
    from app.features.form_builder.qtside.dialogs.table_apply import render_plans

    root.mkdir(parents=True, exist_ok=True)
    (root / "forms").mkdir(exist_ok=True)
    (root / "cbcs").mkdir(exist_ok=True)
    save_connections(str(root), ConnectionSet((connection,)))
    (root / "cbcs_connections.py").write_text(
        render_connections_module(ConnectionSet((connection,)), project_slug="m8r"),
        encoding="utf-8",
    )
    _save_schema(root, schema)
    table = next(item for item in schema.tables if item.name == "invoices")
    columns = tuple(
        choice_for(column, schema.engine or "sqlite")
        for column in table.columns
        if include_column(column, table.key or "", schema.engine or "sqlite")
    )
    request = TableRequest("shop", "invoices", columns, "both", "invoice_lines", "invoice", "yyyy-MM-dd")
    customers = next(item for item in schema.tables if item.name == "customers")
    customer_columns = tuple(
        choice_for(column, schema.engine or "sqlite")
        for column in customers.columns
        if include_column(column, customers.key or "", schema.engine or "sqlite")
    )
    customer_request = TableRequest(
        "shop", "customers", customer_columns, "list", "", "customer_list", "yyyy-MM-dd"
    )
    texts = render_plans(request, schema, str(root)) + render_plans(customer_request, schema, str(root))
    if len(texts) < 3:
        raise RuntimeError("form from a table wrote %d files" % len(texts))
    _write_generated(root, texts)
    screen = screen_for("invoice", "both")
    write_start_entry(str(root), screen.module, screen.class_name)


def _write_generated(root: Path, texts: Sequence[Tuple[str, str]]) -> None:
    from app.features.form_builder.engine.codegen.api import generate_form_module
    from app.features.form_builder.engine.codegen.window_template import render_window_class
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.ui4.reader import read_ui

    forms = root / "forms"
    (forms / "__init__.py").write_text("", encoding="utf-8")
    for stem, text in texts:
        ui_path = forms / ("%s.ui" % stem)
        ui_path.write_text(text, encoding="utf-8")
        read = read_ui(text, allocator=IdAllocator())
        scope = FormScope(
            kind="project",
            ui_path=str(ui_path),
            project_root=str(root),
            generated_path=str(forms / ("ui_%s.py" % stem)),
            window_path=str(forms / ("%s_window.py" % stem)),
            module_name="forms.ui_%s" % stem,
        )
        result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
        if result.text is None:
            raise RuntimeError("%s did not generate. %s" % (stem, [(item.code, item.message) for item in result.diagnostics]))
        (forms / ("ui_%s.py" % stem)).write_text(result.text, encoding="utf-8")
        (forms / ("%s_window.py" % stem)).write_text(render_window_class(read.document, scope=scope), encoding="utf-8")


def _load_module(path: Path, name: str) -> Any:
    import importlib.util as importlib_util

    spec = importlib_util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("can't load %s" % path)
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ui_class(module: Any) -> Any:
    names = [name for name in dir(module) if name.startswith("Ui_")]
    if len(names) != 1:
        raise RuntimeError("ui classes %s" % names)
    return getattr(module, names[0])


class _Host:
    def __init__(self, root: Path, stem: str, password: str) -> None:
        self.root = root
        self.stem = stem
        self.password = password
        self.widget: Any = None
        self.ui: Any = None
        self._previous: Any = None

    def open(self) -> Any:
        from app.qt.QtWidgets import QApplication, QDialog

        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        self._previous = sys.modules.get("cbcs_connections")
        connections = _load_module(self.root / "cbcs_connections.py", "cbcs_connections_m8r_%s" % self.stem)
        if self.password:
            connections.set_password("shop", self.password)
        sys.modules["cbcs_connections"] = connections
        module = _load_module(self.root / "forms" / ("ui_%s.py" % self.stem), "ui_m8r_%s" % self.stem)
        app = QApplication.instance() or QApplication([])

        class Host(QDialog):
            def __init__(self, ui_type: Any) -> None:
                super().__init__()
                self.ui = ui_type()
                self.ui.setupUi(self)

        host = Host(_ui_class(module))
        host.resize(960, 640)
        host.show()
        app.processEvents()
        self.widget = host
        self.ui = host.ui
        return host.ui

    def close(self) -> None:
        connections = sys.modules.get("cbcs_connections")
        closer = getattr(connections, "close_all", None)
        if callable(closer):
            closer()
        if self._previous is None:
            sys.modules.pop("cbcs_connections", None)
        else:
            sys.modules["cbcs_connections"] = self._previous
        if self.widget is not None:
            self.widget.close()
            self.widget.deleteLater()
            self.widget = None


def _line_count(ui: Any) -> int:
    view = getattr(ui, "invoice_linesView", None)
    if view is None:
        raise RuntimeError("the invoice form has no invoice_linesView")
    model = view.model()
    if model is None:
        return 0
    return int(model.rowCount())


def _product_lookup_count(ui: Any) -> int:
    found = getattr(ui, "_cbcs_line_lookup", {}) or {}
    return len(found.get("product_id", ()))


def measure_bound(ui: Any, *, postgres: bool) -> Dict[str, Dict[str, Any]]:
    prefix = "pg_" if postgres else ""
    key_index = {"value": 0}

    def open_form() -> str:
        ui.cbcs_open(1)
        keys = len(getattr(ui, "_cbcs_keys", ()) or ())
        lines = _line_count(ui)
        customers = int(ui.customer_id.count())
        products = _product_lookup_count(ui)
        if keys != 100000 or lines != 20 or customers < 2000 or products < 5000:
            raise RuntimeError(
                "open keys=%s lines=%s customers=%s products=%s" % (keys, lines, customers, products)
            )
        keys_list = list(ui._cbcs_keys)
        key_index["value"] = keys_list.index(2)
        return "keys=%d lines=%d customers=%d products=%d" % (keys, lines, customers, products)

    def show_other() -> str:
        ui._cbcs_show(key_index["value"])
        lines = _line_count(ui)
        if lines != 20:
            raise RuntimeError("show lines=%s" % lines)
        return "lines=%d key=%s" % (lines, getattr(ui, "_cbcs_key", None))

    def prepare_show() -> None:
        ui._cbcs_show(0)

    stamp = {"n": 0}

    def prepare_dirty() -> None:
        stamp["n"] += 1
        ui.notes.setText("note %d" % stamp["n"])

    def dirty() -> str:
        flag = ui._cbcs_is_dirty()
        if flag is not True:
            raise RuntimeError("dirty returned %r" % (flag,))
        return "dirty"

    def save() -> str:
        saved = ui.cbcs_save()
        if saved is not True:
            raise RuntimeError("save returned %r" % (saved,))
        if _line_count(ui) != 20:
            raise RuntimeError("save left %s lines" % _line_count(ui))
        return "saved lines=20"

    def lookup() -> str:
        ui.cbcs_load_lookups("customer_id")
        count = int(ui.customer_id.count())
        if count < 2000:
            raise RuntimeError("lookup count %s" % count)
        return "customers=%d" % count

    rows = {
        prefix + "open_form": _time(open_form),
        prefix + "show_record": _time(show_other, prepare_show),
        prefix + "dirty_check": _time(dirty, prepare_dirty),
        prefix + "save_record": _time(save, prepare_dirty),
        prefix + "load_lookup": _time(lookup),
    }
    return rows


def measure_list(ui: Any, *, postgres: bool) -> Dict[str, Any]:
    def search() -> str:
        ui.cbcs_refresh_list()
        model = ui.resultTable.model()
        rows = 0 if model is None else int(model.rowCount())
        if rows < 1 or rows > 500:
            raise RuntimeError("list rows=%s" % rows)
        return "rows=%d" % rows

    def prepare() -> None:
        ui.searchEdit.setText("Customer 1")

    row = _time(search, prepare)
    key = "pg_list_search" if postgres else "list_search"
    return {key: row}


def measure_data_tab() -> Dict[str, Any]:
    from app.features.form_builder.engine.data.schema import Column, Schema, Table, set_schema_reader
    from app.features.form_builder.engine.data.source import RecordSource, write_data
    from app.features.form_builder.engine.ui4.values import StringValue
    from app.features.form_builder.qtside.data_panel.panel import DataPanel
    from app.qt.QtWidgets import QApplication, QWidget

    columns = tuple(Column("c%02d" % index, "text", True) for index in range(40))
    schema = Schema(
        "shop",
        "sqlite",
        "SQLite",
        "2026-11-04T00:00:00",
        "sqlite3",
        (Table("wide", columns, key="c00"),),
    )
    set_schema_reader(lambda _doc, _name: schema)

    class _Entry:
        def __init__(self, text: str) -> None:
            self.value = StringValue(text)

    class _Root:
        def prop(self, name: str) -> Any:
            if name == "cbcsData":
                return _Entry(write_data(RecordSource("shop", "wide", "c00")))
            return None

    class _Doc:
        root = _Root()

    class _Session:
        document = _Doc()

    class _Workbench(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.session = _Session()
            self.project_root = ""

    app = QApplication.instance() or QApplication([])
    workbench = _Workbench()
    panel = DataPanel(workbench)
    panel.show()
    app.processEvents()
    widget = panel.findChild(QWidget, "formBuilder.data.columns")
    if widget is None:
        set_schema_reader(None)
        raise RuntimeError("the data tab has no column list")

    def fill() -> str:
        widget.refresh()
        found = [
            item
            for item in widget.findChildren(QWidget, "formBuilder.data.columnRow")
            if not item.isHidden()
        ]
        count = len(found)
        if count != 40:
            raise RuntimeError("column rows %s" % count)
        return "columns=%d" % count

    try:
        return {"data_tab": _time(fill)}
    finally:
        panel.close()
        workbench.close()
        set_schema_reader(None)


def responsive_during_refresh(project_root: str, *, pause_s: float = 0.0) -> Dict[str, Any]:
    """The UI thread handles an event while a schema refresh is still in flight."""

    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
    from app.features.form_builder.engine.data.schema_cache import read_sqlite_file as _unused
    from app.features.form_builder.engine.data.source import RecordSource, write_data
    from app.features.form_builder.engine.ui4.values import StringValue
    from app.features.form_builder.qtside.data_panel.panel import DataPanel
    from app.qt.QtCore import QTimer
    from app.qt.QtWidgets import QApplication, QWidget

    del _unused
    root = Path(project_root)
    database = root / "data" / "shop.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    if not database.is_file():
        connection = sqlite3.connect(str(database))
        connection.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO customers (id, name) VALUES (1, 'Acme')")
        connection.commit()
        connection.close()
    save_connections(str(root), ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),)))
    if pause_s > 0:
        import app.features.form_builder.engine.data.schema_cache as cache

        original = cache.read_sqlite_file

        def slow(path: str, name: str, *, read_at: str) -> Any:
            time.sleep(pause_s)
            return original(path, name, read_at=read_at)

        cache.read_sqlite_file = slow  # type: ignore[assignment]
    else:
        original = None

    class _Entry:
        def __init__(self, text: str) -> None:
            self.value = StringValue(text)

    class _Root:
        def prop(self, name: str) -> Any:
            if name == "cbcsData":
                return _Entry(write_data(RecordSource("shop", "customers", "id")))
            return None

    class _Doc:
        root = _Root()

    class _Session:
        document = _Doc()

    class _Workbench(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.session = _Session()
            self.project_root = str(root)

    app = QApplication.instance() or QApplication([])
    workbench = _Workbench()
    panel = DataPanel(workbench)
    button = panel.findChild(QWidget, "formBuilder.data.schemaRefresh")
    footer = panel.findChild(QWidget, "formBuilder.data.schemaFooter")
    if button is None or footer is None:
        raise RuntimeError("the data tab has no refresh footer")
    seen = {"during": False}

    def mark() -> None:
        worker = getattr(footer, "_worker", None)
        running = worker is not None and bool(worker.isRunning())
        if running and bool(getattr(footer, "_busy", False)):
            seen["during"] = True

    try:
        QTimer.singleShot(0, mark)
        button.click()  # type: ignore[attr-defined]
        started = time.monotonic()
        while time.monotonic() - started < 5.0:
            app.processEvents()
            mark()
            worker = getattr(footer, "_worker", None)
            if seen["during"] and (worker is None or not worker.isRunning()):
                break
            if worker is None and not bool(getattr(footer, "_busy", False)) and seen["during"]:
                break
        sentence = ""
        label = panel.findChild(QWidget, "formBuilder.data.schemaSentence")
        if label is not None and hasattr(label, "text"):
            sentence = str(label.text())
        return {
            "ui_thread_ran_during_refresh": seen["during"],
            "sentence": sentence,
            "pause_s": pause_s,
        }
    finally:
        if original is not None:
            import app.features.form_builder.engine.data.schema_cache as cache

            cache.read_sqlite_file = original  # type: ignore[assignment]
        panel.close()
        workbench.close()


def measure_helper(root: Path, connection: Any, password: str, minimum: int = 30) -> Dict[str, Any]:
    from app.features.form_builder.engine.data.schema_cache import install_schema_services, refresh
    from app.features.form_builder.qtside.schema_runner import register_schema_runner

    install_schema_services(str(root), "m8r")
    register_schema_runner()

    def ask(_connection: Any) -> str:
        return password

    def once() -> str:
        outcome = refresh(str(root), connection, ask)
        if not getattr(outcome, "ok", False):
            raise RuntimeError("%s %s" % (getattr(outcome, "kind", ""), getattr(outcome, "reason", "")))
        schema = getattr(outcome, "schema", None)
        tables = 0 if schema is None else len(getattr(schema, "tables", ()) or ())
        if tables < minimum:
            raise RuntimeError("helper read %s tables" % tables)
        return "tables=%d" % tables

    from app.features.form_builder.qtside.schema_runner import helper_command

    row = _time(once)
    command = helper_command()
    row["command0"] = command[0] if command else ""
    row["helper_script"] = "run_schema_helper.py" if any("run_schema_helper.py" in part for part in command) else ""
    return {"schema_helper_30": row}


def _sqlite_connection() -> Any:
    from app.features.form_builder.engine.data.connections import Connection

    return Connection("shop", "Shop database", "sqlite", file="data/shop.db")


def _postgres_connection(fields: Dict[str, str]) -> Any:
    from app.features.form_builder.engine.data.connections import Connection

    port = int(fields.get("port") or "5432")
    policy = "none" if not (fields.get("password") or "") else "ask"
    return Connection(
        "shop",
        "Shop database",
        "postgres",
        host=fields.get("host") or "127.0.0.1",
        port=None if port == 5432 else port,
        database=fields.get("dbname") or fields.get("database") or "shop",
        user=fields.get("user") or "postgres",
        password=policy,
    )


def build_sqlite_project(root: Path, database: Path) -> None:
    from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file

    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-04T00:00:00")
    _project(root, _sqlite_connection(), schema)


def build_postgres_project(root: Path, schema: Any, fields: Dict[str, str]) -> None:
    _project(root, _postgres_connection(fields), _postgres_schema(schema))


def run(machine: str, results: Path, dsn: str, work: Path) -> Dict[str, Any]:
    from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file

    results.mkdir(parents=True, exist_ok=True)
    waited = _wait_for_load()
    sqlite_root = work / "sqlite_proj"
    database = sqlite_root / "data" / "shop.db"
    counts = ensure_reference(database)
    build_sqlite_project(sqlite_root, database)
    summary: Dict[str, Any] = {
        "machine": machine,
        "python": sys.version.split()[0],
        "load_wait": waited,
        "reference": counts,
        "rows": {},
        "recorded": {},
        "errors": [],
    }
    summary["idle_reference"] = _time(_idle)
    fields = parse_dsn(dsn) if dsn else {}
    password = fields.get("password") or ""
    try:
        summary["rows"].update(measure_data_tab())
    except Exception:
        summary["rows"]["data_tab"] = _failed(traceback.format_exc())
    invoice = _Host(sqlite_root, "invoice", "")
    listing = _Host(sqlite_root, "customer_list", "")
    try:
        invoice.open()
        summary["rows"].update(measure_bound(invoice.ui, postgres=False))
        _judge_rows(summary["rows"], budgets_for(machine))
        _profile_open_rows(results, summary, invoice.ui, postgres=False, machine=machine)
    except Exception:
        summary["errors"].append(traceback.format_exc())
    finally:
        invoice.close()
    try:
        listing.open()
        summary["rows"].update(measure_list(listing.ui, postgres=False))
        _judge_rows(summary["rows"], budgets_for(machine))
        if _should_profile(results, machine, "list_search", summary["rows"].get("list_search", {})):
            summary.setdefault("profiles", {})["list_search"] = _profile(
                results,
                "list_search",
                lambda: listing.ui.cbcs_refresh_list() or "list",
                lambda: listing.ui.searchEdit.setText("Customer 1"),
            )
    except Exception:
        summary["rows"]["list_search"] = _failed(traceback.format_exc())
    finally:
        listing.close()
    try:
        summary["responsive"] = responsive_during_refresh(str(work / "responsive"), pause_s=0.0)
        real = responsive_during_refresh(str(sqlite_root), pause_s=0.0)
        summary["responsive_reference"] = real
    except Exception:
        summary["responsive"] = {"error": traceback.format_exc(), "ui_thread_ran_during_refresh": False}
    if dsn:
        try:
            summary["postgres_load"] = load_postgres(str(database), fields)
            schema = read_sqlite_file(str(database), "shop", read_at="2026-11-04T00:00:00")
            pg_root = work / "pg_proj"
            build_postgres_project(pg_root, schema, fields)
            pg_invoice = _Host(pg_root, "invoice", password)
            pg_list = _Host(pg_root, "customer_list", password)
            try:
                pg_invoice.open()
                summary["recorded"].update(measure_bound(pg_invoice.ui, postgres=True))
            finally:
                pg_invoice.close()
            try:
                pg_list.open()
                summary["recorded"].update(measure_list(pg_list.ui, postgres=True))
            finally:
                pg_list.close()
            summary["recorded"].update(measure_helper(pg_root, _postgres_connection(fields), password))
        except Exception:
            summary["recorded"]["postgres"] = _failed(traceback.format_exc())
    else:
        summary["recorded"]["postgres"] = {"error": "no DSN", "pass": None}
    table = budgets_for(machine)
    _judge_rows(summary["rows"], table)
    for key, row in list(summary.get("recorded", {}).items()):
        if isinstance(row, dict) and "p95_ms" in row:
            _judge(row, None)
    (results / ("summary_%s.json" % machine)).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def _judge_rows(rows: Dict[str, Any], table: Dict[str, float]) -> None:
    for key, row in rows.items():
        if not isinstance(row, dict):
            continue
        _judge(row, table.get(key))


def _should_profile(results: Path, machine: str, key: str, row: Dict[str, Any]) -> bool:
    if row.get("pass") is not False or row.get("error"):
        return False
    if machine != "vm":
        return True
    mac_path = results / "summary_mac.json"
    if not mac_path.is_file():
        return True
    mac = json.loads(mac_path.read_text(encoding="utf-8"))
    mac_row = mac.get("rows", {}).get(key, {})
    return mac_row.get("pass") is True


def _profile_open_rows(results: Path, summary: Dict[str, Any], ui: Any, *, postgres: bool, machine: str) -> None:
    prefix = "pg_" if postgres else ""
    rows = summary["rows"]
    calls = {
        prefix + "open_form": (lambda: ui.cbcs_open(1) or "open", None),
        prefix + "show_record": (lambda: ui._cbcs_show(ui._cbcs_keys.index(2)) or "show", lambda: ui._cbcs_show(0)),
        prefix + "dirty_check": (lambda: "dirty" if ui._cbcs_is_dirty() else "clean", lambda: ui.notes.setText("profile")),
        prefix + "save_record": (lambda: "saved" if ui.cbcs_save() else "unsaved", lambda: ui.notes.setText("profile-save")),
        prefix + "load_lookup": (lambda: ui.cbcs_load_lookups("customer_id") or "lookup", None),
    }
    profiles = summary.setdefault("profiles", {})
    for key, (fn, prepare) in calls.items():
        if not _should_profile(results, machine, key, rows.get(key, {})):
            continue
        profiles[key] = _profile(results, "%s_%s" % (machine, key), fn, prepare)


def _failed(text: str) -> Dict[str, Any]:
    return {
        "n": 0,
        "judged": 0,
        "p50_ms": None,
        "p95_ms": None,
        "wall_p95_ms": None,
        "load": _load(),
        "evidence": "",
        "error": text,
        "pass": False,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine", default="mac")
    parser.add_argument("--dsn", default=os.environ.get("CBCS_PG93_DSN", ""))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--work", default="")
    args = parser.parse_args(list(argv) if argv is not None else None)
    work = Path(args.work) if args.work else Path(os.environ.get("TMPDIR", "/tmp")) / "m8r_speed"
    try:
        run(args.machine, Path(args.results), args.dsn, work)
    except Exception:
        path = Path(args.results)
        path.mkdir(parents=True, exist_ok=True)
        (path / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
