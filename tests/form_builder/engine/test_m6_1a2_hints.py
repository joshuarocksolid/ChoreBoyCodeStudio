# pyright: reportAttributeAccessIssue=false
"""M6.1a2: Designer ``<hints>`` survive native, step list, native (CONTRACTS 15.6).

Turning a step off and back on keeps the connection's hint points. A changed
receiver or slot drops them. Generated Python ignores them.
"""

from __future__ import annotations

import ast
import random
from dataclasses import replace
from pathlib import Path
from typing import List, Sequence, Tuple

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import EditConnection
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import parse_steps, write_steps
from app.features.form_builder.engine.logic.events import read_event
from app.features.form_builder.engine.logic.events_codec import EventStep, call_step, read_list, slot_step
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.engine.test_m6_1a_events import ROOT, connection, form

pytestmark = pytest.mark.unit

POINTS = (("sourcelabel", 10, 20), ("destinationlabel", 30, 40), ("bend", -5, 6))
_POOL = (
    slot_step("phoneEdit", "setFocus()"),
    slot_step("phoneEdit", "clear()"),
    slot_step("giftCheck", "toggle()"),
    call_step("m_none", 0),
)


def _hinted(sender: str, signal: str, receiver: str, slot: str) -> str:
    body = "".join(
        '    <hint type="%s">\n     <x>%d</x>\n     <y>%d</y>\n    </hint>\n' % point for point in POINTS
    )
    return (
        "  <connection>\n   <sender>%s</sender>\n   <signal>%s</signal>\n   <receiver>%s</receiver>\n   <slot>%s</slot>\n"
        "   <hints>\n%s   </hints>\n  </connection>\n"
    ) % (sender, signal, receiver, slot, body)


def _hints_block(text: str, sender: str) -> str:
    start = 0
    while True:
        at = text.find("<connection>", start)
        assert at >= 0, sender
        end = text.find("</connection>", at)
        block = text[at:end]
        start = end + 1
        if "<sender>%s</sender>" % sender not in block or "<hints>" not in block:
            continue
        begin = block.find("<hints>")
        return block[begin : block.find("</hints>") + len("</hints>")]


def _saved_steps(sender: str, signal: str, steps: Sequence[EventStep]) -> str:
    log = open_log(form())
    log.execute(SetEventSteps(sender, signal, tuple(steps)))
    return saved(log.document)


def _generate(text: str, tmp_path: Path, name: str) -> str:
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(tmp_path / ("%s.ui" % name)),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / ("ui_%s.py" % name)),
        window_path=str(tmp_path / ("%s_window.py" % name)),
        module_name="ui_%s" % name,
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    return result.text


def _expected(old: Sequence[EventStep], submitted: Sequence[EventStep]) -> Tuple[EventStep, ...]:
    """Hints stay on the same receiver and slot. Copied onto a different end, they go."""
    out: List[EventStep] = []
    for step in submitted:
        hints = step.hints
        if step.verb == "slot" and hints:
            same = any(
                prior.verb == "slot" and prior.hints == hints and prior.target == step.target and prior.slot == step.slot
                for prior in old
            )
            copied = any(
                prior.verb == "slot"
                and prior.hints == hints
                and (prior.target != step.target or prior.slot != step.slot)
                for prior in old
            )
            if copied and not same:
                hints = ()
        out.append(step if hints == step.hints else replace(step, hints=hints))
    return tuple(out)


def test_off_then_on_restores_identical_hints() -> None:
    start = form(
        _hinted("clearButton", "clicked()", "nameEdit", "clear()")
        + connection("cancelButton", "clicked()", ROOT, "close()")
    )
    original = _hints_block(start, "clearButton")
    log = open_log(start)
    step = read_event(log.document, "clearButton", "clicked").steps[0]
    assert step.hints == POINTS
    log.execute(SetEventSteps("clearButton", "clicked", (replace(step, enabled=False),)))
    listed = saved(log.document)
    assert listed.count("<sender>clearButton</sender>") == 0
    assert "sourcelabel" in listed and "bend" in listed and "-5" in listed
    back = read_event(log.document, "clearButton", "clicked").steps[0]
    assert back.hints == POINTS and not back.enabled
    log.execute(SetEventSteps("clearButton", "clicked", (replace(back, enabled=True),)))
    restored = saved(log.document)
    assert _hints_block(restored, "clearButton") == original
    assert read_event(log.document, "clearButton", "clicked").steps[0].hints == POINTS
    assert "<sender>cancelButton</sender>" in restored


