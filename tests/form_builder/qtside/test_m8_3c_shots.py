# pyright: reportAttributeAccessIssue=false
"""M8.3c list shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, Schema, Table, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import ListFilter, ListOpen, ListSource
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.data_panel.listing_page import OwnSqlDialog
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.qt.QtWidgets import QDialogButtonBox, QLabel, QWidget
from tests.form_builder.engine.test_m8_2_scenario import _xml, record_window
from tests.form_builder.qtside.test_m8_2_shots import _shoot

pytestmark = pytest.mark.unit


def test_list_screenshots(tmp_path: Path, qapp) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not raw:
        pytest.skip("set CBCS_FB_SCREENSHOT_DIR to write list screenshots")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    _data_tab(tmp_path, qapp, folder)
    _running(tmp_path, qapp, folder)
    _problem(qapp, folder)


def _data_tab(tmp_path: Path, qapp, folder: Path) -> None:
    root = tmp_path / "panel"
    forms = root / "forms"
    forms.mkdir(parents=True)
    source = ListSource(
        "shop",
        ("name", "phone", "city"),
        table="customers",
        search=("name", "phone"),
        search_field="searchEdit",
        filters=(ListFilter("statusCombo", "status"),),
        order=(("name", "asc"),),
        limit=500,
        open=ListOpen("customer", "id"),
    )
    text = _xml(
        source,
        (
            ("QLineEdit", "searchEdit", "", ""),
            ("QComboBox", "statusCombo", "", ""),
            ("QTableView", "customersView", "", ""),
        ),
    )
    ui_path = forms / "customers.ui"
    ui_path.write_text(text, encoding="utf-8")
    (forms / "customer.ui").write_text("<ui/>", encoding="utf-8")
    save_connections(str(root), ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db"),)))
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-11-02T16:00:00",
        "sqlite3",
        (
            Table(
                "customers",
                (
                    Column("id", "INTEGER", False),
                    Column("name", "TEXT", True),
                    Column("phone", "TEXT", True),
                    Column("city", "TEXT", True),
                    Column("status", "TEXT", True),
                ),
                key="id",
            ),
        ),
    )
    cache = root / "cbcs" / "schema"
    cache.mkdir(parents=True)
    (cache / "shop.json").write_text(write_schema(schema), encoding="utf-8")
    install_schema_reader(str(root))
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
    host.project_root = str(root)
    panel = DataPanel(host)
    sentence = panel.findChild(QLabel, "formBuilder.data.listSentence")
    assert sentence is not None
    assert sentence.text() == "List of customers in Shop database"
    _shoot(panel, qapp, folder, "list-data", 480, 720)
    from app.features.form_builder.engine.data.schema import set_schema_reader

    set_schema_reader(None)


def _running(tmp_path: Path, qapp, folder: Path) -> None:
    source = ListSource(
        "shop",
        ("name", "phone", "city"),
        table="customers",
        search=("name", "phone", "city"),
        search_field="searchEdit",
        filters=(ListFilter("statusCombo", "status"),),
        order=(("name", "asc"),),
        limit=500,
        open=ListOpen("customer", "id"),
    )
    ui = _xml(
        source,
        (
            ("QLineEdit", "searchEdit", "", ""),
            ("QComboBox", "statusCombo", "", ""),
            ("QTableView", "customersView", "", ""),
            ("QPushButton", "newButton", "", '     <property name="text"><string>New</string></property>\n'),
            ("QPushButton", "openButton", "", '     <property name="text"><string>Open</string></property>\n'),
        ),
    )
    with record_window(tmp_path, ui, _rows) as (host, _db):
        host.ui.searchEdit.setText("a")
        host.ui._cbcs_list_timer.timeout.emit()
        assert host.ui.limitLabel.isVisible() is True
        assert host.ui.limitLabel.text().startswith("Showing the first 500 of ")
        assert host.ui.newButton.text()
        assert host.ui.openButton.text()
        _shoot(host, qapp, folder, "list-running", 520, 420)


def _problem(qapp, folder: Path) -> None:
    parent = QWidget()
    dialog = OwnSqlDialog(parent, "DELETE FROM customers")
    assert dialog.findChild(QLabel, "formBuilder.data.listSqlProblem").text() == (
        "Only a single SELECT can be a list's source."
    )
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None and box.button(QDialogButtonBox.StandardButton.Ok).isEnabled() is False
    _shoot(dialog, qapp, folder, "list-sql-problem", 520, 360)
    del qapp


def _rows(root: Path) -> Path:
    folder = root / "data"
    folder.mkdir(parents=True)
    path = folder / "shop.db"
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, phone TEXT, city TEXT, status TEXT)"
        )
        rows = [
            ("C%03d" % index, "Ada %03d" % index, "555-01%02d" % (index % 100), "Austin", "open")
            for index in range(600)
        ]
        connection.executemany(
            "INSERT INTO customers (id, name, phone, city, status) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()
    return path
