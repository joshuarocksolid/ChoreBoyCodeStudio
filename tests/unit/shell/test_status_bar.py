"""Unit tests for shell startup status mapping logic."""

import pytest

from app.core.models import CapabilityCheckResult, CapabilityProbeReport
from app.shell.status_bar import map_editor_status_view, map_startup_report_to_status

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


def test_map_editor_status_view_handles_missing_file() -> None:
    """No active file should map to explicit placeholder copy."""
    view = map_editor_status_view(None, None, None, is_dirty=False)
    assert view.text == "Editor: no file"
