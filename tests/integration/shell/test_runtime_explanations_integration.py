"""Integration tests for contextual runtime explanations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QDialog

from app.packaging.models import PACKAGE_PROFILE_INSTALLABLE
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


def _write_project(project_root: Path, *, source_text: str, default_entry: str = "run.py") -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / default_entry).write_text(source_text, encoding="utf-8")
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Runtime Project",
                "default_entry": default_entry,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_analyze_imports_opens_runtime_center_with_structured_import_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    project_root = tmp_path / "project"
    _write_project(project_root, source_text="import totally_fake\n")

    window = MainWindow(state_root=str(tmp_path.resolve()))
    try:
        assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True

        opened_dialogs = _record_runtime_center_dialogs(monkeypatch)

        def _run_immediately(*, key, task, on_success, on_error):  # type: ignore[no-untyped-def]
            _ = key
            _ = on_error
            on_success(task(None))

        monkeypatch.setattr(window._background_tasks, "run", _run_immediately)
        window._semantic_navigation_workflow.handle_analyze_imports_action()

        assert len(opened_dialogs) == 1
        assert opened_dialogs[0]["title"] == "Import Analysis"
        report = opened_dialogs[0]["report"]
        assert report is not None
        assert report.issues
        assert report.issues[0].issue_id.startswith("import.vendored_dependency_missing")
    finally:
        shutdown_main_window_for_test(window)


def test_headless_runtime_signature_updates_latest_run_issue_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    window = MainWindow(state_root=str(tmp_path.resolve()))
    try:
        window._active_run_output_tail.append(
            "Traceback...\nCannot load Gui module in console application\n"
        )

        problems = window._run_event_workflow.update_problems_from_output()

        assert problems == []
        assert [issue.issue_id for issue in window._latest_run_issue_report.issues] == [
            "runtime.freecad_gui_module_in_headless_run"
        ]
    finally:
        shutdown_main_window_for_test(window)


def test_packaging_preflight_opens_runtime_center_before_export(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    project_root = tmp_path / "project"
    _write_project(project_root, source_text="print('ok')\n", default_entry="run.py")
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["default_entry"] = "missing.py"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    window = MainWindow(state_root=str(tmp_path.resolve()))
    try:
        assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True

        class _FakeWizard:
            def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                self.output_dir = str(tmp_path / "exports")
                self.selected_profile = PACKAGE_PROFILE_INSTALLABLE
                self._package_config = kwargs["package_config"]

            def exec_(self) -> int:
                return QDialog.Accepted

            def build_package_config(self):  # type: ignore[no-untyped-def]
                return self._package_config

        monkeypatch.setattr("app.shell.runtime_support_workflow.PackageProjectWizard", _FakeWizard)
        opened_dialogs = _record_runtime_center_dialogs(monkeypatch)

        def _run_immediately(*, key, task, on_success, on_error):  # type: ignore[no-untyped-def]
            _ = key
            try:
                on_success(task(None))
            except Exception as exc:  # pragma: no cover - defensive path
                on_error(exc)

        monkeypatch.setattr(window._background_tasks, "run", _run_immediately)

        window._runtime_support_workflow.handle_package_project_action()

        assert len(opened_dialogs) == 1
        assert opened_dialogs[0]["title"] == "Packaging Failed"
        report = opened_dialogs[0]["report"]
        assert report is not None
        issue_ids = [issue.issue_id for issue in report.issues]
        assert "package.entry_invalid" in issue_ids
    finally:
        shutdown_main_window_for_test(window)
