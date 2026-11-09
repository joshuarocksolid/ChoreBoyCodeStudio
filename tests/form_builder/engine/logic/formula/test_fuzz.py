"""Seeded token fuzz. analyze stays total, and normalize keeps a parseable tree."""

from __future__ import annotations

import ast
import io
import random
import time
import tokenize

import pytest

from app.features.form_builder.engine.logic.formula import analyze, normalize
from tests.form_builder.engine.logic.formula.support import ENV, SLOTS

pytestmark = pytest.mark.unit

_ATOMS = (
    "qtySpin",
    "nameEdit",
    "priceSpin",
    "discountCheck",
    "1",
    "1.5",
    "1_000",
    '"a"',
    "True",
    "False",
    "None",
    "éSpin",
)
_OPS = ("+", "-", "*", "/", "==", "!=", "<", "<=", ">", "and", "or", "in")
_SEED = 17171


def _stream(rng: random.Random, count: int) -> str:
    parts = []
    depth = 0
    for _ in range(count):
        roll = rng.randrange(12)
        if roll < 6:
            parts.append(rng.choice(_ATOMS))
        elif roll < 9:
            parts.append(rng.choice(_OPS))
        elif roll == 9 and depth < 8:
            parts.append("(")
            depth += 1
        elif roll == 10 and depth > 0:
            parts.append(")")
            depth -= 1
        else:
            parts.append(rng.choice(("not", "is_blank")))
    while depth > 0:
        parts.append(")")
        depth -= 1
    return " ".join(parts)


def test_random_streams_never_raise() -> None:
    rng = random.Random(_SEED)
    slot = SLOTS["cond"]
    for _ in range(5000):
        text = _stream(rng, rng.randrange(1, 24))
        got = analyze(text, ENV, slot)
        assert got.text == text
        assert isinstance(got.problems, tuple)


def test_normalize_fuzz_is_idempotent_and_keeps_the_dump() -> None:
    rng = random.Random(1717)
    kept = 0
    for _ in range(2000):
        text = _stream(rng, rng.randrange(1, 16))
        canonical = normalize(text)
        assert normalize(canonical) == canonical
        try:
            before = ast.parse(text, mode="eval")
        except SyntaxError:
            continue
        after = ast.parse(canonical, mode="eval")
        assert ast.dump(before) == ast.dump(after)
        kept += 1
    assert kept >= 100


def _guard_tokens(text: str) -> int:
    count = 0
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        count += 1
    return count


def _min_call(numbers: int) -> str:
    """``min`` of whole-number literals, including the trailing comma.

    A flat sum of this many terms is deeper than 64 and the depth guard would
    return before the checker ran. A call stays shallow. Digits stay under the
    2,000 character guard, which a 400-token name stream would trip.
    """
    return "min(" + ",".join(["1"] * numbers) + ",)"


def test_analyze_time_stays_linear_in_tokens() -> None:
    """Per-token time at 400 tokens stays under the short-input rate times 25.

    Short inputs include fixed startup, so the factor is a ceiling, not a slope.
    Both sizes are valid calls, so the comparison is the checker and not a guard.
    """
    slot = SLOTS["whole"]
    short_text = _min_call(8)
    long_text = _min_call(198)
    short_n = _guard_tokens(short_text)
    long_n = _guard_tokens(long_text)
    assert short_n == 20
    assert long_n == 400
    assert len(long_text) <= 2000
    checked = analyze(long_text, ENV, slot)
    assert checked.type is not None and checked.type.kind.value == "whole"
    assert not any(problem.code == "FB111" for problem in checked.problems)

    def elapsed(text: str, samples: int) -> float:
        for _ in range(5):
            analyze(text, ENV, slot)
        started = time.perf_counter()
        for _ in range(samples):
            analyze(text, ENV, slot)
        return (time.perf_counter() - started) / samples

    short = elapsed(short_text, 40)
    long = elapsed(long_text, 8)
    per_short = short / short_n
    per_long = long / long_n
    assert per_long < per_short * 25, (per_short, per_long, short, long)
