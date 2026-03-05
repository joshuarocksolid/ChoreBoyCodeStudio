"""Integration tests for `.ui` routing into Designer surface tabs."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

from app.designer.editor_surface import DesignerEditorSurface
from app.editors.code_editor_widget import CodeEditorWidget
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


def test_open_ui_file_uses_designer_surface(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Route")
    ui_file = project_root / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class>"
            "<widget class=\"QWidget\" name=\"Form\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    assert str(ui_file.resolve()) in window._designer_widgets_by_path
    assert str(ui_file.resolve()) not in window._editor_widgets_by_path
    assert window._editor_tabs_widget is not None
    assert isinstance(window._editor_tabs_widget.currentWidget(), DesignerEditorSurface)
    preview_action = window.menu_registry.action("designer.form.preview") if window.menu_registry else None
    layout_action = window.menu_registry.action("designer.layout.vertical") if window.menu_registry else None
    mode_action = window.menu_registry.action("designer.mode.signals_slots") if window.menu_registry else None
    tab_mode_action = window.menu_registry.action("designer.mode.tab_order") if window.menu_registry else None
    add_resource_action = window.menu_registry.action("designer.form.add_resource") if window.menu_registry else None
    assert preview_action is not None and preview_action.isEnabled()
    assert layout_action is not None and layout_action.isEnabled()
    assert mode_action is not None and mode_action.isEnabled()
    assert tab_mode_action is not None and tab_mode_action.isEnabled()
    assert add_resource_action is not None and add_resource_action.isEnabled()
    mode_action.trigger()
    surface = window._active_designer_surface()
    assert surface is not None
    assert surface.current_mode == "signals_slots"
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Connections"  # type: ignore[attr-defined]
    tab_mode_action.trigger()
    assert surface.current_mode == "tab_order"
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Tab Order"  # type: ignore[attr-defined]
    monkeypatch.setattr(qt_widgets.QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", ""))
    add_resource_action.trigger()
    assert [resource.location for resource in surface.model.resources] == []  # type: ignore[union-attr]
    window.close()


def test_open_python_file_still_uses_code_editor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Text Route")
    py_file = project_root / "main.py"
    py_file.write_text("print('hello')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(py_file.resolve())) is True

    assert str(py_file.resolve()) in window._editor_widgets_by_path
    assert str(py_file.resolve()) not in window._designer_widgets_by_path
    assert window._editor_tabs_widget is not None
    assert isinstance(window._editor_tabs_widget.currentWidget(), CodeEditorWidget)
    preview_action = window.menu_registry.action("designer.form.preview") if window.menu_registry else None
    layout_action = window.menu_registry.action("designer.layout.vertical") if window.menu_registry else None
    mode_action = window.menu_registry.action("designer.mode.signals_slots") if window.menu_registry else None
    tab_mode_action = window.menu_registry.action("designer.mode.tab_order") if window.menu_registry else None
    add_resource_action = window.menu_registry.action("designer.form.add_resource") if window.menu_registry else None
    assert preview_action is not None and not preview_action.isEnabled()
    assert layout_action is not None and not layout_action.isEnabled()
    assert mode_action is not None and not mode_action.isEnabled()
    assert tab_mode_action is not None and not tab_mode_action.isEnabled()
    assert add_resource_action is not None and not add_resource_action.isEnabled()
    window.close()
