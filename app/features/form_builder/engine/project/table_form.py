"""Build an unbound form from a SQLite table (UX-TABLE-001, UX-TABLE-002).

Labels are title case with a trailing ``_id`` removed. Field widgets use the
column name. The ``.ui`` text is writer-canonical.
"""

from __future__ import annotations

import keyword
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.project.form_xml import (
    form_document,
    form_row,
    string_property,
    tabstop_block,
)

SHOWS_AS_CHOICES: Tuple[str, ...] = (
    "QLineEdit",
    "QPlainTextEdit",
    "QSpinBox",
    "QDoubleSpinBox",
    "QCheckBox",
    "QDateEdit",
    "QDateTimeEdit",
    "QComboBox",
)

_INTEGER = frozenset({"INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT"})
_REAL = frozenset({"REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL"})
_DATE = frozenset({"DATE"})
_DATETIME = frozenset({"DATETIME", "TIMESTAMP"})
_BOOL = frozenset({"BOOL", "BOOLEAN"})
_DATE_WIDGETS = frozenset({"QDateEdit", "QDateTimeEdit"})


@dataclass(frozen=True)
class TableColumn:
    """One mapping row. ``None`` label or shows-as means "use the default"."""

    name: str
    sql_type: str
    include: bool = True
    shows_as: Optional[str] = None
    label: Optional[str] = None

    def widget_class(self) -> str:
        chosen = self.shows_as or default_shows_as(self.sql_type)
        if chosen not in SHOWS_AS_CHOICES:
            return "QLineEdit"
        return chosen

    def field_label(self) -> str:
        if self.label is None:
            return label_from_column(self.name)
        return self.label


@dataclass(frozen=True)
class BuiltTableForm:
    text: str
    first_widget: Optional[str]


def label_from_column(name: str) -> str:
    """``customer_id`` becomes ``Customer``. ``first_name`` becomes ``First Name``."""
    raw = name.strip()
    stem = raw
    if stem.lower().endswith("_id"):
        stem = stem[:-3]
    parts = [part for part in re.split(r"[_\s]+", stem) if part]
    if not parts:
        parts = [part for part in re.split(r"[_\s]+", raw) if part]
    words = []
    for part in parts:
        words.append(part[:1].upper() + part[1:])
    return " ".join(words)


def default_shows_as(sql_type: str) -> str:
    """SQLite declared type to a Qt field class. Blank types become a line edit."""
    token = sql_type.strip().upper().split("(", 1)[0].strip()
    if token in _INTEGER:
        return "QSpinBox"
    if token in _REAL:
        return "QDoubleSpinBox"
    if token in _BOOL:
        return "QCheckBox"
    if token in _DATE:
        return "QDateEdit"
    if token in _DATETIME:
        return "QDateTimeEdit"
    return "QLineEdit"


def four_digit_year_format(short_format: str) -> str:
    """Force a four-digit year onto a Qt date format string."""
    text = short_format.strip() or "yyyy-MM-dd"
    if "yyyy" in text:
        return text
    return text.replace("yy", "yyyy")


def column_widget_name(column: str, used: Sequence[str]) -> str:
    """A Python identifier taken from the column name."""
    taken = set(used)
    base = _identifier(column.strip() or "field")
    name = base
    number = 2
    while name in taken:
        name = "%s_%d" % (base, number)
        number += 1
    return name


def sqlite_tables(path: str) -> Tuple[str, ...]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    finally:
        connection.close()
    return tuple(str(row[0]) for row in rows)


def sqlite_columns(path: str, table: str) -> Tuple[Tuple[str, str], ...]:
    """``(column name, declared type)`` from ``PRAGMA table_info``."""
    quoted = '"' + table.replace('"', '""') + '"'
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("PRAGMA table_info(%s)" % quoted).fetchall()
    finally:
        connection.close()
    found = []
    for row in rows:
        declared = row[2] if row[2] is not None else ""
        found.append((str(row[1]), str(declared)))
    return tuple(found)


def build_table_form_ui(
    class_name: str,
    columns: Sequence[TableColumn],
    *,
    date_format: str = "yyyy-MM-dd",
) -> BuiltTableForm:
    """A form layout of the included columns. Excluded columns are omitted."""
    used = []
    rows = []
    stops = []
    first = None
    index = 0
    for column in columns:
        if not column.include:
            continue
        widget_name = column_widget_name(column.name, used)
        used.append(widget_name)
        label_name = _label_name(widget_name, used)
        used.append(label_name)
        widget_class = column.widget_class()
        extra = ""
        if widget_class in _DATE_WIDGETS:
            pattern = four_digit_year_format(date_format)
            if widget_class == "QDateTimeEdit" and "h" not in pattern.lower():
                pattern = pattern + " hh:mm"
            extra = string_property("displayFormat", pattern)
        rows.append(
            form_row(
                index,
                label_name,
                column.field_label(),
                widget_name,
                widget_class,
                widget_name,
                extra,
            )
        )
        stops.append(widget_name)
        if first is None:
            first = widget_name
        index += 1
    inner = (
        '  <layout class="QFormLayout" name="formLayout">\n'
        "%s"
        "  </layout>\n"
    ) % "".join(rows)
    text = form_document(
        class_name,
        "QWidget",
        inner,
        tabstops=tabstop_block(tuple(stops)),
    )
    return BuiltTableForm(text=text, first_widget=first)


def _identifier(source: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", source)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "field"
    if cleaned[0].isdigit():
        cleaned = "field_" + cleaned
    if not cleaned.isidentifier() or keyword.iskeyword(cleaned):
        cleaned = "field_" + cleaned
    return cleaned


def _label_name(widget_name: str, used: Sequence[str]) -> str:
    taken = set(used)
    candidate = widget_name + "Label"
    number = 2
    while candidate in taken or keyword.iskeyword(candidate):
        candidate = "%sLabel_%d" % (widget_name, number)
        number += 1
    return candidate
