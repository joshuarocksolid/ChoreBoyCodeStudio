"""Lightweight completion telemetry primitives."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import time
from typing import Iterator

from app.intelligence.latency_tracker import LatencySnapshot, RollingLatencyTracker


@dataclass(frozen=True)
class CompletionTelemetrySnapshot:
    """Snapshot of completion timing windows."""

    operation: str
    latency: LatencySnapshot | None


@dataclass
class CompletionTelemetry:
    """Tracks completion timing without imposing UI dependencies."""

    window_size: int = 120
    snapshot_interval: int = 30
    _trackers: dict[str, RollingLatencyTracker] = field(default_factory=dict)

    def record(self, operation: str, duration_ms: float) -> LatencySnapshot | None:
        """Record a duration and return a periodic snapshot if one is due."""

        tracker = self._trackers.get(operation)
        if tracker is None:
            tracker = RollingLatencyTracker(
                f"completion_{operation}_ms",
                window_size=self.window_size,
                snapshot_interval=self.snapshot_interval,
            )
            self._trackers[operation] = tracker
        return tracker.record(duration_ms)

    @contextmanager
    def span(self, operation: str, breakdown: dict[str, float] | None = None) -> Iterator[None]:
        """Measure a scoped operation and optionally add it to a breakdown."""

        started_at = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if breakdown is not None:
                breakdown[operation] = elapsed_ms
            self.record(operation, elapsed_ms)
