"""Unit tests for semantic reference and rename actions in the shell."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.semantic_navigation_workflow import SemanticNavigationWorkflow

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


class _ReferenceRenameHost:
    def __init__(self) -> None:
        self._loaded_project = SimpleNamespace(project_root="/tmp/project")
        self._editor_manager = SimpleNamespace(
            active_tab=lambda: SimpleNamespace(file_path="/tmp/project/main.py")
        )
        self._editor_widget = SimpleNamespace(
            toPlainText=lambda: "from helper import task_name\nvalue = task_name()\n",
            textCursor=lambda: SimpleNamespace(position=lambda: 36),
            word_under_cursor=lambda: "task_name",
        )
        self._intelligence_controller = _FakeIntelligenceController()
        self._problems_panel = SimpleNamespace(set_results=lambda *_a, **_kw: None)
        self._metrics = False

    def dialog_parent(self) -> object:
        return object()

    def loaded_project(self) -> object | None:
        return self._loaded_project

    def editor_manager(self) -> Any:
        return self._editor_manager

    def active_editor_widget(self) -> Any:
        return self._editor_widget

    def editor_widget_for_path(self, file_path: str) -> Any:
        return None

    def editor_widgets_by_path(self) -> dict[str, Any]:
        return {}

    def intelligence_controller(self) -> _FakeIntelligenceController:
        return self._intelligence_controller

    def editor_buffer_revision(self, file_path: str) -> int | None:
        return None

    def open_file_at_line(self, file_path: str, line_number: int) -> None:
        return None

    def outline_symbols_for_path(self, file_path: str) -> list[object] | None:
        return None

    def set_outline_symbols_for_path(self, file_path: str, symbols: list[object]) -> None:
        return None

    def background_tasks(self) -> Any:
        return None

    def problems_panel(self) -> Any | None:
        return self._problems_panel

    def update_problems_tab_title(self, problem_count: int) -> None:
        self._update_problems_tab_title(problem_count)

    def focus_problems_tab(self) -> None:
        self._focus_problems_tab()

    def set_latest_import_issue_report(self, report: object) -> None:
        return None

    def refresh_latest_runtime_issue_report(self) -> None:
        return None

    def open_runtime_center_dialog(self, *, title: str, report: object) -> None:
        return None

    def known_runtime_modules(self) -> set[str]:
        return set()

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return {}

    def completion_min_chars(self) -> int:
        return 2

    def intelligence_metrics_logging_enabled(self) -> bool:
        return self._metrics

    def reported_completion_degradation_reasons(self) -> set[str]:
        return set()

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        return None

    def log_warning(self, message: str, *args: object) -> None:
        return None

    def log_info(self, message: str, *args: object) -> None:
        return None

    def runtime_introspection_coordinator(self) -> None:
        return None

    def save_all_files(self) -> bool:
        return True

    def record_local_history_transaction(
        self,
        payloads_by_path: dict[str, str],
        *,
        source: str,
        label: str,
    ) -> None:
        return None

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        self._refreshed = list(file_paths)

    def reload_current_project(self) -> None:
        self._reloaded = True


def _build_workflow() -> tuple[SemanticNavigationWorkflow, _ReferenceRenameHost]:
    host = _ReferenceRenameHost()
    host._update_problems_tab_title = lambda count: None
    host._focus_problems_tab = lambda: None
    return SemanticNavigationWorkflow(host), host


def test_handle_find_references_action_dispatches_background_task() -> None:
    workflow, host = _build_workflow()

    workflow.handle_find_references_action()

    assert len(host._intelligence_controller.find_references_calls) == 1
    request_call = host._intelligence_controller.find_references_calls[0]
    assert request_call["project_root"] == "/tmp/project"
    assert request_call["current_file_path"] == "/tmp/project/main.py"
    assert request_call["source_text"] == "from helper import task_name\nvalue = task_name()\n"
    assert request_call["cursor_position"] == 36
    assert callable(request_call["on_success"])
    assert callable(request_call["on_error"])


def test_handle_find_references_action_on_success_updates_results() -> None:
    workflow, host = _build_workflow()
    seen: list[tuple[str, list[object]]] = []
    updated_counts: list[int] = []
    focused: list[bool] = []

    host._problems_panel = SimpleNamespace(
        set_results=lambda title, items: seen.append((title, items)),
        problem_count=lambda: 1,
    )
    host._update_problems_tab_title = lambda count: updated_counts.append(count)
    host._focus_problems_tab = lambda: focused.append(True)

    workflow.handle_find_references_action()
    request_call = host._intelligence_controller.find_references_calls[0]

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
    workflow, host = _build_workflow()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.semantic_navigation_workflow.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    workflow.handle_find_references_action()
    request_call = host._intelligence_controller.find_references_calls[0]
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
    workflow, host = _build_workflow()

    monkeypatch.setattr(
        "app.shell.semantic_navigation_workflow.QInputDialog.getText",
        lambda *_args, **_kwargs: ("renamed_task", True),
    )

    workflow.handle_rename_symbol_action()

    assert len(host._intelligence_controller.rename_plan_calls) == 1
    rename_call = host._intelligence_controller.rename_plan_calls[0]
    assert rename_call["project_root"] == "/tmp/project"
    assert rename_call["current_file_path"] == "/tmp/project/main.py"
    assert rename_call["source_text"] == "from helper import task_name\nvalue = task_name()\n"
    assert rename_call["cursor_position"] == 36
    assert rename_call["new_symbol"] == "renamed_task"
    assert callable(rename_call["on_success"])
    assert callable(rename_call["on_error"])


def test_handle_rename_symbol_action_on_success_applies_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, host = _build_workflow()
    refreshed: list[list[str]] = []
    reloaded: list[bool] = []
    infos: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.shell.semantic_navigation_workflow.QInputDialog.getText",
        lambda *_args, **_kwargs: ("renamed_task", True),
    )
    monkeypatch.setattr(
        "app.shell.semantic_navigation_workflow.QMessageBox.question",
        lambda *_args, **_kwargs: 16384,  # QMessageBox.Yes
    )
    monkeypatch.setattr(
        "app.shell.semantic_navigation_workflow.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    host.refresh_open_tabs_from_disk = lambda paths: refreshed.append(list(paths))  # type: ignore[method-assign]
    host.reload_current_project = lambda: reloaded.append(True)  # type: ignore[method-assign]

    workflow.handle_rename_symbol_action()
    rename_call = host._intelligence_controller.rename_plan_calls[0]

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

    assert len(host._intelligence_controller.apply_rename_calls) == 1
    apply_call = host._intelligence_controller.apply_rename_calls[0]
    assert apply_call["plan"] is plan
    apply_call["on_success"](SimpleNamespace(changed_files=["/tmp/project/main.py"], changed_occurrences=1))
    assert refreshed == [["/tmp/project/main.py"]]
    assert reloaded == [True]
    assert infos[-1][0] == "Rename Symbol"
