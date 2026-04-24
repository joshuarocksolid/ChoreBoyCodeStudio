"""Performance checks for runtime onboarding and explanation surfaces."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.core.models import CapabilityCheckResult, CapabilityProbeReport, RuntimeIssue, RuntimeIssueReport
from app.shell.runtime_center_dialog import RuntimeCenterDialog
from app.shell.status_bar import map_startup_report_to_status
from app.shell.theme_tokens import tokens_from_palette
from app.shell.welcome_widget import WelcomeWidget

pytestmark = [pytest.mark.integration, pytest.mark.timeout(120)]


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _build_runtime_report(issue_count: int) -> RuntimeIssueReport:
    issues = [
        RuntimeIssue(
            issue_id=f"runtime.issue_{index}",
            workflow="runtime_center",
            severity="blocking" if index % 3 == 0 else ("degraded" if index % 3 == 1 else "advisory"),
            title=f"Issue {index}",
            summary=f"Summary {index}",
            why_it_happened=f"Explanation {index}",
            next_steps=[f"Step {index}"],
            help_topic="getting_started" if index % 2 == 0 else None,
            evidence={"index": index},
        )
        for index in range(issue_count)
    ]
    return RuntimeIssueReport(workflow="runtime_center", issues=issues)


def test_runtime_center_set_report_150_issues_under_350ms(_qapp: QApplication) -> None:
    tokens = tokens_from_palette(_qapp.palette(), force_mode="light")
    dialog = RuntimeCenterDialog(
        title="Runtime Center",
        report=RuntimeIssueReport(workflow="runtime_center", issues=[]),
        tokens=tokens,
    )
    report = _build_runtime_report(150)

    start = time.perf_counter()
    dialog.set_report(report)
    elapsed = time.perf_counter() - start

    assert dialog.issue_list.count() == 150
    assert elapsed <= 0.35


def test_welcome_widget_filters_250_recent_projects_under_250ms() -> None:
    widget = WelcomeWidget()
    widget.set_recent_projects([f"/workspace/projects/project_{index:03d}" for index in range(250)])

    start = time.perf_counter()
    widget._apply_filter("project_249")
    elapsed = time.perf_counter() - start

    assert widget._project_list.count() == 1
    assert "project_249" in widget._project_list.item(0).text()
    assert elapsed <= 0.25


def test_startup_status_mapping_200_checks_under_100ms() -> None:
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult(
                check_id=f"probe_{index}",
                is_available=index % 2 == 0,
                message=f"Probe {index}",
            )
            for index in range(200)
        ]
    )

    start = time.perf_counter()
    status = map_startup_report_to_status(report)
    elapsed = time.perf_counter() - start

    assert status.text.startswith("Startup: Runtime issues")
    assert "issue(s)" in status.details
    assert elapsed <= 0.10
