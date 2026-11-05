# pyright: reportMissingImports=false
"""pg8000 placeholder scan of a three-column Find. No database."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.data.sql import find_keys

pytestmark = pytest.mark.unit


def test_pg8000_converts_every_placeholder_in_a_three_column_find() -> None:
    """pg8000's own scanner must turn each ``%s`` into a numbered placeholder."""
    pytest.importorskip(
        "pg8000",
        reason="pg8000 is not importable from this Python, so the placeholder scan is not run",
    )
    from pg8000.dbapi import convert_paramstyle

    statement = find_keys(
        "postgres",
        "invoices",
        "id",
        (("invoice_date", "desc"),),
        ("code", "name", "note"),
    )
    assert statement.text.count("%s") == 3
    assert "$$\\$$" in statement.text
    assert "E'" not in statement.text
    converted, values = convert_paramstyle("format", statement.text, ("%a%", "%b%", "%c%"))
    assert "%s" not in converted
    assert "E'" not in converted
    assert "$1" in converted
    assert "$2" in converted
    assert "$3" in converted
    assert converted.count("$$") == 6
    assert values == ("%a%", "%b%", "%c%")