@pytest.mark.parametrize(
    "target,slot,keep",
    [
        ("nameEdit", "clear()", True),
        ("phoneEdit", "clear()", False),
        ("nameEdit", "setFocus()", False),
        ("phoneEdit", "setFocus()", False),
    ],
)
def test_hints_drop_only_when_the_receiver_or_slot_changes(target: str, slot: str, keep: bool) -> None:
    log = open_log(form(_hinted("clearButton", "clicked()", "nameEdit", "clear()")))
    step = read_event(log.document, "clearButton", "clicked").steps[0]
    log.execute(SetEventSteps("clearButton", "clicked", (replace(step, target=target, slot=slot),)))
    got = read_event(log.document, "clearButton", "clicked").steps[0]
    assert got.target == target and got.slot == slot
    assert got.hints == (POINTS if keep else ())
    assert ("<hints>" in saved(log.document)) is keep


@pytest.mark.parametrize("seed", range(8))
def test_hints_survive_random_sequences_that_keep_the_arrow_end(seed: int) -> None:
    rng = random.Random(seed)
    log = open_log(
        form(
            _hinted("clearButton", "clicked()", "nameEdit", "clear()")
            + connection("cancelButton", "clicked()", ROOT, "close()", hints=True)
        )
    )
    other_id = log.document.connections()[1].id
    other_hints = log.document.node(other_id).field("hints")
    for _ in range(24):
        old = read_event(log.document, "clearButton", "clicked").steps
        current = list(old)
        roll = rng.randrange(6)
        if not current or roll == 0:
            current.insert(rng.randrange(len(current) + 1), rng.choice(_POOL))
        elif roll == 1 and len(current) > 1:
            current.insert(rng.randrange(len(current)), current.pop(rng.randrange(len(current))))
        elif roll == 2 and current:
            index = rng.randrange(len(current))
            step = current[index]
            if step.raw is None:
                current[index] = replace(step, enabled=not step.enabled)
        elif roll == 3:
            index = next((i for i, step in enumerate(current) if step.verb == "slot" and step.hints), None)
            if index is None:
                continue
            step = current[index]
            if rng.randrange(2):
                current[index] = replace(step, target="phoneEdit")
            else:
                current[index] = replace(step, slot="setFocus()")
        elif roll == 4 and current:
            current.pop(rng.randrange(len(current)))
        else:
            current = []
        expected = _expected(old, current)
        before = saved(log.document)
        count = len(log.entries())
        try:
            log.execute(SetEventSteps("clearButton", "clicked", tuple(current)))
        except CommandRejected:
            assert saved(log.document) == before
            continue
        state = read_event(log.document, "clearButton", "clicked")
        assert state.steps == expected
        if all(step.plain for step in expected):
            assert state.list_property is None and len(state.native) == len(expected)
        elif expected:
            assert not state.native and state.list_property is not None
        assert log.document.node(other_id).field("hints") == other_hints
        if rng.random() < 0.35 and len(log.entries()) == count + 1:
            after = saved(log.document)
            assert log.undo() and saved(log.document) == before
            assert log.redo() and saved(log.document) == after


def test_editing_slot_or_sender_drops_hints_and_reordering_keeps_them() -> None:
    log = open_log(
        form(
            _hinted("clearButton", "clicked()", "nameEdit", "clear()")
            + connection("clearButton", "clicked()", "phoneEdit", "setFocus()")
        )
    )
    before = saved(log.document)
    node_id = log.document.connections()[0].id
    log.execute(EditConnection(node_id, slot="clear()"))
    assert "<hints>" in saved(log.document)
    log.execute(EditConnection(node_id, slot="setFocus()"))
    assert "<hints>" not in saved(log.document)
    assert log.undo() and saved(log.document) == before
    log.execute(EditConnection(node_id, sender="cancelButton"))
    assert "<hints>" not in saved(log.document)
    assert log.undo() and saved(log.document) == before
    steps = read_event(log.document, "clearButton", "clicked").steps
    log.execute(SetEventSteps("clearButton", "clicked", (steps[1], steps[0])))
    assert _hints_block(saved(log.document), "clearButton") == _hints_block(before, "clearButton")


