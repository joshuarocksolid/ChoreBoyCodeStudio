"""M6.0b: SetLogic on the codec, the version marker, read-only logic (FB402) and the
rename, paste and delete participants (CONTRACTS.md sections 15.2, 15.7, 15.8).
"""

from __future__ import annotations

import os
import random
from typing import Dict, List, Tuple

import pytest

from app.features.form_builder.engine.clipboard import (
    FRAGMENT_LOGIC_PROPERTY,
    fragment_logic_version,
    paste_placement,
    selection_fragment,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import (
    AddConnection,
    DeleteNodes,
    EditConnection,
    InsertFragment,
    MoveConnection,
    Rename,
    SetFormSlots,
    SetLogic,
    SetProperty,
    SetPropertyMany,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import read_fragment
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_fragment
from tests.form_builder.engine.commands._support import nid, open_log, saved
from tests.support.form_builder.m6_logic_fixtures import CHECKS, CLEAR_STEPS, CONNECTION, prop_xml, form, texts

# --- SetLogic --------------------------------------------------------------


def test_set_logic_stores_canonical_text_and_the_marker() -> None:
    log = open_log(form(marker=""))
    doc = log.document
    assert doc.logic_property_count() == 5
    assert doc.root.prop("cbcsLogic") is None  # no marker, a logic property: version 1, untouched on open
    button = nid(doc, "clearButton")
    messy = '[ {"enabled":false, "method":"m", "do":"call" , "x": 1.0},{"do":"slot","slot":"clear()","target":"nameEdit"} ]'
    log.execute(SetLogic(button, "cbcsOnClicked", messy))
    assert texts(doc)[("clearButton", "cbcsOnClicked")] == (
        "[\n"
        '  {"do": "call", "enabled": false, "method": "m", "x": 1},\n'
        '  {"do": "slot", "target": "nameEdit", "slot": "clear()"}\n'
        "]"
    )
    marker = doc.root.prop("cbcsLogic")
    assert marker is not None and marker.value == StringValue('{"version":1}', notr=True)
    assert log.undo_label() == "Edit logic"
    assert log.undo()
    assert doc.root.prop("cbcsLogic") is None


def test_set_logic_rejects_what_the_codec_cannot_read_and_removes_empty_lists() -> None:
    log = open_log(form())
    doc = log.document
    button = nid(doc, "clearButton")
    before = doc.fingerprint()
    for bad in ('[{"do": "slot"}]', "[1, 2", "{}", "[NaN]"):
        with pytest.raises(CommandRejected) as caught:
            log.execute(SetLogic(button, "cbcsOnClicked", bad))
        assert caught.value.code == "FB401"
    with pytest.raises(CommandRejected) as caught:
        log.execute(SetLogic(nid(doc, "nameEdit"), "cbcsValidate", '{"check": "required"}'))
    assert caught.value.code == "FB401"
    assert doc.fingerprint() == before and not log.can_undo()
    log.execute(SetLogic(button, "cbcsOnClicked", "[]"))
    assert doc.node(button).prop("cbcsOnClicked") is None
    log.execute(SetLogic(nid(doc, "nameEdit"), "cbcsValidate", None))
    log.execute(SetLogic(nid(doc, "nameEdit"), "cbcsEnabledWhen", None))
    log.execute(SetLogic(nid(doc, "nameEdit"), "cbcsErrorLabel", None))
    log.execute(SetLogic(nid(doc, "total"), "cbcsValue", None))
    assert doc.logic_property_count() == 0
    assert doc.root.prop("cbcsLogic") is None  # the marker goes with the last logic property


def test_text_that_means_the_same_keeps_the_stored_bytes() -> None:
    odd = '[{"target":"nameEdit","do":"slot","slot":"clear()"}]'
    log = open_log(form())
    doc = log.document
    button = nid(doc, "clearButton")
    log.execute(SetLogic(button, "cbcsOnClicked", odd))  # changes the value: canonical
    stored = texts(doc)[("clearButton", "cbcsOnClicked")]
    assert stored != odd
    revision = doc.revision
    outcome = log.execute(SetLogic(button, "cbcsOnClicked", '[{"slot":"clear()","target":"nameEdit","do":"slot"}]'))
    assert outcome.noop and doc.revision == revision


def test_set_logic_on_a_noncanonical_file_text_leaves_other_properties_alone() -> None:
    messy = "[ {\"do\":\"slot\",\"target\":\"nameEdit\", \"slot\":\"clear()\", \"zz\": [1,2]}  ]"
    text = form().replace(
        prop_xml("cbcsOnClicked", CLEAR_STEPS), prop_xml("cbcsOnClicked", messy) + prop_xml("cbcsFuture", "keep   me  ")
    )
    log = open_log(text)
    doc = log.document
    assert "keep   me  " in saved(doc)  # the file text reaches the writer as read
    before = texts(doc)
    log.execute(SetLogic(nid(doc, "nameEdit"), "cbcsEnabledWhen", "useName"))
    after = texts(doc)
    assert after[("nameEdit", "cbcsEnabledWhen")] == "useName"
    for key, value in before.items():
        if key != ("nameEdit", "cbcsEnabledWhen"):
            assert after[key] == value
    assert after[("clearButton", "cbcsOnClicked")] == messy
    assert after[("clearButton", "cbcsFuture")] == "keep   me  "
    names = [entry.name for entry in doc.node(nid(doc, "clearButton")).properties()]
    assert names == ["cbcsOnClicked", "cbcsFuture"]  # read order, no re-sort


def test_a_new_step_list_ranks_before_data_and_after_labels() -> None:
    log = open_log(form())
    doc = log.document
    node = nid(doc, "nameEdit")
    log.execute(SetLogic(node, "cbcsData", '{"table": "t"}'))
    log.execute(SetLogic(node, "cbcsOnTextChanged", '[{"do": "call", "method": "m"}]'))
    names = [entry.name for entry in doc.node(node).properties()]
    assert names == [
        "cbcsEnabledWhen",
        "cbcsErrorLabel",
        "cbcsValidate",
        "cbcsOnTextChanged",
        "cbcsData",
    ]


# --- the marker ------------------------------------------------------------


def test_marker_forms_a_file_may_use_are_all_readable_and_kept() -> None:
    for marker in ('{\n "version": 1\n}', "1"):
        log = open_log(form(marker=marker))
        doc = log.document
        log.execute(SetLogic(nid(doc, "total"), "cbcsValue", "1"))
        entry = doc.root.prop("cbcsLogic")
        assert entry is not None and getattr(entry.value, "text") == marker


def test_pasted_logic_adds_the_marker_and_deleting_the_last_removes_it() -> None:
    source = open_log(form())
    target = open_log(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="plain"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
    )
    fragment = selection_fragment(source.document, (nid(source.document, "total"),))
    log, doc = target, target.document
    assert doc.root.prop("cbcsLogic") is None
    log.execute(InsertFragment(paste_placement(doc, (nid(doc, "plain"),)), fragment))
    assert doc.root.prop("cbcsLogic") is not None
    assert doc.logic_property_count() == 1
    assert log.undo()
    assert doc.root.prop("cbcsLogic") is None
    log.redo()
    log.execute(DeleteNodes((nid(doc, "total"),)))
    assert doc.logic_property_count() == 0
    assert doc.root.prop("cbcsLogic") is None


def test_a_marker_with_no_logic_is_left_alone_by_unrelated_deletes() -> None:
    log = open_log(form().replace(prop_xml("cbcsOnClicked", CLEAR_STEPS), ""))
    doc = log.document
    log.execute(DeleteNodes((nid(doc, "other"),)))
    assert doc.root.prop("cbcsLogic") is not None


# --- read-only logic (FB402) ----------------------------------------------


NEWER = (
    '{ "version": 3,\n  "future": true }'
)


def _newer_form() -> str:
    text = form(marker=NEWER, connections=CONNECTION)
    return text.replace(
        prop_xml("cbcsOnClicked", CLEAR_STEPS),
        prop_xml(
            "cbcsOnClicked",
            '{"signal":"clicked(bool)","steps":[{"do":"hyperjump","target":"nameEdit","formula":"nameEdit + 1"}]}   ',
            notr=False,
        ),
    )


READ_ONLY_COMMANDS = [
    ("set_logic", lambda doc: SetLogic(nid(doc, "total"), "cbcsValue", "2")),
    ("add_connection", lambda doc: AddConnection("clearButton", "clicked()", "other", "clear()")),
    ("edit_connection", lambda doc: EditConnection(doc.connections()[0].id, slot="clear()")),
    ("set_form_slots", lambda doc: SetFormSlots(None, ("go()",))),
]


@pytest.mark.parametrize("name,make", READ_ONLY_COMMANDS)
def test_read_only_logic_refuses_logic_commands_with_fb402(name: str, make) -> None:
    log = open_log(_newer_form())
    doc = log.document
    before = saved(doc)
    with pytest.raises(CommandRejected) as caught:
        log.execute(make(doc))
    assert caught.value.code == "FB402"
    assert "newer version of Code Studio" in str(caught.value)
    assert saved(doc) == before and not log.can_undo()


def test_read_only_logic_refuses_move_connection() -> None:
    text = _newer_form().replace(
        "</connections>",
        "<connection><sender>other</sender><signal>textChanged(QString)</signal>"
        "<receiver>nameEdit</receiver><slot>setText(QString)</slot></connection></connections>",
    )
    log = open_log(text)
    doc = log.document
    with pytest.raises(CommandRejected) as caught:
        log.execute(MoveConnection(doc.connections()[0].id, 1))
    assert caught.value.code == "FB402"


def test_read_only_logic_is_written_back_byte_identical_through_layout_edits() -> None:
    log = open_log(_newer_form())
    doc = log.document
    assert NEWER.replace('"', "&quot;") in saved(doc)  # read order, spacing and a missing notr come back as read
    logic_before = texts(doc)
    marker = doc.root.prop("cbcsLogic")
    connections_before = [(c.field("sender"), c.field("signal"), c.field("receiver"), c.field("slot")) for c in doc.connections()]
    log.execute(SetProperty(nid(doc, "nameError"), "text", StringValue("Name is needed")))
    log.execute(DeleteNodes((nid(doc, "other"),)))
    log.execute(SetProperty(nid(doc, "total"), "text", StringValue("0")))
    assert texts(doc) == {key: value for key, value in logic_before.items() if key[0] != "other"}
    assert doc.root.prop("cbcsLogic") == marker
    assert [(c.field("sender"), c.field("signal"), c.field("receiver"), c.field("slot")) for c in doc.connections()] == connections_before
    while log.undo():
        pass
    assert saved(doc) == saved(open_log(_newer_form()).document)


def _logic_bytes(doc: UiDocument) -> Tuple[Dict[Tuple[str, str], str], object, List[Tuple[object, ...]]]:
    return (
        texts(doc),
        doc.root.prop("cbcsLogic"),
        [(c.field("sender"), c.field("signal"), c.field("receiver"), c.field("slot")) for c in doc.connections()],
    )


def test_read_only_logic_survives_every_edit_kind_byte_for_byte() -> None:
    """Delete of a widget the newer logic names, paste in and out, rename of an unmentioned
    widget and generic property writes: logic text and the marker never change; only the
    native connections of a deleted widget go (CONTRACTS 15.7)."""
    log = open_log(_newer_form())
    doc = log.document
    logic, marker, connections = _logic_bytes(doc)
    # Delete nameEdit, which the newer step list targets and the connection receives.
    log.execute(DeleteNodes((nid(doc, "nameEdit"),)))
    after, marker_after, connections_after = _logic_bytes(doc)
    assert marker_after == marker
    assert {k: v for k, v in after.items()} == {k: v for k, v in logic.items() if k[0] != "nameEdit"}
    assert connections_after == []  # its native connection went with it, as DeleteNodes does
    # Paste a copy of the button (it holds newer logic): the copy's text is kept as copied.
    fragment = selection_fragment(doc, (nid(doc, "clearButton"),))
    log.execute(InsertFragment(paste_placement(doc, (nid(doc, "total"),)), fragment))
    assert texts(doc)[("clearButton_2", "cbcsOnClicked")] == logic[("clearButton", "cbcsOnClicked")]
    assert doc.root.prop("cbcsLogic") == marker
    # Generic property writes of logic keys are refused like SetLogic.
    for command in (
        SetProperty(nid(doc, "total"), "cbcsValue", StringValue("3", notr=True), stdset="0"),
        SetProperty(nid(doc, "other"), "cbcsOnClicked", StringValue("[]", notr=True), stdset="0"),
        SetProperty(doc.root.id, "cbcsLogic", None),
        SetPropertyMany((nid(doc, "other"), nid(doc, "total")), "cbcsVisibleWhen", StringValue("x"), "property", "0"),
    ):
        with pytest.raises(CommandRejected) as caught:
            log.execute(command)
        assert caught.value.code == "FB402"
    # Layout keys are not logic and stay editable.
    log.execute(SetProperty(nid(doc, "other"), "cbcsSplitterSizes", StringValue("1,2"), stdset="0"))
    while log.undo():
        pass
    assert saved(doc) == saved(open_log(_newer_form()).document)


def test_read_only_logic_refuses_taking_a_name_the_newer_text_uses() -> None:
    text = _newer_form().replace("nameEdit + 1", "ghostEdit + 1")
    log = open_log(text)
    doc = log.document
    with pytest.raises(CommandRejected) as caught:
        log.execute(Rename(nid(doc, "total"), "ghostEdit"))
    assert caught.value.code == "FB402"
    assert "no widget can take that name" in str(caught.value)
    log.execute(Rename(nid(doc, "total"), "grandTotal"))


def test_renaming_onto_an_existing_name_is_refused_not_merged() -> None:
    log = open_log(form())
    doc = log.document
    before = saved(doc)
    with pytest.raises(CommandRejected) as caught:
        log.execute(Rename(nid(doc, "other"), "nameEdit"))
    assert caught.value.code == "FB010"
    assert saved(doc) == before


def test_read_only_logic_refuses_renaming_a_widget_its_text_mentions() -> None:
    log = open_log(_newer_form())
    doc = log.document
    before = saved(doc)
    with pytest.raises(CommandRejected) as caught:
        log.execute(Rename(nid(doc, "nameEdit"), "fullName"))
    assert caught.value.code == "FB402"
    assert str(caught.value) == "nameEdit is used by behavior from a newer version of Code Studio, so it can't be renamed here."
    with pytest.raises(CommandRejected):
        log.execute(Rename(nid(doc, "clearButton"), "wipe"))  # a connection sender
    assert saved(doc) == before
    with pytest.raises(CommandRejected):
        log.execute(Rename(nid(doc, "useName"), "useFullName"))  # a NAME token of a formula
    with pytest.raises(CommandRejected):
        log.execute(Rename(nid(doc, "nameError"), "errorLine"))  # an error label
    log.execute(Rename(nid(doc, "total"), "grandTotal"))  # nothing mentions it
    assert nid(doc, "grandTotal")
    assert texts(doc)[("grandTotal", "cbcsValue")] == texts(open_log(_newer_form()).document)[("total", "cbcsValue")]


def test_paste_with_unreadable_or_newer_versions_makes_the_target_read_only() -> None:
    source = open_log(form(marker='{"version":4}'))
    target = open_log(form(marker=""))
    src_doc, doc = source.document, target.document
    fragment = selection_fragment(src_doc, (nid(src_doc, "clearButton"), nid(src_doc, "nameEdit")))
    assert fragment_logic_version(fragment) == 4
    assert all(spec.properties[-1].name == FRAGMENT_LOGIC_PROPERTY for spec in fragment.nodes)
    text = write_fragment(fragment)
    # A dynamic property, never an XML attribute: Qt's ui4 reader refuses unknown attributes.
    assert text.count('<property name="cbcsLogic" stdset="0">') == 2 and "cbcslogicversion" not in text
    again = read_fragment(text)
    assert fragment_logic_version(again) == 4
    before = texts(doc)
    result = target.execute(InsertFragment(paste_placement(doc, (nid(doc, "total"),)), again))
    assert doc.root.prop("cbcsLogic") is not None
    assert doc.root.prop("cbcsLogic").value == StringValue('{"version":4}', notr=True)  # type: ignore[union-attr]
    assert saved(doc).count('name="cbcsLogic"') == 1  # the root's marker only
    new_names = [n for n in doc.names() if n.endswith("_2")]
    assert "nameEdit_2" in new_names and "clearButton_2" in new_names
    # copied as it was: the pasted button still acts on the original nameEdit
    assert texts(doc)[("clearButton_2", "cbcsOnClicked")] == CLEAR_STEPS
    for key, value in before.items():
        assert texts(doc)[key] == value
    assert target.undo_label() is not None and result is not None
    assert target.undo()
    assert doc.root.prop("cbcsLogic") is None


def test_paste_of_a_marker_that_cannot_be_read_counts_as_newer() -> None:
    source = open_log(form(marker="what"))
    target = open_log(form(marker=""))
    src_doc, doc = source.document, target.document
    fragment = selection_fragment(src_doc, (nid(src_doc, "total"),))
    assert fragment_logic_version(fragment) == 2
    target.execute(InsertFragment(paste_placement(doc, (nid(doc, "total"),)), fragment))
    assert doc.root.prop("cbcsLogic").value == StringValue('{"version":2}', notr=True)  # type: ignore[union-attr]


# --- rename participants ---------------------------------------------------


def test_rename_rewrites_only_name_tokens_in_one_undo_step() -> None:
    log = open_log(form())
    doc = log.document
    before_fp = doc.fingerprint()
    before_text = saved(doc)
    log.execute(Rename(nid(doc, "nameEdit"), "fullName"))
    found = texts(doc)
    assert found[("fullName", "cbcsEnabledWhen")] == "useName  and   not (other == fullName)  # nameEdit"
    assert found[("fullName", "cbcsErrorLabel")] == "nameError"
    assert found[("total", "cbcsValue")] == 'f(nameEdit=1, key=fullName) + fullName.nameEdit + "nameEdit"'
    steps = found[("clearButton", "cbcsOnClicked")]
    assert steps == (
        "[\n"
        '  {"do": "slot", "target": "fullName", "slot": "clear()"},\n'
        '  {"do": "call", "when": "len(fullName.text) > 0 and fullName != other", "method": "log_clear"},\n'
        '  {"do": "slot", "target": "other", "slot": "setFocus()", "note": {"keep": "nameEdit"}}\n'
        "]"
    )
    assert found[("fullName", "cbcsValidate")] == (
        "[\n"
        '  {"check": "formula", "formula": "len(fullName.text) > 2", "message": "nameEdit is too short"},\n'
        '  {"check": "range", "min": "today()", "max": 5}\n'
        "]"
    )
    assert [entry.name for entry in doc.node(nid(doc, "clearButton")).properties()] == ["cbcsOnClicked"]
    assert log.undo() and not log.can_undo()
    assert doc.fingerprint() == before_fp and saved(doc) == before_text
    assert log.redo()


def test_rename_updates_the_error_label_and_a_simultaneous_swap_does_not_chain() -> None:
    log = open_log(form())
    doc = log.document
    log.execute(Rename(nid(doc, "nameError"), "nameProblem"))
    assert texts(doc)[("nameEdit", "cbcsErrorLabel")] == "nameProblem"
    from app.features.form_builder.engine.commands.participants import default_registry

    renames = (("nameEdit", "other"), ("other", "nameEdit"))
    ops: List[object] = []
    for participant in default_registry().all():
        rename_ops = getattr(participant, "rename_ops", None)
        if rename_ops is not None:
            ops.extend(rename_ops(doc, renames, None))
    assert ops
    from app.features.form_builder.engine.commands.ops import SetPropertyOp

    flipped = {op.owner: op.entry.value.text for op in ops if isinstance(op, SetPropertyOp) and op.name == "cbcsEnabledWhen"}  # type: ignore[union-attr]
    assert list(flipped.values()) == ["useName  and   not (nameEdit == other)  # nameEdit"]


def test_unreadable_step_lists_are_left_alone_by_a_rename() -> None:
    broken = "[{\"do\": \"slot\", \"target\": \"nameEdit\""
    log = open_log(form().replace(prop_xml("cbcsOnClicked", CLEAR_STEPS), prop_xml("cbcsOnClicked", broken)))
    doc = log.document
    log.execute(Rename(nid(doc, "nameEdit"), "fullName"))
    assert texts(doc)[("clearButton", "cbcsOnClicked")] == broken


# --- paste -----------------------------------------------------------------


def test_paste_points_copied_references_at_the_copies_and_keeps_outside_ones() -> None:
    log = open_log(form())
    doc = log.document
    both = selection_fragment(doc, (nid(doc, "nameEdit"), nid(doc, "clearButton")))
    log.execute(InsertFragment(paste_placement(doc, (nid(doc, "total"),)), both))
    found = texts(doc)
    copy_edit = [n for n in doc.names() if n.startswith("nameEdit") and n != "nameEdit"]
    assert copy_edit == ["nameEdit_2"]
    pasted = found[("clearButton_2", "cbcsOnClicked")]
    assert '"target": "nameEdit_2", "slot": "clear()"' in pasted
    assert '"when": "len(nameEdit_2.text) > 0 and nameEdit_2 != other"' in pasted
    assert '"target": "other"' in pasted  # outside the paste: stays
    assert found[("nameEdit_2", "cbcsEnabledWhen")] == "useName  and   not (other == nameEdit_2)  # nameEdit"
    assert found[("nameEdit_2", "cbcsErrorLabel")] == "nameError"
    # the originals are unchanged
    assert found[("clearButton", "cbcsOnClicked")] == CLEAR_STEPS
    assert found[("nameEdit", "cbcsEnabledWhen")] == "useName  and   not (other == nameEdit)  # nameEdit"
    assert log.undo()
    assert texts(doc) == {key: value for key, value in found.items() if "_2" not in key[0]}


def test_paste_alone_keeps_every_reference_on_the_original() -> None:
    log = open_log(form())
    doc = log.document
    alone = selection_fragment(doc, (nid(doc, "clearButton"),))
    log.execute(InsertFragment(paste_placement(doc, (nid(doc, "total"),)), alone))
    assert texts(doc)[("clearButton_2", "cbcsOnClicked")] == CLEAR_STEPS


# --- delete ----------------------------------------------------------------


def test_delete_keeps_logic_references_untouched() -> None:
    log = open_log(form(connections=CONNECTION))
    doc = log.document
    before = texts(doc)
    log.execute(DeleteNodes((nid(doc, "nameEdit"),)))
    after = texts(doc)
    assert after[("clearButton", "cbcsOnClicked")] == CLEAR_STEPS
    assert after[("total", "cbcsValue")] == before[("total", "cbcsValue")]
    assert doc.connections() == () or len(doc.connections()) == 0  # the native connection went with the widget
    assert doc.root.prop("cbcsLogic") is not None
    assert log.undo()
    assert texts(doc) == before


# --- sequences: undo-all and redo-all --------------------------------------


def _seed() -> int:
    raw = os.environ.get("FB_SEED")
    return int(raw) if raw else 20261029


@pytest.mark.timeout(180)
def test_random_logic_sequences_undo_to_the_start_and_redo_to_the_same_end() -> None:
    names = ["nameEdit", "other", "useName", "clearButton", "total", "nameError"]
    for offset in range(8):
        rng = random.Random(_seed() + offset)
        log = open_log(form(connections=CONNECTION))
        doc = log.document
        start_text, start_fp = saved(doc), doc.fingerprint()
        for _ in range(40):
            live = [n for n in names if doc.by_name(n)]
            roll = rng.randrange(6)
            try:
                if roll == 0 and live:
                    new = rng.choice(["a1", "b2", "c3", "nameEdit", "other"]) + rng.choice(["", "x"])
                    log.execute(Rename(nid(doc, rng.choice(live)), new))
                elif roll == 1 and live:
                    log.execute(SetLogic(nid(doc, rng.choice(live)), "cbcsEnabledWhen", rng.choice([None, "other", "useName and total"])))
                elif roll == 2 and live:
                    steps = '[{"do": "slot", "target": "%s", "slot": "clear()"}]' % rng.choice(names)
                    log.execute(SetLogic(nid(doc, rng.choice(live)), "cbcsOnClicked", rng.choice([None, steps])))
                elif roll == 3 and live:
                    pick = tuple(nid(doc, n) for n in rng.sample(live, min(2, len(live))))
                    fragment = selection_fragment(doc, pick)
                    log.execute(InsertFragment(paste_placement(doc, (nid(doc, rng.choice(live)),)), fragment))
                elif roll == 4 and len(live) > 2:
                    log.execute(DeleteNodes((nid(doc, rng.choice(live)),)))
                elif roll == 5 and log.undo():
                    assert log.redo()
            except CommandRejected:
                pass
            doc.validate()
        end_fp = doc.fingerprint()
        while log.redo():
            pass
        assert doc.fingerprint() == end_fp
        while log.undo():
            pass
        assert saved(doc) == start_text and doc.fingerprint() == start_fp
        while log.redo():
            pass
        assert doc.fingerprint() == end_fp
