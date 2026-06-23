"""Composition helpers for shell workflow wiring."""

from __future__ import annotations

from typing import Any, Callable

from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QMessageBox, QWidget

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.test_runtime_flags import background_runtime_disabled
from app.core.models import RuntimeIssue, RuntimeIssueReport
from app.plugins.contributions import DeclarativeContributionManager
from app.plugins.events import (
    PLUGIN_EVENT_HOOK_PROJECT_OPEN_FAILED,
    PLUGIN_EVENT_HOOK_PROJECT_OPENED,
    PLUGIN_EVENT_HOOK_RUN_EXIT,
    PLUGIN_EVENT_HOOK_RUN_OUTPUT,
    PLUGIN_EVENT_HOOK_RUN_START,
)
from app.plugins.workflow_adapters import run_pytest_with_workflow
from app.shell.events import (
    ProjectOpenFailedEvent,
    ProjectOpenedEvent,
    RunProcessExitEvent,
    RunProcessOutputEvent,
    RunSessionStartedEvent,
)
from app.shell.diagnostics_search_coordinator import DiagnosticsOrchestrator
from app.shell.editor_sync_factory import build_editor_sync_workflow
from app.shell.external_file_change_workflow import (
    ExternalFileChangeWorkflow,
    MainWindowExternalFileChangeHost,
)
from app.shell.file_project_commands_workflow import (
    FileProjectCommandsWorkflow,
    MainWindowFileProjectCommandsHost,
)
from app.shell.plugin_activation_workflow import PluginActivationWorkflow
from app.shell.project_tree_action_workflow import ProjectTreeActionWorkflow
from app.shell.python_console_workflow import (
    MainWindowPythonConsoleHost,
    PythonConsoleWorkflow,
)
from app.shell.run_launch.run_launch_workflow_host import MainWindowRunLaunchHost
from app.shell.run_launch_workflow import RunLaunchWorkflow
from app.shell.runtime_support_workflow import RuntimeSupportWorkflow
from app.shell.save_workflow import MainWindowSaveDocumentHost, SaveWorkflow
from app.shell.settings_apply_workflow import (
    MainWindowSettingsApplyHost,
    SettingsApplyWorkflow,
)
from app.shell.shell_composition_context import (
    ShellCompositionContext,
    ShellCompositionTimers,
    ShellDiagnosticsLatchState,
    ShellRuntimeIssueState,
)
from app.shell.shell_theme_host import MainWindowShellThemeHost
from app.shell.shell_theme_workflow import ShellThemeWorkflow
from app.shell.test_runner_workflow import ActiveTestEditor, TestRunnerWorkflow


def build_save_workflow(ctx: ShellCompositionContext) -> SaveWorkflow:
    window = ctx.w
    return SaveWorkflow(
        local_history=window._local_history_workflow,
        intelligence_cache=window._intelligence_cache_workflow,
        host=MainWindowSaveDocumentHost(window),
        settings_service=window._settings_service,
    )


def build_external_file_change_workflow(ctx: ShellCompositionContext) -> ExternalFileChangeWorkflow:
    window = ctx.w
    editor_sync = build_editor_sync_workflow(window)
    return ExternalFileChangeWorkflow(
        editor_manager=window._editor_manager,
        editor_sync=editor_sync,
        save_workflow=window._save_workflow,
        local_history=window._local_history_workflow,
        host=MainWindowExternalFileChangeHost(window),
    )


def build_project_tree_action_workflow(ctx: ShellCompositionContext) -> ProjectTreeActionWorkflow:
    window = ctx.w
    return ProjectTreeActionWorkflow(
        save_workflow=window._save_workflow,
        local_history_workflow=window._local_history_workflow,
        project_tree_action_coordinator=window._project_tree_action_coordinator,
        dialog_parent=window,
    )


def build_settings_apply_workflow(ctx: ShellCompositionContext) -> SettingsApplyWorkflow:
    window = ctx.w
    return SettingsApplyWorkflow(
        settings_service=window._settings_service,
        host=MainWindowSettingsApplyHost(window),
    )


def build_python_console_workflow(ctx: ShellCompositionContext) -> PythonConsoleWorkflow:
    window = ctx.w
    logger = get_subsystem_logger("shell")

    def _start_background_work(work: Callable[[], None]) -> None:
        def task(_cancellation: object) -> None:
            work()

        def on_error(exc: Exception) -> None:
            logger.warning("Python console background work failed: %s", exc)

        window._background_tasks.run(
            key="python_console_completion",
            task=task,
            on_error=on_error,
        )

    return PythonConsoleWorkflow(
        repl_manager=window._repl_manager,
        host=MainWindowPythonConsoleHost(window),
        start_background_work=_start_background_work,
    )


