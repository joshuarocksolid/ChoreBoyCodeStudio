# pyright: reportAttributeAccessIssue=false
"""M6.1a events engine: storage choice, minimal diff, signal compatibility, the catalog, intents (UX-LST-004/005, UX-PICK-002/004/006/011).

Clauses: UX-LST-004 (conversion is invisible and exact), UX-LST-005 (FB404 and Merge),
UX-PICK-002 (catalog), UX-PICK-004 (intents), UX-PICK-006 (compatibility), UX-PICK-011 (no project code),
CONTRACTS 15.6 rules 1 to 6.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import AddConnection, EditConnection, MoveConnection
from app.features.form_builder.engine.commands.catalog_ext.events import MergeEventStorage, SetEventSteps
from app.features.form_builder.engine.commands.log import replay
from app.features.form_builder.engine.commands.ops import InsertNodeOp, MoveNodeOp, RemoveNodeOp
from app.features.form_builder.engine.diagnostic_codes import discover
from app.features.form_builder.engine.diagnostic_codes.fb40x_events import event_diagnostics
from app.features.form_builder.engine.logic import compat, events_catalog
from app.features.form_builder.engine.logic.events import read_event, read_events, signal_of_property, signal_property
from app.features.form_builder.engine.logic.events_codec import EventStep, call_step, read_list, slot_step, write_list
from app.features.form_builder.engine.logic.intents import m6 as intents
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from tests.form_builder.engine.commands._support import open_log, saved

pytestmark = pytest.mark.unit

discover()

ROOT = "Sale"


def form(extra_connections: str = "", extra_root: str = "", extra_widgets: str = "", extra_tail: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Sale</class>\n'
        ' <widget class="QDialog" name="Sale">\n'
        + extra_root
        + '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        + "".join(
            '   <item>\n    <widget class="%s" name="%s"/>\n   </item>\n' % pair
            for pair in (
                ("QPushButton", "cancelButton"),
                ("QPushButton", "clearButton"),
                ("QLineEdit", "nameEdit"),
                ("QLineEdit", "phoneEdit"),
                ("QCheckBox", "discountCheck"),
                ("QCheckBox", "giftCheck"),
                ("QSpinBox", "qtySpin"),
                ("QSlider", "qtySlider"),
                ("QComboBox", "customerCombo"),
                ("QTabWidget", "tabs"),
                ("QDialogButtonBox", "buttonBox"),
            )
        )
        + '   <item>\n    <spacer name="gap"><property name="orientation"><enum>Qt::Vertical</enum></property></spacer>\n   </item>\n'
        + "  </layout>\n"
        + extra_widgets
        + " </widget>\n <resources/>\n <connections>\n"
        + extra_connections
        + " </connections>\n"
        + extra_tail
        + "</ui>\n"
    )


def connection(sender: str, signal: str, receiver: str, slot: str, hints: bool = False) -> str:
    text = "  <connection>\n   <sender>%s</sender>\n   <signal>%s</signal>\n   <receiver>%s</receiver>\n   <slot>%s</slot>\n" % (
        sender,
        signal,
        receiver,
        slot,
    )
    if hints:
        text += (
            '   <hints>\n    <hint type="sourcelabel">\n     <x>10</x>\n     <y>20</y>\n    </hint>\n'
            '    <hint type="destinationlabel">\n     <x>30</x>\n     <y>40</y>\n    </hint>\n   </hints>\n'
        )
    return text + "  </connection>\n"


def conn_ids(doc) -> List[int]:  # type: ignore[no-untyped-def]
    return [int(node.id) for node in doc.connections()]


def fields(doc) -> List[Tuple[str, str, str, str]]:  # type: ignore[no-untyped-def]
    return [
        (node.field("sender"), node.field("signal"), node.field("receiver"), node.field("slot"))
        for node in doc.connections()
    ]


CLEAR = slot_step("nameEdit", "clear()")
FOCUS = slot_step("phoneEdit", "setFocus()")
CLOSE = slot_step(ROOT, "close()")
PRINT = call_step("print_receipt", 1)


# --- storage choice and conversion (UX-LST-004) -------------------------------------------


def test_plain_steps_are_native_connections_in_list_order() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, FOCUS)))
    doc = log.document
    assert fields(doc) == [
        ("clearButton", "clicked()", "nameEdit", "clear()"),
        ("clearButton", "clicked()", "phoneEdit", "setFocus()"),
    ]
    assert read_event(doc, "clearButton", "clicked").list_property is None
    assert "cbcs" not in saved(doc)


def test_turning_a_step_off_makes_one_list_and_turning_it_on_restores_the_bytes() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, FOCUS)))
    native_text = saved(log.document)
    entries = len(log.entries())
    off = (CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))
    log.execute(SetEventSteps("clearButton", "clicked", off))
    assert len(log.entries()) == entries + 1  # conversion is part of the same step
    text = saved(log.document)
    assert "cbcsOnClicked" in text and text.count("<connection>") == 0 and "cbcsLogic" in text
    state = read_event(log.document, "clearButton", "clicked")
    assert state.steps == off and not state.native
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, FOCUS)))
    assert saved(log.document) == native_text  # no cbcsOnClicked, no cbcsLogic, same order
    assert log.undo() and log.undo() and log.undo()
    assert saved(log.document) == saved(open_log(form()).document)


def test_undo_of_a_conversion_restores_the_previous_bytes_exactly() -> None:
    start = form(connection("clearButton", "clicked()", "nameEdit", "clear()", hints=True))
    log = open_log(start)
    before = saved(log.document)
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))))
    assert saved(log.document) != before
    assert log.undo()
    assert saved(log.document) == before
    assert log.redo() and log.undo()
    assert saved(log.document) == before


def test_one_unreadable_list_is_refused_not_rewritten() -> None:
    text = form(extra_widgets="")
    log = open_log(text)
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))))
    # Break the list by hand, as an editor of the XML would.
    broken = saved(log.document).replace('[\n  {&quot;do&quot;', "[\n  {&quot;do")
    log2 = open_log(broken)
    state = read_event(log2.document, "clearButton", "clicked")
    assert state.list_error is not None
    before = saved(log2.document)
    with pytest.raises(CommandRejected) as caught:
        log2.execute(SetEventSteps("clearButton", "clicked", (CLEAR,)))
    assert caught.value.code == "FB401"
    assert saved(log2.document) == before


# --- minimal diff (rule 3) -----------------------------------------------------------------


def test_adding_a_step_keeps_the_existing_connection_and_its_hints() -> None:
    start = form(
        connection("clearButton", "clicked()", "nameEdit", "clear()", hints=True)
        + connection("cancelButton", "clicked()", "Sale", "close()")
    )
    log = open_log(start)
    before_ids = conn_ids(log.document)
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, FOCUS)))
    doc = log.document
    assert conn_ids(doc)[0] == before_ids[0]  # the same node, hints and all
    assert "<hints>" in saved(doc) and saved(doc).count("<hints>") == 1
    assert [name for name, *_ in fields(doc)] == ["clearButton", "clearButton", "cancelButton"]
    last = log.entries()[-1]
    assert [type(op) for op in last.ops].count(InsertNodeOp) == 1
    assert not any(isinstance(op, (RemoveNodeOp, MoveNodeOp)) for op in last.ops)


def test_a_new_step_in_the_middle_lands_between_its_neighbours_and_nothing_else_moves() -> None:
    start = form(
        connection("clearButton", "clicked()", "nameEdit", "clear()")
        + connection("cancelButton", "clicked()", "Sale", "close()")
        + connection("clearButton", "clicked()", "phoneEdit", "setFocus()")
    )
    log = open_log(start)
    ids = conn_ids(log.document)
    middle = slot_step("phoneEdit", "clear()")
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, middle, FOCUS)))
    now = fields(log.document)
    clear_rows = [row for row in now if row[0] == "clearButton"]
    assert [row[3] for row in clear_rows] == ["clear()", "clear()", "setFocus()"]
    assert [row[2] for row in clear_rows] == ["nameEdit", "phoneEdit", "phoneEdit"]
    after = conn_ids(log.document)
    assert [i for i in after if i in ids] == ids  # old elements keep their order
    assert not any(isinstance(op, (RemoveNodeOp, MoveNodeOp)) for op in log.entries()[-1].ops)


def test_reordering_two_steps_moves_one_element_and_other_events_stay() -> None:
    start = form(
        connection("clearButton", "clicked()", "nameEdit", "clear()", hints=True)
        + connection("cancelButton", "clicked()", "Sale", "close()")
        + connection("clearButton", "clicked()", "phoneEdit", "setFocus()")
    )
    log = open_log(start)
    ids = conn_ids(log.document)
    log.execute(SetEventSteps("clearButton", "clicked", (FOCUS, CLEAR)))
    ops = log.entries()[-1].ops
    assert [type(op) for op in ops] == [MoveNodeOp]
    after = conn_ids(log.document)
    assert sorted(after) == sorted(ids)
    assert [i for i in after if i != ids[1]] == [ids[2], ids[0]]
    assert saved(log.document).count("<hints>") == 1


def test_deleting_the_middle_step_removes_exactly_that_element() -> None:
    start = form(
        connection("clearButton", "clicked()", "nameEdit", "clear()", hints=True)
        + connection("clearButton", "clicked()", "phoneEdit", "clear()")
        + connection("clearButton", "clicked()", "phoneEdit", "setFocus()", hints=True)
    )
    log = open_log(start)
    ids = conn_ids(log.document)
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, FOCUS)))
    assert conn_ids(log.document) == [ids[0], ids[2]]
    assert [type(op) for op in log.entries()[-1].ops] == [RemoveNodeOp]
    assert saved(log.document).count("<hints>") == 2


def test_first_connection_of_an_event_goes_after_its_senders_last_connection() -> None:
    start = form(
        connection("clearButton", "pressed()", "nameEdit", "clear()")
        + connection("cancelButton", "clicked()", "Sale", "close()")
        + connection("clearButton", "pressed()", "phoneEdit", "clear()")
        + connection("nameEdit", "returnPressed()", "phoneEdit", "setFocus()")
    )
    log = open_log(start)
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR,)))
    rows = fields(log.document)
    assert rows[3][:2] == ("clearButton", "clicked()")  # right after clearButton's last connection
    assert rows[4][0] == "nameEdit"


# --- overload choice, methods, declarations (rules 2 and 4) --------------------------------


def test_the_overload_is_the_one_with_the_fewest_arguments_that_covers_the_step() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR,)))
    log.execute(SetEventSteps("discountCheck", "toggled", (slot_step("giftCheck", "setChecked(bool)"),)))
    log.execute(SetEventSteps("cancelButton", "clicked", (slot_step("giftCheck", "setChecked(bool)"),)))
    log.execute(SetEventSteps("customerCombo", "currentIndexChanged", (slot_step("tabs", "setCurrentIndex(int)"),)))
    rows = fields(log.document)
    assert rows[0][1] == "clicked()"
    assert rows[1][1] == "toggled(bool)"
    assert rows[2][1] == "clicked(bool)"  # the slot needs the checked value
    assert rows[3][1] == "currentIndexChanged(int)"


def test_a_call_step_connects_to_the_form_and_declares_the_method_once() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("cancelButton", "clicked", (call_step("print_receipt", 0),)))
    log.execute(SetEventSteps("clearButton", "clicked", (call_step("print_receipt", 1),)))
    doc = log.document
    assert fields(doc) == [
        ("cancelButton", "clicked()", ROOT, "print_receipt()"),
        ("clearButton", "clicked(bool)", ROOT, "print_receipt(bool)"),
    ]
    assert text_between(saved(doc), "<slots>", "</slots>").count("print_receipt") == 1
    state = read_event(doc, "clearButton", "clicked")
    assert state.steps == (call_step("print_receipt", 1),)  # a declared form slot reads back as a call


def text_between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_removing_the_last_step_keeps_the_declaration() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("cancelButton", "clicked", (call_step("print_receipt", 0),)))
    log.execute(SetEventSteps("cancelButton", "clicked", ()))
    text = saved(log.document)
    assert "<connection>" not in text
    assert "<slot>print_receipt()</slot>" in text


def test_steps_that_cannot_run_are_refused_and_change_nothing() -> None:
    log = open_log(form())
    before = saved(log.document)
    bad = [
        ("cancelButton", "clicked", (slot_step("nameEdit", "setText(QString)"),), "needs more values"),
        ("cancelButton", "clicked", (slot_step("ghost", "clear()"),), "isn't on this form"),
        ("cancelButton", "clicked", (call_step("print_receipt", 5),), "more values"),
        ("cancelButton", "clicked", (call_step("not valid", 0),), "isn't a name"),
        ("cancelButton", "doesNotExist", (CLEAR,), "no event"),
        ("verticalLayout", "clicked", (CLEAR,), "Layouts and spacers"),
        ("gap", "clicked", (CLEAR,), "Layouts and spacers"),
    ]
    for sender, signal, steps, words in bad:
        with pytest.raises(CommandRejected) as caught:
            log.execute(SetEventSteps(sender, signal, steps))
        assert words in str(caught.value), (sender, str(caught.value))
        assert saved(log.document) == before
    assert not log.entries()


# --- FB402 (rule 1) ------------------------------------------------------------------------

NEWER = (
    '  <property name="cbcsLogic" stdset="0">\n   <string notr="true">{"version":2}</string>\n  </property>\n'
)


def test_a_newer_logic_version_refuses_every_event_write() -> None:
    start = form(connection("clearButton", "clicked()", "nameEdit", "clear()"), extra_root=NEWER)
    log = open_log(start)
    before = saved(log.document)
    node_id = log.document.connections()[0].id
    for command in (
        SetEventSteps("clearButton", "clicked", (CLEAR, FOCUS)),
        MergeEventStorage("clearButton", "clicked"),
        AddConnection("cancelButton", "clicked()", ROOT, "close()"),
        EditConnection(node_id, slot="setFocus()"),
        MoveConnection(node_id, 0),
    ):
        with pytest.raises(CommandRejected) as caught:
            log.execute(command)
        assert caught.value.code == "FB402", command
    assert saved(log.document) == before and not log.entries()


def test_editing_a_connections_receiver_drops_its_hints_and_other_edits_keep_them() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()", hints=True)))
    node_id = log.document.connections()[0].id
    log.execute(EditConnection(node_id, slot="clear()"))
    assert "<hints>" in saved(log.document)
    log.execute(EditConnection(node_id, receiver="phoneEdit"))
    assert "<hints>" not in saved(log.document)
    assert log.undo()
    assert "<hints>" in saved(log.document)


# --- FB404, Merge, FB405 -------------------------------------------------------------------


def test_designer_made_native_plus_a_list_is_fb404_and_merge_puts_the_native_steps_first() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()", hints=True)))
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))))
    # Designer adds a connection to an event that has a list: both are stored.
    mixed = saved(log.document).replace(
        " <connections/>\n",
        " <connections>\n" + connection("clearButton", "clicked()", "phoneEdit", "clear()") + " </connections>\n",
    )
    log = open_log(mixed)
    state = read_event(log.document, "clearButton", "clicked")
    assert state.stored_twice
    assert [d.code for d in event_diagnostics(log.document)] == ["FB404"]
    fix = event_diagnostics(log.document)[0].fixes[0].command
    entries = len(log.entries())
    log.execute(fix)
    assert len(log.entries()) == entries + 1
    merged = read_event(log.document, "clearButton", "clicked")
    assert merged.steps == (slot_step("phoneEdit", "clear()"), CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))
    assert not merged.native and not event_diagnostics(log.document)
    assert log.undo()
    assert read_event(log.document, "clearButton", "clicked").stored_twice


def test_merge_of_all_plain_steps_ends_as_native_connections() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    # a list of plain steps written by a hand editor, next to the connection
    text = saved(log.document).replace(
        '<widget class="QPushButton" name="clearButton"/>',
        '<widget class="QPushButton" name="clearButton">\n    <property name="cbcsOnClicked" stdset="0"><string notr="true">'
        + write_list((FOCUS,)).replace('"', "&quot;")
        + "</string></property>\n   </widget>",
    )
    log = open_log(text)
    assert read_event(log.document, "clearButton", "clicked").stored_twice
    log.execute(MergeEventStorage("clearButton", "clicked"))
    state = read_event(log.document, "clearButton", "clicked")
    assert state.steps == (CLEAR, FOCUS) and len(state.native) == 2 and state.list_property is None


def test_a_list_step_whose_target_left_the_form_is_fb405() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))))
    text = saved(log.document).replace("&quot;target&quot;: &quot;nameEdit&quot;", "&quot;target&quot;: &quot;gone&quot;")
    log = open_log(text)
    found = [d for d in event_diagnostics(log.document) if d.code == "FB405"]
    assert len(found) == 1
    assert "Step 1 of clearButton clicked acts on gone, which isn't on this form." == found[0].message
    # The step stays editable in place: other steps can change while the broken one is kept.
    state = read_event(log.document, "clearButton", "clicked")
    log.execute(SetEventSteps("clearButton", "clicked", state.steps[:1]))
    assert read_event(log.document, "clearButton", "clicked").steps[0].target == "gone"


# --- the storage invariant over random sequences (CONTRACTS 13) ---------------------------

EVENTS = (
    ("cancelButton", "clicked"),
    ("clearButton", "clicked"),
    ("discountCheck", "toggled"),
    ("qtySpin", "valueChanged"),
    ("nameEdit", "returnPressed"),
    ("customerCombo", "currentIndexChanged"),
)
MESSAGE = read_list('[{"do": "message", "text": "hi"}]').steps[0]


def _pool(signal: str) -> List[EventStep]:
    base = [CLOSE, CLEAR, FOCUS, slot_step("giftCheck", "toggle()"), call_step("m_none", 0), call_step("m_one", 1), MESSAGE]
    if signal in ("toggled", "valueChanged", "currentIndexChanged"):
        base.append(slot_step("tabs", "setCurrentIndex(int)") if signal == "currentIndexChanged" else slot_step("giftCheck", "setChecked(bool)"))
    return base


def _invariants(doc, sender: str, signal: str, wanted: Tuple[EventStep, ...]) -> None:  # type: ignore[no-untyped-def]
    state = read_event(doc, sender, signal)
    assert state.steps == wanted
    if all(step.plain for step in wanted):
        assert state.list_property is None and len(state.native) == len(wanted)
    else:
        assert not state.native and state.list_property is not None
    assert (doc.root.prop("cbcsLogic") is not None) == (doc.logic_property_count() > 0)


@pytest.mark.parametrize("seed", range(12))
def test_storage_invariant_over_random_sequences(seed: int) -> None:
    rng = random.Random(seed)
    log = open_log(form(connection("cancelButton", "clicked()", ROOT, "close()", hints=True)))
    original = saved(log.document)
    wanted: Dict[Tuple[str, str], Tuple[EventStep, ...]] = {}
    declared_before: set = set()
    for _ in range(40):
        sender, signal = rng.choice(EVENTS)
        current = list(read_event(log.document, sender, signal).steps)
        roll = rng.randrange(6)
        pool = _pool(signal)
        if roll == 0 or not current:
            current.insert(rng.randrange(len(current) + 1), rng.choice(pool))
        elif roll == 1:
            current.pop(rng.randrange(len(current)))
        elif roll == 2 and len(current) > 1:
            current.insert(rng.randrange(len(current)), current.pop(rng.randrange(len(current))))
        elif roll == 3:
            index = rng.randrange(len(current))
            step = current[index]
            if step.raw is None:
                current[index] = EventStep(**{**step.__dict__, "enabled": not step.enabled})
        elif roll == 4:
            current.insert(rng.randrange(len(current) + 1), rng.choice(pool))
        else:
            current = []
        before_text = saved(log.document)
        others_before = [
            row for row in fields(log.document) if not (row[0] == sender and row[1].split("(")[0] == signal)
        ]
        others_ids = [
            int(n.id)
            for n in log.document.connections()
            if not (n.field("sender") == sender and str(n.field("signal")).split("(")[0] == signal)
        ]
        count = len(log.entries())
        try:
            log.execute(SetEventSteps(sender, signal, tuple(current)))
        except CommandRejected:
            assert saved(log.document) == before_text
            continue
        doc = log.document
        wanted[(sender, signal)] = tuple(current)
        _invariants(doc, sender, signal, tuple(current))
        assert [
            row for row in fields(doc) if not (row[0] == sender and row[1].split("(")[0] == signal)
        ] == others_before
        assert [
            int(n.id)
            for n in doc.connections()
            if not (n.field("sender") == sender and str(n.field("signal")).split("(")[0] == signal)
        ] == others_ids
        declared_now = {s for s in _declared(doc)}
        assert declared_before <= declared_now  # declarations are never lost
        declared_before = declared_now
        if rng.random() < 0.4 and len(log.entries()) == count + 1:
            after_text = saved(doc)
            assert log.undo()
            assert saved(log.document) == before_text
            assert log.redo()
            assert saved(log.document) == after_text
    for (sender, signal), steps in wanted.items():
        _invariants(log.document, sender, signal, steps)
    assert replay(original, log.entries()).fingerprint() == log.document.fingerprint()
    while log.undo():
        pass
    assert saved(log.document) == original


def _declared(doc) -> List[str]:  # type: ignore[no-untyped-def]
    declared = doc.ui.field("form_slots")
    return list(getattr(declared, "slots", ()) or ())


# --- compatibility (UX-PICK-006) ---------------------------------------------------------


@pytest.mark.parametrize(
    "slot,signal,expected",
    [
        ("clear()", "clicked(bool)", True),
        ("setChecked(bool)", "clicked(bool)", True),
        ("setChecked(bool)", "clicked()", False),
        ("setValue(int)", "valueChanged(int)", True),
        ("setValue(double)", "valueChanged(int)", False),
        ("setText(const QString&)", "textChanged(QString)", True),
        ("move(int,int)", "sectionMoved(int,int,int)", True),
        ("setValue(qreal)", "valueChanged(double)", True),
    ],
)
def test_a_slot_fits_when_its_parameters_are_a_prefix_after_normalising(slot: str, signal: str, expected: bool) -> None:
    assert compat.fits(compat.split_signature(slot)[1], compat.split_signature(signal)[1]) is expected


def test_incompatible_slots_say_why_in_the_spec_words() -> None:
    overloads = compat.overloads_of(("clicked(bool)", "clicked()"), "clicked")
    assert compat.slot_fit("setChecked(bool)", overloads, "clicked").ok
    none_sent = compat.overloads_of(("returnPressed()",), "returnPressed")
    fit = compat.slot_fit("setChecked(bool)", none_sent, "Enter is pressed")
    assert not fit.ok and fit.reason == "Needs yes or no; Enter is pressed sends nothing."
    sends = compat.overloads_of(("textChanged(QString)",), "textChanged")
    fit = compat.slot_fit("setValue(int)", sends, "the text changes")
    assert fit.reason == "Needs a whole number; the text changes sends text."


# --- the catalog (UX-PICK-002) -------------------------------------------------------------


def test_every_common_and_default_event_exists_on_its_class() -> None:
    classes = QtClassTable.shared()
    for class_name, row in events_catalog._CLASS_EVENTS.items():  # noqa: SLF001
        known = {compat.split_signature(item)[0] for item in classes.signals(class_name)}
        assert known, class_name
        for name in row.common:
            assert name in known, (class_name, name)
        assert row.default is None or row.default in row.common


def test_a_subclass_uses_its_base_row_and_an_own_class_adds_its_declared_signals() -> None:
    classes = QtClassTable.shared()
    assert events_catalog.default_event(classes, "QCommandLinkButton") == "clicked"
    assert events_catalog.default_event(classes, "QRadioButton") == "toggled"
    assert events_catalog.common_events(classes, "QCheckBox") == ("toggled", "clicked")
    assert events_catalog.common_events(classes, "QPushButton", ("tilted(int)",)) == ("clicked", "tilted")
    assert events_catalog.default_event(classes, "QLabel") is None
    more = events_catalog.more_events(classes, "QLineEdit")
    assert "cursorPositionChanged" in more and "editingFinished" not in more and "destroyed" not in more


def test_event_words_follow_the_class_and_fall_back_to_the_signal_name() -> None:
    assert events_catalog.event_words("clicked", ("QDialogButtonBox", "QWidget")).header == "any of its buttons is clicked"
    assert events_catalog.event_words("returnPressed").header == "Enter is pressed"
    assert events_catalog.event_words("currentChanged", ("QTabWidget",)).short == "page_changed"
    odd = events_catalog.event_words("selectionBehaviorChanged")
    assert (odd.header, odd.short) == ("selectionBehaviorChanged", "selection_behavior_changed")


# --- intents (UX-PICK-004) -----------------------------------------------------------------


def _form_for_intents() -> str:
    return form()


def test_intents_are_offered_by_sender_class_and_dialog_root() -> None:
    log = open_log(_form_for_intents())
    doc, classes = log.document, QtClassTable.shared()
    offered = lambda sender, event=None: [i.intent_id for i in intents.intents_for(doc, classes, sender, event)]  # noqa: E731
    assert offered("clearButton") == ["close-form", "accept", "reject", "clear-field", "move-focus"]
    assert offered("discountCheck") == ["close-form", "accept", "reject", "clear-field", "move-focus", "check-same-way"]
    assert offered("nameEdit") == ["next-field"]
    assert offered("nameEdit", "editingFinished") == []
    assert offered("customerCombo") == ["show-page"]
    assert offered("qtySpin") == ["keep-in-step"] and offered("qtySlider") == ["keep-in-step"]
    assert offered("buttonBox") == ["buttons-accept-reject"]
    plain = open_log(form().replace('class="QDialog" name="Sale"', 'class="QWidget" name="Sale"')).document
    assert "accept" not in [i.intent_id for i in intents.intents_for(plain, classes, "clearButton")]


def test_target_pages_list_fitting_widgets_in_reading_order() -> None:
    log = open_log(_form_for_intents())
    doc, classes = log.document, QtClassTable.shared()
    by_id = {i.intent_id: i for i in intents.INTENTS}
    assert intents.target_candidates(doc, classes, by_id["clear-field"], "clearButton") == ("nameEdit", "phoneEdit", "qtySpin", "customerCombo")
    assert intents.target_candidates(doc, classes, by_id["check-same-way"], "discountCheck") == ("giftCheck",)
    assert intents.target_candidates(doc, classes, by_id["show-page"], "customerCombo") == ("tabs",)
    assert intents.target_candidates(doc, classes, by_id["keep-in-step"], "qtySpin") == ("qtySlider",)
    assert "Sale" not in intents.target_candidates(doc, classes, by_id["move-focus"], "clearButton")
    assert intents.default_target(doc, by_id["next-field"], "nameEdit") == "phoneEdit"


def test_an_intent_is_one_undo_step_that_adds_after_the_existing_steps() -> None:
    log = open_log(_form_for_intents())
    classes = QtClassTable.shared()
    by_id = {i.intent_id: i for i in intents.INTENTS}
    log.execute(intents.command(log.document, classes, by_id["close-form"], "cancelButton"))
    assert log.undo_label() == "Add Close this form to cancelButton clicked"
    assert fields(log.document) == [("cancelButton", "clicked()", ROOT, "close()")]
    log.execute(intents.command(log.document, classes, by_id["clear-field"], "clearButton", "nameEdit"))
    log.execute(intents.command(log.document, classes, by_id["move-focus"], "clearButton", "phoneEdit"))
    assert [row[3] for row in fields(log.document) if row[0] == "clearButton"] == ["clear()", "setFocus()"]
    entries = len(log.entries())
    log.execute(intents.command(log.document, classes, by_id["keep-in-step"], "qtySpin", "qtySlider", display=str.upper))
    assert len(log.entries()) == entries + 1 and log.undo_label() == "Keep QTYSPIN and QTYSLIDER in step"
    assert fields(log.document)[-2:] == [
        ("qtySpin", "valueChanged(int)", "qtySlider", "setValue(int)"),
        ("qtySlider", "valueChanged(int)", "qtySpin", "setValue(int)"),
    ]
    log.execute(intents.command(log.document, classes, by_id["buttons-accept-reject"], "buttonBox"))
    assert log.undo_label() == "Make OK accept and Cancel close"
    assert fields(log.document)[-2:] == [
        ("buttonBox", "accepted()", ROOT, "accept()"),
        ("buttonBox", "rejected()", ROOT, "reject()"),
    ]
    assert log.undo() and log.undo() and log.undo()
    assert [row for row in fields(log.document) if row[0] == "qtySpin"] == []


def test_the_cbcs_on_property_name_is_reversible() -> None:
    for name in ("clicked", "valueChanged", "x"):
        assert signal_of_property(signal_property(name)) == name
    assert signal_of_property("cbcsOn") is None and signal_of_property("cbcsOnclicked") is None
    assert signal_of_property("cbcsLogic") is None


# --- reading events never imports project code (UX-PICK-011) --------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.names: List[str] = []

    def find_spec(self, name, path=None, target=None):  # type: ignore[no-untyped-def]
        self.names.append(name)
        return None


def test_events_over_a_promoted_class_read_declarations_only(tmp_path: Path) -> None:
    custom = (
        " <customwidgets>\n  <customwidget>\n   <class>TillButton</class>\n   <extends>QPushButton</extends>\n"
        "   <header location=\"local\">till_button.h</header>\n   <slots>\n    <signal>tilted(int)</signal>\n"
        "    <slot>bump()</slot>\n   </slots>\n  </customwidget>\n </customwidgets>\n"
    )
    text = form(extra_tail="").replace(
        '<widget class="QPushButton" name="clearButton"/>', '<widget class="TillButton" name="clearButton"/>'
    ).replace(" <resources/>\n", custom + " <resources/>\n")
    (tmp_path / "till_button.py").write_text("raise SystemExit('imported')\n", encoding="utf-8")
    recorder = _Recorder()
    sys.path.insert(0, str(tmp_path))
    sys.meta_path.insert(0, recorder)
    try:
        log = open_log(text)
        doc, classes = log.document, QtClassTable.shared()
        node = doc.node(doc.by_name("clearButton")[0])
        class_name, declared = compat.node_class(doc, classes, node)
        signals = compat.signals_of(classes, class_name, declared)
        assert class_name == "QPushButton" and "tilted(int)" in signals
        assert events_catalog.common_events(classes, class_name, declared.signals) == ("clicked", "tilted")
        log.execute(SetEventSteps("clearButton", "tilted", (call_step("on_tilt", 1), slot_step("nameEdit", "clear()"))))
        assert [row[1] for row in fields(doc)] == ["tilted(int)", "tilted(int)"]
        assert intents.intents_for(doc, classes, "clearButton")
        assert read_events(doc)
    finally:
        sys.meta_path.remove(recorder)
        sys.path.remove(str(tmp_path))
    assert "till_button" not in sys.modules and "till_button" not in recorder.names


# --- the codec and the neighbours' APIs (strict xfails for other lanes) -------------------


@pytest.mark.xfail(strict=True, reason="M6.0b: engine/logic/codec.py (parse_steps, write_steps) has not merged")
def test_m6_0b_codec_api_is_present() -> None:
    from app.features.form_builder.engine.logic import codec  # type: ignore[attr-defined]

    read = codec.parse_steps(write_list((CLEAR, FOCUS)))
    assert read.error is None and len(read.steps) == 2
    assert codec.write_steps(read.steps) == write_list((CLEAR, FOCUS))


@pytest.mark.xfail(strict=True, reason="M6.0b: storage.signal_property / signal_of_property are not in logic/storage.py yet")
def test_m6_0b_storage_owns_the_signal_property_names() -> None:
    from app.features.form_builder.engine.logic import storage

    assert storage.signal_property("clicked") == "cbcsOnClicked"  # type: ignore[attr-defined]


@pytest.mark.xfail(strict=True, reason="M6.0b: new cbcsOn* entries of one owner are inserted among themselves by name (CONTRACTS 15.1)")
def test_m6_0b_cbcs_on_entries_rank_by_name_when_inserted() -> None:
    log = open_log(form())
    log.execute(SetEventSteps("nameEdit", "textChanged", (CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))))
    log.execute(SetEventSteps("nameEdit", "editingFinished", (CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False))))
    names = [entry.name for entry in log.document.node(log.document.by_name("nameEdit")[0]).properties()]
    assert names == ["cbcsOnEditingFinished", "cbcsOnTextChanged"]
