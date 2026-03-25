"""Integration tests for run/debug toolbar wiring in main window."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide2.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_run_debug_toolbar_actions_exist_and_enable_after_project_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _ensure_qapplication(monkeypatch)
    window = MainWindow(state_root=str(Path("/tmp").resolve()))

    registry = window.menu_registry
    assert registry is not None
    assert registry.action("shell.action.run.run") is not None
    assert registry.action("shell.action.run.debug") is not None
    assert registry.action("shell.action.run.pause") is not None
    assert registry.action("shell.action.run.stepOver") is not None
    assert registry.action("shell.action.run.toggleBreakpoint") is not None

    project_root = Path("/tmp/choreboy_toolbar_project")
    if project_root.exists():
        import shutil

        shutil.rmtree(project_root)
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('toolbar')\n", encoding="utf-8")
    opened = window._open_project_by_path(str(project_root.resolve()))
    assert opened is True

    run_action = registry.action("shell.action.run.run")
    debug_action = registry.action("shell.action.run.debug")
    stop_action = registry.action("shell.action.run.stop")
    python_console_action = registry.action("shell.action.run.pythonConsole")
    pause_action = registry.action("shell.action.run.pause")
    assert run_action.isEnabled() is True
    assert debug_action.isEnabled() is True
    assert stop_action.isEnabled() is False
    assert python_console_action.isEnabled() is True
    assert pause_action.isEnabled() is False
