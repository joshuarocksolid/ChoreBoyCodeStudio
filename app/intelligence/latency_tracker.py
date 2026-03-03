"""Rolling latency metric tracker helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class LatencySnapshot:
    """Summary statistics for one latency metric."""

    metric_name: str
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


class RollingLatencyTracker:
    """Track a rolling latency window and emit periodic snapshots."""

    def __init__(self, metric_name: str, *, window_size: int = 200, snapshot_interval: int = 25) -> None:
        self._metric_name = metric_name
        self._window_size = max(1, window_size)
        self._snapshot_interval = max(1, snapshot_interval)
        self._samples: deque[float] = deque(maxlen=self._window_size)
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def metric_name(self) -> str:
        return self._metric_name

    def record(self, elapsed_ms: float) -> LatencySnapshot | None:
        sample = max(0.0, float(elapsed_ms))
        self._samples.append(sample)
        self._count += 1
        if self._count % self._snapshot_interval != 0:
            return None
        return self.snapshot()

    def snapshot(self) -> LatencySnapshot | None:
        if not self._samples:
            return None
        ordered = sorted(self._samples)
        return LatencySnapshot(
            metric_name=self._metric_name,
            count=self._count,
            p50_ms=_percentile(ordered, 0.50),
            p95_ms=_percentile(ordered, 0.95),
            max_ms=ordered[-1],
        )


def _percentile(ordered_samples: list[float], quantile: float) -> float:
    if not ordered_samples:
        return 0.0
    if len(ordered_samples) == 1:
        return ordered_samples[0]
    bounded = min(1.0, max(0.0, quantile))
    rank = int(math.ceil(bounded * len(ordered_samples))) - 1
    rank = min(len(ordered_samples) - 1, max(0, rank))
    return ordered_samples[rank]
