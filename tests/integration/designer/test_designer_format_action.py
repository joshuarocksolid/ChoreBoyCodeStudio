"""Integration tests for designer format-ui command."""

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


def test_designer_format_action_normalizes_noncanonical_ui(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Format")
    ui_file = project_root / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class><widget class=\"QWidget\" name=\"Form\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(main_window_module.QMessageBox, "information", lambda *args, **kwargs: 0)
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *args, **kwargs: qt_widgets.QMessageBox.Discard)

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    format_action = window.menu_registry.action("designer.form.format_ui_xml") if window.menu_registry else None
    assert format_action is not None
    format_action.trigger()

    surface = window._active_designer_surface()
    assert surface is not None
    assert surface.is_dirty is True
    assert "\n <class>Form</class>" in surface.serialize_to_ui_string()
    window.close()
