"""Unit tests for rolling latency tracker metrics."""

from __future__ import annotations

import pytest

from app.intelligence.latency_tracker import RollingLatencyTracker

pytestmark = pytest.mark.unit


def test_record_emits_snapshot_on_interval() -> None:
    tracker = RollingLatencyTracker("metric.test", window_size=10, snapshot_interval=3)

    assert tracker.record(12.0) is None
    assert tracker.record(16.0) is None
    snapshot = tracker.record(20.0)

    assert snapshot is not None
    assert snapshot.metric_name == "metric.test"
    assert snapshot.count == 3
    assert snapshot.p50_ms == 16.0
    assert snapshot.p95_ms == 20.0
    assert snapshot.max_ms == 20.0


def test_window_trims_old_samples_for_snapshot() -> None:
    tracker = RollingLatencyTracker("metric.trim", window_size=4, snapshot_interval=2)
    for sample in [1.0, 2.0, 3.0, 4.0, 50.0, 100.0]:
        tracker.record(sample)

    snapshot = tracker.snapshot()
    assert snapshot is not None
    # Only the latest 4 samples are kept: [3.0, 4.0, 50.0, 100.0]
    assert snapshot.p50_ms == 4.0
    assert snapshot.p95_ms == 100.0
    assert snapshot.max_ms == 100.0


def test_negative_values_are_clamped() -> None:
    tracker = RollingLatencyTracker("metric.clamp", window_size=5, snapshot_interval=1)
    snapshot = tracker.record(-42.0)
    assert snapshot is not None
    assert snapshot.p50_ms == 0.0
