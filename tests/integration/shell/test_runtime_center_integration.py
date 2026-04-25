"""Integration tests for Runtime Center shell wiring."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QLabel

from app.core.models import CapabilityCheckResult, CapabilityProbeReport
from app.shell.main_window import MainWindow
from app.support.diagnostics import DiagnosticItem, ProjectHealthReport
from testing.main_window_shutdown import shutdown_main_window_for_test

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_startup_status_click_opens_runtime_center(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ = _ensure_qapplication(monkeypatch)
    opened_dialogs: list[dict[str, object]] = []

    class _FakeRuntimeCenterDialog:
        def __init__(self, *, title, report, tokens, open_help_topic=None, parent=None):  # type: ignore[no-untyped-def]
            opened_dialogs.append(
                {
                    "title": title,
                    "report": report,
                    "tokens": tokens,
                    "open_help_topic": open_help_topic,
                    "parent": parent,
                }
            )

        def exec_(self) -> int:
            opened_dialogs[-1]["executed"] = True
            return 0

    monkeypatch.setattr("app.shell.main_window.RuntimeCenterDialog", _FakeRuntimeCenterDialog)
    window = MainWindow(
        startup_report=CapabilityProbeReport(
            checks=[
                CapabilityCheckResult("apprun_presence", False, "AppRun missing"),
            ]
        ),
        state_root=str(tmp_path.resolve()),
    )
    try:
        assert window.menu_registry is not None
        assert window.menu_registry.action("shell.action.tools.runtimeCenter") is not None

        startup_label = window.findChild(QLabel, "shell.startupStatusLabel")
        assert startup_label is not None
        startup_label.clicked.emit()  # type: ignore[attr-defined]

        assert len(opened_dialogs) == 1
        assert opened_dialogs[0]["title"] == "Runtime Center"
        report = opened_dialogs[0]["report"]
        assert report.workflow == "runtime_center"
        assert [issue.issue_id for issue in report.issues] == ["runtime.apprun_missing"]
    finally:
        shutdown_main_window_for_test(window)


def test_project_health_check_opens_runtime_center_with_latest_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    opened_dialogs: list[dict[str, object]] = []

    class _FakeRuntimeCenterDialog:
        def __init__(self, *, title, report, tokens, open_help_topic=None, parent=None):  # type: ignore[no-untyped-def]
            opened_dialogs.append({"title": title, "report": report})

        def exec_(self) -> int:
            opened_dialogs[-1]["executed"] = True
            return 0

    monkeypatch.setattr("app.shell.main_window.RuntimeCenterDialog", _FakeRuntimeCenterDialog)

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "run.py").write_text("print('ok')\n", encoding="utf-8")

    window = MainWindow(state_root=str(tmp_path.resolve()))
    try:
        assert window._open_project_by_path(str(project_root.resolve())) is True

        fake_report = ProjectHealthReport(
            project_root=str(project_root.resolve()),
            checks=[
                DiagnosticItem(
                    check_id="project_structure",
                    is_ok=False,
                    message="No Python files were found.",
                )
            ],
        )

        def _run_immediately(*, key, task, on_success, on_error):  # type: ignore[no-untyped-def]
            _ = key
            _ = task
            _ = on_error
            on_success(fake_report)

        monkeypatch.setattr(window._background_tasks, "run", _run_immediately)
        window._runtime_support_workflow.handle_project_health_check_action()

        assert window._latest_health_report == fake_report
        assert len(opened_dialogs) == 1
        assert opened_dialogs[0]["title"] == "Project Health Check"
        report = opened_dialogs[0]["report"]
        assert report.workflow == "runtime_center"
        assert [issue.issue_id for issue in report.issues] == ["project.structure_invalid"]
    finally:
        shutdown_main_window_for_test(window)
