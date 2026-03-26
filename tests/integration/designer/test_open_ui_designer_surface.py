"""Integration tests for `.ui` routing into Designer surface tabs."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtCore import QMimeData

from app.designer.editor_surface import DesignerEditorSurface
from app.designer.palette.palette_panel import PALETTE_WIDGET_MIME
from app.editors.code_editor_widget import CodeEditorWidget
from app.project.project_service import create_blank_project
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


class _FakeDropEvent:
    def __init__(self, class_name: str) -> None:
        self._mime_data = QMimeData()
        self._mime_data.setData(PALETTE_WIDGET_MIME, class_name.encode("utf-8"))
        self.accepted = False
        self.ignored = False

    def mimeData(self) -> QMimeData:  # noqa: N802 - Qt-style
        return self._mime_data

    def acceptProposedAction(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


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
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda *args, **kwargs: qt_widgets.QMessageBox.Discard,
    )
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
    buddy_mode_action = window.menu_registry.action("designer.mode.buddy") if window.menu_registry else None
    add_resource_action = window.menu_registry.action("designer.form.add_resource") if window.menu_registry else None
    promote_action = window.menu_registry.action("designer.form.promote_widget") if window.menu_registry else None
    format_action = window.menu_registry.action("designer.form.format_ui_xml") if window.menu_registry else None
    save_component_action = window.menu_registry.action("designer.form.save_component") if window.menu_registry else None
    insert_component_action = window.menu_registry.action("designer.form.insert_component") if window.menu_registry else None
    duplicate_action = window.menu_registry.action("designer.form.duplicate_selection") if window.menu_registry else None
    assert preview_action is not None and preview_action.isEnabled()
    assert layout_action is not None and layout_action.isEnabled()
    assert mode_action is not None and mode_action.isEnabled()
    assert tab_mode_action is not None and tab_mode_action.isEnabled()
    assert buddy_mode_action is not None and buddy_mode_action.isEnabled()
    assert add_resource_action is not None and add_resource_action.isEnabled()
    assert promote_action is not None and promote_action.isEnabled()
    assert format_action is not None and format_action.isEnabled()
    assert save_component_action is not None and save_component_action.isEnabled()
    assert insert_component_action is not None and insert_component_action.isEnabled()
    assert duplicate_action is not None and duplicate_action.isEnabled()
    initial_dirty = surface = None
    surface = window._active_designer_surface()
    assert surface is not None
    initial_dirty = surface.is_dirty
    assert initial_dirty is False
    assert surface.can_undo is False

    # Simulate canvas drag/drop insertion path via dropEvent.
    event = _FakeDropEvent("QPushButton")
    surface._canvas.dropEvent(event)  # type: ignore[attr-defined]
    assert event.accepted is True
    assert event.ignored is False
    assert surface.model is not None
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None
    assert surface.is_dirty is True
    assert surface.can_undo is True

    mode_action.trigger()
    tab_titles = [surface._inspector_tabs.tabText(index) for index in range(surface._inspector_tabs.count())]  # type: ignore[attr-defined]
    assert "Library" in tab_titles
    assert surface.current_mode == "signals_slots"
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Signals"  # type: ignore[attr-defined]
    status_label = window.findChild(qt_widgets.QLabel, "shell.editorStatusLabel")
    assert status_label is not None
    assert "Mode Signals/Slots" in status_label.text()
    tab_mode_action.trigger()
    assert surface.current_mode == "tab_order"
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Tab \u2195"  # type: ignore[attr-defined]
    assert "Mode Tab Order" in status_label.text()
    buddy_mode_action.trigger()
    assert surface.current_mode == "buddy"
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Buddy"  # type: ignore[attr-defined]
    assert "Mode Buddy" in status_label.text()
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
    buddy_mode_action = window.menu_registry.action("designer.mode.buddy") if window.menu_registry else None
    add_resource_action = window.menu_registry.action("designer.form.add_resource") if window.menu_registry else None
    promote_action = window.menu_registry.action("designer.form.promote_widget") if window.menu_registry else None
    format_action = window.menu_registry.action("designer.form.format_ui_xml") if window.menu_registry else None
    save_component_action = window.menu_registry.action("designer.form.save_component") if window.menu_registry else None
    insert_component_action = window.menu_registry.action("designer.form.insert_component") if window.menu_registry else None
    duplicate_action = window.menu_registry.action("designer.form.duplicate_selection") if window.menu_registry else None
    assert preview_action is not None and not preview_action.isEnabled()
    assert layout_action is not None and not layout_action.isEnabled()
    assert mode_action is not None and not mode_action.isEnabled()
    assert tab_mode_action is not None and not tab_mode_action.isEnabled()
    assert buddy_mode_action is not None and not buddy_mode_action.isEnabled()
    assert add_resource_action is not None and not add_resource_action.isEnabled()
    assert promote_action is not None and not promote_action.isEnabled()
    assert format_action is not None and not format_action.isEnabled()
    assert save_component_action is not None and not save_component_action.isEnabled()
    assert insert_component_action is not None and not insert_component_action.isEnabled()
    assert duplicate_action is not None and not duplicate_action.isEnabled()
    window.close()


def test_designer_validation_issues_are_visible_in_global_problems_panel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda *args, **kwargs: qt_widgets.QMessageBox.Discard,
    )
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Problems Bridge")
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

    surface = window._active_designer_surface()
    assert surface is not None
    validation_rows = [surface._validation_list.item(index).text() for index in range(surface._validation_list.count())]  # type: ignore[attr-defined]
    assert any("DLAYOUT001" in row for row in validation_rows)

    problems_panel = window._problems_panel
    assert problems_panel is not None
    assert problems_panel.problem_count() >= 1
    assert problems_panel.tree_widget().topLevelItemCount() >= 1
    first_group = problems_panel.tree_widget().topLevelItem(0)
    assert first_group is not None
    assert "form.ui" in first_group.text(1)
    window.close()
