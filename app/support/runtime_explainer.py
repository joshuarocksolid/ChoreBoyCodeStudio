"""Structured runtime/onboarding explanation helpers."""
from __future__ import annotations

from typing import Iterable

from app.bootstrap.capability_probe import (
    APP_RUN_PRESENCE_CHECK_ID,
    FREECAD_IMPORT_CHECK_ID,
    GLOBAL_LOGS_WRITABLE_CHECK_ID,
    PYSIDE2_IMPORT_CHECK_ID,
    PYTHON_TOOLING_RUNTIME_CHECK_ID,
    STATE_ROOT_WRITABLE_CHECK_ID,
    TEMP_ROOT_WRITABLE_CHECK_ID,
)
from app.core.models import CapabilityCheckResult, CapabilityProbeReport, RuntimeIssue, RuntimeIssueReport
from app.intelligence.diagnostics_service import ImportDiagnostic, explain_unresolved_import
from app.support.diagnostics import DiagnosticItem, ProjectHealthReport

HELP_TOPIC_GETTING_STARTED = "getting_started"
HELP_TOPIC_HEADLESS_NOTES = "headless_notes"
HELP_TOPIC_PACKAGING = "packaging_backup"

_HEADLESS_GUI_SIGNATURE = "Cannot load Gui module in console application"
_SEVERITY_ORDER = {
    "blocking": 3,
    "degraded": 2,
    "advisory": 1,
}


def build_startup_issue_report(report: CapabilityProbeReport) -> RuntimeIssueReport:
    """Convert startup capability failures into structured runtime issues."""
    issues = [
        issue
        for check in report.checks
        for issue in [_issue_from_capability_check(check, workflow="startup")]
        if issue is not None
    ]
    return RuntimeIssueReport(workflow="startup", issues=_sort_issues(issues))


def build_project_health_issue_report(report: ProjectHealthReport) -> RuntimeIssueReport:
    """Convert project health failures into structured runtime issues."""
    issues = [
        issue
        for check in report.checks
        for issue in [_issue_from_diagnostic_item(check)]
        if issue is not None
    ]
    return RuntimeIssueReport(workflow="project", issues=_sort_issues(issues))


def merge_runtime_issue_reports(*reports: RuntimeIssueReport, workflow: str = "general") -> RuntimeIssueReport:
    """Merge multiple reports into one stable, de-duplicated issue list."""
    merged: dict[tuple[str, str], RuntimeIssue] = {}
    for report in reports:
        for issue in report.issues:
            merged[(issue.workflow, issue.issue_id)] = issue
    return RuntimeIssueReport(workflow=workflow, issues=_sort_issues(merged.values()))


def build_import_issue_report(
    project_root: str,
    diagnostics: list[ImportDiagnostic],
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
) -> RuntimeIssueReport:
    """Convert unresolved-import diagnostics into structured runtime issues."""
    issues: list[RuntimeIssue] = []
    for diagnostic in diagnostics:
        module_name = diagnostic.message.removeprefix("Unresolved import: ").strip()
        if not module_name:
            continue
        explanation = explain_unresolved_import(
            project_root,
            module_name,
            known_runtime_modules=known_runtime_modules,
            allow_runtime_import_probe=allow_runtime_import_probe,
        )
        issues.append(
            RuntimeIssue(
                issue_id=f"import.{explanation.kind}.{_sanitize_issue_component(module_name)}",
                workflow="run",
                severity="degraded",
                title=explanation.summary,
                summary=diagnostic.message,
                why_it_happened=explanation.why_it_happened,
                next_steps=list(explanation.next_steps),
                help_topic=HELP_TOPIC_GETTING_STARTED,
                evidence=dict(explanation.evidence),
            )
        )
    return RuntimeIssueReport(workflow="import", issues=_sort_issues(issues))


def explain_runtime_message(message_text: str, *, workflow: str = "run") -> list[RuntimeIssue]:
    """Return structured issues for known runtime failure signatures."""
    normalized = message_text or ""
    issues: list[RuntimeIssue] = []
    if _HEADLESS_GUI_SIGNATURE in normalized:
        issues.append(
            RuntimeIssue(
                issue_id="runtime.freecad_gui_module_in_headless_run",
                workflow=workflow,
                severity="blocking",
                title="GUI-only FreeCAD path used in a headless run",
                summary=(
                    "This run tried to use a FreeCAD GUI module from Code Studio's normal "
                    "headless runner."
                ),
                why_it_happened=(
                    "Code Studio launches standard runs through the AppRun console/runtime path, "
                    "not through an interactive FreeCAD GUI session."
                ),
                next_steps=[
                    "Switch to a headless-safe FreeCAD API path where possible.",
                    "If the workflow requires an open FreeCAD document or GUI state, edit in Code Studio but run it from FreeCAD.",
                    "Keep the run log so the exact failing call is preserved for support.",
                ],
                help_topic=HELP_TOPIC_HEADLESS_NOTES,
                evidence={"matched_text": _HEADLESS_GUI_SIGNATURE},
            )
        )
    return _sort_issues(issues)


