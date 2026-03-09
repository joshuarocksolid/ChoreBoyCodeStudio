"""Unit tests for backgrounded reference and rename actions in MainWindow."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


class _FakeBackgroundTasks:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _build_window_for_reference_actions() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    window_any._editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(file_path="/tmp/project/main.py")
    )
    editor_widget = SimpleNamespace(
        toPlainText=lambda: "from helper import task_name\nvalue = task_name()\n",
        textCursor=lambda: SimpleNamespace(position=lambda: 36),
        word_under_cursor=lambda: "task_name",
    )
    window_any._active_editor_widget = lambda: editor_widget
    window_any._intelligence_runtime_settings = SimpleNamespace(metrics_logging_enabled=False)
    window_any._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)
    window_any._background_tasks = _FakeBackgroundTasks()
    window_any._problems_panel = SimpleNamespace(set_results=lambda *_a, **_kw: None)
    window_any._update_problems_tab_title = lambda *_a, **_kw: None
    window_any._focus_problems_tab = lambda: None
    window_any._handle_save_all_action = lambda: True
    window_any._refresh_open_tabs_from_disk = lambda *_a, **_kw: None
    window_any._reload_current_project = lambda: None
    return window


def test_handle_find_references_action_dispatches_background_task(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_for_reference_actions()
    window_any = cast(Any, window)

    calls: list[dict[str, object]] = []
    expected_result = SimpleNamespace(symbol_name="task_name", hits=[object(), object()])

    def _fake_find_references(**kwargs: object) -> object:
        calls.append(kwargs)
        return expected_result

    monkeypatch.setattr("app.shell.main_window.find_references", _fake_find_references)

    MainWindow._handle_find_references_action(window)

    assert len(window_any._background_tasks.calls) == 1
    background_call = window_any._background_tasks.calls[0]
    assert background_call["key"] == "find_references"

    task = background_call["task"]
    result = task(threading.Event())

    assert result is expected_result
    assert calls == [
        {
            "project_root": "/tmp/project",
            "current_file_path": "/tmp/project/main.py",
            "source_text": "from helper import task_name\nvalue = task_name()\n",
            "cursor_position": 36,
        }
    ]


def test_handle_find_references_action_on_success_updates_results() -> None:
    window = _build_window_for_reference_actions()
    window_any = cast(Any, window)
    seen: list[tuple[str, list[object]]] = []
    updated_counts: list[int] = []
    focused: list[bool] = []

    window_any._problems_panel = SimpleNamespace(
        set_results=lambda title, items: seen.append((title, items)),
        problem_count=lambda: 1,
    )
    window_any._update_problems_tab_title = lambda count: updated_counts.append(count)
    window_any._focus_problems_tab = lambda: focused.append(True)

    MainWindow._handle_find_references_action(window)
    background_call = window_any._background_tasks.calls[0]

    hit = SimpleNamespace(
        is_definition=False,
        line_text="value = task_name()",
        file_path="/tmp/project/main.py",
        line_number=2,
    )
    result = SimpleNamespace(symbol_name="task_name", hits=[hit])

    background_call["on_success"](result)

    assert len(seen) == 1
    assert seen[0][0] == "References: task_name"
    assert len(seen[0][1]) == 1
    assert updated_counts == [1]
    assert focused == [True]


def test_handle_rename_symbol_action_dispatches_background_task(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_for_reference_actions()
    window_any = cast(Any, window)

    calls: list[dict[str, object]] = []
    expected_plan = SimpleNamespace(old_symbol="task_name", new_symbol="renamed_task", hits=[object()])

    monkeypatch.setattr(
        "app.shell.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("renamed_task", True),
    )

    def _fake_plan_rename_symbol(**kwargs: object) -> object:
        calls.append(kwargs)
        return expected_plan

    monkeypatch.setattr("app.shell.main_window.plan_rename_symbol", _fake_plan_rename_symbol)

    MainWindow._handle_rename_symbol_action(window)

    assert len(window_any._background_tasks.calls) == 1
    background_call = window_any._background_tasks.calls[0]
    assert background_call["key"] == "rename_symbol"

    task = background_call["task"]
    result = task(threading.Event())

    assert result is expected_plan
    assert calls == [
        {
            "project_root": "/tmp/project",
            "current_file_path": "/tmp/project/main.py",
            "source_text": "from helper import task_name\nvalue = task_name()\n",
            "cursor_position": 36,
            "new_symbol": "renamed_task",
        }
    ]


def test_handle_rename_symbol_action_on_success_applies_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_for_reference_actions()
    window_any = cast(Any, window)
    refreshed: list[list[str]] = []
    reloaded: list[bool] = []
    infos: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.shell.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("renamed_task", True),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: 16384,  # QMessageBox.Yes
    )
    monkeypatch.setattr(
        "app.shell.main_window.apply_rename_plan",
        lambda plan: SimpleNamespace(changed_files=["/tmp/project/main.py"], changed_occurrences=len(plan.hits)),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    window_any._refresh_open_tabs_from_disk = lambda paths: refreshed.append(list(paths))
    window_any._reload_current_project = lambda: reloaded.append(True)

    MainWindow._handle_rename_symbol_action(window)
    background_call = window_any._background_tasks.calls[0]

    hit = SimpleNamespace(file_path="/tmp/project/main.py", line_number=2, column_number=8)
    plan = SimpleNamespace(
        old_symbol="task_name",
        new_symbol="renamed_task",
        hits=[hit],
        touched_files=["/tmp/project/main.py"],
    )

    background_call["on_success"](plan)

    assert refreshed == [["/tmp/project/main.py"]]
    assert reloaded == [True]
    assert infos[-1][0] == "Rename Symbol"
