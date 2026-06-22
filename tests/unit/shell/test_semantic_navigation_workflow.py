"""Unit tests for semantic navigation workflow actions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.semantic_navigation_workflow import SemanticNavigationWorkflow

pytestmark = pytest.mark.unit


class _FakeIntelligenceController:
    def __init__(self) -> None:
        self.lookup_definition_calls: list[dict[str, Any]] = []
        self.signature_help_calls: list[dict[str, Any]] = []
        self.hover_info_calls: list[dict[str, Any]] = []

    def request_lookup_definition(self, **kwargs: Any) -> None:
        self.lookup_definition_calls.append(kwargs)

    def request_signature_help(self, **kwargs: Any) -> None:
        self.signature_help_calls.append(kwargs)

    def request_hover_info(self, **kwargs: Any) -> None:
        self.hover_info_calls.append(kwargs)

    @staticmethod
    def format_inline_signature_text(signature: object | None) -> str | None:
        if signature is None:
            return None
        return getattr(signature, "signature_text", None)

    @staticmethod
    def format_inline_hover_text(hover_info: object | None) -> str | None:
        if hover_info is None:
            return None
        return f"Symbol: {getattr(hover_info, 'symbol_name', 'unknown')}"


class _FakeHost:
    def __init__(self) -> None:
        self._loaded_project = SimpleNamespace(project_root="/tmp/project")
        self._editor_manager = SimpleNamespace(
            active_tab=lambda: SimpleNamespace(file_path="/tmp/project/main.py")
        )
        self._editor_widget = SimpleNamespace(
            toPlainText=lambda: "from helper import helper_task\nvalue = helper_task()\n",
            textCursor=lambda: SimpleNamespace(position=lambda: 40),
            word_under_cursor=lambda: "helper_task",
            show_calltip=lambda _text: None,
            allocate_signature_help_request_generation=lambda: 1,
            allocate_hover_request_generation=lambda: 1,
            signature_help_request_generation=lambda: 1,
            hover_request_generation=lambda: 1,
        )
        self._intelligence_controller = _FakeIntelligenceController()
        self.opened_at_line: list[tuple[str, int]] = []

    def dialog_parent(self) -> object:
        return object()

    def loaded_project(self) -> object | None:
        return self._loaded_project

    def editor_manager(self) -> object:
        return self._editor_manager

    def active_editor_widget(self) -> object:
        return self._editor_widget

    def editor_widget_for_path(self, file_path: str) -> object | None:
        return self._editor_widget

    def editor_widgets_by_path(self) -> dict[str, object]:
        return {"/tmp/project/main.py": self._editor_widget}

    def intelligence_controller(self) -> _FakeIntelligenceController:
        return self._intelligence_controller

    def editor_buffer_revision(self, file_path: str) -> int | None:
        return 1

    def open_file_at_line(self, file_path: str, line_number: int) -> None:
        self.opened_at_line.append((file_path, line_number))

    def outline_symbols_for_path(self, file_path: str) -> list[object] | None:
        return None

    def set_outline_symbols_for_path(self, file_path: str, symbols: list[object]) -> None:
        return None

    def background_tasks(self) -> object:
        return None

    def problems_panel(self) -> object | None:
        return None

    def update_problems_tab_title(self, problem_count: int) -> None:
        return None

    def focus_problems_tab(self) -> None:
        return None

    def set_latest_import_issue_report(self, report: object) -> None:
        return None

    def refresh_latest_runtime_issue_report(self) -> None:
        return None

    def open_runtime_center_dialog(self, *, title: str, report: object) -> None:
        return None

    def known_runtime_modules(self) -> object:
        return frozenset()

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return {}

    def completion_min_chars(self) -> int:
        return 2

    def intelligence_metrics_logging_enabled(self) -> bool:
        return False

    def reported_completion_degradation_reasons(self) -> set[str]:
        return set()

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        return None

    def log_warning(self, message: str, *args: object) -> None:
        return None

    def log_info(self, message: str, *args: object) -> None:
        return None


def _build_workflow() -> tuple[SemanticNavigationWorkflow, _FakeHost]:
    host = _FakeHost()
    return SemanticNavigationWorkflow(host), host


def test_menu_intelligence_controller_has_no_blocking_resolvers() -> None:
    from app.shell.editor_intelligence_controller import EditorIntelligenceController

    assert not hasattr(EditorIntelligenceController, "resolve_hover_info_blocking")
    assert not hasattr(EditorIntelligenceController, "resolve_signature_help_blocking")
    assert not hasattr(EditorIntelligenceController, "build_inline_hover_text")
    assert not hasattr(EditorIntelligenceController, "build_inline_signature_text")


def test_handle_go_to_definition_action_dispatches_semantic_task() -> None:
    workflow, host = _build_workflow()

    workflow.handle_go_to_definition_action()

    assert len(host.intelligence_controller().lookup_definition_calls) == 1
    lookup_call = host.intelligence_controller().lookup_definition_calls[0]
    assert lookup_call["project_root"] == "/tmp/project"
    assert lookup_call["current_file_path"] == "/tmp/project/main.py"
    assert lookup_call["source_text"] == "from helper import helper_task\nvalue = helper_task()\n"
    assert lookup_call["cursor_position"] == 40
    assert callable(lookup_call["on_success"])
    assert callable(lookup_call["on_error"])


def test_handle_go_to_definition_action_uses_target_chooser(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, host = _build_workflow()
    monkeypatch.setattr(
        "app.shell.symbol_navigation_workflow.QInputDialog.getItem",
        lambda *_args, **_kwargs: ("b.py:8 (function)", True),
    )

    workflow.handle_go_to_definition_action()
    lookup_call = host.intelligence_controller().lookup_definition_calls[0]
    lookup_call["on_success"](
        SimpleNamespace(
            found=True,
            symbol_name="helper_task",
            locations=[
                SimpleNamespace(file_path="/tmp/project/a.py", line_number=3, symbol_kind="function"),
                SimpleNamespace(file_path="/tmp/project/b.py", line_number=8, symbol_kind="function"),
            ],
            metadata=SimpleNamespace(unsupported_reason="", source="semantic", confidence="exact"),
        )
    )

    assert host.opened_at_line == [("/tmp/project/b.py", 8)]


def test_handle_go_to_definition_action_surfaces_semantic_runtime_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow, host = _build_workflow()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.symbol_navigation_workflow.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    workflow.handle_go_to_definition_action()
    lookup_call = host.intelligence_controller().lookup_definition_calls[0]
    lookup_call["on_success"](
        SimpleNamespace(
            found=False,
            symbol_name="helper_task",
            locations=[],
            metadata=SimpleNamespace(
                unsupported_reason="runtime_unavailable: RuntimeError: semantic backend unavailable",
                source="semantic_unavailable",
                confidence="unsupported",
            ),
        )
    )

    assert warnings
    assert warnings[-1][0] == "Go To Definition"
    assert "Semantic definitions are currently unavailable." in warnings[-1][1]


def test_signature_help_action_uses_async_request_not_blocking() -> None:
    workflow, host = _build_workflow()

    workflow.handle_signature_help_action()

    assert len(host.intelligence_controller().signature_help_calls) == 1
    call = host.intelligence_controller().signature_help_calls[0]
    assert call["current_file_path"] == "/tmp/project/main.py"
    assert callable(call["on_success"])


def test_hover_info_action_uses_async_request_not_blocking() -> None:
    workflow, host = _build_workflow()

    workflow.handle_hover_info_action()

    assert len(host.intelligence_controller().hover_info_calls) == 1
    call = host.intelligence_controller().hover_info_calls[0]
    assert call["current_file_path"] == "/tmp/project/main.py"
    assert callable(call["on_success"])


def test_signature_help_action_shows_calltip_after_async_success() -> None:
    workflow, host = _build_workflow()
    shown: list[str] = []
    host._editor_widget.show_calltip = lambda text: shown.append(text)

    workflow.handle_signature_help_action()
    call = host.intelligence_controller().signature_help_calls[0]
    call["on_success"](
        (
            1,
            SimpleNamespace(signature_text="helper_task(value)"),
        )
    )

    assert shown == ["helper_task(value)"]


def test_hover_info_action_shows_calltip_after_async_success() -> None:
    workflow, host = _build_workflow()
    shown: list[str] = []
    host._editor_widget.show_calltip = lambda text: shown.append(text)

    workflow.handle_hover_info_action()
    call = host.intelligence_controller().hover_info_calls[0]
    call["on_success"](
        (
            1,
            SimpleNamespace(symbol_name="helper_task"),
        )
    )

    assert shown == ["Symbol: helper_task"]


def test_hover_info_skips_calltip_when_generation_is_stale() -> None:
    workflow, host = _build_workflow()
    shown: list[str] = []
    host._editor_widget.show_calltip = lambda text: shown.append(text)

    workflow.handle_hover_info_action()
    host._editor_widget.hover_request_generation = lambda: 2

    call = host.intelligence_controller().hover_info_calls[0]
    call["on_success"](
        (
            1,
            SimpleNamespace(symbol_name="helper_task"),
        )
    )

    assert shown == []
