"""M6.0b: the logic codec (CONTRACTS.md section 15.3 to 15.5).

The generators are seeded ``random`` loops, as in ``test_fuzz.py`` (``hypothesis`` is not
bundled); ``FB_SEED`` picks another seed.
"""

from __future__ import annotations

import json
import os
import random
import string
import time
from typing import List, Optional, Tuple

import pytest

from app.features.form_builder.engine.logic import codec
from app.features.form_builder.engine.logic.codec import (
    JsonObject,
    LogicWriteError,
    Step,
    call_step,
    canonical_logic_text,
    marker_read_only,
    parse_json,
    parse_steps,
    read_marker,
    slot_step,
    write_json,
    write_steps,
)
from app.features.form_builder.engine.logic.storage import (
    LOGIC_PROPERTY_ORDER,
    logic_rank,
    signal_of_property,
    signal_property,
)
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.engine.ui4.values import BoolValue, NumberValue, StringValue


def _seed() -> int:
    raw = os.environ.get("FB_SEED")
    return int(raw) if raw else 20261029


# --- canonical bytes -------------------------------------------------------

CANONICAL_STEPS = (
    "[\n"
    '  {"do": "slot", "target": "nameEdit", "slot": "clear()"},\n'
    '  {"do": "call", "when": "total > 0", "enabled": false, "method": "print_receipt", "args": 1},\n'
    '  {"do": "message", "level": "info", "text": "Saved.", "later": [1, 2.5, "x"]}\n'
    "]"
)

CANONICAL_WRAPPED = (
    '{"signal": "valueChanged(int)", "steps": [\n'
    '  {"do": "slot", "target": "box", "slot": "setValue(int)"}\n'
    "]}"
)

CANONICAL_ROWS = (
    '{"table": "lines", "link": "invoice_id", "key": "id", "columns": [\n'
    '  {"column": "qty", "header": "Qty", "validate": [\n'
    '    {"check": "required"},\n'
    '    {"check": "range", "min": 1, "max": "today()"}\n'
    "  ]},\n"
    '  {"name": "total", "formula": "qty * price"}\n'
    '], "order": [["id", "asc"]]}'
)


@pytest.mark.parametrize("text", [CANONICAL_STEPS, CANONICAL_WRAPPED])
def test_canonical_step_text_is_a_fixed_point(text: str) -> None:
    read = parse_steps(text)
    assert read.error is None
    assert write_steps(read.steps, read.signal, read.extra) == text


def test_canonical_json_text_is_a_fixed_point() -> None:
    got = parse_json(CANONICAL_ROWS)
    assert got.error is None
    assert write_json(got.value) == CANONICAL_ROWS
    assert canonical_logic_text("cbcsRows", CANONICAL_ROWS).text == CANONICAL_ROWS


def test_writing_reorders_known_keys_and_keeps_unknown_ones_in_read_order() -> None:
    text = '[{"zeta": 1, "method": "m", "enabled": false, "alpha": [true, null], "when": "a", "do": "call", "args": 2}]'
    read = parse_steps(text)
    assert read.error is None
    step = read.steps[0]
    assert step.unknown == (("zeta", 1), ("alpha", (True, None)))
    assert write_steps(read.steps) == (
        '[\n  {"do": "call", "when": "a", "enabled": false, "method": "m", "args": 2, '
        '"zeta": 1, "alpha": [true, null]}\n]'
    )


def test_numbers_strings_and_xml_safety() -> None:
    value = parse_json('{"a": 1.0, "b": 2.50, "c": 1e2, "d": -0.0, "e": "caf\\u00e9 \\u007f \\ud800 \\uffff \\u0001"}').value
    text = write_json(value)
    assert text == '{"a": 1, "b": 2.5, "c": 100, "d": 0, "e": "café \\u007f \\ud800 \\uffff \\u0001"}'
    for char in text:
        assert ord(char) >= 0x20 and not 0x7F <= ord(char) <= 0x9F and ord(char) not in (0xFFFE, 0xFFFF)
        assert not 0xD800 <= ord(char) <= 0xDFFF
    assert parse_json(text).value == value
    assert write_json("é ") == '"é "'


def test_writer_refuses_nan_and_infinity_and_deep_nesting() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(LogicWriteError):
            write_json(JsonObject((("x", bad),)))
    deep: codec.JsonValue = 1
    for _ in range(codec.MAX_DEPTH + 2):
        deep = (deep,)
    with pytest.raises(LogicWriteError):
        write_json(deep)


