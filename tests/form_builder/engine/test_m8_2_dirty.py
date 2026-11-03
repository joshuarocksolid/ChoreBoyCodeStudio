"""Dirty detection, including a typed-back value and a formatting round trip."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from tests.form_builder.engine.test_m8_2_scenario import _xml, record_window
from app.features.form_builder.engine.data.source import RecordSource

pytestmark = pytest.mark.unit


def test_typing_the_value_back_is_not_dirty(tmp_path: Path) -> None:
    with record_window(tmp_path, _wide_ui(), _wide_db, filename="wide.ui", connection_file="data/wide.db") as (host, _db):
        original = host.ui.n0Edit.text()
        host.ui.n0Edit.setText(original + "x")
        assert host.ui._cbcs_is_dirty() is True
        host.ui.n0Edit.setText(original)
        assert host.ui._cbcs_is_dirty() is False


def test_decimal_and_date_round_trips_are_not_dirty(tmp_path: Path) -> None:
    with record_window(tmp_path, _wide_ui(), _wide_db, filename="wide.ui", connection_file="data/wide.db") as (host, _db):
        assert host.ui._cbcs_is_dirty() is False
        amount = host.ui.amountSpin.value()
        host.ui.amountSpin.setValue(amount + 1)
        assert host.ui._cbcs_is_dirty() is True
        host.ui.amountSpin.setValue(amount)
        assert host.ui._cbcs_is_dirty() is False
        day = host.ui.whenEdit.date()
        host.ui.whenEdit.setDate(day.addDays(1))
        assert host.ui._cbcs_is_dirty() is True
        host.ui.whenEdit.setDate(day)
        assert host.ui._cbcs_is_dirty() is False


def test_dirty_check_for_twenty_fields_stays_under_the_ceiling(tmp_path: Path) -> None:
    with record_window(tmp_path, _wide_ui(), _wide_db, filename="wide.ui", connection_file="data/wide.db") as (host, _db):
        samples = []
        for _index in range(3):
            started = time.perf_counter()
            for _call in range(50):
                host.ui._cbcs_is_dirty()
            samples.append((time.perf_counter() - started) * 1000.0 / 50.0)
        print("DIRTY_MS=%s" % ",".join("%.3f" % sample for sample in samples))
        assert max(samples) < 50


def _wide_ui() -> str:
    widgets = []
    for index in range(20):
        widgets.append(("QLineEdit", "n%dEdit" % index, "c%d" % index, ""))
    widgets.append(
        (
            "QDoubleSpinBox",
            "amountSpin",
            "amount",
            '<property name="decimals"><number>2</number></property>\n',
        )
    )
    widgets.append(("QDateEdit", "whenEdit", "when_on", ""))
    return _xml(RecordSource("shop", "wide", "id"), tuple(widgets))


def _wide_db(root: Path) -> Path:
    path = root / "data" / "wide.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        columns = ", ".join("c%d TEXT" % index for index in range(20))
        connection.execute(
            "CREATE TABLE wide (id INTEGER PRIMARY KEY, %s, amount NUMERIC, when_on TEXT)" % columns
        )
        names = ", ".join("c%d" % index for index in range(20))
        marks = ", ".join("?" for _index in range(20))
        values = tuple("t%d" % index for index in range(20))
        connection.execute(
            "INSERT INTO wide (id, %s, amount, when_on) VALUES (1, %s, ?, ?)" % (names, marks),
            values + ("1.50", "2026-03-01"),
        )
        connection.commit()
    finally:
        connection.close()
    return path
