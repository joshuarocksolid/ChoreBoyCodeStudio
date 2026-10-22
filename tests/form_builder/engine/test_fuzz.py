"""Malformed input never escapes the reader as an unexpected exception."""
from __future__ import annotations

import os
import random
from xml.parsers import expat

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_SEED_FORMS = (
    '<?xml version="1.0" encoding="UTF-8"?><ui version="4.0"><widget class="QWidget" name="Form">'
    '<property name="windowTitle"><string>Hello</string></property></widget></ui>',
    '<ui version="4.0"><widget class="QDialog" name="Dialog"><layout class="QVBoxLayout" name="lay">'
    '<item><widget class="QPushButton" name="ok"/></item></layout></widget>'
    '<connections><connection><sender>ok</sender><signal>clicked()</signal>'
    '<receiver>Dialog</receiver><slot>accept()</slot></connection></connections></ui>',
)


def test_fuzzed_double_save_is_byte_identical() -> None:
    stray = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form"/>
 stray
</ui>
"""
    rng = random.Random(20261021)
    cases = [stray]
    for _case in range(400):
        cases.append(_mutate(rng.choice(_SEED_FORMS + (stray,)), rng))
    for text in cases:
        try:
            once = write_ui(read_ui(text, allocator=IdAllocator()).document).text
        except UiReadError:
            continue
        twice = write_ui(read_ui(once, allocator=IdAllocator()).document).text
        assert twice == once


def _seed() -> int:
    raw = os.environ.get("FB_SEED")
    if raw:
        return int(raw)
    return 20261021


def _check_fuzz(count: int) -> None:
    seed = _seed()
    print("FB_SEED %s cases %s" % (seed, count))
    rng = random.Random(seed)
    for index in range(count):
        text = _mutate(rng.choice(_SEED_FORMS), rng)
        try:
            loaded = read_ui(text, allocator=IdAllocator())
        except UiReadError as exc:
            cause = exc.__cause__
            if cause is not None and not isinstance(cause, expat.ExpatError):
                raise AssertionError(
                    "seed %s case %s wrapped %s: %s" % (seed, index, type(cause).__name__, cause)
                ) from exc
            continue
        once = write_ui(loaded.document).text
        twice = write_ui(read_ui(once, allocator=IdAllocator()).document).text
        assert twice == once, "seed %s case %s" % (seed, index)


def test_fuzzed_input_only_raises_read_errors() -> None:
    _check_fuzz(2000)


@pytest.mark.oracle
def test_fuzz_gate_keeps_accepted_input_stable() -> None:
    _check_fuzz(20000)


def _mutate(text: str, rng: random.Random) -> str:
    raw = bytearray(text.encode("utf-8", errors="replace"))
    if not raw:
        return text
    kind = rng.randrange(4)
    if kind == 0:
        index = rng.randrange(len(raw))
        raw[index] = rng.randrange(256)
    elif kind == 1:
        index = rng.randrange(len(raw))
        del raw[index:index + rng.randint(1, 8)]
    elif kind == 2:
        index = rng.randrange(len(raw) + 1)
        raw[index:index] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 6)))
    else:
        raw = raw[: rng.randrange(len(raw))]
    return raw.decode("utf-8", errors="replace")
