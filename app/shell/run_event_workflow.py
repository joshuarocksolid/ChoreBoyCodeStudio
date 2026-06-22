"""Run/debug process event queue processing and output routing."""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any, Callable, Protocol

from app.core import constants
from app.core.models import RuntimeIssueReport
from app.debug.debug_session import DebugSession
from app.run.problem_parser import ProblemEntry, parse_traceback_problems
from app.run.process_supervisor import ProcessEvent
from app.shell.events import RunProcessExitEvent, RunProcessOutputEvent, RunProcessStateEvent
from app.shell.run_launch_workflow import RunLaunchWorkflow
from app.shell.run_log_panel import RunInfo
from app.shell.run_output_coordinator import RunOutputCoordinator
from app.shell.run_session_controller import RunSessionController
from app.support.runtime_explainer import explain_runtime_message

EVENT_QUEUE_BATCH_LIMIT = 200


class RunEventBusPort(Protocol):
    """Minimal event bus surface for run process lifecycle events."""

    def publish(self, event: object) -> None:
        ...


class RunEventWorkflowHost(Protocol):
    """Host ports for :class:`RunEventWorkflow`."""

    @property
    def is_shutting_down(self) -> bool:
        ...

    @property
    def run_event_queue(self) -> queue.Queue[ProcessEvent]:
        ...

    @property
    def run_session_controller(self) -> RunSessionController:
        ...

    @property
    def debug_session(self) -> DebugSession:
        ...

    @property
    def active_run_output_tail(self) -> object:
        ...

    @property
    def event_bus(self) -> RunEventBusPort:
        ...

    @property
    def active_transient_entry_file_path(self) -> str | None:
        ...

    @active_transient_entry_file_path.setter
    def active_transient_entry_file_path(self, path: str | None) -> None:
        ...

    @property
    def run_launch_workflow(self) -> RunLaunchWorkflow:
        ...

    @property
    def console_model(self) -> object:
        ...

    @property
    def run_log_panel(self) -> object | None:
        ...

    @property
    def latest_run_issue_ids(self) -> tuple[str, ...]:
        ...

    @latest_run_issue_ids.setter
    def latest_run_issue_ids(self, issue_ids: tuple[str, ...]) -> None:
        ...

    @property
    def latest_run_issue_report(self) -> RuntimeIssueReport:
        ...

    @latest_run_issue_report.setter
    def latest_run_issue_report(self, report: RuntimeIssueReport) -> None:
        ...

    @property
    def stored_runtime_problems(self) -> list[ProblemEntry]:
        ...

    @stored_runtime_problems.setter
    def stored_runtime_problems(self, problems: list[ProblemEntry]) -> None:
        ...

    @property
    def auto_open_console_on_run_output(self) -> bool:
        ...

    @property
    def auto_open_problems_on_run_failure(self) -> bool:
        ...

    @property
    def menu_registry(self) -> object | None:
        ...

    @property
    def loaded_project(self) -> object | None:
        ...

    @property
    def debug_control_workflow(self) -> object:
        ...

    @property
    def run_service(self) -> object:
        ...

    @property
    def run_debug_presenter(self) -> object:
        ...

    @property
    def test_runner_workflow(self) -> object | None:
        ...

    @property
    def editor_manager(self) -> object:
        ...

    @property
    def status_controller(self) -> object | None:
        ...

    @property
    def debug_panel(self) -> object | None:
        ...

    def has_active_python_file(self) -> bool:
        ...

    def render_merged_problems_panel(self) -> None:
        ...

    def build_runtime_issue_report(self) -> RuntimeIssueReport:
        ...

    def open_runtime_center_dialog(self, *, title: str, report: RuntimeIssueReport) -> None:
        ...

    def focus_run_log_tab(self) -> None:
        ...

    def focus_problems_tab(self) -> None:
        ...

    def append_debug_output_line(self, text: str) -> None:
        ...

    def apply_debug_inspector_event(self) -> None:
        ...

    def log_exception(self, message: str) -> None:
        ...


