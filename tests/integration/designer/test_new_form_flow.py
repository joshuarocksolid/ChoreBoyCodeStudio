"""Integration tests for New Form workflow scaffolding."""

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


def test_new_form_creates_ui_file_and_opens_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Form Project")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    text_responses = iter([("CustomerForm", True), ("customer_form.ui", True)])
    monkeypatch.setattr("app.shell.main_window.QInputDialog.getText", lambda *args, **kwargs: next(text_responses))
    monkeypatch.setattr(
        "app.shell.main_window.QInputDialog.getItem",
        lambda *args, **kwargs: ("QWidget", True),
    )

    opened_paths: list[str] = []
    monkeypatch.setattr(window, "_open_file_in_editor", lambda file_path: opened_paths.append(file_path) or True)

    window._handle_new_form_action()

    expected_path = (project_root / "customer_form.ui").resolve()
    assert expected_path.is_file()
    xml_payload = expected_path.read_text(encoding="utf-8")
    assert "<class>CustomerForm</class>" in xml_payload
    assert "windowTitle" in xml_payload
    assert opened_paths == [str(expected_path)]
    window.close()
