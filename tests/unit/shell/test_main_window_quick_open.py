"""Unit tests for MainWindow quick-open behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list[Any] = []

    def connect(self, callback) -> None:  # type: ignore[no-untyped-def]
        self._callbacks.append(callback)

    def emit(self, value: str) -> None:
        for callback in list(self._callbacks):
            callback(value)


class _FakeQuickOpenDialog:
    instances: list["_FakeQuickOpenDialog"] = []

    def __init__(self, _parent) -> None:  # type: ignore[no-untyped-def]
        self.file_selected = _FakeSignal()
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


def test_handle_quick_open_without_project_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = None
    window_any._quick_open_dialog = None

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    MainWindow._handle_quick_open_action(window)

    assert warnings == [("Quick Open unavailable", "Open a project first.")]


def test_handle_quick_open_filters_directories_and_reuses_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeQuickOpenDialog.instances.clear()
    monkeypatch.setattr("app.shell.main_window.QuickOpenDialog", _FakeQuickOpenDialog)

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(
        entries=[
            _file_entry("src/main.py", "/tmp/project/src/main.py"),
            _dir_entry("src", "/tmp/project/src"),
            _file_entry("README.md", "/tmp/project/README.md"),
        ]
    )
    window_any._quick_open_dialog = None
    opened_paths: list[str] = []
    window_any._open_file_in_editor = lambda path: opened_paths.append(path)

    MainWindow._handle_quick_open_action(window)

    assert len(_FakeQuickOpenDialog.instances) == 1
    dialog = _FakeQuickOpenDialog.instances[0]
    assert window_any._quick_open_dialog is dialog
    assert dialog.open_calls == 1
    assert [candidate.relative_path for candidate in dialog.set_candidates_calls[0]] == [
        "src/main.py",
        "README.md",
    ]

    dialog.file_selected.emit("/tmp/project/README.md")
    assert opened_paths == ["/tmp/project/README.md"]

    window_any._loaded_project = SimpleNamespace(entries=[_file_entry("pkg/new_file.py", "/tmp/project/pkg/new_file.py")])
    MainWindow._handle_quick_open_action(window)

    assert len(_FakeQuickOpenDialog.instances) == 1
    assert dialog.open_calls == 2
    assert [candidate.relative_path for candidate in dialog.set_candidates_calls[1]] == ["pkg/new_file.py"]
