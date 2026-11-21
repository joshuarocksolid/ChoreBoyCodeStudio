"""Save with no edits must not rerun theme, editor, tree, or history work."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication, QDialog  # noqa: E402

from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_settings_save_with_no_changes_skips_expensive_reapply(
    tmp_path: Path,
    _qapp: QApplication,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "hello.py").write_text("print(1)\n", encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=_qapp)
    calls: list[str] = []

    def record(name: str):
        def _called(*_args: object, **_kwargs: object) -> None:
            calls.append(name)

        return _called

    window._shell_theme_workflow.apply_theme_styles = record("theme")  # type: ignore[method-assign]
    window._editor_tab_workflow.apply_editor_preferences_to_open_editors = record("editor")  # type: ignore[method-assign]
    window._editor_tab_workflow.apply_runtime_intelligence_preferences_to_open_editors = record("intelligence")  # type: ignore[method-assign]
    window._diagnostics_orchestrator.relint_open_python_files = record("relint")  # type: ignore[method-assign]
    window._intelligence_cache_workflow.start_symbol_indexing = record("reindex")  # type: ignore[method-assign]
    window._project_tree_ui_workflow.refresh_project_tree_from_disk = record("tree")  # type: ignore[method-assign]
    window._project_tree_ui_workflow.reload_current_project = record("reload")  # type: ignore[method-assign]
    window._local_history_workflow.local_history_store.prune_all_checkpoints = record("prune")  # type: ignore[method-assign]
    window._repl_manager.restart = record("repl")  # type: ignore[method-assign]
    window._plugin_activation_workflow.reload = record("plugins")  # type: ignore[method-assign]

    import app.shell.file_project_commands_workflow as commands

    real_exec = commands.exec_qt
    started = {"at": 0.0}

    def accept_now(dialog: QDialog):  # type: ignore[no-untyped-def]
        started["at"] = time.perf_counter()
        dialog.accept()
        return QDialog.Accepted

    try:
        window._file_project_commands_workflow.open_project_by_path(str(project))
        calls.clear()
        commands.exec_qt = accept_now  # type: ignore[assignment]
        window._file_project_commands_workflow.handle_open_settings_action()
        elapsed_ms = (time.perf_counter() - started["at"]) * 1000.0
        assert calls == []
        assert elapsed_ms < 200.0
        assert window._local_history_retention_policy.max_tracked_file_bytes == 1_000_000
    finally:
        commands.exec_qt = real_exec
        shutdown_main_window_for_test(window, _qapp)
