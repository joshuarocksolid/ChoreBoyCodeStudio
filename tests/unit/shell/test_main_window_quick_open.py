"""Unit tests for MainWindow quick-open behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.file_project_commands_workflow import FileProjectCommandsWorkflow
from app.shell.theme_tokens import ShellThemeTokens

pytestmark = pytest.mark.unit

_DUMMY_TOKENS = ShellThemeTokens(
    window_bg="#1F2428", panel_bg="#262C33", editor_bg="#1B1F23",
    text_primary="#E9ECEF", text_muted="#ADB5BD", border="#3C434A",
    accent="#5B8CFF", gutter_bg="#1F2428", gutter_text="#6C757D",
    line_highlight="#252B33", is_dark=True,
)


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list[Any] = []

    def connect(self, callback) -> None:  # type: ignore[no-untyped-def]
        self._callbacks.append(callback)

    def emit(self, *args: object) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class _FakeQuickOpenDialog:
    instances: list["_FakeQuickOpenDialog"] = []

    def __init__(self, _parent, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
        self.file_preview_requested = _FakeSignal()
        self.file_selected = _FakeSignal()
        self.file_preview_at_line_requested = _FakeSignal()
        self.file_selected_at_line = _FakeSignal()
        self.set_candidates_calls: list[list[Any]] = []
        self.open_calls = 0
        _FakeQuickOpenDialog.instances.append(self)

    def set_candidates(self, candidates) -> None:  # type: ignore[no-untyped-def]
        self.set_candidates_calls.append(list(candidates))

    def open_dialog(self) -> None:
        self.open_calls += 1


def _file_entry(relative_path: str, absolute_path: str) -> SimpleNamespace:
    return SimpleNamespace(relative_path=relative_path, absolute_path=absolute_path, is_directory=False)


def _dir_entry(relative_path: str, absolute_path: str) -> SimpleNamespace:
    return SimpleNamespace(relative_path=relative_path, absolute_path=absolute_path, is_directory=True)


def _make_quick_open_workflow(
    *,
    loaded_project: object | None,
) -> tuple[FileProjectCommandsWorkflow, SimpleNamespace, dict[str, Any]]:
    host = SimpleNamespace(
        dialog_parent=lambda: None,
        loaded_project=loaded_project,
        editor_manager=lambda: host._editor_manager_impl,
    )
    host._editor_manager_impl = SimpleNamespace(active_tab=lambda: None)
    opened_with_preview: list[tuple[str, bool]] = []
    opened_at_line_with_preview: list[tuple[str, int, bool]] = []

    host.editor_tab_factory = lambda: SimpleNamespace(
        open_file_in_editor=lambda path, preview=False: opened_with_preview.append((path, preview)) or True
    )
    host.open_file_at_line = (
        lambda path, line, preview=False: opened_at_line_with_preview.append((path, line, preview))
    )
    host.shell_theme_workflow = lambda: SimpleNamespace(
        resolve_theme_tokens=lambda: _DUMMY_TOKENS,
    )
    host.tree_file_icon_map = lambda: {}
    host.tree_filename_icon_map = lambda: {}

    def _set_quick_open_dialog(dialog: object | None) -> None:
        host._quick_open_dialog_impl = dialog

    host.set_quick_open_dialog = _set_quick_open_dialog
    host.quick_open_dialog = lambda: host._quick_open_dialog_impl
    host._quick_open_dialog_impl = None

    workflow = FileProjectCommandsWorkflow(host)  # type: ignore[arg-type]
    return workflow, host, {
        "opened_with_preview": opened_with_preview,
        "opened_at_line_with_preview": opened_at_line_with_preview,
    }


def test_handle_quick_open_without_project_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, _host, _captured = _make_quick_open_workflow(loaded_project=None)

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.file_project_commands_workflow.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    workflow.handle_quick_open_action()

    assert warnings == [("Quick Open unavailable", "Open a project first.")]


def test_handle_quick_open_filters_directories_and_reuses_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeQuickOpenDialog.instances.clear()
    monkeypatch.setattr("app.shell.file_project_commands_workflow.QuickOpenDialog", _FakeQuickOpenDialog)

    workflow, host, captured = _make_quick_open_workflow(
        loaded_project=SimpleNamespace(
            entries=[
                _file_entry("src/main.py", "/tmp/project/src/main.py"),
                _dir_entry("src", "/tmp/project/src"),
                _file_entry("README.md", "/tmp/project/README.md"),
            ]
        )
    )
    host._editor_manager_impl = SimpleNamespace(open_paths=lambda: set())

    workflow.handle_quick_open_action()

    assert len(_FakeQuickOpenDialog.instances) == 1
    dialog = _FakeQuickOpenDialog.instances[0]
    assert host._quick_open_dialog_impl is dialog
    assert dialog.open_calls == 1
    assert [candidate.relative_path for candidate in dialog.set_candidates_calls[0]] == [
        "src/main.py",
        "README.md",
    ]

    dialog.file_preview_requested.emit("/tmp/project/README.md")
    dialog.file_selected.emit("/tmp/project/src/main.py")
    dialog.file_preview_at_line_requested.emit("/tmp/project/src/main.py", 27)
    dialog.file_selected_at_line.emit("/tmp/project/src/main.py", 9)
    assert captured["opened_with_preview"] == [
        ("/tmp/project/README.md", True),
        ("/tmp/project/src/main.py", False),
    ]
    assert captured["opened_at_line_with_preview"] == [
        ("/tmp/project/src/main.py", 27, True),
        ("/tmp/project/src/main.py", 9, False),
    ]

    host.loaded_project = SimpleNamespace(entries=[_file_entry("pkg/new_file.py", "/tmp/project/pkg/new_file.py")])
    workflow.handle_quick_open_action()

    assert len(_FakeQuickOpenDialog.instances) == 1
    assert dialog.open_calls == 2
    assert [candidate.relative_path for candidate in dialog.set_candidates_calls[1]] == ["pkg/new_file.py"]
