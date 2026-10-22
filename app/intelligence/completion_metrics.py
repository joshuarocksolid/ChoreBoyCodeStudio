"""Lightweight completion telemetry primitives."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import time
from typing import Iterator

from app.core.constants import APP_LOGGER_NAMESPACE
from app.core.metrics import LatencySnapshot, RollingLatencyTracker

_phase_logger = logging.getLogger(f"{APP_LOGGER_NAMESPACE}.intelligence")


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


def note_phase(breakdown: dict[str, float] | None, phase: str, started_at: float) -> float:
    """Store one phase duration in milliseconds and return it."""

    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if breakdown is not None:
        breakdown[phase] = elapsed_ms
    return elapsed_ms


def log_completion_phase(phase: str, elapsed_ms: float, **fields: object) -> None:
    """Write one completion phase onto the app intelligence log."""

    extra = " ".join(f"{key}={value}" for key, value in fields.items())
    _phase_logger.info(
        "Completion phase telemetry: phase=%s elapsed_ms=%.2f %s",
        phase,
        elapsed_ms,
        extra.strip(),
    )
