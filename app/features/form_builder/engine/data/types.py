"""Column type to kind, widget, words and conversion (LOGIC_DESIGN section 5.3, CONTRACTS section 19.5).

Qt-free. Where the two documents differ, section 19 wins: ``timestamp`` is a
date-and-time edit, ``time`` is a time edit, and uuid, json, bytea, arrays and
intervals are read-only text.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

_VARCHAR = re.compile(r"^(?:var)?char\s*\(\s*(\d+)\s*\)$", re.IGNORECASE)
_NUMERIC = re.compile(r"^(?:numeric|decimal)\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)$", re.IGNORECASE)
_INT = frozenset(
    {
        "integer",
        "int",
        "int2",
        "int4",
        "int8",
        "smallint",
        "bigint",
        "serial",
        "bigserial",
        "smallserial",
    }
)
_FLOAT = frozenset({"real", "float", "float4", "float8", "double", "double precision"})
_READONLY = frozenset({"uuid", "json", "jsonb", "bytea", "interval"})


@dataclass(frozen=True)
class ColumnKind:
    """One column's formula kind, the widget to suggest, the on-screen words, and how values move.

    ``direction`` is the conversion family: ``int``, ``decimal``, ``text``,
    ``date``, ``time``, ``datetime`` or ``bool``. ``read_only`` is the default
    binding for types a field cannot edit honestly.
    """

    kind: str
    widget: str
    words: str
    direction: str
    read_only: bool = False
    decimals: Optional[int] = None
    max_length: Optional[int] = None
    nullable: bool = True


def is_sqlite_rowid(declared: str, *, without_rowid: bool = False) -> bool:
    """True only for a column declared exactly ``INTEGER`` on a rowid table.

    ``BIGINT`` and ``INT`` have integer affinity and are not the rowid alias.
    ``WITHOUT ROWID`` has no rowid alias even when the type is ``INTEGER``.
    """

    if without_rowid:
        return False
    return " ".join(declared.strip().lower().split()) == "integer"


def sqlite_affinity(declared: str) -> str:
    """SQLite's affinity of a declared type. Empty and blob stay ``BLOB``."""

    text = declared.upper()
    if "INT" in text:
        return "INTEGER"
    if "CHAR" in text or "CLOB" in text or "TEXT" in text:
        return "TEXT"
    if not text or "BLOB" in text:
        return "BLOB"
    if "REAL" in text or "FLOA" in text or "DOUB" in text:
        return "REAL"
    return "NUMERIC"


def describe(
    declared: str,
    *,
    engine: str = "sqlite",
    column_name: str = "",
    references_table: str = "",
    nullable: bool = True,
) -> ColumnKind:
    """The kind, suggested widget and words for one column."""

    kind = _classify(declared, engine=engine, nullable=nullable)
    name = column_name.lower()
    if kind.direction == "int" and (name.startswith("is_") or name.startswith("has_")):
        kind = ColumnKind("yesno", "QCheckBox", "yes/no", "bool", nullable=nullable)
    if references_table and kind.direction == "int":
        kind = ColumnKind(
            kind.kind,
            "QComboBox",
            "points to %s" % references_table,
            kind.direction,
            nullable=nullable,
        )
    return kind


def to_sql(kind: ColumnKind, value: object, engine: str) -> object:
    """The value bound for ``engine`` (``sqlite`` or ``postgres``)."""

    if value is None:
        return None
    family = kind.direction
    if family == "text":
        text = str(value)
        if text == "" and kind.nullable:
            return None
        return text
    if family == "int":
        return int(value)  # type: ignore[arg-type]
    if family == "decimal":
        decimal = value if isinstance(value, Decimal) else Decimal(str(value))
        if engine == "postgres":
            return decimal
        return str(decimal)
    if family == "bool":
        flag = bool(value)
        if engine == "postgres":
            return flag
        return 1 if flag else 0
    if family == "date":
        return _iso_date(value)
    if family == "time":
        return _iso_time(value)
    if family == "datetime":
        return _iso_datetime(value)
    return value


