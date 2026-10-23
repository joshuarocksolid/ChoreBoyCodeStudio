"""Column labels, widget names, and the date format for a table form."""

from __future__ import annotations

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.table_form import (
    TableColumn,
    build_table_form_ui,
    default_shows_as,
    four_digit_year_format,
    label_from_column,
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
