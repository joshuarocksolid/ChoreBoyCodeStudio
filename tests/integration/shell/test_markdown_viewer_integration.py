"""Integration coverage for Markdown viewer tabs in MainWindow."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.markdown_editor_pane import MarkdownEditorPane  # noqa: E402
from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide2.QtWidgets import QApplication
    import PySide2.QtGui as qt_gui
    import PySide2.QtWidgets as qt_widgets

    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_open_markdown_file_uses_preview_pane_without_breaking_save_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Markdown Project")
    readme = project_root / "README.md"
    readme.write_text("# Original\n", encoding="utf-8")

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True

    readme_path = str(readme.resolve())
    assert window._editor_tab_factory.open_file_in_editor(readme_path) is True
    app.processEvents()

    markdown_pane = window._markdown_panes_by_path.get(readme_path)
    assert isinstance(markdown_pane, MarkdownEditorPane)
    source_editor = window._editor_widgets_by_path[readme_path]
    assert markdown_pane.source_editor() is source_editor

    source_editor.setPlainText("# Changed\n")
    app.processEvents()

    tab_state = window._editor_manager.get_tab(readme_path)
    assert tab_state is not None
    assert tab_state.is_dirty

    assert window._save_workflow.save_tab(readme_path, apply_transforms=False)
    assert readme.read_text(encoding="utf-8") == "# Changed\n"
    assert not window._editor_manager.get_tab(readme_path).is_dirty  # type: ignore[union-attr]
    window.close()
