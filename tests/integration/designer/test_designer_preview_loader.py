"""Integration tests for designer preview and compatibility actions."""

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


def test_designer_preview_and_compatibility_actions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _ensure_qapplication(monkeypatch)
    info_messages: list[str] = []
    warning_messages: list[str] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.information",
        lambda _parent, _title, text: info_messages.append(text),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda *args, **kwargs: warning_messages.append(str(args[2] if len(args) > 2 else kwargs.get("text", ""))),
    )

    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Preview")
    ui_file = project_root / "preview_test.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>PreviewForm</class>"
            "<widget class=\"QWidget\" name=\"PreviewForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    window._handle_designer_compatibility_check_action()
    assert any("compatibility check passed" in message.lower() for message in info_messages)

    window._handle_designer_preview_action()
    assert warning_messages == []

    for top_level in app.topLevelWidgets():
        if top_level is not window:
            top_level.close()
    window.close()