def _issue_from_diagnostic_item(check: DiagnosticItem) -> RuntimeIssue | None:
    if check.is_ok:
        return None
    if check.check_id.startswith("runtime."):
        capability_check = CapabilityCheckResult(
            check_id=check.check_id.removeprefix("runtime."),
            is_available=check.is_ok,
            message=check.message,
            details=check.details,
        )
        return _issue_from_capability_check(capability_check, workflow="project")
    if check.check_id == "project_structure":
        return RuntimeIssue(
            issue_id="project.structure_invalid",
            workflow="project",
            severity="blocking",
            title="Selected folder is not ready as a project",
            summary="The chosen folder does not currently look like a runnable Python project.",
            why_it_happened=(
                "Code Studio needs Python files or valid `cbcs/project.json` metadata to treat "
                "a folder as a project."
            ),
            next_steps=[
                "Open a folder that contains runnable `.py` files.",
                "If you are starting fresh, use File > New Project to create a template project.",
                "Re-run the health check after fixing the folder contents.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence={"check_id": check.check_id, "details": dict(check.details), "message": check.message},
        )
    if check.check_id == "project_manifest":
        return RuntimeIssue(
            issue_id="project.manifest_invalid",
            workflow="project",
            severity="blocking",
            title="Project metadata is invalid",
            summary="The project's `cbcs/project.json` metadata could not be parsed or validated.",
            why_it_happened=(
                "Run targets, project identity, and several editor workflows depend on valid "
                "project metadata."
            ),
            next_steps=[
                "Review the reported validation error in the health check details.",
                "Repair the project's `cbcs/project.json` or reopen a known-good project.",
                "Generate a support bundle if the metadata should already be valid.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence={"check_id": check.check_id, "details": dict(check.details), "message": check.message},
        )
    return RuntimeIssue(
        issue_id=f"project.{check.check_id}",
        workflow="project",
        severity="degraded",
        title="Project diagnostic reported an issue",
        summary=check.message,
        why_it_happened="One of the project health checks reported a failure.",
        next_steps=[
            "Review the diagnostic details and correct the reported problem.",
            "Re-run the health check after applying the fix.",
        ],
        help_topic=HELP_TOPIC_GETTING_STARTED,
        evidence={"check_id": check.check_id, "details": dict(check.details), "message": check.message},
    )


def _issue_from_capability_check(check: CapabilityCheckResult, *, workflow: str) -> RuntimeIssue | None:
    if check.is_available:
        return None
    evidence = {"check_id": check.check_id, "details": dict(check.details), "message": check.message}
    if check.check_id == APP_RUN_PRESENCE_CHECK_ID:
        return RuntimeIssue(
            issue_id="runtime.apprun_missing",
            workflow=workflow,
            severity="blocking",
            title="AppRun runtime is unavailable",
            summary="The editor could not find the FreeCAD AppRun path it uses for ChoreBoy-compatible runs.",
            why_it_happened=(
                "Run, debug, packaging, and runtime probes rely on the expected AppRun path to "
                "match the real ChoreBoy environment."
            ),
            next_steps=[
                "Verify that the expected AppRun path exists on this machine.",
                "Repair or reinstall the runtime package if AppRun was moved or removed.",
                "Open the application log or generate a support bundle if the path should already exist.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence=evidence,
        )
    if check.check_id == PYSIDE2_IMPORT_CHECK_ID:
        return RuntimeIssue(
            issue_id="runtime.pyside2_unavailable",
            workflow=workflow,
            severity="blocking",
            title="Qt runtime is unavailable",
            summary="PySide2 could not be imported in the active runtime, so the editor cannot rely on its normal UI stack.",
            why_it_happened=(
                "Code Studio is built around the PySide2 runtime bundled with FreeCAD AppRun."
            ),
            next_steps=[
                "Confirm that the expected FreeCAD runtime is installed correctly.",
                "If this is a packaged deployment, reinstall or repair it before relying on GUI workflows.",
                "Capture logs/support bundle details if the runtime should already include PySide2.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence=evidence,
        )
    if check.check_id == FREECAD_IMPORT_CHECK_ID:
        return RuntimeIssue(
            issue_id="runtime.freecad_import_failed",
            workflow=workflow,
            severity="degraded",
            title="FreeCAD backend import is unavailable",
            summary="FreeCAD could not be imported in the target runtime, so backend/headless workflows may fail.",
            why_it_happened=(
                "Code Studio uses the FreeCAD runtime both for runtime parity and for headless backend features."
            ),
            next_steps=[
                "Avoid relying on FreeCAD-specific project workflows until the runtime issue is resolved.",
                "Re-run diagnostics after confirming the runtime installation.",
                "Use a support bundle if FreeCAD should already be importable on this system.",
            ],
            help_topic=HELP_TOPIC_HEADLESS_NOTES,
            evidence=evidence,
        )
    if check.check_id == STATE_ROOT_WRITABLE_CHECK_ID:
        return RuntimeIssue(
            issue_id="runtime.state_root_not_writable",
            workflow=workflow,
            severity="degraded",
            title="Global state folder is not writable",
            summary="Code Studio could not write to its visible global state directory.",
            why_it_happened=(
                "Settings, caches, and some diagnostics depend on a writable global state root under Home."
            ),
            next_steps=[
                "Check permissions for the visible `choreboy_code_studio_state` location.",
                "Avoid moving the global state path into hidden or restricted folders.",
                "Review the app log for fallback-path details if logging still works.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence=evidence,
        )
    if check.check_id == GLOBAL_LOGS_WRITABLE_CHECK_ID:
        return RuntimeIssue(
            issue_id="runtime.logs_not_writable",
            workflow=workflow,
            severity="degraded",
            title="Global log folder is not writable",
            summary="Persistent shell logs may be incomplete because the global log path is not writable.",
            why_it_happened=(
                "The editor keeps diagnostics and crash details in a visible global log folder for supportability."
            ),
            next_steps=[
                "Check permissions for the global logs directory under the visible state root.",
                "Generate a support bundle if you need to capture the current fallback logging path.",
                "Avoid hidden or restricted directories for app state on ChoreBoy.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence=evidence,
        )
    if check.check_id == TEMP_ROOT_WRITABLE_CHECK_ID:
        return RuntimeIssue(
            issue_id="runtime.temp_root_not_writable",
            workflow=workflow,
            severity="degraded",
            title="Temporary runtime area is not writable",
            summary="Some transient runtime workflows may fail because the temp directory is not writable.",
            why_it_happened=(
                "Code Studio uses a writable temp area for transient runner and support workflows."
            ),
            next_steps=[
                "Check permissions for the visible temp/runtime area used by the app.",
                "Retry the workflow after clearing permission or disk-space issues.",
                "Capture diagnostics if the temp path should already be available.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence=evidence,
        )
    if check.check_id == PYTHON_TOOLING_RUNTIME_CHECK_ID:
        return RuntimeIssue(
            issue_id="runtime.python_tooling_unavailable",
            workflow=workflow,
            severity="advisory",
            title="Python format/import tooling is unavailable",
            summary="Vendored Python formatting/import tooling is not ready, so some editor comfort features may be limited.",
            why_it_happened=(
                "Black, isort, and TOML parsing are shipped as vendored tooling and can fail independently of core editing/run workflows."
            ),
            next_steps=[
                "Core open/edit/run workflows can still continue if no other blocking issues are present.",
                "Review the reported tooling detail before relying on Python format/import actions.",
                "Capture a support bundle if tooling should already be available in this deployment.",
            ],
            help_topic=HELP_TOPIC_GETTING_STARTED,
            evidence=evidence,
        )
    return RuntimeIssue(
        issue_id=f"runtime.{check.check_id}",
        workflow=workflow,
        severity="degraded",
        title="Runtime capability check failed",
        summary=check.message,
        why_it_happened="One of the runtime capability checks reported a failure.",
        next_steps=[
            "Review the issue details and correct the reported runtime problem.",
            "Re-run the relevant diagnostics after applying the fix.",
        ],
        help_topic=HELP_TOPIC_GETTING_STARTED,
        evidence=evidence,
    )


def _sort_issues(issues: Iterable[RuntimeIssue]) -> list[RuntimeIssue]:
    return sorted(
        issues,
        key=lambda issue: (-_SEVERITY_ORDER.get(issue.severity, 0), issue.workflow, issue.issue_id),
    )


def _sanitize_issue_component(text: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in text).strip("_") or "import"
