"""Section 12 budgets through the speed harness.

The gate uses 5 samples, not the CLI's 15, so this module stays inside the
30 second perf-gate budget. The numbers are still process CPU p95 with the
tolerance and the one retry from ``stats.py``.
"""

from __future__ import annotations

from typing import Optional

import pytest

from tests.form_builder.perf.harness import (
    GATE_SAMPLES,
    GATE_SIZES,
    GATE_WARMUP,
    SECTION_12_POINTS,
    STRUCTURAL_POINTS,
    STRUCTURAL_RATIO_POINTS,
    SHELL_SELECT_POINT,
    Row,
    SpeedReport,
    run_speed,
)


@pytest.fixture(scope="module")
def mac_report() -> SpeedReport:
    return run_speed(
        profile="mac",
        samples=GATE_SAMPLES,
        warmup=GATE_WARMUP,
        sizes=GATE_SIZES,
    )


@pytest.mark.perf
@pytest.mark.timeout(60)
def test_realistic_300_read_and_write_meet_section_12(mac_report: SpeedReport) -> None:
    read = _row(mac_report, "read_ui", 300)
    write = _row(mac_report, "write_ui", 300)
    assert read.verdict == "pass", _explain(read)
    assert write.verdict == "pass", _explain(write)
    assert read.samples == GATE_SAMPLES
    assert mac_report.cpu_tolerance == 1.25


@pytest.mark.perf
@pytest.mark.timeout(60)
def test_one_command_at_1000_stays_within_1_6x_of_300(mac_report: SpeedReport) -> None:
    ratio = _row(mac_report, "one command O(changed)", None)
    assert ratio.verdict == "pass", _explain(ratio)
    assert ratio.p95 is not None
    if str(ratio.budget).endswith("x"):
        assert ratio.p95 <= 1.6
    else:
        assert ratio.p95 <= 0.5


@pytest.mark.perf
@pytest.mark.timeout(60)
def test_structural_realize_patches_meet_section_12(mac_report: SpeedReport) -> None:
    for point in STRUCTURAL_POINTS:
        row = _row(mac_report, point, 300)
        assert row.verdict == "pass", _explain(row)
        assert row.budget == "8 ms"
        assert row.total_p95 is not None
    for point in STRUCTURAL_RATIO_POINTS:
        ratio = _row(mac_report, "%s O(changed)" % point, None)
        assert ratio.verdict == "pass", _explain(ratio)


@pytest.mark.perf
@pytest.mark.timeout(60)
@pytest.mark.parametrize(("point", "widgets"), [("hit index refresh", 300), ("hit index refresh", 1000), ("hit query", 300)])
def test_hit_index_meets_section_12(mac_report: SpeedReport, point: str, widgets: int) -> None:
    row = _row(mac_report, point, widgets)
    assert row.verdict == "pass", _explain(row)


@pytest.mark.perf
@pytest.mark.timeout(60)
@pytest.mark.parametrize("point", ["overlay paint", "selection change", "edit total"])
def test_canvas_paths_meet_section_12(mac_report: SpeedReport, point: str) -> None:
    row = _row(mac_report, point, 300)
    assert row.verdict == "pass", _explain(row)


@pytest.mark.perf
@pytest.mark.timeout(60)
@pytest.mark.parametrize("point", ["direct hit", "overlay paint direct"])
def test_direct_manipulation_at_1000_meets_section_12(mac_report: SpeedReport, point: str) -> None:
    row = _row(mac_report, point, 1000)
    assert row.verdict == "pass", _explain(row)


@pytest.mark.perf
@pytest.mark.timeout(60)
def test_missing_section_12_points_are_listed(mac_report: SpeedReport) -> None:
    present = {row.point for row in mac_report.rows}
    missing = [name for name in SECTION_12_POINTS if name not in present]
    assert missing == []
    unavailable = [row for row in mac_report.rows if row.verdict == "not yet available"]
    assert unavailable
    assert all(row.verdict != "fail" for row in mac_report.rows)


@pytest.mark.perf
@pytest.mark.timeout(60)
def test_memory_and_undo_log_meet_section_12(mac_report: SpeedReport) -> None:
    for point in (
        "memory one form tracemalloc",
        "memory one form rss",
        "memory three forms tracemalloc",
        "memory three forms rss",
        "undo log",
    ):
        row = _row(mac_report, point, 300)
        assert row.verdict == "pass", _explain(row)


@pytest.mark.perf
@pytest.mark.timeout(60)
def test_inspector_select_in_the_shell_meets_section_12(mac_report: SpeedReport) -> None:
    """Select then flush, All properties open, under the real shell style sheet."""
    row = _row(mac_report, SHELL_SELECT_POINT, 300)
    if row.verdict == "skip":
        pytest.skip(row.detail)
    assert row.verdict == "pass", _explain(row)
    assert row.budget == "16 ms"


def _row(report: SpeedReport, point: str, widgets: Optional[int]) -> Row:
    found = [row for row in report.rows if row.point == point and row.widgets == widgets]
    assert found, point
    return found[0]


def _explain(row: Row) -> str:
    return "%s p95=%s budget=%s %s" % (row.point, row.p95, row.budget, row.detail)
