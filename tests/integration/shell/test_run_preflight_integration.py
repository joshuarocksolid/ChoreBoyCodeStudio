"""Integration tests for run-target clarity and preflight behavior."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QToolButton

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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


def test_run_toolbar_target_summary_reflects_selected_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    project_root = tmp_path / "project"
    (project_root / "run.py").parent.mkdir(parents=True, exist_ok=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (project_root / "tools").mkdir(parents=True, exist_ok=True)
    (project_root / "tools" / "tool.py").write_text("print('tool')\n", encoding="utf-8")
    _write_project(
        project_root,
        default_entry="run.py",
        run_configs=[
            {
                "name": "Tool",
                "entry_file": "tools/tool.py",
                "argv": ["--verbose"],
                "working_directory": "tools",
                "env_overrides": {"APP_ENV": "dev"},
            }
        ],
    )

    window = MainWindow(state_root=str(tmp_path.resolve()))
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str((project_root / "run.py").resolve()), preview=False) is True

    monkeypatch.setattr("app.shell.main_window.QInputDialog.getItem", lambda *_args, **_kwargs: ("Tool", True))
    started: list[dict[str, object]] = []
    monkeypatch.setattr(
        window,
        "_start_session",
        lambda **kwargs: started.append(kwargs) or True,
    )

    window._handle_run_with_configuration_action()

    assert window._active_named_run_config_name == "Tool"
    toolbar_button = window.findChild(QToolButton, "shell.toolbar.btn.runTarget")
    assert toolbar_button is not None
    assert "F5 run.py" in toolbar_button.text()
    assert "Shift+F5 run.py" in toolbar_button.text()
    assert "Config Tool" in toolbar_button.text()
    assert "Working directory: tools" in toolbar_button.toolTip()
    assert "Env overrides: APP_ENV=dev" in toolbar_button.toolTip()
    assert started and started[0]["entry_file"] == "tools/tool.py"


def test_run_project_preflight_opens_runtime_center_for_missing_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project(project_root, default_entry="missing.py")

    window = MainWindow(state_root=str(tmp_path.resolve()))
    assert window._open_project_by_path(str(project_root.resolve())) is True

    opened_dialogs: list[dict[str, object]] = []
    monkeypatch.setattr(
        window,
        "_open_runtime_center_dialog",
        lambda *, title="Runtime Center", report=None: opened_dialogs.append(
            {"title": title, "report": report}
        ),
    )
    monkeypatch.setattr(
        window,
        "_start_session",
        lambda **_kwargs: pytest.fail("run should not start when preflight fails"),
    )

    started = window._handle_run_project_action()

    assert started is False
    assert len(opened_dialogs) == 1
    assert opened_dialogs[0]["title"] == "Run Project"
    report = opened_dialogs[0]["report"]
    assert report is not None
    assert [issue.issue_id for issue in report.issues] == ["run.entry_not_found"]
