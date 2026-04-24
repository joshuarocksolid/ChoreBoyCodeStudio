"""Unit tests for shell startup status mapping logic."""

import pytest

from app.core.models import CapabilityCheckResult, CapabilityProbeReport
from app.shell.status_bar import (
    format_diagnostics_counts,
    map_editor_status_view,
    map_indent_status_view,
    map_python_tooling_status_view,
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


def test_map_startup_report_to_status_handles_partial_minimal_report() -> None:
    """Minimal startup reports should still render deterministic ready text."""
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_presence", True, "ok"),
            CapabilityCheckResult("pyside2_import", True, "ok"),
            CapabilityCheckResult("state_root_writable", True, "ok"),
            CapabilityCheckResult("global_logs_writable", True, "ok"),
            CapabilityCheckResult("temp_root_writable", True, "ok"),
        ]
    )

    status = map_startup_report_to_status(report)
    assert status.severity == "ok"
    assert status.text == "Startup: Runtime ready (5/5 checks)"


def test_map_startup_report_to_status_includes_issue_titles() -> None:
    """Failing checks should surface human-readable issue titles."""
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
    assert (
        status.details
        == "2 issue(s): FreeCAD backend import is unavailable; Global log folder is not writable"
    )


def test_map_editor_status_view_formats_active_file_coordinates() -> None:
    """Active editor telemetry should include file, coordinates, and dirty state."""
    view = map_editor_status_view("main.py", 12, 4, is_dirty=True)
    assert view.text == "Editor: main.py | Ln 12, Col 4 | modified"


def test_map_editor_status_view_handles_missing_file() -> None:
    """No active file should map to explicit placeholder copy."""
    view = map_editor_status_view(None, None, None, is_dirty=False)
    assert view.text == "Editor: no file"


@pytest.mark.parametrize(
    ("errors", "warnings", "expected"),
    [
        (2, 3, "2 errors, 3 warnings"),
        (1, 1, "1 error, 1 warning"),
        (5, 0, "5 errors"),
        (0, 2, "2 warnings"),
        (0, 0, ""),
    ],
)
def test_format_diagnostics_counts(errors: int, warnings: int, expected: str) -> None:
    assert format_diagnostics_counts(errors, warnings) == expected


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


def test_map_python_tooling_status_view_handles_ready_pyproject_state() -> None:
    view = map_python_tooling_status_view(
        runtime_available=True,
        config_state="pyproject",
        config_path="/tmp/project/pyproject.toml",
    )
    assert view.severity == "ok"
    assert view.text == "Python: tools ready | pyproject"
    assert "/tmp/project/pyproject.toml" in view.details


def test_map_python_tooling_status_view_handles_unavailable_runtime() -> None:
    view = map_python_tooling_status_view(runtime_available=False, config_state="defaults")
    assert view.severity == "warning"
    assert view.text == "Python: tools unavailable"


def test_map_indent_status_view_handles_no_active_file() -> None:
    view = map_indent_status_view(style=None, size=None, source=None)
    assert view.text == ""
    assert view.details == ""


def test_map_indent_status_view_user_source_uses_settings_tooltip() -> None:
    view = map_indent_status_view(style="spaces", size=4, source="user")
    assert view.text == "Spaces: 4"
    assert "settings" in view.details.lower()


def test_map_indent_status_view_editorconfig_source_mentions_editorconfig() -> None:
    view = map_indent_status_view(style="spaces", size=2, source="editorconfig")
    assert view.text == "Spaces: 2"
    assert ".editorconfig" in view.details.lower()


def test_map_indent_status_view_auto_source_marks_text_and_details() -> None:
    view = map_indent_status_view(style="spaces", size=4, source="auto")
    assert view.text == "Spaces: 4 (auto)"
    assert "auto-detected" in view.details.lower()


def test_map_indent_status_view_tabs_render_with_tab_label() -> None:
    view = map_indent_status_view(style="tabs", size=4, source="user")
    assert view.text == "Tabs: 4"
