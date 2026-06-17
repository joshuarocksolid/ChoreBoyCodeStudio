"""Typed shell host stubs for unit tests (no ``MainWindow.__new__``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

from app.core import constants
from app.intelligence.diagnostics_service import CodeDiagnostic
from app.shell.debug_control_workflow import DebugControlWorkflow
from app.shell.debug_shell_host import DebugShellHost
from app.shell.lint_workflow import LintWorkflow, LintWorkflowHost
from app.shell.run_debug_presenter import RunDebugPresenter
from app.shell.run_launch_workflow import RunLaunchWorkflow


@dataclass
class StubDebugShellHost:
    """Minimal :class:`DebugShellHost` stub for workflow unit tests."""

    _loaded_project: Any | None = None
    opened_files: list[tuple[str, int, bool]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._editor_tab_workflow = SimpleNamespace(
            open_file_at_line=lambda file_path, line_number, preview=False: self.opened_files.append(
                (file_path, line_number, preview)
            ),
        )
        self._debug_inspector_workflow = SimpleNamespace(
            append_debug_output_line=lambda _text: None,
        )
        self._repl_event_workflow = SimpleNamespace(
            append_python_console_line=lambda _text, _stream="stdout": None,
        )
        self._run_event_workflow = SimpleNamespace(
            refresh_run_action_states=lambda: None,
        )
        self._run_service = SimpleNamespace(
            supervisor=SimpleNamespace(is_running=lambda: False),
        )
        self._debug_session = SimpleNamespace()
        self._run_session_controller = SimpleNamespace()
        self._debug_panel = None
        self._editor_widgets_by_path: dict[str, Any] = {}
        self._debug_exception_policy = SimpleNamespace()


def debug_control_workflow(host: StubDebugShellHost | None = None) -> DebugControlWorkflow:
    stub = host or StubDebugShellHost()
    return DebugControlWorkflow(cast(DebugShellHost, stub))


class _FakeBackgroundTasks:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class LintHostStub:
    """Minimal :class:`LintWorkflowHost` for lint probe policy tests."""

    def __init__(self) -> None:
        self._diagnostics_enabled = True
        self._diagnostics_realtime = True
        self._loaded_project = None
        self._editor_widgets_by_path: dict[str, Any] = {}
        self._known_runtime_modules = None
        self._selected_linter = constants.LINTER_PROVIDER_DEFAULT
        self._lint_rule_overrides: dict[str, dict[str, object]] = {}
        self._stored_lint_diagnostics: dict[str, list[CodeDiagnostic]] = {}
        self._intelligence_runtime_settings = SimpleNamespace(metrics_logging_enabled=False)
        self._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)
        self._editor_manager = SimpleNamespace(active_tab=lambda: None)
        self._background_tasks = _FakeBackgroundTasks()
        self._workflow_broker = object()
        self._workspace_controller = SimpleNamespace(
            open_editor_paths=lambda: list(self._editor_widgets_by_path.keys())
        )
        self._problems_controller = SimpleNamespace(
            apply_lint_diagnostics_result=lambda *_args, **_kwargs: None,
            render_merged_problems_panel=lambda: None,
            update_status_bar_diagnostics=lambda *_args, **_kwargs: None,
        )
        self._editor_tab_workflow = SimpleNamespace(buffer_revision=lambda _path: 1)

    def dialog_parent(self) -> object:
        return object()

    def diagnostics_enabled(self) -> bool:
        return self._diagnostics_enabled

    def diagnostics_realtime(self) -> bool:
        return self._diagnostics_realtime

    def loaded_project(self) -> object | None:
        return self._loaded_project

    def editor_widgets_by_path(self) -> dict[str, Any]:
        return self._editor_widgets_by_path

    def editor_buffer_revision(self, file_path: str) -> int | None:
        return self._editor_tab_workflow.buffer_revision(file_path)

    def known_runtime_modules(self) -> frozenset[str] | None:
        return self._known_runtime_modules

    def selected_linter(self) -> str:
        return self._selected_linter

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._lint_rule_overrides

    def workflow_broker(self) -> object:
        return self._workflow_broker

    def background_tasks(self) -> _FakeBackgroundTasks:
        return self._background_tasks

    def project_inventory_snapshot(self) -> None:
        return None

    def intelligence_metrics_logging_enabled(self) -> bool:
        return self._intelligence_runtime_settings.metrics_logging_enabled

    def logger(self) -> object:
        return self._logger

    def open_editor_paths(self) -> list[str]:
        return self._workspace_controller.open_editor_paths()

    def editor_manager(self) -> object:
        return self._editor_manager

    def apply_lint_diagnostics_result(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        self._problems_controller.apply_lint_diagnostics_result(file_path, diagnostics)

    def render_merged_problems_panel(self) -> None:
        self._problems_controller.render_merged_problems_panel()

    def update_status_bar_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        self._problems_controller.update_status_bar_diagnostics(diagnostics)

    def stored_lint_diagnostics(self) -> dict[str, list[CodeDiagnostic]]:
        return self._stored_lint_diagnostics

    def problems_panel(self) -> None:
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


def lint_workflow_stub() -> tuple[LintWorkflow, LintHostStub]:
    host = LintHostStub()
    return LintWorkflow(cast(LintWorkflowHost, host)), host


@dataclass
class RunLaunchHostStub:
    """Minimal host for :class:`RunLaunchWorkflow` rerun/debug routing tests."""

    _loaded_project: object | None = None
    _debug_panel: Any | None = None
    _run_session_controller: Any | None = None
    _save_workflow: Any = field(default_factory=lambda: SimpleNamespace(handle_save_all_action=lambda: True))
    _is_shutting_down: bool = False
    open_calls: list[tuple[str, object]] = field(default_factory=list)
    tab_calls: list[tuple[str, int]] = field(default_factory=list)
    debug_calls: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._python_console_workflow = SimpleNamespace(prepare_for_session_start=lambda: None)
        self._run_event_workflow = SimpleNamespace(
            append_console_line=lambda _text, _stream="stdout": None,
            bind_append_console_line=lambda: (lambda _text, _stream="stdout": None),
            set_run_status=lambda _status, return_code=None: None,
            refresh_run_action_states=lambda: None,
        )
        self._repl_event_workflow = SimpleNamespace(
            append_python_console_line=lambda _text, _stream="stdout": None,
        )
        self._auto_open_console_on_run_output = False
        self._event_bus = SimpleNamespace(publish=lambda _event: None)
        self._editor_tab_factory = SimpleNamespace(
            open_file_in_editor=lambda file_path, preview=False: self.open_calls.append(("open", file_path)) or True
        )
        self._editor_tabs_widget = SimpleNamespace(
            setCurrentIndex=lambda index: self.tab_calls.append(("tab", index))
        )
        self._editor_tab_workflow = SimpleNamespace(tab_index_for_path=lambda _file_path: 2)
        self._test_runner_workflow = SimpleNamespace(
            debug_current_file_tests=lambda: self.debug_calls.append("current_test")
        )
        self._run_debug_presenter = RunDebugPresenter(self._presenter_host())

    def _presenter_host(self) -> Any:
        host = self

        class _PresenterHost:
            def dialog_parent(_self) -> object:
                return None

            def loaded_project(_self) -> object:
                return host._loaded_project or object()

            def run_session_controller(_self) -> Any:
                return host._run_session_controller

            def save_workflow(_self) -> Any:
                return host._save_workflow

            def prepare_for_session_start(_self) -> None:
                host._python_console_workflow.prepare_for_session_start()

            def run_event_workflow(_self) -> Any:
                return host._run_event_workflow

            def repl_event_workflow(_self) -> Any:
                return host._repl_event_workflow

            def event_bus(_self) -> Any:
                return host._event_bus

            def debug_panel(_self) -> Any:
                return host._debug_panel

            def auto_open_console_on_run_output(_self) -> bool:
                return host._auto_open_console_on_run_output

            def bottom_tabs_widget(_self) -> None:
                return None

            def run_log_panel(_self) -> None:
                return None

            def run_service(_self) -> Any:
                return SimpleNamespace(supervisor=SimpleNamespace(is_running=lambda: False))

            def run_launch_workflow(_self) -> Any:
                return SimpleNamespace(
                    handle_run_action=lambda: None,
                    handle_rerun_last_debug_target_action=lambda: None,
                )

            def is_shutting_down(_self) -> bool:
                return host._is_shutting_down

        return _PresenterHost()

    def dialog_parent(self) -> object:
        return None

    def loaded_project(self) -> object | None:
        return self._loaded_project

    def set_loaded_project(self, project: object) -> None:
        self._loaded_project = project

    def active_named_run_config_name(self) -> None:
        return None

    def set_active_named_run_config_name(self, name: str | None) -> None:
        return None

    def editor_manager(self) -> object:
        return SimpleNamespace()

    def debug_control_workflow(self) -> DebugControlWorkflow:
        return debug_control_workflow()

    def debug_exception_policy(self) -> object:
        return SimpleNamespace()

    def run_config_controller(self) -> object:
        return SimpleNamespace(load_configs=lambda _p: [])

    def run_debug_presenter(self) -> RunDebugPresenter:
        return self._run_debug_presenter

    def settings_service(self) -> object:
        return SimpleNamespace(load_recent_argv_history=lambda: [])

    def resolve_theme_tokens(self) -> object:
        return SimpleNamespace()

    def show_run_preflight_result(self, title: str, summary: str, issues: list[object]) -> None:
        return None

    def refresh_run_action_states(self) -> None:
        return None

    def editor_tab_factory(self) -> object:
        return self._editor_tab_factory

    def editor_tabs_widget(self) -> object:
        return self._editor_tabs_widget

    def tab_index_for_path(self, file_path: str) -> int:
        return self._editor_tab_workflow.tab_index_for_path(file_path)

    def test_runner_workflow(self) -> object:
        return self._test_runner_workflow

    def active_transient_entry_file_path(self) -> None:
        return None

    def set_active_transient_entry_file_path(self, path: str | None) -> None:
        return None

    def status_bar(self) -> object:
        return SimpleNamespace()

    def show_warning(self, title: str, message: str) -> None:
        return None

    def show_information(self, title: str, message: str) -> None:
        return None

    def logger(self) -> object:
        return SimpleNamespace()


def run_launch_workflow_stub(**kwargs: object) -> tuple[RunLaunchWorkflow, RunLaunchHostStub]:
    host = RunLaunchHostStub(**kwargs)  # type: ignore[arg-type]
    return RunLaunchWorkflow(host), host
