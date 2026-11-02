# pyright: reportAttributeAccessIssue=false
"""A rule-graph patch must not keep formula text the note no longer lists."""

from __future__ import annotations

from typing import Any

import pytest

from app.features.form_builder.engine.commands.catalog import SetGeometry, SetLogic
from app.features.form_builder.engine.logic import rules as rules_mod
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.rules import rule_graph
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.layers.feeds import form_has_rules
from tests.form_builder.engine.commands._support import open_log

pytestmark = pytest.mark.unit


def _form() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Sale</class>\n'
        ' <widget class="QDialog" name="Sale">\n'
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        '   <item>\n    <widget class="QLineEdit" name="nameEdit"/>\n   </item>\n'
        "  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n"
    )


def _env(doc: UiDocument) -> Any:
    return env_for(doc, None, QtClassTable.shared())


def _matches_fresh(doc: UiDocument) -> None:
    env = _env(doc)
    live = rule_graph(doc, env)
    fresh, _reads = rules_mod._build(doc, env)
    assert dict(live.records) == dict(fresh.records)
    assert live.order() == fresh.order()


def _text(doc: UiDocument, key: str) -> str:
    record = next(item for item in rule_graph(doc, _env(doc)).records.values() if item.key == key)
    return record.text


def test_two_formula_commits_before_the_graph_keep_both_texts() -> None:
    log = open_log(_form())
    doc = log.document
    owner = doc.by_name("nameEdit")[0]
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "True"))
    log.execute(SetLogic(owner, "cbcsEnabledWhen", "True"))
    rule_graph(doc, _env(doc))
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "False"))
    log.execute(SetLogic(owner, "cbcsEnabledWhen", "False"))
    _matches_fresh(doc)
    assert _text(doc, "cbcsVisibleWhen") == "False"
    assert _text(doc, "cbcsEnabledWhen") == "False"


def test_undo_then_redo_of_a_formula_matches_a_fresh_graph() -> None:
    log = open_log(_form())
    doc = log.document
    owner = doc.by_name("nameEdit")[0]
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "True"))
    rule_graph(doc, _env(doc))
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "False"))
    rule_graph(doc, _env(doc))
    assert log.undo()
    _matches_fresh(doc)
    assert _text(doc, "cbcsVisibleWhen") == "True"
    assert log.redo()
    _matches_fresh(doc)
    assert _text(doc, "cbcsVisibleWhen") == "False"


def test_a_geometry_edit_between_formula_edits_rebuilds() -> None:
    log = open_log(_form())
    doc = log.document
    owner = doc.by_name("nameEdit")[0]
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "True"))
    log.execute(SetGeometry(owner, RectValue(4, 5, 40, 20)))
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "False"))
    _matches_fresh(doc)
    assert _text(doc, "cbcsVisibleWhen") == "False"


def test_blanking_the_only_formula_clears_form_has_rules() -> None:
    log = open_log(_form())
    doc = log.document
    owner = doc.by_name("nameEdit")[0]
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "True"))
    assert form_has_rules(doc) is True
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "   "))
    assert form_has_rules(doc) is False