def test_an_empty_list_is_never_written() -> None:
    assert write_steps(()) == ""
    assert canonical_logic_text("cbcsOnClicked", "[]").text is None
    assert canonical_logic_text("cbcsOnClicked", '{"signal": "x()", "steps": []}').text is None
    assert canonical_logic_text("cbcsValidate", "[]").text is None
    assert canonical_logic_text("cbcsLookup", "{}").text == "{}"


# --- reading ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "not json",
        "[1]",
        "{}",
        '{"signal": "x()"}',
        '[{"do": "slot", "target": "a"}]',
        '[{"do": "slot", "target": "", "slot": "x()"}]',
        '[{"do": "call", "method": "m", "args": true}]',
        '[{"do": "call", "method": "m", "args": -1}]',
        '[{"do": "call", "do": "slot"}]',
        '[{"when": "x"}]',
        "[NaN]",
        "[Infinity]",
        "[1e999]",
        "[" * 60 + "]" * 60,
    ],
)
def test_unreadable_step_lists_are_reported_not_raised(text: str) -> None:
    read = parse_steps(text)
    assert read.error is not None
    assert read.error[0] >= 1
    assert read.steps == ()


def test_error_lines_point_into_the_text() -> None:
    assert parse_steps('[\n  {"do": "call", "method": "m"},\n  5\n]').error == (3, "step 2: it is not an object")
    assert parse_steps('[\n{"do": "call", "method": "m"},\n{"do": "slot"}\n]').error[0] == 3  # type: ignore[index]
    wrapped = '{"signal": "x()", "other": [1, 2],\n "steps": [\n {"do": "call", "method": "m"},\n 7]}'
    assert parse_steps(wrapped).error[0] == 4  # type: ignore[index]
    assert parse_steps('[\n\n{"do": "call", "method": "m"} x]').error[0] == 3  # type: ignore[index]


def test_a_verb_this_build_does_not_type_keeps_every_key_in_order() -> None:
    text = '[{"do": "set", "formula": "a + b", "field": "totalEdit", "when": "x", "future": {"k": [1]}}]'
    read = parse_steps(text)
    assert read.error is None
    step = read.steps[0]
    assert not step.is_typed and not step.is_plain
    assert step.when == "x"
    assert [key for key, _ in step.fields] == ["formula", "field", "future"]
    assert write_steps(read.steps) == (
        '[\n  {"do": "set", "when": "x", "formula": "a + b", "field": "totalEdit", "future": {"k": [1]}}\n]'
    )


def test_size_and_depth_limits() -> None:
    big = '["' + "a" * (codec.MAX_TEXT_BYTES + 1) + '"]'
    assert parse_json(big).error == (1, "larger than 1 MB")
    assert parse_steps(big).error is not None
    started = time.process_time()
    wide = "[" + ",".join('{"do": "call", "method": "m%d"}' % index for index in range(20000)) + "]"
    assert len(wide) < codec.MAX_TEXT_BYTES
    read = parse_steps(wide)
    assert read.error is None and len(read.steps) == 20000
    assert time.process_time() - started < 20


# --- round trips (seeded, property style) ----------------------------------

_WORDS = ["a", "b", "é", "tab\there", 'quote"s', "back\\slash", "\x01ctl", "\x85", "￾", "\ud83d", "😀", "", " "]


def _scalar(rng: random.Random) -> codec.JsonValue:
    roll = rng.randrange(7)
    if roll == 0:
        return None
    if roll == 1:
        return rng.choice([True, False])
    if roll == 2:
        return rng.randrange(-5, 10**9)
    if roll == 3:
        return rng.choice([0.5, -2.25, 1e-7, 3.0, 1e22, 123456.789])
    return rng.choice(_WORDS) + "".join(rng.choice(string.ascii_letters) for _ in range(rng.randrange(3)))


def _value(rng: random.Random, depth: int) -> codec.JsonValue:
    roll = rng.randrange(6)
    if depth > 3 or roll < 3:
        return _scalar(rng)
    if roll == 3:
        return tuple(_value(rng, depth + 1) for _ in range(rng.randrange(4)))
    if roll == 4:
        return tuple(_object(rng, depth + 1) for _ in range(rng.randrange(1, 4)))
    return _object(rng, depth + 1)


def _object(rng: random.Random, depth: int) -> JsonObject:
    keys = [rng.choice(["x", "y", "zz", "k é", "a\"b"]) for _ in range(rng.randrange(4))]
    return JsonObject(tuple((key, _value(rng, depth)) for key in keys))


