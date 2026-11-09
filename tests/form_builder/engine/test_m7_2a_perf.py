# pyright: reportAttributeAccessIssue=false
"""Graph build stays inside the 5 ms budget for 300 widgets and 100 rules."""

from __future__ import annotations

import time

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.rules import rule_graph
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


def test_rule_graph_of_300_widgets_and_100_rules_is_under_5ms() -> None:
    doc = read_ui(_form(), allocator=IdAllocator()).document
    catalog = QtClassTable.shared()
    env = env_for(doc, None, catalog)
    rule_graph(doc, env)
    doc2 = read_ui(_form(), allocator=IdAllocator()).document
    env2 = env_for(doc2, None, catalog)
    started = time.perf_counter()
    graph = rule_graph(doc2, env2)
    elapsed = time.perf_counter() - started
    assert len(graph.order()) == 100
    assert elapsed < 0.005, elapsed