class RunEventWorkflow:
    """Owns run process event queue draining and shell-side run output routing."""

    def __init__(self, host: RunEventWorkflowHost) -> None:
        self._host = host
        self._run_output_coordinator: RunOutputCoordinator | None = None

    def enqueue_run_event(self, event: ProcessEvent) -> None:
        if self._host.is_shutting_down:
            return
        self._host.run_event_queue.put(event)

    def process_queued_run_events(self) -> None:
        if self._host.is_shutting_down:
            self.drain_run_event_queue()
            return
        processed = 0
        while processed < EVENT_QUEUE_BATCH_LIMIT:
            try:
                event = self._host.run_event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self.apply_run_event(event)
            except Exception:
                self._host.log_exception("Failed to process run event")
            processed += 1

    def apply_run_event(self, event: ProcessEvent) -> None:
        active_session = self._host.run_session_controller.session_store.active_session
        run_id = active_session.run_id if active_session is not None else None
        mode = active_session.mode if active_session is not None else None
        self.get_run_output_coordinator().apply(event)
        if event.event_type == "output":
            self._host.event_bus.publish(
                RunProcessOutputEvent(
                    run_id=run_id,
                    mode=mode,
                    stream=event.stream or "stdout",
                    text=event.text or "",
                )
            )
        elif event.event_type == "state":
            self._host.event_bus.publish(
                RunProcessStateEvent(
                    run_id=run_id,
                    mode=mode,
                    state=event.state,
                    terminated_by_user=event.terminated_by_user,
                )
            )
        elif event.event_type == "exit":
            self._host.event_bus.publish(
                RunProcessExitEvent(
                    run_id=run_id,
                    mode=mode,
                    return_code=event.return_code,
                    terminated_by_user=event.terminated_by_user,
                )
            )
            transient_entry_file = self._host.active_transient_entry_file_path
            if transient_entry_file:
                self._host.run_launch_workflow.delete_transient_entry_file(transient_entry_file)
                self._host.active_transient_entry_file_path = None
            self._host.run_debug_presenter.execute_pending_restart_if_any()

    def drain_run_event_queue(self) -> None:
        while True:
            try:
                self._host.run_event_queue.get_nowait()
            except queue.Empty:
                break

    def get_run_output_coordinator(self) -> RunOutputCoordinator:
        if self._run_output_coordinator is not None:
            return self._run_output_coordinator
        output_tail = self._host.active_run_output_tail
        append_output_tail = output_tail.append  # type: ignore[attr-defined]
        coordinator = RunOutputCoordinator(
            is_shutting_down=lambda: self._host.is_shutting_down,
            get_active_session_mode=lambda: self._host.run_session_controller.active_session_mode,
            clear_active_session=self._host.run_session_controller.clear_active_session,
            get_debug_session=lambda: self._host.debug_session,
            append_output_tail=append_output_tail,
            append_console_line=self.bind_append_console_line(),
            append_debug_output_line=self._host.append_debug_output_line,
            apply_debug_inspector_event=self._host.apply_debug_inspector_event,
            refresh_run_action_states=self.refresh_run_action_states,
            set_run_status=lambda status, return_code=None: self.set_run_status(status, return_code=return_code),
            focus_run_log_tab=self._host.focus_run_log_tab,
            focus_problems_tab=self._host.focus_problems_tab,
            set_debug_command_input_enabled=lambda enabled: (
                self._host.debug_panel.set_command_input_enabled(enabled)  # type: ignore[attr-defined]
                if self._host.debug_panel is not None
                else None
            ),
            finalize_run_log=self.finalize_run_log,
            update_problems_from_output=self.update_problems_from_output,
            auto_open_console_on_run_output_enabled=lambda: bool(self._host.auto_open_console_on_run_output),
            auto_open_problems_on_run_failure_enabled=lambda: bool(self._host.auto_open_problems_on_run_failure),
        )
        self._run_output_coordinator = coordinator
        return coordinator

    def bind_append_console_line(self) -> Callable[[str, str], None]:
        return lambda text, stream: self.append_console_line(text, stream=stream)

    def append_console_line(self, text: str, *, stream: str = "stdout") -> None:
        self._host.console_model.append(stream, text)  # type: ignore[attr-defined]
        run_log_panel = self._host.run_log_panel
        if run_log_panel is not None:
            run_log_panel.append_live_line(text, stream=stream)  # type: ignore[attr-defined]

    def finalize_run_log(self, return_code: int | None = None) -> None:
        panel = self._host.run_log_panel
        if panel is None:
            return
        active_session = self._host.run_session_controller.session_store.active_session
        run_info = RunInfo(
            run_id=active_session.run_id if active_session else "",
            mode=active_session.mode if active_session else "",
            entry_file=active_session.entry_file if active_session else "",
            exit_code=return_code,
        )
        active_log_path = self._host.run_session_controller.session_store.log_path
        log_path_str: str | None = None
        if active_log_path:
            log_path = Path(active_log_path)
            if log_path.exists():
                log_path_str = str(log_path)
        panel.end_run(run_info, log_path=log_path_str)  # type: ignore[attr-defined]

    def update_problems_from_output(self) -> list[ProblemEntry]:
        output_text = self._host.active_run_output_tail.text()  # type: ignore[attr-defined]
        problems = parse_traceback_problems(output_text)
        run_issues = explain_runtime_message(output_text, workflow="run")
        issue_ids = tuple(issue.issue_id for issue in run_issues)
        if issue_ids != self._host.latest_run_issue_ids and run_issues:
            summaries = "; ".join(issue.title for issue in run_issues)
            self.append_console_line(
                f"[system] Runtime explanation available: {summaries}. Open Runtime Center for details.",
                stream="system",
            )
        self._host.latest_run_issue_ids = issue_ids
        self._host.latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=run_issues)
        self._host.build_runtime_issue_report()  # side effect: updates merged runtime report via host
        self.set_problems(problems)
        return problems

    def set_problems(self, problems: list[ProblemEntry]) -> None:
        self._host.stored_runtime_problems = problems
        self._host.render_merged_problems_panel()

    def focus_problems_tab(self) -> None:
        self._host.focus_problems_tab()

    def refresh_run_action_states(self) -> None:
        self._host.run_session_controller.refresh_action_states(
            self._host.menu_registry,
            has_project=self._host.loaded_project is not None,
            has_active_file=self.has_active_python_file(),
            has_breakpoints=self._host.debug_control_workflow.breakpoint_store.has_any_breakpoints(),  # type: ignore[attr-defined]
            debug_execution_state=self._host.debug_session.state.execution_state,
        )
        menu_registry = self._host.menu_registry
        if menu_registry is None:
            return
        debug_current_test_action = menu_registry.action("shell.action.run.debugPytestCurrentFile")  # type: ignore[attr-defined]
        if debug_current_test_action is not None:
            debug_current_test_action.setEnabled(
                self._host.loaded_project is not None
                and self.has_active_python_file()
                and not self._host.run_service.supervisor.is_running()  # type: ignore[attr-defined]
            )
        run_test_at_cursor_action = menu_registry.action("shell.action.run.pytestAtCursor")  # type: ignore[attr-defined]
        if run_test_at_cursor_action is not None:
            run_test_at_cursor_action.setEnabled(
                self._host.loaded_project is not None
                and self.has_active_python_file()
                and not self._host.run_service.supervisor.is_running()  # type: ignore[attr-defined]
            )
        debug_failed_test_action = menu_registry.action("shell.action.run.debugPytestFailed")  # type: ignore[attr-defined]
        if debug_failed_test_action is not None:
            test_runner_workflow = self._host.test_runner_workflow
            debug_failed_test_action.setEnabled(
                self._host.loaded_project is not None
                and test_runner_workflow is not None
                and test_runner_workflow.has_failed_tests()  # type: ignore[attr-defined]
                and not self._host.run_service.supervisor.is_running()  # type: ignore[attr-defined]
            )
        rerun_last_debug_action = menu_registry.action("shell.action.run.rerunLastDebugTarget")  # type: ignore[attr-defined]
        if rerun_last_debug_action is not None:
            rerun_last_debug_action.setEnabled(
                self._host.run_launch_workflow.has_rerun_target()
                and not self._host.run_service.supervisor.is_running()  # type: ignore[attr-defined]
            )
        exception_settings_action = menu_registry.action("shell.action.run.debugExceptionStops")  # type: ignore[attr-defined]
        if exception_settings_action is not None:
            exception_settings_action.setEnabled(
                self._host.loaded_project is not None
                and not self._host.run_service.supervisor.is_running()  # type: ignore[attr-defined]
            )

    def has_active_python_file(self) -> bool:
        active_tab = self._host.editor_manager.active_tab()  # type: ignore[attr-defined]
        if active_tab is None:
            return False
        return Path(active_tab.file_path).suffix.lower() == ".py"

    def set_run_status(self, status: str, *, return_code: int | None = None) -> None:
        status_controller = self._host.status_controller
        if status_controller is None:
            return
        status_controller.set_run_status(status, return_code=return_code)  # type: ignore[attr-defined]

    def show_run_preflight_result(self, title: str, summary: str, issues: list[Any]) -> None:
        report = RuntimeIssueReport(workflow="run", issues=list(issues))
        self._host.open_runtime_center_dialog(title=title, report=report)
        self.append_console_line(summary, stream="system")