def _step(rng: random.Random) -> Step:
    when = rng.choice([None, "a > 1", "total == 0"])
    enabled = rng.choice([True, True, False])
    unknown = tuple((rng.choice(["u1", "u2", "u3"]) + str(index), _value(rng, 2)) for index in range(rng.randrange(3)))
    roll = rng.randrange(3)
    if roll == 0:
        return slot_step("w%d" % rng.randrange(5), rng.choice(["clear()", "setValue(int)", "setText(QString)"]), when=when, enabled=enabled, unknown=unknown)
    if roll == 1:
        return call_step("m%d" % rng.randrange(5), rng.choice([None, 0, 1, 2]), when=when, enabled=enabled, unknown=unknown)
    fields = tuple(("f%d" % index, _value(rng, 2)) for index in range(rng.randrange(4)))
    return Step(rng.choice(["message", "set", "future"]), when, enabled, fields, ())


def test_json_round_trip_over_random_models() -> None:
    rng = random.Random(_seed())
    for _ in range(600):
        value = _value(rng, 0)
        text = write_json(value)
        again = parse_json(text)
        assert again.error is None, text
        assert again.value == value, text
        assert write_json(again.value) == text
        json.loads(text)  # plain JSON to any other reader
        text.encode("utf-8")
        assert "\r" not in text and not any(line.endswith(" ") for line in text.split("\n"))


def test_step_round_trip_over_random_lists() -> None:
    rng = random.Random(_seed() + 1)
    for _ in range(400):
        steps = tuple(_step(rng) for _ in range(rng.randrange(1, 6)))
        signal: Optional[str] = rng.choice([None, "valueChanged(int)"])
        extra: codec.Pairs = (("note", _value(rng, 2)),) if signal is not None and rng.randrange(3) == 0 else ()
        text = write_steps(steps, signal, extra)
        read = parse_steps(text)
        assert read.error is None, text
        assert read.steps == steps, text
        assert read.signal == signal and read.extra == extra
        assert write_steps(read.steps, read.signal, read.extra) == text
        canonical = canonical_logic_text("cbcsOnValueChanged", text)
        assert canonical.text == text


def test_parse_and_write_never_raise_on_garbage() -> None:
    rng = random.Random(_seed() + 2)
    seeds = [CANONICAL_STEPS, CANONICAL_WRAPPED, CANONICAL_ROWS, '{"version": 1}', "[1, 2"]
    alphabet = '[]{}",:\\ \n\tnulltrue0123456789.eE-+é\ud800'
    for _ in range(1500):
        text = list(rng.choice(seeds))
        for _ in range(rng.randrange(1, 6)):
            roll = rng.randrange(3)
            position = rng.randrange(len(text) + 1)
            if roll == 0 and text:
                del text[min(position, len(text) - 1)]
            elif roll == 1:
                text.insert(position, rng.choice(alphabet))
            else:
                text[min(position, len(text) - 1)] = rng.choice(alphabet)
        joined = "".join(text)
        for read in (parse_steps(joined), parse_json(joined)):
            assert (read.error is None) or (read.error[0] >= 1)
        assert read_marker(PropertyEntry("property", "cbcsLogic", StringValue(joined), "0")) is not None
        outcome = canonical_logic_text("cbcsOnClicked", joined)
        if outcome.error is None and outcome.text is not None:
            assert canonical_logic_text("cbcsOnClicked", outcome.text).text == outcome.text


# --- the marker ------------------------------------------------------------


def _entry(value: object) -> PropertyEntry:
    return PropertyEntry("property", "cbcsLogic", value, "0")  # type: ignore[arg-type]


MARKER_TABLE = [
    # (entry, version, readable, read_only)
    (None, None, True, False),
    (_entry(StringValue('{"version":1}', notr=True)), 1, True, False),
    (_entry(StringValue('{\n "version": 1,\n "extra": [1]\n}')), 1, True, False),
    (_entry(StringValue("1")), 1, True, False),
    (_entry(StringValue(" 1\n")), 1, True, False),
    (_entry(NumberValue(1)), 1, True, False),
    (_entry(StringValue('{"version":0}')), 0, True, False),
    (_entry(StringValue('{"version":2}')), 2, True, True),
    (_entry(StringValue("2")), 2, True, True),
    (_entry(NumberValue(7)), 7, True, True),
    (_entry(StringValue('{"version":99999999999999999999}')), 99999999999999999999, True, True),
    (_entry(StringValue('{"version":true}')), None, False, True),
    (_entry(StringValue('{"version":1.0}')), None, False, True),
    (_entry(StringValue('{"version":"1"}')), None, False, True),
    (_entry(StringValue("{}")), None, False, True),
    (_entry(StringValue("")), None, False, True),
    (_entry(StringValue("[1]")), None, False, True),
    (_entry(StringValue("one")), None, False, True),
    (_entry(BoolValue(True)), None, False, True),
]


