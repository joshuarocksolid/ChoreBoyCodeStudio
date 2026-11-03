# pyright: reportAttributeAccessIssue=false
"""The column footer: hidden without a source, and it follows a refresh."""

from __future__ import annotations

import datetime
import time
from pathlib import Path

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, Schema, Table, set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import set_schema_runner
from app.features.form_builder.engine.data.checks.listing import cached_list_probe
from app.features.form_builder.engine.data.source import ListSource, RecordSource, write_data
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.features.form_builder.qtside.data_panel.sections_ext.schema_footer import FORCE_FOOTER
from app.qt.QtWidgets import QApplication, QLabel, QWidget
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit


class _Entry:
    def __init__(self, text: str) -> None:
        self.value = StringValue(text)


class _Root:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def prop(self, name: str):
        if name == "cbcsData" and self._text:
            return _Entry(self._text)
        return None


class _Doc:
    def __init__(self, text: str = "") -> None:
        self.root = _Root(text)


class _Session:
    def __init__(self, document: _Doc) -> None:
        self.document = document


class _Workbench(QWidget):
    def __init__(self, document: _Doc, root: str) -> None:
        super().__init__()
        self.session = _Session(document)
        self.project_root = root


def test_the_footer_stays_hidden_until_a_source_or_a_forced_document(qapp, tmp_path: Path) -> None:
    del qapp
    empty = _Doc()
    panel = DataPanel(_Workbench(empty, str(tmp_path)))
    assert panel.findChild(QWidget, "formBuilder.data.schemaFooter") is None
    FORCE_FOOTER.add(empty)
    try:
        panel.reload()
        assert panel.findChild(QWidget, "formBuilder.data.schemaFooter") is not None
    finally:
        FORCE_FOOTER.discard(empty)
    sourced = _Doc(write_data(RecordSource("office", "customers", "id")))
    shown = DataPanel(_Workbench(sourced, str(tmp_path)))
    assert shown.findChild(QWidget, "formBuilder.data.schemaFooter") is not None


def test_refresh_shows_the_frozen_day_and_emits_the_connection(qapp, tmp_path: Path, monkeypatch) -> None:
    _save(tmp_path)
    panel = _panel(tmp_path)
    seen = []
    panel.schema_changed.connect(seen.append)
    _freeze(monkeypatch)
    set_schema_runner(_Ok())
    try:
        panel.findChild(QWidget, "formBuilder.data.schemaRefresh").click()
        _until(qapp, lambda: "2 Nov 14:02" in _sentence(panel))
        assert seen == ["office"]
    finally:
        set_schema_runner(None)
        set_schema_reader(None)


def test_a_failure_keeps_the_previous_day_and_the_reason(qapp, tmp_path: Path) -> None:
    _save(tmp_path)
    previous = Schema(
        "office",
        "postgres",
        "PostgreSQL 9.3.25",
        "2026-11-01T09:15:00",
        "psycopg",
        (Table("customers", (Column("id", "integer", False),), key="id", rows=2),),
    )
    cache = tmp_path / "cbcs" / "schema" / "office.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(write_schema(previous), encoding="utf-8", newline="\n")
    panel = _panel(tmp_path)
    set_schema_runner(_Fail())
    try:
        panel.findChild(QWidget, "formBuilder.data.schemaRefresh").click()
        _until(qapp, lambda: "took too long" in _sentence(panel))
        assert "1 Nov" in _sentence(panel)
        assert "Office" in _sentence(panel)
    finally:
        set_schema_runner(None)
        set_schema_reader(None)


def test_refresh_probes_list_sql_once_and_remembers_it(qapp, tmp_path: Path, monkeypatch) -> None:
    _save(tmp_path)
    sql = "SELECT id FROM customers -- keep"
    document = _Doc(write_data(ListSource("office", ("id",), table="customers", sql=sql)))
    panel = DataPanel(_Workbench(document, str(tmp_path)))
    runner = _Probe()
    asks = []
    import app.features.form_builder.qtside.data_panel.sections_ext.schema_footer as footer

    monkeypatch.setattr(footer, "ask_connection_secret", lambda _root, item: asks.append(item) or "secret")
    set_schema_runner(runner)
    try:
        panel.findChild(QWidget, "formBuilder.data.schemaRefresh").click()
        _until(qapp, lambda: bool(runner.probes))
    finally:
        set_schema_runner(None)
        set_schema_reader(None)
    assert runner.probes == [sql]
    assert len(asks) == 1
    cached = cached_list_probe(document, sql)
    assert cached is not None and cached.ok is False
    assert cached.reason == "no such table"


def test_the_stale_label_uses_the_warning_token(qapp, tmp_path: Path) -> None:
    del qapp
    _save(tmp_path)
    previous = Schema(
        "office",
        "postgres",
        "PostgreSQL 9.3.25",
        "2020-01-01T00:00:00",
        "psycopg",
        (Table("customers", (Column("id", "integer", False),), key="id"),),
    )
    cache = tmp_path / "cbcs" / "schema" / "office.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(write_schema(previous), encoding="utf-8", newline="\n")
    panel = _panel(tmp_path)
    panel.window().show()
    stale = panel.findChild(QLabel, "formBuilder.data.stale")
    assert stale is not None
    assert stale.isHidden() is False
    tokens = tokens_from_palette(panel.palette())
    panel.apply_theme(tokens)
    sheet = panel.styleSheet()
    assert "QLabel#formBuilder\\.data\\.stale" in sheet
    assert tokens.diag_warning_color in sheet
    set_schema_reader(None)


class _Ok:
    def schema(self, root, connection, ask):
        del root, connection, ask
        return {
            "ok": True,
            "schema": {
                "version": 1,
                "connection": "office",
                "engine": "postgres",
                "server": "PostgreSQL 9.3.25",
                "readAt": "2000-01-01T00:00:00",
                "driver": "psycopg",
                "tables": [],
            },
        }

    def cancel(self) -> None:
        return None


class _Probe(_Ok):
    def __init__(self) -> None:
        self.probes = []

    def schema(self, root, connection, ask):
        ask(connection)
        return super().schema(root, connection, ask)

    def probe_select(self, root, connection, sql, ask):
        del root
        self.probes.append(sql)
        ask(connection)
        return {"ok": False, "kind": "other", "message": "no such table"}


class _Fail:
    def schema(self, root, connection, ask):
        del root, connection, ask
        return {"ok": False, "kind": "unreachable", "message": "took too long"}

    def cancel(self) -> None:
        return None


def _save(tmp_path: Path) -> None:
    save_connections(
        str(tmp_path),
        ConnectionSet(
            (
                Connection(
                    "office",
                    "Office",
                    "postgres",
                    host="10.1.1.9",
                    port=5432,
                    database="shop",
                    user="clerk",
                    password="none",
                ),
            )
        ),
    )


def _panel(tmp_path: Path) -> DataPanel:
    document = _Doc(write_data(RecordSource("office", "customers", "id")))
    return DataPanel(_Workbench(document, str(tmp_path)))


def _sentence(panel: DataPanel) -> str:
    label = panel.findChild(QLabel, "formBuilder.data.schemaSentence")
    return "" if label is None else label.text()


def _freeze(monkeypatch) -> None:
    import app.features.form_builder.engine.data.schema_cache as schema_cache

    real = datetime.datetime

    class Frozen(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 11, 2, 14, 2, 11)

    monkeypatch.setattr(schema_cache.datetime, "datetime", Frozen)


def _until(qapp: QApplication, predicate, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("the footer did not update")
