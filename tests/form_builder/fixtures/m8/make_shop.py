"""Deterministic shop database for the M8 fixtures (CONTRACTS.md section 19.11).

The small database is the default. ``--reference`` builds the large one.
The path is the caller's. This module never writes a database into the tree.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Iterable, Sequence, Tuple

_SCHEMA = (
    """
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT,
        city TEXT,
        email TEXT UNIQUE
    )
    """,
    """
    CREATE TABLE products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        price NUMERIC NOT NULL
    )
    """,
    """
    CREATE TABLE invoices (
        id INTEGER PRIMARY KEY,
        invoice_no TEXT NOT NULL UNIQUE,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        invoice_date TEXT,
        notes TEXT,
        total NUMERIC
    )
    """,
    """
    CREATE TABLE invoice_lines (
        id INTEGER PRIMARY KEY,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        line_no INTEGER NOT NULL,
        product_id INTEGER REFERENCES products(id),
        description TEXT,
        qty INTEGER NOT NULL,
        price NUMERIC NOT NULL,
        UNIQUE (invoice_id, line_no)
    )
    """,
)


def build(path: str, *, reference: bool = False) -> None:
    """Write a new database at ``path``. An existing file is replaced."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    connection = sqlite3.connect(str(target))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement in _SCHEMA:
            connection.execute(statement)
        if reference:
            _reference(connection)
        else:
            _small(connection)
        connection.commit()
    finally:
        connection.close()


def _small(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT INTO customers (id, name, phone, city, email) VALUES (?, ?, ?, ?, ?)",
        (
            (1, "Acme", "555-0100", "North", "acme@example.com"),
            (2, "Northwind", "555-0101", "South", "northwind@example.com"),
        ),
    )
    connection.executemany(
        "INSERT INTO products (id, name, price) VALUES (?, ?, ?)",
        (
            (1, "Widget", "1.50"),
            (2, "Gadget", "2.00"),
        ),
    )
    connection.execute(
        "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "INV-1", 1, "2026-01-15", "", "1.50"),
    )
    connection.execute(
        "INSERT INTO invoice_lines (id, invoice_id, line_no, product_id, description, qty, price) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, 1, 1, 1, "Widget", 1, "1.50"),
    )


def _reference(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT INTO customers (id, name, phone, city, email) VALUES (?, ?, ?, ?, ?)",
        (
            (index, "Customer %d" % index, "555-%04d" % (index % 10000), "City %d" % (index % 50), "c%d@example.com" % index)
            for index in range(1, 2001)
        ),
    )
    connection.executemany(
        "INSERT INTO products (id, name, price) VALUES (?, ?, ?)",
        ((index, "Product %d" % index, "%d.00" % ((index % 20) + 1)) for index in range(1, 5001)),
    )
    connection.executemany(
        "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                index,
                "INV-%d" % index,
                (index % 2000) + 1,
                "2026-01-%02d" % ((index % 28) + 1),
                "",
                "0",
            )
            for index in range(1, 100001)
        ),
    )
    connection.executemany(
        "INSERT INTO invoice_lines (id, invoice_id, line_no, product_id, description, qty, price) VALUES (?, ?, ?, ?, ?, ?, ?)",
        _lines(),
    )


def _lines() -> Iterable[Tuple[object, ...]]:
    for index in range(1, 400001):
        invoice_id = ((index - 1) % 100000) + 1
        line_no = ((index - 1) // 100000) + 1
        product_id = ((index - 1) % 5000) + 1
        yield (index, invoice_id, line_no, product_id, "Line %d" % index, 1, "1.00")


def dump(path: str) -> str:
    connection = sqlite3.connect(path)
    try:
        return "\n".join(connection.iterdump())
    finally:
        connection.close()


def main(argv: Sequence[str]) -> int:
    reference = "--reference" in argv
    positional = [item for item in argv if not item.startswith("--")]
    if not positional:
        print("usage: make_shop.py [--reference] PATH", file=sys.stderr)
        return 2
    build(positional[0], reference=reference)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
