"""Integration tests for designer reusable component actions."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

from app.project.project_service import create_blank_project
from app.shell import main_window as main_window_module
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


def test_designer_save_and_insert_component_actions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Components")
    ui_file = project_root / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class>"
            "<widget class=\"QWidget\" name=\"Form\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "<widget class=\"QGroupBox\" name=\"targetGroup\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *args, **kwargs: qt_widgets.QMessageBox.Discard)
    monkeypatch.setattr(main_window_module.QMessageBox, "information", lambda *args, **kwargs: 0)

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True
    surface = window._active_designer_surface()
    assert surface is not None

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    monkeypatch.setattr(main_window_module.QInputDialog, "getText", lambda *args, **kwargs: ("ButtonPart", True))
    window._handle_designer_save_component_action()
    assert "ButtonPart" in surface.available_component_names()

    surface._selection_controller.set_selected_object_name("targetGroup")  # type: ignore[attr-defined]
    monkeypatch.setattr(main_window_module.QInputDialog, "getItem", lambda *args, **kwargs: ("ButtonPart", True))
    window._handle_designer_insert_component_action()

    target = surface.model.root_widget.find_by_object_name("targetGroup")  # type: ignore[union-attr]
    assert target is not None
    assert any(child.class_name == "QPushButton" for child in target.children)

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    window._handle_designer_duplicate_selection_action()
    assert surface.model.root_widget.find_by_object_name("pushButton1") is not None  # type: ignore[union-attr]
    window.close()


def test_designer_clipboard_edit_actions_cut_copy_paste(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Clipboard")
    ui_file = project_root / "clipboard.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class>"
            "<widget class=\"QWidget\" name=\"Form\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "<widget class=\"QGroupBox\" name=\"targetGroup\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *args, **kwargs: qt_widgets.QMessageBox.Discard)
    monkeypatch.setattr(main_window_module.QMessageBox, "information", lambda *args, **kwargs: 0)

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True
    surface = window._active_designer_surface()
    assert surface is not None
    assert surface.model is not None

    copy_action = window.menu_registry.action("shell.action.edit.copy") if window.menu_registry else None
    cut_action = window.menu_registry.action("shell.action.edit.cut") if window.menu_registry else None
    paste_action = window.menu_registry.action("shell.action.edit.paste") if window.menu_registry else None
    assert copy_action is not None and copy_action.isEnabled()
    assert cut_action is not None and cut_action.isEnabled()
    assert paste_action is not None and paste_action.isEnabled()

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    window._handle_copy_action()
    assert "ClipboardPayload" in qt_widgets.QApplication.clipboard().text()

    surface._selection_controller.set_selected_object_name("targetGroup")  # type: ignore[attr-defined]
    window._handle_paste_action()
    target_group = surface.model.root_widget.find_by_object_name("targetGroup")
    assert target_group is not None
    assert any(child.object_name == "pushButton1" for child in target_group.children)

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    window._handle_cut_action()
    assert surface.model.root_widget.find_by_object_name("pushButton") is None
    window._handle_undo_action()
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None
    window.close()
