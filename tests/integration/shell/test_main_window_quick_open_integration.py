"""Integration tests for MainWindow quick-open workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

from app.core import constants
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


def test_quick_open_opens_selected_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Quick Open Project")
    (project_root / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    nested_dir = project_root / "pkg"
    nested_dir.mkdir(parents=True, exist_ok=True)
    beta_file = nested_dir / "beta_module.py"
    beta_file.write_text("print('beta')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    window._handle_quick_open_action()
    app.processEvents()

    dialog = window._quick_open_dialog
    assert dialog is not None

    dialog._search_input.setText("beta")
    app.processEvents()
    assert dialog._list_model.rowCount() >= 1

    first_item_text = dialog._list_model.stringList()[0]
    assert first_item_text == "pkg/beta_module.py"

    dialog._accept_current()
    app.processEvents()

    active_tab = window._editor_manager.active_tab()
    assert active_tab is not None
    assert active_tab.file_path == str(beta_file.resolve())
    window.close()


def test_quick_open_preview_then_enter_promotes_to_permanent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Quick Open Preview Project")
    target_file = project_root / "beta.py"
    target_file.write_text("print('beta')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    window._handle_quick_open_action()
    app.processEvents()
    dialog = window._quick_open_dialog
    assert dialog is not None
    dialog._search_input.setText("beta")
    app.processEvents()
    assert dialog._list_model.rowCount() == 1

    preview_index = dialog._list_model.index(0, 0)
    dialog._on_item_preview(preview_index)
    app.processEvents()
    active_tab = window._editor_manager.active_tab()
    assert active_tab is not None
    assert active_tab.file_path == str(target_file.resolve())
    assert active_tab.is_preview is True

    dialog._accept_current()
    app.processEvents()
    promoted_tab = window._editor_manager.active_tab()
    assert promoted_tab is not None
    assert promoted_tab.file_path == str(target_file.resolve())
    assert promoted_tab.is_preview is False
    window.close()


def test_preview_tab_promotes_on_first_edit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Preview Edit Promotion")
    first_file = project_root / "first.py"
    second_file = project_root / "second.py"
    first_file.write_text("print('first')\n", encoding="utf-8")
    second_file.write_text("print('second')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    window._handle_quick_open_action()
    app.processEvents()
    dialog = window._quick_open_dialog
    assert dialog is not None
    dialog._search_input.setText("first")
    app.processEvents()
    assert dialog._list_model.rowCount() == 1
    preview_index = dialog._list_model.index(0, 0)
    dialog._on_item_preview(preview_index)
    app.processEvents()

    first_tab = window._editor_manager.active_tab()
    assert first_tab is not None
    assert first_tab.file_path == str(first_file.resolve())
    assert first_tab.is_preview is True

    editor = window._editor_widgets_by_path[str(first_file.resolve())]
    editor.insertPlainText("# edited")
    app.processEvents()

    promoted_tab = window._editor_manager.get_tab(str(first_file.resolve()))
    assert promoted_tab is not None
    assert promoted_tab.is_preview is False

    assert window._open_file_in_editor(str(second_file.resolve()), preview=True) is True
    app.processEvents()
    assert window._editor_tabs_widget is not None
    assert window._editor_tabs_widget.count() == 2
    assert window._handle_save_all_action() is True
    window.close()


def test_quick_open_can_open_under_light_and_dark_themes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Theme Check Project")
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    for mode in (constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK):
        window._handle_set_theme(mode)
        window._handle_quick_open_action()
        app.processEvents()

        dialog = window._quick_open_dialog
        assert dialog is not None
        assert dialog._search_input is not None
        assert dialog._total_count >= 1
        dialog.hide()

    window.close()