def build_find_replace_workflow(ctx: ShellCompositionContext) -> Any:
    from app.shell.find_replace_workflow import FindReplaceWorkflow, MainWindowFindReplaceHost

    return FindReplaceWorkflow(MainWindowFindReplaceHost(ctx.w))


def build_semantic_navigation_workflow(ctx: ShellCompositionContext) -> Any:
    from app.shell.semantic_navigation_workflow import (
        MainWindowSemanticNavigationHost,
        SemanticNavigationWorkflow,
    )

    return SemanticNavigationWorkflow(MainWindowSemanticNavigationHost(ctx.w))


def build_run_launch_workflow(ctx: ShellCompositionContext) -> RunLaunchWorkflow:
    return RunLaunchWorkflow(MainWindowRunLaunchHost(ctx.w))


def build_shell_theme_workflow(ctx: ShellCompositionContext) -> ShellThemeWorkflow:
    return ShellThemeWorkflow(MainWindowShellThemeHost(ctx.w))


def build_file_project_commands_workflow(ctx: ShellCompositionContext) -> FileProjectCommandsWorkflow:
    return FileProjectCommandsWorkflow(MainWindowFileProjectCommandsHost(ctx.w))


def build_realtime_lint_runner(
    *,
    is_shutting_down: Callable[[], bool],
    orchestrator: Any,
) -> Callable[[], None]:
    def run_scheduled_realtime_lint() -> None:
        if is_shutting_down():
            return
        orchestrator.run_scheduled_realtime_lint()

    return run_scheduled_realtime_lint


def focus_bottom_tab(ctx: ShellCompositionContext, widget: QWidget | None) -> None:
    window = ctx.w
    bottom_tabs = getattr(window, "_bottom_tabs_widget", None)
    if bottom_tabs is None or widget is None:
        return
    index = bottom_tabs.indexOf(widget)
    if index < 0:
        return
    bottom_tabs.setCurrentIndex(index)


def build_declarative_contribution_manager(ctx: ShellCompositionContext) -> DeclarativeContributionManager:
    window = ctx.w
    plugin_event_type_map: dict[str, type[object]] = {
        PLUGIN_EVENT_HOOK_RUN_START: RunSessionStartedEvent,
        PLUGIN_EVENT_HOOK_RUN_OUTPUT: RunProcessOutputEvent,
        PLUGIN_EVENT_HOOK_RUN_EXIT: RunProcessExitEvent,
        PLUGIN_EVENT_HOOK_PROJECT_OPENED: ProjectOpenedEvent,
        PLUGIN_EVENT_HOOK_PROJECT_OPEN_FAILED: ProjectOpenFailedEvent,
    }
    return DeclarativeContributionManager(
        register_runtime_command=lambda command_id, handler, replace: window.register_runtime_command(
            command_id=command_id,
            handler=handler,
            replace=replace,
        ),
        register_runtime_menu_command=lambda **kwargs: window.register_runtime_menu_command(**kwargs),
        unregister_runtime_menu_command=window.unregister_runtime_menu_command,
        execute_runtime_command=window.execute_runtime_command,
        subscribe_shell_event=lambda event_type, handler: window.subscribe_shell_event(event_type, handler),
        unsubscribe_shell_event=lambda event_type, handler: window.unsubscribe_shell_event(event_type, handler),
        resolve_event_type=lambda event_name: plugin_event_type_map.get(event_name),
        emit_message=lambda message: QMessageBox.information(window, "Plugin Command", message),
        execute_plugin_runtime_command=lambda command_id, payload, activation_event: window._plugin_api_broker.invoke_runtime_command_for_event(
            command_id,
            payload,
            activation_event=activation_event,
        ),
        on_runtime_command_success=lambda plugin_id, version: window._plugin_dialog_workflow.clear_plugin_runtime_failure(
            plugin_id,
            version,
        ),
        on_runtime_command_failure=lambda plugin_id, version, error_message: window._plugin_dialog_workflow.record_plugin_runtime_failure(
            plugin_id,
            version,
            error_message,
        ),
    )


def build_plugin_activation_workflow(
    ctx: ShellCompositionContext,
    *,
    contribution_manager: DeclarativeContributionManager,
) -> PluginActivationWorkflow:
    window = ctx.w
    return PluginActivationWorkflow(
        state_root=window._state_root,
        project_root_provider=lambda: None
        if window._loaded_project is None
        else window._loaded_project.project_root,
        safe_mode_enabled=lambda: window._plugin_safe_mode,
        contribution_manager=contribution_manager,
        runtime_manager=window._plugin_runtime_manager,
        plugin_api_broker=window._plugin_api_broker,
        workflow_broker=window._workflow_broker,
        on_catalog_changed=lambda catalog: setattr(window, "_workflow_provider_catalog", catalog),
    )


