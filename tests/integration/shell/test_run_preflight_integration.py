"""Integration tests for run-target clarity and preflight behavior."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _record_runtime_center_dialogs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Intercept Runtime Center dialog opens at the dialog boundary."""
    opened: list[dict[str, object]] = []

    class _RecordingRuntimeCenterDialog:
        def __init__(self, *, title: str = "Runtime Center", report: object = None, **_kwargs: object) -> None:
            opened.append({"title": title, "report": report})

        def exec_(self) -> int:
            return 0

    monkeypatch.setattr(
        "app.shell.runtime_onboarding_workflow.RuntimeCenterDialog",
        _RecordingRuntimeCenterDialog,
    )
    return opened


def _write_project(
    project_root: Path,
    *,
    default_entry: str,
    run_configs: list[dict[str, object]] | None = None,
) -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Run Project",
                "default_entry": default_entry,
                "run_configs": run_configs or [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_project_preflight_opens_runtime_center_for_missing_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project(project_root, default_entry="missing.py")

    window = MainWindow(state_root=str(tmp_path.resolve()))
    try:
        assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True

        opened_dialogs = _record_runtime_center_dialogs(monkeypatch)
        monkeypatch.setattr(
            window._run_launch_workflow,
            "start_session",
            lambda **_kwargs: pytest.fail("run should not start when preflight fails"),
        )

        started = window._run_launch_workflow.handle_run_project_action()

        assert started is False
        assert len(opened_dialogs) == 1
        assert opened_dialogs[0]["title"] == "Run Project"
        report = opened_dialogs[0]["report"]
        assert report is not None
        assert [issue.issue_id for issue in report.issues] == ["run.entry_not_found"]
    finally:
        shutdown_main_window_for_test(window)
