"""Map a SQLite column to a form widget. No Qt imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnPlan:
    name: str
    declared_type: str
    not_null: bool
    widget: str
    required_marker: bool


def widget_for_column(name: str, declared_type: str, not_null: bool, foreign_key: bool) -> str:
    lowered = name.lower()
    kind = (declared_type or "").upper()
    if foreign_key:
        return "QComboBox"
    if "BOOL" in kind or (
        "INT" in kind
        and (
            lowered.startswith("is_")
            or lowered.startswith("has_")
            or lowered == "paid"
            or lowered.startswith("paid_")
        )
    ):
        return "QCheckBox"
    if "DATETIME" in kind or "TIMESTAMP" in kind or ("DATE" in kind and "TIME" in kind):
        return "QDateTimeEdit"
    if kind == "DATE" or kind.startswith("DATE"):
        return "QDateEdit"
    if any(token in kind for token in ("REAL", "FLOA", "DOUB", "NUM")):
        return "QDoubleSpinBox"
    if "INT" in kind:
        return "QSpinBox"
    if any(token in lowered for token in ("note", "notes", "memo", "comment", "description", "body")):
        return "QPlainTextEdit"
    return "QLineEdit"


def plan_table(connection: sqlite3.Connection, table: str) -> list[ColumnPlan]:
    info = connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    foreign = {row[3] for row in connection.execute(f"PRAGMA foreign_key_list({_quote(table)})")}
    plans = []
    for row in info:
        name = row[1]
        declared = row[2] or ""
        not_null = bool(row[3])
        widget = widget_for_column(name, declared, not_null, name in foreign)
        plans.append(ColumnPlan(name, declared, not_null, widget, not_null))
    return plans


def list_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