def build_runtime_support_workflow(
    ctx: ShellCompositionContext,
    *,
    runtime_issues: ShellRuntimeIssueState,
) -> RuntimeSupportWorkflow:
    window = ctx.w
    return RuntimeSupportWorkflow(
        parent=window,
        state_root=window._state_root,
        background_tasks=window._background_tasks,
        workflow_broker=window._workflow_broker,
        loaded_project=lambda: window._loaded_project,
        startup_report=lambda: window._startup_report,
        latest_health_report=lambda: runtime_issues.latest_health_report,
        set_latest_health_report=lambda report: runtime_issues.set_latest_health_report(window, report),
        latest_import_issue_report=lambda: runtime_issues.latest_import_issue_report or RuntimeIssueReport(
            workflow="import",
            issues=[],
        ),
        latest_run_issue_report=lambda: runtime_issues.latest_run_issue_report or RuntimeIssueReport(
            workflow="run",
            issues=[],
        ),
        latest_package_issue_report=lambda: runtime_issues.latest_package_issue_report or RuntimeIssueReport(
            workflow="package",
            issues=[],
        ),
        set_latest_package_issue_report=lambda report: runtime_issues.set_latest_package_issue_report(
            window,
            report,
        ),
        set_latest_runtime_issue_report=lambda report: runtime_issues.set_latest_runtime_issue_report(
            window,
            report,
        ),
        set_latest_import_issue_report=lambda report: runtime_issues.set_latest_import_issue_report(
            window,
            report,
        ),
        set_latest_run_issue_report=lambda report: runtime_issues.set_latest_run_issue_report(window, report),
        clear_active_run_config=lambda: runtime_issues.clear_active_run_config(window),
        build_runtime_issue_report=window._runtime_onboarding_workflow.build_runtime_issue_report,
        open_runtime_center_dialog=window._runtime_onboarding_workflow.open_runtime_center_dialog,
        active_run_session_log_path=lambda: window._run_session_controller.session_store.log_path,
        known_runtime_modules=lambda: window._known_runtime_modules,
        resolve_theme_tokens=lambda: window._shell_theme_workflow.resolve_theme_tokens(),
    )


def build_diagnostics_orchestrator(
    ctx: ShellCompositionContext,
    *,
    diagnostics_latches: ShellDiagnosticsLatchState,
) -> DiagnosticsOrchestrator:
    window = ctx.w
    return DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: window._diagnostics_enabled,
        diagnostics_realtime=lambda: window._diagnostics_realtime,
        set_pending_realtime_file_path=lambda file_path: diagnostics_latches.set_pending_realtime_lint_file_path(
            window,
            file_path,
        ),
        get_pending_realtime_file_path=lambda: diagnostics_latches.pending_realtime_lint_file_path,
        start_realtime_timer=window._realtime_lint_timer.start,
        get_active_tab_file_path=window._editor_manager.active_file_path,
        render_lint_for_file=lambda file_path, trigger: window._lint_workflow.render_diagnostics_for_file(
            file_path,
            trigger=trigger,
        ),
        get_open_editor_paths=window._workspace_controller.open_editor_paths,
        render_merged_problems_panel=lambda: window._problems_controller.render_merged_problems_panel(),
        set_known_runtime_modules=lambda modules: diagnostics_latches.set_known_runtime_modules(window, modules),
        run_background_task=window._background_tasks.run,
        state_root=lambda: window._state_root,
        logger=window._logger,
        show_runtime_probe_warning=lambda message: QMessageBox.warning(
            window,
            "Refresh Runtime Modules",
            message,
        ),
    )


