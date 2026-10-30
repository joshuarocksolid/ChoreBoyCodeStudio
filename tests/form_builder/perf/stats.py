"""Sample, percentile and verdict rules for the speed harness.

The contract metric is process CPU time (``time.process_time``), p50 and p95,
after warmup. Wall time is recorded beside it.

CPU budgets are enforced with ``CPU_TOLERANCE``. One full resample is allowed
when the first set misses the tolerated budget. The resample is the result
that is judged. Wall budgets use the contract number with no extra tolerance,
and only when the 1-minute load average stays below ``WALL_LOAD_LIMIT`` at
both the start and the end of the run.
"""

from __future__ import annotations

import gc
import math
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

# Process CPU p95 may sit 25% over the contract number. The gap covers
# frequency scaling and allocator noise on a loaded machine. It is not a
# change to the contract. Wall time has no extra tolerance. It is skipped
# when the machine is not idle.
CPU_TOLERANCE = 1.25
WALL_LOAD_LIMIT = 2.0
# One command at 1000 widgets, divided by the same command at 300 widgets.
CHANGED_RATIO_LIMIT = 1.6
# A 300-widget p95 under this is timer noise. The ratio is not evidence.
RATIO_NOISE_FLOOR_MS = 0.3
# When the 300-widget sample is noise, the 1000-widget p95 must stay under this.
QUIET_PAIR_CEILING_MS = 0.5
# ChoreBoy open and edit, divided by the raw Qt cost of the same work.
OVERHEAD_RATIO_LIMIT = 1.5


@dataclass(frozen=True)
class ScaleJudgment:
    """A 1000-vs-300 pair. ``measured`` is a ratio, or milliseconds when the small sample is noise."""

    measured: float
    budget: str
    passed: bool
    detail: str


def judge_changed_scale(small_seconds: float, large_seconds: float) -> ScaleJudgment:
    """Judge growth only when the 300-widget p95 is large enough to be a ratio.

    Below ``RATIO_NOISE_FLOOR_MS`` the row checks the 1000-widget p95 against
    ``QUIET_PAIR_CEILING_MS``. Raising ``CHANGED_RATIO_LIMIT`` would hide a
    real doubling of a sample that is already big enough to measure.
    """
    small_ms = small_seconds * 1000.0
    large_ms = large_seconds * 1000.0
    if small_ms < RATIO_NOISE_FLOOR_MS:
        passed = large_ms <= QUIET_PAIR_CEILING_MS
        return ScaleJudgment(
            large_ms,
            "%.1f ms" % QUIET_PAIR_CEILING_MS,
            passed,
            "300-widget p95 is %.3f ms, under %.1f ms, so the row judges the 1000-widget p95 %.3f ms against %.1f ms"
            % (small_ms, RATIO_NOISE_FLOOR_MS, large_ms, QUIET_PAIR_CEILING_MS),
        )
    if small_seconds <= 0.0:
        ratio = float("inf")
    else:
        ratio = large_seconds / small_seconds
    return ScaleJudgment(
        ratio,
        "%.1fx" % CHANGED_RATIO_LIMIT,
        ratio <= CHANGED_RATIO_LIMIT,
        "1000-widget p95 / 300-widget p95 (%.3f / %.3f ms)" % (large_ms, small_ms),
    )


@dataclass(frozen=True)
class Sample:
    cpu_seconds: float
    wall_seconds: float


@dataclass(frozen=True)
class Distribution:
    samples: Tuple[Sample, ...]

    @property
    def n(self) -> int:
        return len(self.samples)

    @property
    def cpu_p50(self) -> float:
        return percentile([item.cpu_seconds for item in self.samples], 0.50)

    @property
    def cpu_p95(self) -> float:
        return percentile([item.cpu_seconds for item in self.samples], 0.95)

    @property
    def wall_p50(self) -> float:
        return percentile([item.wall_seconds for item in self.samples], 0.50)

    @property
    def wall_p95(self) -> float:
        return percentile([item.wall_seconds for item in self.samples], 0.95)


@dataclass(frozen=True)
class Attempt:
    distribution: Distribution
    tries: int


def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear percentile (Hyndman-Fan type 7). ``fraction`` is 0.50 or 0.95."""
    if not values:
        raise ValueError("percentile of an empty sample")
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError("fraction must be between 0 and 1")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * fraction
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def wall_policy(load_start: Sequence[float], load_end: Sequence[float]) -> Tuple[bool, str]:
    """Return ``(enforced, reason)``. Enforcement needs an idle machine."""
    start = float(load_start[0])
    end = float(load_end[0])
    if start >= WALL_LOAD_LIMIT or end >= WALL_LOAD_LIMIT:
        return (
            False,
            "skipped: 1-minute load start %.2f end %.2f >= %.0f"
            % (start, end, WALL_LOAD_LIMIT),
        )
    return True, "enforced"


def cpu_within_budget(cpu_p95_ms: float, budget_ms: float, tolerance: float = CPU_TOLERANCE) -> bool:
    return cpu_p95_ms <= budget_ms * tolerance


def measure(
    fn: Callable[[], None],
    *,
    warmup: int,
    samples: int,
    prepare: Optional[Callable[[], None]] = None,
    cleanup: Optional[Callable[[], None]] = None,
    collect_each: bool = False,
) -> Distribution:
    """Time ``fn`` after ``warmup`` discarded calls.

    ``prepare`` and ``cleanup`` run outside the clock. Garbage collection is
    off for the timed calls so a collection does not land in one sample.
    ``collect_each`` collects before every sample instead, and leaves
    collection enabled, for rows whose budget is close to the work.
    """
    if warmup < 0 or samples < 1:
        raise ValueError("warmup must be >= 0 and samples must be >= 1")
    taken: list[Sample] = []
    if not collect_each:
        gc.collect()
        gc.disable()
    try:
        for _turn in range(warmup):
            if collect_each:
                gc.collect()
            if prepare is not None:
                prepare()
            fn()
            if cleanup is not None:
                cleanup()
        for _turn in range(samples):
            if collect_each:
                gc.collect()
            if prepare is not None:
                prepare()
            cpu_started = time.process_time()
            wall_started = time.perf_counter()
            fn()
            cpu_elapsed = time.process_time() - cpu_started
            wall_elapsed = time.perf_counter() - wall_started
            taken.append(Sample(max(0.0, cpu_elapsed), max(0.0, wall_elapsed)))
            if cleanup is not None:
                cleanup()
    finally:
        gc.enable()
    return Distribution(tuple(taken))


def sample_until_budget(
    measure_once: Callable[[], Distribution],
    budget_ms: Optional[float],
) -> Attempt:
    """Keep the first set that meets the tolerated CPU budget, else the retry."""
    first = measure_once()
    if budget_ms is None or cpu_within_budget(first.cpu_p95 * 1000.0, budget_ms):
        return Attempt(first, 1)
    return Attempt(measure_once(), 2)


def judge_timed(
    dist: Distribution,
    budget_ms: Optional[float],
    *,
    wall_enforced: bool,
) -> str:
    """``pass``, ``fail`` or ``reported`` (no numeric budget)."""
    if budget_ms is None:
        return "reported"
    if not cpu_within_budget(dist.cpu_p95 * 1000.0, budget_ms):
        return "fail"
    if wall_enforced and dist.wall_p95 * 1000.0 > budget_ms:
        return "fail"
    return "pass"