class MainWindowRunEventHost:
    """Adapts :class:`MainWindow` to :class:`RunEventWorkflowHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def is_shutting_down(self) -> bool:
        return self._window._is_shutting_down

    @property
    def run_event_queue(self) -> queue.Queue[ProcessEvent]:
        return self._window._run_event_queue

    @property
    def run_session_controller(self) -> RunSessionController:
        return self._window._run_session_controller

    @property
    def debug_session(self) -> DebugSession:
        return self._window._debug_session

    @property
    def active_run_output_tail(self) -> object:
        return self._window._active_run_output_tail

    @property
    def event_bus(self) -> RunEventBusPort:
        return self._window._event_bus

    @property
    def active_transient_entry_file_path(self) -> str | None:
        return self._window._active_transient_entry_file_path

    @active_transient_entry_file_path.setter
    def active_transient_entry_file_path(self, path: str | None) -> None:
        self._window._active_transient_entry_file_path = path

    @property
    def run_launch_workflow(self) -> RunLaunchWorkflow:
        return self._window._run_launch_workflow

    @property
    def console_model(self) -> object:
        return self._window._console_model

    @property
    def run_log_panel(self) -> object | None:
        return self._window._run_log_panel

    @property
    def latest_run_issue_ids(self) -> tuple[str, ...]:
        return self._window._latest_run_issue_ids

    @latest_run_issue_ids.setter
    def latest_run_issue_ids(self, issue_ids: tuple[str, ...]) -> None:
        self._window._latest_run_issue_ids = issue_ids

    @property
    def latest_run_issue_report(self) -> RuntimeIssueReport:
        return self._window._latest_run_issue_report

    @latest_run_issue_report.setter
    def latest_run_issue_report(self, report: RuntimeIssueReport) -> None:
        self._window._latest_run_issue_report = report

    @property
    def stored_runtime_problems(self) -> list[ProblemEntry]:
        return self._window._stored_runtime_problems

    @stored_runtime_problems.setter
    def stored_runtime_problems(self, problems: list[ProblemEntry]) -> None:
        self._window._stored_runtime_problems = problems

    @property
    def auto_open_console_on_run_output(self) -> bool:
        return bool(getattr(self._window, "_auto_open_console_on_run_output", False))

    @property
    def auto_open_problems_on_run_failure(self) -> bool:
        return bool(getattr(self._window, "_auto_open_problems_on_run_failure", False))

    @property
    def menu_registry(self) -> object | None:
        return self._window._menu_registry

    @property
    def loaded_project(self) -> object | None:
        return self._window._loaded_project

    @property
    def debug_control_workflow(self) -> object:
        return self._window._debug_control_workflow

    @property
    def run_service(self) -> object:
        return self._window._run_service

    @property
    def run_debug_presenter(self) -> object:
        return self._window._run_debug_presenter

    @property
    def test_runner_workflow(self) -> object | None:
        return getattr(self._window, "_test_runner_workflow", None)

    @property
    def editor_manager(self) -> object:
        return self._window._editor_manager

    @property
    def status_controller(self) -> object | None:
        return getattr(self._window, "_status_controller", None)

    @property
    def debug_panel(self) -> object | None:
        return self._window._debug_panel

    def has_active_python_file(self) -> bool:
        active_tab = self._window._editor_manager.active_tab()
        if active_tab is None:
            return False
        return Path(active_tab.file_path).suffix.lower() == ".py"

    def render_merged_problems_panel(self) -> None:
        self._window._problems_controller.render_merged_problems_panel()

    def build_runtime_issue_report(self) -> RuntimeIssueReport:
        report = self._window._runtime_onboarding_workflow.build_runtime_issue_report()
        self._window._latest_runtime_issue_report = report
        return report

    def open_runtime_center_dialog(self, *, title: str, report: RuntimeIssueReport) -> None:
        self._window._runtime_onboarding_workflow.open_runtime_center_dialog(title=title, report=report)

    def focus_run_log_tab(self) -> None:
        bottom_tabs = self._window._bottom_tabs_widget
        run_log = self._window._run_log_panel
        if bottom_tabs is None or run_log is None:
            return
        index = bottom_tabs.indexOf(run_log)
        if index >= 0:
            bottom_tabs.setCurrentIndex(index)

    def focus_problems_tab(self) -> None:
        bottom_tabs = self._window._bottom_tabs_widget
        problems = self._window._problems_panel
        if bottom_tabs is None or problems is None:
            return
        index = bottom_tabs.indexOf(problems)
        if index >= 0:
            bottom_tabs.setCurrentIndex(index)

    def append_debug_output_line(self, text: str) -> None:
        self._window._debug_inspector_workflow.append_debug_output_line(text)

    def apply_debug_inspector_event(self) -> None:
        self._window._debug_inspector_workflow.apply_debug_inspector_event()

    def log_exception(self, message: str) -> None:
        self._window._logger.exception(message)
