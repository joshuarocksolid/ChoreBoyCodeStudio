"""Integration tests for Designer layout action handlers."""

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


def test_designer_layout_actions_apply_and_break(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr("app.shell.main_window.QMessageBox.warning", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.shell.main_window.QMessageBox.information", lambda *args, **kwargs: None)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Layouts")
    ui_file = project_root / "layout_test.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>LayoutForm</class>"
            "<widget class=\"QWidget\" name=\"LayoutForm\">"
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
    assert surface.model is not None
    assert surface.model.root_widget.layout is None

    window._handle_designer_layout_vertical_action()
    assert surface.model.root_widget.layout is not None
    assert surface.model.root_widget.layout.class_name == "QVBoxLayout"

    undo_action = window.menu_registry.action("shell.action.edit.undo") if window.menu_registry else None
    assert undo_action is not None and undo_action.isEnabled()
    window._handle_undo_action()
    assert surface.model.root_widget.layout is None

    window._handle_redo_action()
    assert surface.model.root_widget.layout is not None

    window._handle_designer_layout_break_action()
    assert surface.model.root_widget.layout is None
    window.close()


def test_designer_alignment_distribute_adjust_and_context_text_edit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr("app.shell.main_window.QMessageBox.warning", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.shell.main_window.QMessageBox.information", lambda *args, **kwargs: None)
    monkeypatch.setattr("PySide2.QtWidgets.QInputDialog.getText", lambda *args, **kwargs: ("Renamed", True))
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Affordances")
    ui_file = project_root / "affordances.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class>"
            "<widget class=\"QWidget\" name=\"Form\">"
            "<widget class=\"QPushButton\" name=\"pushButton\">"
            "<property name=\"text\"><string>One</string></property>"
            "<property name=\"geometry\"><rect><x>16</x><y>16</y><width>120</width><height>32</height></rect></property>"
            "</widget>"
            "<widget class=\"QLabel\" name=\"label\">"
            "<property name=\"text\"><string>Two</string></property>"
            "<property name=\"geometry\"><rect><x>200</x><y>48</y><width>120</width><height>32</height></rect></property>"
            "</widget>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\">"
            "<property name=\"placeholderText\"><string>Three</string></property>"
            "<property name=\"geometry\"><rect><x>320</x><y>80</y><width>220</width><height>32</height></rect></property>"
            "</widget>"
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

    surface._selection_controller.set_selected_object_names(["pushButton", "label"])  # type: ignore[attr-defined]
    window._handle_designer_layout_align_left_action()
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    label = surface.model.root_widget.find_by_object_name("label")
    assert push_button is not None and label is not None
    assert push_button.properties["geometry"].value["x"] == label.properties["geometry"].value["x"]

    surface._selection_controller.set_selected_object_names(["pushButton", "label", "lineEdit"])  # type: ignore[attr-defined]
    window._handle_designer_layout_distribute_vertical_action()
    y_positions = [
        int(surface.model.root_widget.find_by_object_name(name).properties["geometry"].value["y"])  # type: ignore[union-attr]
        for name in ("pushButton", "label", "lineEdit")
    ]
    assert y_positions[0] < y_positions[1] < y_positions[2]

    surface._selection_controller.set_selected_object_names(["lineEdit"])  # type: ignore[attr-defined]
    window._handle_designer_layout_adjust_size_action()
    line_edit = surface.model.root_widget.find_by_object_name("lineEdit")
    assert line_edit is not None
    assert line_edit.properties["geometry"].value["width"] == 120
    assert line_edit.properties["geometry"].value["height"] == 32

    surface._selection_controller.set_selected_object_names(["pushButton"])  # type: ignore[attr-defined]
    surface._handle_canvas_context_action("designer.canvas.context.edit_text")  # type: ignore[attr-defined]
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    assert push_button is not None
    assert push_button.properties["text"].value == "Renamed"
    window.close()
