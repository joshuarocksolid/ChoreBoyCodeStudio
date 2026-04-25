"""Unit tests for semantic reference and rename actions in MainWindow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


class _FakeIntelligenceController:
    def __init__(self) -> None:
        self.find_references_calls: list[dict[str, Any]] = []
        self.rename_plan_calls: list[dict[str, Any]] = []
        self.apply_rename_calls: list[dict[str, Any]] = []

    def request_find_references(self, **kwargs: Any) -> None:
        self.find_references_calls.append(kwargs)

    def request_rename_plan(self, **kwargs: Any) -> None:
        self.rename_plan_calls.append(kwargs)

    def request_apply_rename(self, **kwargs: Any) -> None:
        self.apply_rename_calls.append(kwargs)


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
    window_any._intelligence_controller = _FakeIntelligenceController()
    window_any._problems_panel = SimpleNamespace(set_results=lambda *_a, **_kw: None)
    window_any._update_problems_tab_title = lambda *_a, **_kw: None
    window_any._focus_problems_tab = lambda: None
    window_any._handle_save_all_action = lambda: True
    window_any._refresh_open_tabs_from_disk = lambda *_a, **_kw: None
    window_any._reload_current_project = lambda: None
    window_any._local_history_workflow = SimpleNamespace(record_transaction=lambda *_a, **_kw: None)
    return window


def test_handle_find_references_action_dispatches_background_task(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_for_reference_actions()
    window_any = cast(Any, window)

    MainWindow._handle_find_references_action(window)

    assert len(window_any._intelligence_controller.find_references_calls) == 1
    request_call = window_any._intelligence_controller.find_references_calls[0]
    assert request_call["project_root"] == "/tmp/project"
    assert request_call["current_file_path"] == "/tmp/project/main.py"
    assert request_call["source_text"] == "from helper import task_name\nvalue = task_name()\n"
    assert request_call["cursor_position"] == 36
    assert callable(request_call["on_success"])
    assert callable(request_call["on_error"])


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
    request_call = window_any._intelligence_controller.find_references_calls[0]

    hit = SimpleNamespace(
        is_definition=False,
        line_text="value = task_name()",
        file_path="/tmp/project/main.py",
        line_number=2,
    )
    result = SimpleNamespace(
        symbol_name="task_name",
        hits=[hit],
        metadata=SimpleNamespace(unsupported_reason="", source="semantic", confidence="exact"),
    )

    request_call["on_success"](result)

    assert len(seen) == 1
    assert seen[0][0] == "References: task_name"
    assert len(seen[0][1]) == 1
    assert updated_counts == [1]
    assert focused == [True]


def test_handle_find_references_action_surfaces_semantic_runtime_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _build_window_for_reference_actions()
    window_any = cast(Any, window)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    MainWindow._handle_find_references_action(window)
    request_call = window_any._intelligence_controller.find_references_calls[0]
    request_call["on_success"](
        SimpleNamespace(
            symbol_name="task_name",
            hits=[],
            metadata=SimpleNamespace(
                unsupported_reason="runtime_unavailable: RuntimeError: semantic backend unavailable",
                source="semantic_unavailable",
                confidence="unsupported",
            ),
        )
    )

    assert warnings
    assert warnings[-1][0] == "Find References"
    assert "Semantic references are currently unavailable." in warnings[-1][1]


def test_handle_rename_symbol_action_dispatches_background_task(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_for_reference_actions()
    window_any = cast(Any, window)

    monkeypatch.setattr(
        "app.shell.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("renamed_task", True),
    )

    MainWindow._handle_rename_symbol_action(window)

    assert len(window_any._intelligence_controller.rename_plan_calls) == 1
    rename_call = window_any._intelligence_controller.rename_plan_calls[0]
    assert rename_call["project_root"] == "/tmp/project"
    assert rename_call["current_file_path"] == "/tmp/project/main.py"
    assert rename_call["source_text"] == "from helper import task_name\nvalue = task_name()\n"
    assert rename_call["cursor_position"] == 36
    assert rename_call["new_symbol"] == "renamed_task"
    assert callable(rename_call["on_success"])
    assert callable(rename_call["on_error"])


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
        "app.shell.main_window.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    window_any._refresh_open_tabs_from_disk = lambda paths: refreshed.append(list(paths))
    window_any._reload_current_project = lambda: reloaded.append(True)

    MainWindow._handle_rename_symbol_action(window)
    rename_call = window_any._intelligence_controller.rename_plan_calls[0]

    hit = SimpleNamespace(file_path="/tmp/project/main.py", line_number=2, column_number=8)
    plan = SimpleNamespace(
        old_symbol="task_name",
        new_symbol="renamed_task",
        hits=[hit],
        preview_patches=[
            SimpleNamespace(
                file_path="/tmp/project/main.py",
                updated_content="from helper import renamed_task\nvalue = renamed_task()\n",
                diff_text="--- a\n+++ a\n@@\n-task_name\n+renamed_task",
            )
        ],
        touched_files=["/tmp/project/main.py"],
        metadata=SimpleNamespace(source="semantic", confidence="exact"),
    )

    rename_call["on_success"](plan)

    assert len(window_any._intelligence_controller.apply_rename_calls) == 1
    apply_call = window_any._intelligence_controller.apply_rename_calls[0]
    assert apply_call["plan"] is plan
    apply_call["on_success"](SimpleNamespace(changed_files=["/tmp/project/main.py"], changed_occurrences=1))
    assert refreshed == [["/tmp/project/main.py"]]
    assert reloaded == [True]
    assert infos[-1][0] == "Rename Symbol"