@pytest.mark.parametrize("entry,version,readable,read_only", MARKER_TABLE)
def test_marker_truth_table(entry: Optional[PropertyEntry], version: Optional[int], readable: bool, read_only: bool) -> None:
    got = read_marker(entry)
    assert (got.version, got.readable) == (version, readable)
    assert marker_read_only(entry) is read_only


# --- names -----------------------------------------------------------------


def test_signal_property_names_are_exact_inverses() -> None:
    for name in ("clicked", "currentIndexChanged", "valueChanged", "x", "aB", "toggled"):
        assert signal_of_property(signal_property(name)) == name
    assert signal_property("clicked") == "cbcsOnClicked"
    assert signal_of_property("cbcsOnline") is None
    assert signal_of_property("cbcsOn") is None
    assert signal_of_property("cbcsEnabledWhen") is None
    rng = random.Random(_seed() + 3)
    for _ in range(300):
        name = rng.choice(string.ascii_lowercase) + "".join(rng.choice(string.ascii_letters + string.digits + "_") for _ in range(rng.randrange(12)))
        assert signal_of_property(signal_property(name)) == name


def test_step_lists_rank_at_the_cbcs_on_slot_and_by_name() -> None:
    order = list(LOGIC_PROPERTY_ORDER)
    assert logic_rank("cbcsOnClicked") == logic_rank("cbcsOnOpened") == order.index("cbcsOn*")
    assert logic_rank("cbcsOnline") is None and logic_rank("cbcsFuture") is None
    assert order.index("cbcsErrorSummary") + 1 == order.index("cbcsOn*") == order.index("cbcsData") - 1

    table = QtClassTable.shared()
    names = ["cbcsOnToggled", "cbcsData", "cbcsOnClicked", "cbcsValidate", "cbcsFuture", "cbcsErrorLabel", "cbcsChoice"]
    ranked = sorted(names, key=lambda item: table.property_rank("QPushButton", item, dynamic=True))
    assert ranked == ["cbcsValidate", "cbcsErrorLabel", "cbcsOnClicked", "cbcsOnToggled", "cbcsData", "cbcsChoice", "cbcsFuture"]


def test_a_typed_step_with_a_condition_it_cannot_read_is_fb401_not_plain() -> None:
    for text in (
        '[{"do": "slot", "target": "a", "slot": "clear()", "when": 5}]',
        '[{"do": "call", "method": "m", "enabled": "no"}]',
        '[{"do": "call", "method": "m", "enabled": null}]',
    ):
        read = parse_steps(text)
        assert read.error is not None and read.steps == ()
    # an untyped verb keeps such keys as read (FB403 shows it read-only)
    read = parse_steps('[{"do": "later", "when": 5}]')
    assert read.error is None and read.steps[0].fields == (("when", 5),)


def test_only_false_turns_a_step_off_when_writing() -> None:
    on = Step("call", None, None, (("method", "m"),), ())  # type: ignore[arg-type]
    assert write_steps((on,)) == '[\n  {"do": "call", "method": "m"}\n]'
    assert on.is_plain


@pytest.mark.timeout(60)
def test_hostile_texts_stay_fast_and_total() -> None:
    import time

    from app.features.form_builder.engine.logic.refs import opaque_mentions, rename_formula

    hostile = [
        "[" * (1024 * 1024),
        "[" * 5000 + "]" * 5000,
        "1" * (1024 * 1024 - 10),
        "[" + "1" * 5000 + "]",
        "[" + "1e" + "9" * 500 + "]",
        '["' + "\\" * 400000 + '"]',
        "[" + ", ".join(['{"do": "slot", "target": "a", "slot": "b()"}'] * 20000) + "]",
        '{"a": ' * 40 + "1" + "}" * 40,
        "[\ud800]",
        "\x00" * 1000,
    ]
    for text in hostile:
        started = time.perf_counter()
        parse_steps(text)
        parse_json(text)
        canonical_logic_text("cbcsOnClicked", text)
        opaque_mentions(text, "a")
        assert time.perf_counter() - started < 5.0, text[:40]
    assert parse_json('{"a": ' * 40 + "1" + "}" * 40).error is not None  # deeper than 32
    for formula in ("(" * 60000, "a+" * 30000 + "a", "'" + "x" * 60000, "a." * 30000 + "a"):
        started = time.perf_counter()
        rename_formula(formula, {"a": "b"})
        assert time.perf_counter() - started < 5.0, formula[:40]