def build_test_runner_workflow(ctx: ShellCompositionContext) -> TestRunnerWorkflow:
    window = ctx.w

    def active_test_editor() -> ActiveTestEditor | None:
        active_tab = window._editor_manager.active_tab()
        editor_widget = window._editor_tab_workflow.active_editor_widget()
        if active_tab is None or editor_widget is None:
            return None
        return ActiveTestEditor(
            file_path=active_tab.file_path,
            source_text=active_tab.current_content,
            cursor_line=editor_widget.textCursor().blockNumber() + 1,
        )

    return TestRunnerWorkflow(
        loaded_project_provider=lambda: window._loaded_project,
        active_editor_provider=active_test_editor,
        workflow_broker=window._workflow_broker,
        background_tasks=window._background_tasks,
        test_explorer_panel=window._test_explorer_panel,
        run_pytest_with_workflow=run_pytest_with_workflow,
        start_debug_session=window._run_launch_workflow.start_session,
        build_debug_breakpoints=window._debug_control_workflow.build_debug_breakpoints_for_launch,
        debug_exception_policy_provider=lambda: window._debug_exception_policy,
        append_console_line=window._run_event_workflow.bind_append_console_line(),
        set_problems=window._run_event_workflow.set_problems,
        focus_run_log_tab=lambda: focus_bottom_tab(ctx, window._run_log_panel),
        focus_problems_tab=lambda: focus_bottom_tab(ctx, window._problems_panel),
        show_warning=lambda title, message: QMessageBox.warning(window, title, message),
        show_information=lambda title, message: QMessageBox.information(window, title, message),
        record_debug_target=window._run_launch_workflow.record_debug_target_from_dict,
        auto_open_console_on_output=lambda: window._auto_open_console_on_run_output,
        auto_open_problems_on_failure=lambda: window._auto_open_problems_on_run_failure,
        logger=window._logger,
    )


def create_composition_timers(ctx: ShellCompositionContext) -> ShellCompositionTimers:
    """Create all composition QTimers and attach them to the window."""
    window = ctx.w
    timers = ShellCompositionTimers(
        project_tree_preview_click=QTimer(window),
        auto_save_to_file=QTimer(window),
        realtime_lint=QTimer(window),
        outline_refresh=QTimer(window),
        run_event=QTimer(window),
        repl_event=QTimer(window),
        external_change_poll=QTimer(window),
        restore_project=QTimer(window),
        auto_start_repl=QTimer(window),
        runtime_probe=QTimer(window),
        startup_probe_refresh=QTimer(window),
    )
    timers.project_tree_preview_click.setSingleShot(True)
    timers.project_tree_preview_click.setInterval(175)
    timers.auto_save_to_file.setSingleShot(True)
    timers.auto_save_to_file.setInterval(1000)
    timers.realtime_lint.setSingleShot(True)
    timers.realtime_lint.setInterval(300)
    timers.outline_refresh.setSingleShot(True)
    timers.outline_refresh.setInterval(300)
    timers.run_event.setInterval(50)
    timers.repl_event.setInterval(50)
    timers.external_change_poll.setInterval(1000)
    timers.restore_project.setSingleShot(True)
    timers.auto_start_repl.setSingleShot(True)
    timers.runtime_probe.setSingleShot(True)
    timers.startup_probe_refresh.setSingleShot(True)
    timers.bind_to_window(window)
    ctx.timers = timers
    return timers


def connect_composition_timers(ctx: ShellCompositionContext) -> None:
    """Connect timer timeout handlers once all workflows exist."""
    window = ctx.w
    assert ctx.timers is not None
    timers = ctx.timers
    timers.auto_save_to_file.timeout.connect(window._save_workflow.flush_auto_save_to_file)
    timers.outline_refresh.timeout.connect(window._editor_tab_workflow.refresh_outline_for_active_tab)
    timers.project_tree_preview_click.timeout.connect(
        window._project_tree_ui_workflow.open_pending_project_tree_preview
    )
    timers.realtime_lint.timeout.connect(
        build_realtime_lint_runner(
            is_shutting_down=lambda: window._is_shutting_down,
            orchestrator=window._diagnostics_orchestrator,
        )
    )
    timers.run_event.timeout.connect(window._run_event_workflow.process_queued_run_events)
    timers.repl_event.timeout.connect(window._repl_event_workflow.process_queued_events)
    timers.external_change_poll.timeout.connect(window._editor_tab_workflow.poll_external_file_changes)
    timers.restore_project.timeout.connect(window._file_project_commands_workflow.try_restore_last_project)
    timers.auto_start_repl.timeout.connect(window._repl_manager.start)
    timers.runtime_probe.timeout.connect(lambda: window._diagnostics_orchestrator.start_runtime_module_probe())
    timers.startup_probe_refresh.timeout.connect(
        window._runtime_onboarding_workflow.refresh_startup_capability_report_async
    )


def start_composition_timers(ctx: ShellCompositionContext) -> None:
    """Start deferred and polling timers after composition is complete."""
    window = ctx.w
    assert ctx.timers is not None
    timers = ctx.timers
    timers.run_event.start()
    timers.repl_event.start()
    timers.external_change_poll.start()
    timers.restore_project.start(0)
    if not background_runtime_disabled():
        timers.auto_start_repl.start(100)
    timers.runtime_probe.start(200)
    timers.startup_probe_refresh.start(0)
    window._startup_capability_facade.set_refresh_callback(
        window._runtime_onboarding_workflow.handle_startup_report_refresh
    )
