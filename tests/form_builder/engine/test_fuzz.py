"""Malformed input never escapes the reader as an unexpected exception."""
from __future__ import annotations

import random

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


def test_fuzzed_input_only_raises_read_errors() -> None:
    rng = random.Random(20261021)
    for _case in range(2000):
        text = _mutate(rng.choice(_SEED_FORMS), rng)
        try:
            read_ui(text, allocator=IdAllocator())
        except UiReadError:
            continue


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
