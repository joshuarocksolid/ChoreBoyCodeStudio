# pyright: reportAttributeAccessIssue=false
"""M8.6 column footer and PostgreSQL test shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, Schema, Table, write_schema
from app.features.form_builder.engine.data.schema_cache import set_schema_runner
from app.features.form_builder.engine.data.source import RecordSource, write_data
from app.features.form_builder.engine.data.tester import failure_sentence, set_connection_tester
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.settings_ext.connections_page import ConnectionsPage
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.qt.QtWidgets import QApplication, QLabel, QWidget
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


class _Entry:
    def __init__(self, text: str) -> None:
        self.value = StringValue(text)


class _Root:
    def __init__(self, text: str) -> None:
        self._text = text

    def prop(self, name: str):
        if name == "cbcsData" and self._text:
            return _Entry(self._text)
        return None


class _Doc:
    def __init__(self, text: str) -> None:
        self.root = _Root(text)


class _Workbench(QWidget):
    def __init__(self, root: str) -> None:
        super().__init__()
        self.session = SimpleNamespace(
            document=_Doc(write_data(RecordSource("office", "customers", "id")))
        )
        self.project_root = root


def test_column_states(qapp, tmp_path: Path) -> None:
    directory = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not directory:
        pytest.skip("set CBCS_FB_SCREENSHOT_DIR to grab form-builder screenshots")
    root = Path(directory)
    _save(tmp_path)
    page = ConnectionsPage(None, str(tmp_path))
    try:
        for mode in _MODES:
            _cache(tmp_path, "2026-11-02T14:02:11")
            panel = DataPanel(_Workbench(str(tmp_path)))
            _grab(panel, mode, qapp, root / ("footer-fresh-%s.png" % mode))
            _cache(tmp_path, "2020-01-01T00:00:00")
            panel = DataPanel(_Workbench(str(tmp_path)))
            _grab(panel, mode, qapp, root / ("footer-stale-%s.png" % mode))
            sentence = panel.findChild(QLabel, "formBuilder.data.schemaSentence")
            stale = panel.findChild(QLabel, "formBuilder.data.stale")
            if sentence is not None:
                sentence.setText("Reading columns\u2026")
            if stale is not None:
                stale.hide()
            _grab(panel, mode, qapp, root / ("footer-reading-%s.png" % mode))
            if sentence is not None:
                sentence.setText("Using columns read 1 Nov. Can't reach Office: took too long")
            _grab(panel, mode, qapp, root / ("footer-unreachable-%s.png" % mode))
            page._result.setText("\u2713 Connected \u00b7 PostgreSQL 9.3.25 \u00b7 14 tables \u00b7 psycopg")
            _grab(page, mode, qapp, root / ("test-success-%s.png" % mode))
            office = Connection("office", "Office", "postgres", host="10.1.1.9", user="clerk")
            page._result.setText(failure_sentence(office, "auth", ""))
            _grab(page, mode, qapp, root / ("test-auth-%s.png" % mode))
    finally:
        set_schema_runner(None)
        set_connection_tester(None)


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
                    database="shop",
                    user="clerk",
                    password="ask",
                ),
            )
        ),
    )


def _cache(tmp_path: Path, read_at: str) -> None:
    schema = Schema(
        "office",
        "postgres",
        "PostgreSQL 9.3.25",
        read_at,
        "psycopg",
        (Table("customers", (Column("id", "integer", False),), key="id", rows=2),),
    )
    path = tmp_path / "cbcs" / "schema" / "office.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(write_schema(schema), encoding="utf-8", newline="\n")


def _grab(widget: QWidget, mode: str, qapp: QApplication, path: Path) -> None:
    widget.apply_theme(tokens_from_palette(widget.palette(), force_mode=mode))
    height = 900 if widget.objectName() == "formBuilder.connections.page" else 140
    widget.resize(960, height)
    widget.show()
    for _ in range(4):
        qapp.processEvents()
        time.sleep(0.01)
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))
