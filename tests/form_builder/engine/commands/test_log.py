"""Undo, merge, transactions and listener rules (CONTRACTS.md section 3)."""

from __future__ import annotations

from typing import ClassVar, List

import pytest

from app.features.form_builder.engine.commands.base import (
    CommandRejected,
    PlanContext,
    ReentrantCommandError,
)
from app.features.form_builder.engine.commands.catalog import DeleteNodes, SetProperty
from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, nid, open_log, prop_text, saved


@pytest.mark.parity("R3-33")
def test_undo_then_redo_restores_the_edit() -> None:
    log = open_log(BOX)
    doc = log.document
    original = saved(doc)
    fingerprint = doc.fingerprint()
    log.execute(SetProperty(nid(doc, "okButton"), "text", StringValue("Go")))
    assert prop_text(doc, "okButton") == "Go"
    assert log.undo_label() == "Edit"
    assert log.undo()
    assert saved(doc) == original
    assert doc.fingerprint() == fingerprint
    assert log.redo()
    assert prop_text(doc, "okButton") == "Go"


def test_same_merge_key_is_one_undo_step() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    log.execute(SetProperty(owner, "text", StringValue("A"), merge_token="g"))
    log.execute(SetProperty(owner, "text", StringValue("B"), merge_token="g"))
    assert len(log.entries()) == 1
    assert log.undo_label() == "Edit"
    assert log.undo()
    assert prop_text(doc, "okButton") == "OK"
    assert not log.can_undo()


def test_net_nil_merge_pops_the_step_and_stays_clean() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    seen: List[ChangeSet] = []
    log.subscribe(lambda change_set: seen.append(change_set), priority=0)
    log.execute(SetProperty(owner, "text", StringValue("A"), merge_token="g"))
    log.execute(SetProperty(owner, "text", StringValue("OK"), merge_token="g"))
    assert log.entries() == ()
    assert not log.is_dirty()
    assert prop_text(doc, "okButton") == "OK"
    assert len(seen) == 2


def test_continue_gesture_absorbs_a_different_merge_key() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    log.execute(
        SetProperty(button, "text", StringValue("A"), merge_token="drop"),
        continue_gesture=True,
    )
    log.execute(SetProperty(label, "text", StringValue("B"), merge_token="drop"))
    assert len(log.entries()) == 1
    assert log.undo()
    assert prop_text(doc, "okButton") == "OK"
    assert prop_text(doc, "label") == "Hi"


def test_edit_after_undo_past_the_save_point_stays_dirty() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    log.execute(SetProperty(owner, "text", StringValue("A")))
    log.mark_saved()
    assert not log.is_dirty()
    assert log.undo()
    assert log.is_dirty()
    log.execute(SetProperty(owner, "text", StringValue("B")))
    assert log.is_dirty()
    assert not log.can_redo()


def test_transaction_rollback_emits_nothing_and_restores_bytes() -> None:
    log = open_log(BOX)
    doc = log.document
    original = saved(doc)
    fingerprint = doc.fingerprint()
    seen: List[ChangeSet] = []
    log.subscribe(lambda change_set: seen.append(change_set), priority=0)
    with pytest.raises(CommandRejected):
        with log.transaction("Group"):
            log.execute(SetProperty(nid(doc, "okButton"), "text", StringValue("A")))
            log.execute(DeleteNodes((NodeId(10**9),)))
    assert saved(doc) == original
    assert doc.fingerprint() == fingerprint
    assert seen == []
    assert not log.can_undo()


def test_failed_command_inside_a_transaction_rolls_its_own_ops_back_too() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    original = saved(doc)

    class Partial:
        command_type: ClassVar[str] = "partial"
        label = "Partial"
        merge_token = None

        def merge_key(self) -> None:
            return None

        def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
            del doc
            ctx.run(SetProperty(owner, "text", StringValue("partial")))
            raise CommandRejected("stop")

    with pytest.raises(CommandRejected):
        with log.transaction("Group"):
            log.execute(SetProperty(owner, "text", StringValue("kept")))
            log.execute(Partial())
    assert saved(doc) == original
    assert prop_text(doc, "okButton") == "OK"


def test_set_then_reset_in_one_transaction_is_not_property_dirty() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    seen: List[ChangeSet] = []
    log.subscribe(lambda change_set: seen.append(change_set), priority=0)
    with log.transaction("Type"):
        log.execute(SetProperty(owner, "text", StringValue("ZZ")))
        log.execute(SetProperty(owner, "text", StringValue("OK")))
    assert len(seen) == 1
    assert (owner, "property", "text") not in seen[0].property_dirty
    assert prop_text(doc, "okButton") == "OK"


def test_listener_cannot_edit_and_the_outer_edit_still_stands() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    seen: List[str] = []

    def listener(_change_set: ChangeSet) -> None:
        try:
            log.execute(SetProperty(owner, "text", StringValue("nested")))
        except ReentrantCommandError:
            seen.append("rejected")
            raise

    log.subscribe(listener, priority=0)
    log.execute(SetProperty(owner, "text", StringValue("outer")))
    assert seen == ["rejected"]
    assert prop_text(doc, "okButton") == "outer"
    assert log.can_undo()


def test_listener_exception_does_not_undo_the_entry() -> None:
    log = open_log(BOX)
    doc = log.document

    def boom(_change_set: ChangeSet) -> None:
        raise RuntimeError("boom")

    log.subscribe(boom, priority=0)
    log.execute(SetProperty(nid(doc, "okButton"), "text", StringValue("Go")))
    assert prop_text(doc, "okButton") == "Go"
    assert log.can_undo()


def test_undo_limit_drops_the_oldest_step() -> None:
    log = open_log(BOX, undo_limit=2)
    doc = log.document
    owner = nid(doc, "okButton")
    for text in ("A", "B", "C"):
        log.execute(SetProperty(owner, "text", StringValue(text)))
    assert len(log.entries()) == 2
    assert log.undo()
    assert log.undo()
    assert not log.can_undo()
    assert prop_text(doc, "okButton") == "A"


def test_redo_does_not_run_apply_again() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    calls = {"n": 0}

    class Once:
        command_type: ClassVar[str] = "once"
        label = "Once"
        merge_token = None

        def merge_key(self) -> None:
            return None

        def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
            del doc
            calls["n"] += 1
            ctx.run(SetProperty(owner, "text", StringValue("Go")))

    log.execute(Once())
    assert log.undo()
    assert log.redo()
    assert calls["n"] == 1
    assert prop_text(doc, "okButton") == "Go"
