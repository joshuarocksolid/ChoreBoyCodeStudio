"""Column labels, widget names, and the date format for a table form."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.table_form import (
    TableColumn,
    build_table_form_ui,
    default_shows_as,
    four_digit_year_format,
    label_from_column,
    sqlite_columns,
    sqlite_tables,
)
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui


def test_labels_are_title_case_with_id_dropped() -> None:
    assert label_from_column("customer_id") == "Customer"
    assert label_from_column("first_name") == "First Name"
    assert label_from_column("email") == "Email"


def test_a_table_form_names_widgets_after_columns() -> None:
    columns = (
        TableColumn("customer_id", "INTEGER"),
        TableColumn("joined", "DATE"),
        TableColumn("notes", "TEXT", shows_as="QPlainTextEdit", label="Shop notes"),
    )
    assert default_shows_as("INTEGER") == "QSpinBox"
    assert default_shows_as("DATE") == "QDateEdit"
    built = build_table_form_ui("Customer", columns, date_format="M/d/yy")
    assert built.first_widget == "customer_id"
    assert 'name="customer_id"' in built.text
    assert 'name="joined"' in built.text
    assert "label_2" not in built.text
    assert "Shop notes" in built.text
    assert "M/d/yyyy" in built.text
    assert "M/d/yy<" not in built.text
    document = read_ui(built.text, allocator=IdAllocator()).document
    assert write_ui(document).text == built.text


def test_a_short_year_becomes_four_digits() -> None:
    assert four_digit_year_format("M/d/yy") == "M/d/yyyy"
    assert four_digit_year_format("yyyy-MM-dd") == "yyyy-MM-dd"


def test_spin_boxes_use_the_full_numeric_range() -> None:
    columns = (
        TableColumn("qty", "INTEGER"),
        TableColumn("price", "REAL"),
    )
    built = build_table_form_ui("Order", columns)
    assert "-2147483647" in built.text
    assert "2147483647" in built.text
    assert 'name="decimals"' in built.text
    assert "-1000000000000.000000000000000" in built.text
    assert "1000000000000.000000000000000" in built.text


def test_reading_sqlite_does_not_create_the_file_or_a_journal(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    try:
        sqlite_tables(str(missing))
    except sqlite3.Error:
        pass
    assert not missing.exists()
    path = tmp_path / "shop.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("create table customer (customer_id integer primary key, name text)")
    connection.commit()
    connection.close()
    before = {item.name for item in tmp_path.iterdir()}
    columns = sqlite_columns(str(path), "customer")
    by_name = {column.name: column for column in columns}
    assert by_name["customer_id"].primary_key is True
    assert by_name["name"].primary_key is False
    assert sqlite_tables(str(path)) == ("customer",)
    assert {item.name for item in tmp_path.iterdir()} == before
