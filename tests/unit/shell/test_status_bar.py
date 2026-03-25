"""Unit tests for shell startup status mapping logic."""

import pytest

from app.core.models import CapabilityCheckResult, CapabilityProbeReport
from app.shell.status_bar import (
    format_diagnostics_counts,
    map_editor_status_view,
    map_run_status_view,
    map_startup_report_to_status,
)

pytestmark = pytest.mark.unit


def test_map_startup_report_to_status_handles_missing_report() -> None:
    """Missing startup report should be visible as unknown state."""
    status = map_startup_report_to_status(None)

    assert status.severity == "unknown"
    assert "unavailable" in status.text.lower()
    assert "startup capability data" in status.details.lower()


def test_map_startup_report_to_status_handles_all_checks_passing() -> None:
    """Passing capability checks should map to healthy startup text."""
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_presence", True, "ok"),
            CapabilityCheckResult("pyside2_import", True, "ok"),
        ]
    )

    status = map_startup_report_to_status(report)
    assert status.severity == "ok"
    assert status.text == "Startup: Runtime ready (2/2 checks)"
    assert status.details == "All startup capability checks passed."


def test_map_startup_report_to_status_includes_failed_check_ids() -> None:
    """Failing checks should remain explicit and actionable."""
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_presence", True, "ok"),
            CapabilityCheckResult("freecad_import", False, "missing FreeCAD"),
            CapabilityCheckResult("global_logs_writable", False, "permission denied"),
        ]
    )

    status = map_startup_report_to_status(report)
    assert status.severity == "warning"
    assert status.text == "Startup: Runtime issues (1/3 checks)"
    assert status.details == "Failed checks: freecad_import, global_logs_writable"


def test_map_editor_status_view_formats_active_file_coordinates() -> None:
    """Active editor telemetry should include file, coordinates, and dirty state."""
    view = map_editor_status_view("main.py", 12, 4, is_dirty=True)
    assert view.text == "Editor: main.py | Ln 12, Col 4 | modified"


def test_map_editor_status_view_includes_mode_label_when_present() -> None:
    view = map_editor_status_view("form.ui", 1, 1, is_dirty=False, mode_label="Signals/Slots")
    assert view.text == "Editor: form.ui | Ln 1, Col 1 | Mode Signals/Slots | saved"


def test_map_editor_status_view_handles_missing_file() -> None:
    """No active file should map to explicit placeholder copy."""
    view = map_editor_status_view(None, None, None, is_dirty=False)
    assert view.text == "Editor: no file"


def test_format_diagnostics_counts_errors_and_warnings() -> None:
    assert format_diagnostics_counts(2, 3) == "2 errors, 3 warnings"


def test_format_diagnostics_counts_singular() -> None:
    assert format_diagnostics_counts(1, 1) == "1 error, 1 warning"


def test_format_diagnostics_counts_only_errors() -> None:
    assert format_diagnostics_counts(5, 0) == "5 errors"


def test_format_diagnostics_counts_only_warnings() -> None:
    assert format_diagnostics_counts(0, 2) == "2 warnings"


def test_format_diagnostics_counts_zero() -> None:
    assert format_diagnostics_counts(0, 0) == ""


def test_map_run_status_view_handles_running() -> None:
    view = map_run_status_view("running")
    assert view.severity == "running"
    assert view.text == "Run: running"


def test_map_run_status_view_handles_failed_exit_code() -> None:
    view = map_run_status_view("failed", return_code=1)
    assert view.severity == "error"
    assert view.text == "Run: failed (code=1)"


def test_map_run_status_view_defaults_to_idle_for_unknown_state() -> None:
    view = map_run_status_view("mystery")
    assert view.severity == "idle"
    assert view.text == "Run: idle"
