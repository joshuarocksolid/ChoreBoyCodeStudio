"""UX-M8-003 budget table and the refresh responsiveness claim."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.form_builder.perf.m8_paths import MAC_ROWS, budgets_for, responsive_during_refresh

pytestmark = pytest.mark.unit


def test_budget_rows_match_ux_m8_003() -> None:
    assert tuple((row.key, row.mac_ms, row.vm_ms) for row in MAC_ROWS) == (
        ("data_tab", 16.0, 60.0),
        ("open_form", 200.0, 800.0),
        ("show_record", 16.0, 60.0),
        ("dirty_check", 1.0, 4.0),
        ("save_record", 40.0, 160.0),
        ("load_lookup", 30.0, 120.0),
        ("list_search", 50.0, 200.0),
    )
    assert budgets_for("mac")["dirty_check"] == 1.0
    assert budgets_for("vm")["open_form"] == 800.0


def test_the_ui_thread_processes_events_during_schema_refresh(qapp: object, tmp_path: Path) -> None:
    del qapp
    result = responsive_during_refresh(str(tmp_path), pause_s=0.4)
    assert result["ui_thread_ran_during_refresh"] is True