def from_sql(kind: ColumnKind, value: object, engine: str) -> object:
    """The Python value a formula reads. ``engine`` selects bool and date shapes."""

    del engine
    if value is None:
        return None
    family = kind.direction
    if family == "int":
        return int(value)  # type: ignore[arg-type]
    if family == "decimal":
        return Decimal(str(value))
    if family == "bool":
        if isinstance(value, str):
            return value not in ("", "0", "false", "False")
        return bool(value)
    if family == "date":
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(str(value)[:10])
    if family == "time":
        if isinstance(value, datetime.datetime):
            return value.time()
        if isinstance(value, datetime.time):
            return value
        return datetime.time.fromisoformat(str(value))
    if family == "datetime":
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            return datetime.datetime(value.year, value.month, value.day)
        return datetime.datetime.fromisoformat(str(value).replace("T", " "))
    if family == "text":
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8")
        return str(value)
    return value


def formula_kind(kind: ColumnKind) -> str:
    """The formula type name (``whole``, ``money``, ``yesno``, and the rest)."""

    return kind.kind


def _classify(declared: str, *, engine: str, nullable: bool) -> ColumnKind:
    raw = " ".join(declared.strip().lower().split())
    base = raw.split("(", 1)[0].strip()
    if raw.endswith("[]") or base in _READONLY or base.startswith("_"):
        return ColumnKind("text", "QLineEdit", base or "text", "text", read_only=True, nullable=nullable)
    varchar = _VARCHAR.match(raw.replace(" ", ""))
    if varchar is not None:
        length = int(varchar.group(1))
        words = "text up to %d" % length
        return ColumnKind("text", "QLineEdit", words, "text", max_length=length, nullable=nullable)
    numeric = _NUMERIC.match(raw.replace(" ", ""))
    if numeric is not None:
        scale = int(numeric.group(2) or "0")
        if scale == 2:
            return ColumnKind("money", "QDoubleSpinBox", "money", "decimal", decimals=scale, nullable=nullable)
        words = "whole number" if scale == 0 else "number"
        kind_name = "whole" if scale == 0 else "number"
        widget = "QSpinBox" if scale == 0 else "QDoubleSpinBox"
        direction = "int" if scale == 0 else "decimal"
        return ColumnKind(kind_name, widget, words, direction, decimals=scale, nullable=nullable)
    if base in ("boolean", "bool"):
        return ColumnKind("yesno", "QCheckBox", "yes/no", "bool", nullable=nullable)
    if base in ("date",):
        return ColumnKind("date", "QDateEdit", "date", "date", nullable=nullable)
    if base in ("time", "timetz"):
        return ColumnKind("time", "QTimeEdit", "time", "time", nullable=nullable)
    if base in ("timestamp", "timestamptz") or base.startswith("timestamp "):
        return ColumnKind("datetime", "QDateTimeEdit", "date and time", "datetime", nullable=nullable)
    if base in _INT or (engine == "sqlite" and sqlite_affinity(declared) == "INTEGER" and "bool" not in base):
        if base in _INT or sqlite_affinity(declared) == "INTEGER":
            return ColumnKind("whole", "QSpinBox", "whole number", "int", nullable=nullable)
    if base in _FLOAT or base in ("numeric", "decimal"):
        words = "money" if base in ("numeric", "decimal") else "number"
        kind_name = "money" if base in ("numeric", "decimal") else "number"
        return ColumnKind(kind_name, "QDoubleSpinBox", words, "decimal", nullable=nullable)
    if engine == "sqlite":
        affinity = sqlite_affinity(declared)
        if affinity == "INTEGER":
            return ColumnKind("whole", "QSpinBox", "whole number", "int", nullable=nullable)
        if affinity == "REAL":
            return ColumnKind("number", "QDoubleSpinBox", "number", "decimal", nullable=nullable)
        if affinity == "NUMERIC":
            return ColumnKind("number", "QDoubleSpinBox", "number", "decimal", nullable=nullable)
        if affinity == "TEXT":
            return ColumnKind("text", "QLineEdit", "text", "text", nullable=nullable)
    if "date" in base:
        return ColumnKind("date", "QDateEdit", "date", "date", nullable=nullable)
    return ColumnKind("text", "QLineEdit", "text", "text", nullable=nullable)


def _iso_date(value: object) -> str:
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)[:10]


def _iso_time(value: object) -> str:
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.datetime):
        return value.time().isoformat()
    return str(value)


def _iso_datetime(value: object) -> str:
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


__all__ = [
    "ColumnKind",
    "describe",
    "formula_kind",
    "from_sql",
    "is_sqlite_rowid",
    "sqlite_affinity",
    "to_sql",
]
