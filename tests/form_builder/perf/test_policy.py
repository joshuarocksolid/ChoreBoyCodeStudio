"""Verdict rules that keep the perf gate stable under load."""

from __future__ import annotations

from typing import List

from tests.form_builder.perf.stats import (
    CPU_TOLERANCE,
    WALL_LOAD_LIMIT,
    Distribution,
    Sample,
    cpu_within_budget,
    percentile,
    sample_until_budget,
    wall_policy,
)


def test_percentile_is_the_linear_rank() -> None:
    assert percentile((1.0, 2.0, 3.0, 4.0), 0.50) == 2.5
    assert percentile((1.0, 2.0, 3.0, 4.0, 5.0), 0.95) == 4.8
    assert percentile((7.0,), 0.95) == 7.0


def test_wall_assertions_stop_when_the_one_minute_load_hits_the_limit() -> None:
    assert wall_policy((WALL_LOAD_LIMIT, 0.0, 0.0), (0.1, 0.0, 0.0))[0] is False
    assert wall_policy((0.1, 0.0, 0.0), (WALL_LOAD_LIMIT, 0.0, 0.0))[0] is False
    enforced, reason = wall_policy((WALL_LOAD_LIMIT - 0.01, 0.0, 0.0), (0.2, 0.0, 0.0))
    assert enforced is True
    assert reason == "enforced"


def test_cpu_budget_allows_the_documented_tolerance_and_one_retry() -> None:
    budget = 25.0
    assert cpu_within_budget(budget * CPU_TOLERANCE, budget) is True
    assert cpu_within_budget(budget * CPU_TOLERANCE + 0.01, budget) is False
    slow = Distribution((Sample(0.040, 0.040),))
    fast = Distribution((Sample(0.010, 0.010),))
    seen: List[str] = []

    def measure_once() -> Distribution:
        seen.append("go")
        return slow if len(seen) == 1 else fast

    attempt = sample_until_budget(measure_once, budget)
    assert attempt.tries == 2
    assert attempt.distribution is fast

    seen.clear()

    def already_fast() -> Distribution:
        seen.append("go")
        return fast

    once = sample_until_budget(already_fast, budget)
    assert once.tries == 1
    assert seen == ["go"]
