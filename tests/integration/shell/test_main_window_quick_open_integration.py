"""Integration tests for MainWindow quick-open workflow."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtWidgets as qt_widgets

from app.core import constants
from app.project.project_service import create_blank_project
from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.main_window_test_helpers import prepare_main_window_for_test

pytestmark = pytest.mark.integration


def _wait_for_quick_open_results(app) -> None:  # type: ignore[no-untyped-def]
    deadline = time.time() + 0.15
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def _first_quick_open_relative_path(dialog) -> str:  # type: ignore[no-untyped-def]
    ranked = dialog._list_model.ranked_at(0)
    assert ranked is not None
    return ranked.candidate.relative_path


def _quick_open_index_for_relative_path(dialog, relative_path: str) -> int:  # type: ignore[no-untyped-def]
    for index in range(dialog._list_model.rowCount()):
        ranked = dialog._list_model.ranked_at(index)
        if ranked is not None and ranked.candidate.relative_path == relative_path:
            return index
    raise AssertionError(f"No quick-open match for {relative_path!r}")


def _open_quick_open_dialog(window, app) -> qt_widgets.QDialog:  # type: ignore[no-untyped-def]
    window._file_project_commands_workflow.handle_quick_open_action()
    app.processEvents()
    dialog = window._quick_open_dialog
    assert dialog is not None
    return dialog


def test_quick_open_search_preview_and_edit_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    """Search ranking, preview promotion, and edit promotion in one MainWindow session."""
    app = shell_qapp
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Quick Open Project")
    (project_root / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    nested_dir = project_root / "pkg"
    nested_dir.mkdir(parents=True, exist_ok=True)
    beta_module = nested_dir / "beta_module.py"
    beta_module.write_text("print('beta')\n", encoding="utf-8")
    first_file = project_root / "first.py"
    second_file = project_root / "second.py"
    first_file.write_text("print('first')\n", encoding="utf-8")
    second_file.write_text("print('second')\n", encoding="utf-8")
    beta_file = project_root / "beta.py"
    beta_file.write_text("print('beta')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    prepare_main_window_for_test(window, app=app)
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True

    dialog = _open_quick_open_dialog(window, app)
    dialog._search_input.setText("beta_module")
    _wait_for_quick_open_results(app)
    assert dialog._list_model.rowCount() >= 1
    assert _first_quick_open_relative_path(dialog) == "pkg/beta_module.py"
    dialog._accept_current()
    app.processEvents()
    active_tab = window._editor_manager.active_tab()
    assert active_tab is not None
    assert active_tab.file_path == str(beta_module.resolve())

    window._editor_tab_workflow.reset_editor_tabs()
    app.processEvents()

    dialog = _open_quick_open_dialog(window, app)
    dialog._search_input.setText("beta")
    _wait_for_quick_open_results(app)
    preview_index = dialog._list_model.index(_quick_open_index_for_relative_path(dialog, "beta.py"), 0)
    dialog._on_item_preview(preview_index)
    app.processEvents()
    active_tab = window._editor_manager.active_tab()
    assert active_tab is not None
    assert active_tab.file_path == str(beta_file.resolve())
    assert active_tab.is_preview is True
    dialog._accept_current()
    app.processEvents()
    promoted_tab = window._editor_manager.active_tab()
    assert promoted_tab is not None
    assert promoted_tab.file_path == str(beta_file.resolve())
    assert promoted_tab.is_preview is False

    window._editor_tab_workflow.reset_editor_tabs()
    app.processEvents()

    dialog = _open_quick_open_dialog(window, app)
    dialog._search_input.setText("first")
    _wait_for_quick_open_results(app)
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

    assert window._editor_tab_factory.open_file_in_editor(str(second_file.resolve()), preview=True) is True
    app.processEvents()
    assert window._editor_tabs_widget is not None
    assert window._editor_tabs_widget.count() == 2
    assert window._save_workflow.handle_save_all_action() is True
    shutdown_main_window_for_test(window, app)


def test_quick_open_can_open_under_light_and_dark_themes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Theme Check Project")
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    prepare_main_window_for_test(window, app=app)
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True

    for mode in (constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK):
        window._shell_preferences_runtime.handle_set_theme(mode, skip_theme_styles=True)
        dialog = _open_quick_open_dialog(window, app)
        assert dialog._search_input is not None
        assert dialog._total_count >= 1
        dialog.hide()

    shutdown_main_window_for_test(window, app)
