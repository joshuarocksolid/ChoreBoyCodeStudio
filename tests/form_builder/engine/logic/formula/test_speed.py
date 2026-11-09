"""Wall time for a short formula. Marked perf so the unit gate can skip it."""

from __future__ import annotations

import time

import pytest

from app.features.form_builder.engine.logic.formula import analyze, normalize
from tests.form_builder.engine.logic.formula.support import ENV, SLOTS

pytestmark = [pytest.mark.unit, pytest.mark.perf]


def test_two_hundred_characters_p95_under_a_millisecond() -> None:
    piece = "qtySpin * priceSpin + "
    text = (piece * 9) + "0 "
    assert len(text) == 200
    slot = SLOTS["money"]
    for _ in range(30):
        normalize(analyze(text, ENV, slot).text)
    samples = []
    for _ in range(200):
        started = time.perf_counter()
        got = analyze(text, ENV, slot)
        normalize(got.text)
        samples.append(time.perf_counter() - started)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 <= 0.001, p95
