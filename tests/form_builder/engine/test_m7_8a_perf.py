# pyright: reportAttributeAccessIssue=false
"""Collecting 100 rules on a 300-widget form stays under 16 ms."""

from __future__ import annotations

import time

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.uses import PanelQuery, collect, panel_rows
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.perf


def _form() -> str:
    rows = []
    for index in range(300):
        props = ""
        if 0 < index <= 100:
            props = (
                '<property name="cbcsValue" stdset="0"><string notr="true">w%d</string></property>'
                % (index - 1)
            )
        rows.append('<item><widget class="QLineEdit" name="w%d">%s</widget></item>' % (index, props))
    body = "\n".join(rows)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Bulk</class>\n'
        ' <widget class="QDialog" name="Bulk">\n  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "%s\n  </layout>\n </widget>\n</ui>\n"
    ) % body


def test_collect_and_panel_rows_of_100_rules_is_under_16ms() -> None:
    catalog = QtClassTable.shared()
    warm = read_ui(_form(), allocator=IdAllocator()).document
    collect(warm, env_for(warm, None, catalog), "", "")
    doc = read_ui(_form(), allocator=IdAllocator()).document
    env = env_for(doc, None, catalog)
    started = time.perf_counter()
    book = collect(doc, env, "", "")
    rows = panel_rows(book, PanelQuery())
    elapsed = time.perf_counter() - started
    assert len(rows) == 100
    assert elapsed < 0.016, elapsed
