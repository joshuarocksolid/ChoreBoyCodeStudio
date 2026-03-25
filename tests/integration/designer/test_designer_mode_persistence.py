"""Integration tests for persisted designer last-mode preference."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

from app.persistence.settings_store import load_settings
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


def test_designer_last_mode_is_persisted_and_restored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Mode Persist")
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

    first = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(first, "_start_symbol_indexing", lambda _project_root: None)
    assert first._open_project_by_path(str(project_root.resolve())) is True
    assert first._open_file_in_editor(str(ui_file.resolve())) is True
    action = first.menu_registry.action("designer.mode.signals_slots") if first.menu_registry else None
    assert action is not None
    action.trigger()
    first.close()

    payload = load_settings(state_root=str(state_root.resolve()))
    assert payload.get("designer", {}).get("last_mode") == "signals_slots"

    second = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(second, "_start_symbol_indexing", lambda _project_root: None)
    assert second._open_project_by_path(str(project_root.resolve())) is True
    assert second._open_file_in_editor(str(ui_file.resolve())) is True
    surface = second._active_designer_surface()
    assert surface is not None
    assert surface.current_mode == "signals_slots"
    second.close()
