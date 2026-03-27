"""Integration tests for designer action/menu/toolbar authoring workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

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


def test_designer_action_editor_crud_and_placement_persist_on_save(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr("app.shell.main_window.QMessageBox.warning", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.shell.main_window.QMessageBox.information", lambda *args, **kwargs: None)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Actions")
    ui_file = project_root / "main_window.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>MainWindow</class>"
            "<widget class=\"QMainWindow\" name=\"MainWindow\">"
            "<widget class=\"QWidget\" name=\"centralWidget\"/>"
            "<widget class=\"QMenuBar\" name=\"menuBar\"/>"
            "<widget class=\"QToolBar\" name=\"mainToolBar\"/>"
            "<widget class=\"QStatusBar\" name=\"statusBar\"/>"
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
    assert surface.model is not None

    action_panel = surface._action_editor_panel  # type: ignore[attr-defined]
    action_panel.add_action_requested.emit("actionOpen")
    action_panel.add_action_requested.emit("actionSave")
    action_panel.add_group_requested.emit("fileGroup")
    action_panel.action_group_changed.emit("actionOpen", "fileGroup")
    action_panel.group_add_action_requested.emit("fileGroup", "actionSave")
    action_panel.placement_add_action_requested.emit("menuBar", "actionOpen")
    action_panel.placement_add_action_requested.emit("menuBar", "actionSave")
    action_panel.placement_move_action_requested.emit("menuBar", "actionSave", -1)
    action_panel.placement_remove_action_requested.emit("menuBar", "actionOpen")

    assert [action.name for action in surface.model.actions] == ["actionOpen", "actionSave"]
    assert [group.name for group in surface.model.action_groups] == ["fileGroup"]
    assert [ref.name for ref in surface.model.action_groups[0].add_actions] == ["actionOpen", "actionSave"]
    menu_bar = surface.model.root_widget.find_by_object_name("menuBar")
    assert menu_bar is not None
    assert [ref.name for ref in menu_bar.add_actions] == ["actionSave"]

    assert window._save_tab(str(ui_file.resolve())) is True

    reloaded_window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(reloaded_window, "_start_symbol_indexing", lambda _project_root: None)
    assert reloaded_window._open_project_by_path(str(project_root.resolve())) is True
    assert reloaded_window._open_file_in_editor(str(ui_file.resolve())) is True
    reloaded_surface = reloaded_window._active_designer_surface()
    assert reloaded_surface is not None
    assert reloaded_surface.model is not None
    assert [action.name for action in reloaded_surface.model.actions] == ["actionOpen", "actionSave"]
    assert [group.name for group in reloaded_surface.model.action_groups] == ["fileGroup"]
    assert [ref.name for ref in reloaded_surface.model.action_groups[0].add_actions] == ["actionOpen", "actionSave"]
    reloaded_menu_bar = reloaded_surface.model.root_widget.find_by_object_name("menuBar")
    assert reloaded_menu_bar is not None
    assert [ref.name for ref in reloaded_menu_bar.add_actions] == ["actionSave"]
    reloaded_window.close()
    window.close()
