"""Unit tests for structured runtime explanation helpers."""
from __future__ import annotations

from app.core.models import CapabilityCheckResult, CapabilityProbeReport, RuntimeIssue, RuntimeIssueReport
from app.support.diagnostics import DiagnosticItem, ProjectHealthReport
from app.support.runtime_explainer import (
    build_project_health_issue_report,
    build_startup_issue_report,
    explain_runtime_message,
    merge_runtime_issue_reports,
)


def test_build_startup_issue_report_maps_failed_checks_by_severity() -> None:
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult(
                check_id="apprun_presence",
                is_available=False,
                message="AppRun path not found",
            ),
            CapabilityCheckResult(
                check_id="python_tooling_runtime",
                is_available=False,
                message="Vendored Python tools missing",
            ),
            CapabilityCheckResult(
                check_id="pyside2_import",
                is_available=True,
                message="PySide2 import succeeded.",
            ),
        ]
    )

    issue_report = build_startup_issue_report(report)

    assert issue_report.workflow == "startup"
    assert issue_report.total_count == 2
    assert issue_report.blocking_count == 1
    assert issue_report.advisory_count == 1
    assert issue_report.highest_severity == "blocking"
    assert [issue.issue_id for issue in issue_report.issues] == [
        "runtime.apprun_missing",
        "runtime.python_tooling_unavailable",
    ]


def test_build_project_health_issue_report_maps_project_and_runtime_failures() -> None:
    report = ProjectHealthReport(
        project_root="/tmp/example",
        checks=[
            DiagnosticItem(
                check_id="project_structure",
                is_ok=False,
                message="This folder is invalid because no Python files were found.",
            ),
            DiagnosticItem(
                check_id="runtime.freecad_import",
                is_ok=False,
                message="Failed to import FreeCAD.",
            ),
        ],
    )

    issue_report = build_project_health_issue_report(report)

    assert issue_report.workflow == "project"
    assert issue_report.total_count == 2
    assert issue_report.highest_severity == "blocking"
    assert {issue.issue_id for issue in issue_report.issues} == {
        "project.structure_invalid",
        "runtime.freecad_import_failed",
    }


def test_merge_runtime_issue_reports_deduplicates_by_workflow_and_id() -> None:
    shared_issue = RuntimeIssue(
        issue_id="runtime.apprun_missing",
        workflow="startup",
        severity="blocking",
        title="AppRun runtime is unavailable",
        summary="AppRun missing",
        why_it_happened="Missing runtime",
    )
    report_a = RuntimeIssueReport(workflow="startup", issues=[shared_issue])
    report_b = RuntimeIssueReport(
        workflow="project",
        issues=[
            RuntimeIssue(
                issue_id="project.manifest_invalid",
                workflow="project",
                severity="blocking",
                title="Manifest invalid",
                summary="Manifest invalid",
                why_it_happened="Bad metadata",
            ),
            shared_issue,
        ],
    )

    merged = merge_runtime_issue_reports(report_a, report_b)

    assert merged.workflow == "general"
    assert merged.total_count == 2
    assert [issue.issue_id for issue in merged.issues] == [
        "project.manifest_invalid",
        "runtime.apprun_missing",
    ]


def test_explain_runtime_message_detects_headless_gui_signature() -> None:
    issues = explain_runtime_message(
        "Traceback...\nCannot load Gui module in console application\n",
        workflow="run",
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue.issue_id == "runtime.freecad_gui_module_in_headless_run"
    assert issue.workflow == "run"
    assert issue.help_topic == "headless_notes"