def test_codec_round_trip_rejects_hostile_hints_and_python_stays_39(tmp_path: Path) -> None:
    raw = (
        '[{"do":"slot","hints":{"destinationlabel":[4,5],"sourcelabel":[1,2]},'
        '"slot":"clear()","target":"nameEdit","enabled":true}]'
    )
    read = parse_steps(raw)
    assert read.error is None
    text = write_steps(read.steps)
    assert text == (
        "[\n"
        '  {"do": "slot", "target": "nameEdit", "slot": "clear()", '
        '"hints": {"destinationlabel": [4, 5], "sourcelabel": [1, 2]}}\n'
        "]"
    )
    assert write_steps(parse_steps(text).steps) == text
    assert read_list(text).steps[0].hints == (("destinationlabel", 4, 5), ("sourcelabel", 1, 2))
    edge = '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"sourcelabel": [%d, %d]}}]' % (
        -2147483648,
        2147483647,
    )
    assert parse_steps(edge).error is None
    omitted = parse_steps('[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {}}]')
    assert omitted.error is None and omitted.steps[0].field("hints") is None
    hostile = [
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"sourcelabel": [1.5, 2]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"sourcelabel": [true, 1]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"sourcelabel": [1.0, 2]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"sourcelabel": [2147483648, 0]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"sourcelabel": [-2147483649, 0]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"bad\\ntype": [1, 2]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"x\\"><y": [1, 2]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": {"sourcelabel": [1, 2], "sourcelabel": [3, 4]}}]',
        '[{"do": "slot", "target": "nameEdit", "slot": "clear()", "hints": ["sourcelabel", 1, 2]}]',
    ]
    for item in hostile:
        refused = parse_steps(item)
        assert refused.error is not None and refused.steps == (), item
    escaped = hostile[5].replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    ui = form().replace(
        '<widget class="QPushButton" name="clearButton"/>',
        '<widget class="QPushButton" name="clearButton">\n'
        '    <property name="cbcsOnClicked" stdset="0"><string notr="true">%s</string></property>\n'
        "   </widget>" % escaped,
    )
    source = _generate(ui, tmp_path, "hostile")
    ast.parse(source, feature_version=(3, 9))
    assert "def _cbcs_" not in source
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom)) and any(alias.name.split(".")[0] == "os" for alias in node.names)
        for node in ast.walk(ast.parse(source))
    )


def _without_source_hash(text: str) -> str:
    """The module apart from the banner line that hashes the ``.ui`` bytes."""
    return "\n".join(line for line in text.split("\n") if not line.startswith("## cbcs-source-sha256:"))


def test_codegen_is_identical_with_and_without_hints(tmp_path: Path) -> None:
    off = slot_step("phoneEdit", "setFocus()", enabled=False)
    plain = slot_step("nameEdit", "clear()")
    hinted = replace(plain, hints=POINTS)
    listed_with = _saved_steps("clearButton", "clicked", (hinted, off))
    listed_without = _saved_steps("clearButton", "clicked", (plain, off))
    assert "sourcelabel" in listed_with and "sourcelabel" not in listed_without
    same_list = _generate(listed_with, tmp_path, "sale")
    other_list = _generate(listed_without, tmp_path, "sale")
    assert same_list != other_list  # the banner hashes the .ui, and the .ui kept the hints
    assert _without_source_hash(same_list) == _without_source_hash(other_list)
    native_with = _saved_steps("clearButton", "clicked", (hinted,))
    native_without = _saved_steps("clearButton", "clicked", (plain,))
    assert "<hints>" in native_with and "<hints>" not in native_without
    same_native = _generate(native_with, tmp_path, "sale")
    other_native = _generate(native_without, tmp_path, "sale")
    assert _without_source_hash(same_native) == _without_source_hash(other_native)
    ast.parse(same_list, feature_version=(3, 9))
    ast.parse(same_native, feature_version=(3, 9))


def test_undo_and_redo_of_each_conversion_restores_exact_bytes() -> None:
    start = form(_hinted("clearButton", "clicked()", "nameEdit", "clear()"))
    log = open_log(start)
    original = saved(log.document)
    step = read_event(log.document, "clearButton", "clicked").steps[0]
    log.execute(SetEventSteps("clearButton", "clicked", (replace(step, enabled=False),)))
    as_list = saved(log.document)
    assert as_list != original
    assert log.undo() and saved(log.document) == original
    assert log.redo() and saved(log.document) == as_list
    back = read_event(log.document, "clearButton", "clicked").steps[0]
    log.execute(SetEventSteps("clearButton", "clicked", (replace(back, enabled=True),)))
    as_native = saved(log.document)
    assert _hints_block(as_native, "clearButton") == _hints_block(original, "clearButton")
    assert log.undo() and saved(log.document) == as_list
    assert log.redo() and saved(log.document) == as_native
    assert log.undo() and log.undo() and saved(log.document) == original


@pytest.mark.parametrize(
    "points",
    [(("sourcelabel", 2 ** 40, 0),), (('a"b', 1, 2),), (("s", 1, 2), ("s", 3, 4))],
)
def test_native_storage_refuses_hints_a_ui_file_cannot_hold(points) -> None:
    """A caller-built step with bad hints is refused, as list storage already refuses it."""
    log = open_log(form(""))
    before = saved(log.document)
    count = len(log.entries())
    with pytest.raises(CommandRejected):
        log.execute(SetEventSteps("clearButton", "clicked", (slot_step("nameEdit", "clear()", hints=points),)))
    assert saved(log.document) == before and len(log.entries()) == count
