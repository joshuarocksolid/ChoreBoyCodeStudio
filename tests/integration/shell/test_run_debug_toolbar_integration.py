"""Integration tests for run/debug toolbar wiring in main window."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, Qt
from PySide2.QtGui import QKeyEvent
from PySide2.QtWidgets import QWidget

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide2.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_run_debug_toolbar_actions_exist_and_enable_after_project_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _ensure_qapplication(monkeypatch)
    window = MainWindow(state_root=str(Path("/tmp").resolve()))

    registry = window.menu_registry
    assert registry is not None
    assert registry.action("shell.action.run.run") is not None
    assert registry.action("shell.action.run.debug") is not None
    assert registry.action("shell.action.run.pause") is not None
    assert registry.action("shell.action.run.stepOver") is not None
    assert registry.action("shell.action.run.toggleBreakpoint") is not None

    project_root = Path("/tmp/choreboy_toolbar_project")
    if project_root.exists():
        import shutil

        shutil.rmtree(project_root)
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('toolbar')\n", encoding="utf-8")
    opened = window._open_project_by_path(str(project_root.resolve()))
    assert opened is True

    run_action = registry.action("shell.action.run.run")
    debug_action = registry.action("shell.action.run.debug")
    stop_action = registry.action("shell.action.run.stop")
    python_console_action = registry.action("shell.action.run.pythonConsole")
    pause_action = registry.action("shell.action.run.pause")
    assert run_action.isEnabled() is True
    assert debug_action.isEnabled() is True
    assert stop_action.isEnabled() is False
    assert python_console_action.isEnabled() is True
    assert pause_action.isEnabled() is False


def test_f5_f6_shortcuts_are_focus_scoped_between_designer_and_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "run.py").write_text("print('shortcut arbitration')\n", encoding="utf-8")
    ui_file = project_root / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>ShortcutForm</class>"
            "<widget class=\"QWidget\" name=\"ShortcutForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    registry = window.menu_registry
    assert registry is not None
    run_action = registry.action("shell.action.run.run")
    continue_action = registry.action("shell.action.run.continue")
    buddy_action = registry.action("designer.mode.buddy")
    tab_action = registry.action("designer.mode.tab_order")
    assert run_action is not None
    assert continue_action is not None
    assert buddy_action is not None
    assert tab_action is not None

    run_calls: list[str] = []
    continue_calls: list[str] = []
    run_action.triggered.connect(lambda: run_calls.append("run"))
    continue_action.triggered.connect(lambda: continue_calls.append("continue"))

    surface = window._active_designer_surface()
    assert surface is not None
    canvas_tree = surface._canvas._canvas_tree  # type: ignore[attr-defined]
    monkeypatch.setattr("app.shell.main_window.QApplication.focusWidget", lambda: canvas_tree)
    f5_event = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_F5, Qt.NoModifier)
    assert window._handle_designer_mode_shortcut_override(f5_event) is True  # type: ignore[attr-defined]
    assert surface.current_mode == "buddy"
    f6_event = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_F6, Qt.NoModifier)
    assert window._handle_designer_mode_shortcut_override(f6_event) is True  # type: ignore[attr-defined]
    assert surface.current_mode == "tab_order"
    assert run_calls == []
    assert continue_calls == []

    continue_action.setEnabled(True)
    focus_proxy = QWidget(window)
    focus_proxy.setFocusPolicy(Qt.StrongFocus)
    focus_proxy.show()
    monkeypatch.setattr("app.shell.main_window.QApplication.focusWidget", lambda: focus_proxy)
    f5_event_outside = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_F5, Qt.NoModifier)
    f6_event_outside = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_F6, Qt.NoModifier)
    assert window._handle_designer_mode_shortcut_override(f5_event_outside) is False  # type: ignore[attr-defined]
    assert window._handle_designer_mode_shortcut_override(f6_event_outside) is False  # type: ignore[attr-defined]
    run_action.trigger()
    continue_action.trigger()
    assert run_calls == ["run"]
    assert continue_calls == ["continue"]
    assert surface.current_mode == "tab_order"
