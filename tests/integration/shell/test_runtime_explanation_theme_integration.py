"""Theme integration checks for runtime explanation surfaces."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QDialog, QTextBrowser

from app.core import constants
from app.core.models import CapabilityCheckResult, CapabilityProbeReport
from app.project.project_service import create_blank_project
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    return app


def _dispose_window(window: MainWindow, app) -> None:  # type: ignore[no-untyped-def]
    window._is_shutting_down = True
    window._begin_shutdown_teardown()
    window._stop_active_run_before_close()
    window.deleteLater()
    app.processEvents()


def test_runtime_explanation_surfaces_open_under_light_and_dark_themes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Runtime Theme Project")

    runtime_dialogs: list[object] = []
    onboarding_dialogs: list[object] = []

    def fake_runtime_center_exec(dialog) -> int:  # type: ignore[no-untyped-def]
        runtime_dialogs.append(dialog)
        return QDialog.Rejected

    def fake_dialog_exec(dialog) -> int:  # type: ignore[no-untyped-def]
        if dialog.objectName() == "shell.runtimeOnboardingDialog":
            onboarding_dialogs.append(dialog)
        return QDialog.Rejected

    monkeypatch.setattr("app.shell.main_window.RuntimeCenterDialog.exec_", fake_runtime_center_exec)
    monkeypatch.setattr("app.shell.main_window.QDialog.exec_", fake_dialog_exec)

    window = MainWindow(
        startup_report=CapabilityProbeReport(
            checks=[CapabilityCheckResult("apprun_presence", False, "AppRun missing")]
        ),
        state_root=str(state_root.resolve()),
    )
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    run_target_panel = window.findChild(qt_widgets.QFrame, "shell.toolbar.btn.runTarget")
    assert run_target_panel is not None

    for mode in (constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK):
        window._handle_set_theme(mode)
        style_sheet = window.styleSheet()
        assert "QDialog#shell\\.runtimeCenterDialog" in style_sheet
        assert "QWidget#shell\\.welcome\\.onboardingCard" in style_sheet

        assert run_target_panel.isEnabled() is True
        assert "Run Project" in run_target_panel.toolTip()

        window._handle_runtime_center_action()
        app.processEvents()

        assert runtime_dialogs
        runtime_dialog = runtime_dialogs[-1]
        assert runtime_dialog.objectName() == "shell.runtimeCenterDialog"
        assert runtime_dialog.issue_list.count() == 1
        assert runtime_dialog.findChild(QTextBrowser, "shell.runtimeCenterDialog.detailBrowser") is not None

        window._handle_runtime_onboarding_action()
        app.processEvents()

        assert onboarding_dialogs
        onboarding_dialog = onboarding_dialogs[-1]
        assert onboarding_dialog.objectName() == "shell.runtimeOnboardingDialog"
        assert onboarding_dialog.findChild(qt_widgets.QWidget, "shell.welcome") is not None
        assert onboarding_dialog.findChild(qt_widgets.QWidget, "shell.welcome.onboardingCard") is not None

    _dispose_window(window, app)
