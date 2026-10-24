"""Quiet 300-vs-1000 pairs are not ratio evidence."""

from __future__ import annotations

import pytest

from tests.form_builder.perf.stats import judge_changed_scale

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("small_ms", "large_ms", "passed", "budget"),
    [
        (0.10, 0.166, True, "0.5 ms"),
        (0.10, 0.80, False, "0.5 ms"),
        (1.00, 1.50, True, "1.6x"),
        (1.00, 2.00, False, "1.6x"),
        (0.30, 0.48, True, "1.6x"),
        (0.29, 0.49, True, "0.5 ms"),
    ],
)
def test_changed_scale_uses_a_ratio_only_above_the_noise_floor(
    small_ms: float,
    large_ms: float,
    passed: bool,
    budget: str,
) -> None:
    judgment = judge_changed_scale(small_ms / 1000.0, large_ms / 1000.0)
    assert judgment.passed is passed
    assert judgment.budget == budget
    if budget.endswith("x"):
        assert judgment.measured == pytest.approx(large_ms / small_ms)
    else:
        assert judgment.measured == pytest.approx(large_ms)
