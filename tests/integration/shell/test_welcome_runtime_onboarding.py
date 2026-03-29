"""Integration tests for welcome/onboarding discoverability."""
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


def _write_valid_project(project_root: Path) -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps({"schema_version": 1, "name": "Onboarding Project"}, indent=2),
        encoding="utf-8",
    )


def test_runtime_onboarding_is_not_auto_opened_but_reachable_from_help_after_autoload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    project_root = tmp_path / "project"
    _write_valid_project(project_root)

    settings_path = tmp_path / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "last_project_path": str(project_root.resolve()),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    onboarding_calls: list[str] = []

    def _record_onboarding_action(self) -> None:  # type: ignore[no-untyped-def]
        onboarding_calls.append("opened")

    monkeypatch.setattr(MainWindow, "_handle_runtime_onboarding_action", _record_onboarding_action)

    window = MainWindow(state_root=str(tmp_path.resolve()))
    try:
        app.processEvents()
        app.processEvents()

        assert window._loaded_project is not None
        assert window._loaded_project.project_root == str(project_root.resolve())
        assert onboarding_calls == []

        assert window.menu_registry is not None
        action = window.menu_registry.action("shell.action.help.runtimeOnboarding")
        assert action is not None
        action.trigger()

        assert onboarding_calls == ["opened"]
    finally:
        shutdown_main_window_for_test(window)
