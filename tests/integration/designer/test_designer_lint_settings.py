"""Integration tests for designer naming-lint settings wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

from app.shell import main_window as main_window_module
from app.persistence.settings_store import save_settings
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


def test_designer_respects_disable_naming_lint_setting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *args, **kwargs: qt_widgets.QMessageBox.Discard)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    save_settings({"designer": {"enable_naming_lint": False}}, state_root=str(state_root.resolve()))

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Lint Settings")
    ui_file = project_root / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True
    surface = window._active_designer_surface()
    assert surface is not None
    rows = [surface._validation_list.item(index).text() for index in range(surface._validation_list.count())]  # type: ignore[attr-defined]
    assert not any("DLINT001" in row for row in rows)
    window.close()


def test_designer_respects_snap_grid_size_setting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *args, **kwargs: qt_widgets.QMessageBox.Discard)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    save_settings({"designer": {"snap_to_grid": True, "grid_size": 16}}, state_root=str(state_root.resolve()))

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Grid Settings")
    ui_file = project_root / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True
    surface = window._active_designer_surface()
    assert surface is not None
    surface._apply_property_mutation(  # type: ignore[attr-defined]
        "pushButton",
        "geometry",
        "set",
        {"x": 31, "y": 31, "width": 100, "height": 40},
    )
    push_button = surface.model.root_widget.find_by_object_name("pushButton")  # type: ignore[union-attr]
    assert push_button is not None
    geometry = push_button.properties["geometry"].value
    assert geometry["x"] == 16
    assert geometry["y"] == 16
    window.close()
