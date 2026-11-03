# pyright: reportAttributeAccessIssue=false
"""List screens read rows, filter them, and open the record they point at."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import ListFilter, ListOpen, ListSource, write_data
from app.features.form_builder.engine.diagnostics import CODES
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.qt.QtWidgets import QLabel, QWidget
from tests.form_builder.engine.test_m8_2_scenario import _xml, record_window

pytestmark = pytest.mark.unit

_WINDOW = """
from PySide6.QtWidgets import QDialog

class CustomerWindow(QDialog):
    made = 0
    opened = []

    def __init__(self, parent=None):
        super().__init__(parent)
        CustomerWindow.made += 1
        self.ui = self
        self._up = False

    def cbcs_open(self, key):
        CustomerWindow.opened.append(key)

    def cbcs_new(self):
        CustomerWindow.opened.append(("new",))

    def isVisible(self):
        return self._up

    def exec(self):
        self._up = True
        self.finished.emit(0)
        return 0

    def raise_(self):
        return None

    def activateWindow(self):
        return None
"""


def test_an_empty_search_lists_a_null_name(tmp_path: Path) -> None:
    with _open(tmp_path, limit=10) as (host, db):
        names = _names(host)
        assert None in _stored_names(db)
        assert "" in names
        assert "Ann" in names
        assert _stored_names(db).count(None) == 1


def test_a_typed_search_skips_a_null_name(tmp_path: Path) -> None:
    with _open(tmp_path, limit=10) as (host, db):
        _type(host, "ann")
        assert _names(host) == ["Ann"]
        assert _stored_names(db).count(None) == 1


def test_the_cutoff_line_counts_every_match(tmp_path: Path) -> None:
    with _open(tmp_path, limit=2) as (host, _db):
        label = host.ui.limitLabel
        assert label.isVisible() is True
        assert label.text() == "Showing the first 2 of 3. Type more to narrow the list."
        assert host.ui.customersView.model().rowCount() == 2


def test_typing_waits_for_a_quiet_moment(tmp_path: Path) -> None:
    with _open(tmp_path, limit=10) as (host, _db):
        host.ui.searchEdit.setText("zzz")
        assert "Ann" in _names(host)
        host.ui._cbcs_list_timer.timeout.emit()
        assert _names(host) == []
        assert host.ui._cbcs_list_timer.interval() == 250


def test_a_blank_filter_keeps_every_status(tmp_path: Path) -> None:
    with _open(tmp_path, limit=10) as (host, _db):
        host.ui.statusCombo.addItem("")
        host.ui.statusCombo.addItem("open")
        host.ui.statusCombo.addItem("closed")
        host.ui.statusCombo.setCurrentText("")
        host.ui.cbcs_refresh_list()
        assert sorted(name for name in _names(host) if name) == ["Ann", "Bob"]
        host.ui.statusCombo.setCurrentText("closed")
        host.ui.cbcs_refresh_list()
        assert _names(host) == ["Bob"]


def test_a_price_shows_the_stored_decimal(tmp_path: Path) -> None:
    with _open(tmp_path, limit=10) as (host, db):
        _type(host, "ann")
        stored = _one(db, "SELECT price, when_on FROM customers WHERE id = 'A1'")
        assert stored == ("12.50", "2026-04-01")
        assert _cell(host, 1) == "12.50"
        assert _cell(host, 2) == "2026-04-01"


def test_a_text_key_opens_that_record(tmp_path: Path) -> None:
    with _open(tmp_path, limit=10) as (host, db):
        _install_window(db)
        _type(host, "ann")
        host.ui.customersView.selectRow(0)
        host.ui.cbcs_open_record("selected")
        from forms.customer_window import CustomerWindow  # pyright: ignore[reportMissingImports]

        assert CustomerWindow.opened == ["A1"]
        assert _one(db, "SELECT name FROM customers WHERE id = 'A1'") == ("Ann",)


def test_an_open_record_form_comes_forward(tmp_path: Path) -> None:
    with _open(tmp_path, limit=10) as (host, db):
        _install_window(db)
        host.ui.customersView.selectRow(0)
        host.ui.cbcs_open_record("selected")
        host.ui.customersView.selectRow(1)
        host.ui.cbcs_open_record("selected")
        from forms.customer_window import CustomerWindow  # pyright: ignore[reportMissingImports]

        assert CustomerWindow.made == 1
        assert len(CustomerWindow.opened) == 2


def test_own_sql_with_a_percent_returns_the_matching_rows(tmp_path: Path) -> None:
    source = _source(10, sql="SELECT id, name, price, when_on FROM customers WHERE note LIKE '%keep%'")
    with _open(tmp_path, limit=10, source=source) as (host, db):
        assert sorted(_names(host)) == ["Ann"]
        assert _one(db, "SELECT COUNT(*) FROM customers") == (3,)


def test_fb314_refuses_a_statement_that_is_not_one_select() -> None:
    document = _doc(_source(10, sql="DELETE FROM customers"))
    found = [item for item in run_checks(document) if item.code == "FB314"]
    assert [item.message for item in found] == ["Only a single SELECT can be a list's source."]
    assert found[0].message == CODES["FB314"].title


def test_fb314_reports_the_database_when_the_select_cannot_run(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    path = root / "data" / "shop.db"
    sqlite3.connect(str(path)).close()
    install_schema_reader(str(root))
    try:
        document = _doc(_source(10, sql="SELECT * FROM missing_table"))
        connections = ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),))
        found = [item for item in run_checks(document, connections) if item.code == "FB314"]
    finally:
        from app.features.form_builder.engine.data.schema import set_schema_reader

        set_schema_reader(None)
    assert len(found) == 1
    assert "missing_table" in found[0].message


def test_fb315_warns_when_the_search_box_is_not_a_line_edit() -> None:
    source = _source(10)
    source = ListSource(
        source.connection,
        source.columns,
        table=source.table,
        search=source.search,
        search_field="searchEdit",
        filters=(ListFilter("statusCombo", "status"),),
        order=source.order,
        limit=source.limit,
        open=source.open,
    )
    document = _doc(source, (("QPushButton", "searchEdit"), ("QLabel", "statusCombo")))
    found = [item.message for item in run_checks(document) if item.code == "FB315"]
    assert "searchEdit can't be used here." in found
    assert "statusCombo can't be used here." in found


def test_list_settings_are_one_undo_step(tmp_path: Path, qapp) -> None:
    del qapp
    text = _xml(_source(500), _widgets())
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "customers.ui"
    ui_path.write_text(text, encoding="utf-8")
    from app.features.form_builder.engine.project.forms import FormScope

    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(root),
        generated_path=str(forms / "ui_customers.py"),
        window_path=str(forms / "customers_window.py"),
        module_name="forms.ui_customers",
    )
    session = FormSession.open(text, path=str(ui_path), scope=scope)
    host = QWidget()
    host.session = session
    panel = DataPanel(host)
    panel.show()
    sentence = panel.findChild(QLabel, "formBuilder.data.listSentence")
    assert sentence is not None
    assert sentence.text().startswith("List of customers")
    from app.features.form_builder.qtside.data_panel.listing_edits import set_limit

    set_limit(session, _read(session), 40)
    assert _read(session).limit == 40
    assert session.log.undo() is True
    assert _read(session).limit == 500


def _open(tmp_path: Path, limit: int, source: Optional[ListSource] = None):
    chosen = source if source is not None else _source(limit)
    return record_window(tmp_path, _xml(chosen, _widgets()), _prepare)


def _source(limit: int, sql: str = "") -> ListSource:
    return ListSource(
        "shop",
        ("name", "price", "when_on"),
        table="customers",
        sql=sql,
        search=("name",),
        search_field="searchEdit",
        filters=(ListFilter("statusCombo", "status"),),
        order=(("name", "asc"),),
        limit=limit,
        open=ListOpen("customer", "id"),
    )


def _widgets() -> Tuple[Tuple[str, str, str, str], ...]:
    return (
        ("QLineEdit", "searchEdit", "", ""),
        ("QComboBox", "statusCombo", "", ""),
        ("QTableView", "customersView", "", ""),
    )


def _prepare(root: Path) -> Path:
    folder = root / "data"
    folder.mkdir(parents=True)
    path = folder / "shop.db"
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, price TEXT, when_on TEXT, note TEXT, status TEXT)"
        )
        connection.executemany(
            "INSERT INTO customers (id, name, price, when_on, note, status) VALUES (?, ?, ?, ?, ?, ?)",
            (
                ("A1", "Ann", "12.50", "2026-04-01", "keep me", "open"),
                ("A2", "Bob", "3.00", None, "drop", "closed"),
                ("A3", None, None, "2026-05-01", "also", "open"),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _install_window(db: Path) -> None:
    forms = db.parent.parent / "forms"
    (forms / "__init__.py").write_text("", encoding="utf-8")
    (forms / "customer_window.py").write_text(_WINDOW, encoding="utf-8")
    import sys

    sys.modules.pop("forms.customer_window", None)
    sys.modules.pop("forms", None)


def _type(host: Any, text: str) -> None:
    host.ui.searchEdit.setText(text)
    host.ui._cbcs_list_timer.timeout.emit()


def _names(host: Any) -> List[str]:
    model = host.ui.customersView.model()
    assert model is not None
    return [model.item(row, 0).text() for row in range(model.rowCount())]


def _cell(host: Any, column: int) -> str:
    model = host.ui.customersView.model()
    assert model is not None and model.rowCount() == 1
    return model.item(0, column).text()


def _stored_names(db: Path) -> List[Optional[str]]:
    connection = sqlite3.connect(str(db))
    try:
        return [row[0] for row in connection.execute("SELECT name FROM customers ORDER BY id")]
    finally:
        connection.close()


def _one(db: Path, sql: str) -> Optional[Tuple[Any, ...]]:
    connection = sqlite3.connect(str(db))
    try:
        return connection.execute(sql).fetchone()
    finally:
        connection.close()


def _read(session: Any) -> ListSource:
    from app.features.form_builder.engine.data.source import read_data

    text = session.document.root.prop("cbcsData").value.text
    found = read_data(text).value
    assert isinstance(found, ListSource)
    return found


class _Entry:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.value = StringValue(text)


class _Node:
    def __init__(self, name: str, class_name: str, props: tuple, node_id: int) -> None:
        self._name = name
        self.class_name = class_name
        self._props = props
        self.node_id = node_id

    def object_name(self) -> str:
        return self._name

    def prop(self, name: str):
        for entry in self._props:
            if entry.name == name:
                return entry
        return None


class _Doc:
    def __init__(self, nodes: tuple) -> None:
        self.root = nodes[0]
        self._nodes = nodes

    def iter_widgets(self):
        return iter(self._nodes)


def _doc(source: ListSource, widgets: Sequence[Tuple[str, str]] = ()) -> _Doc:
    data = _Entry("cbcsData", write_data(source))
    root = _Node("Customers", "QDialog", (data,), 1)
    nodes = [root]
    for index, (class_name, name) in enumerate(widgets, start=2):
        nodes.append(_Node(name, class_name, (), index))
    return _Doc(tuple(nodes))
