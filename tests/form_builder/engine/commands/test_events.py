"""Change sets rebuild the tree, and categories follow the op (CONTRACTS.md section 4)."""

from __future__ import annotations

from typing import List

from app.features.form_builder.engine.commands.catalog import (
    AddConnection,
    Rename,
    SetLogic,
    SetProperty,
)
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, nid, open_log


def test_shadow_tree_matches_after_edits_undo_and_redo() -> None:
    from tests.support.form_builder.gen import run_sequence

    for seed in range(4):
        run_sequence(seed, 20)


def test_categories_follow_the_op() -> None:
    log = open_log(BOX)
    doc = log.document
    found: List[ChangeSet] = []
    log.subscribe(lambda change_set: found.append(change_set), priority=0)
    button = nid(doc, "okButton")
    log.execute(SetProperty(button, "text", StringValue("Go")))
    log.execute(SetLogic(button, "cbcsEnabledWhen", "1"))
    log.execute(AddConnection("okButton", "clicked", "label", "clear"))
    log.execute(Rename(nid(doc, "label"), "caption"))
    assert found[0].categories == frozenset({"property"})
    assert "logic" in found[1].categories
    assert "connection" in found[2].categories
    assert "name" in found[3].categories


def test_listeners_run_in_priority_order() -> None:
    log = open_log(BOX)
    order: List[int] = []
    log.subscribe(lambda _change_set: order.append(100), priority=100)
    log.subscribe(lambda _change_set: order.append(0), priority=0)
    log.execute(SetProperty(nid(log.document, "okButton"), "text", StringValue("Go")))
    assert order == [0, 100]


def test_one_change_per_op() -> None:
    log: CommandLog = open_log(BOX)
    found: List[ChangeSet] = []
    log.subscribe(lambda change_set: found.append(change_set), priority=0)
    log.execute(SetProperty(nid(log.document, "okButton"), "text", StringValue("Go")))
    assert len(found) == 1
    assert len(found[0].changes) == len(log.entries()[-1].ops)
