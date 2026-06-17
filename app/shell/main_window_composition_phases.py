"""Phased install helpers for main-window shell composition."""

# pyright: reportInvalidTypeForm=false

from __future__ import annotations

import queue
from typing import Any, Optional

from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.test_runtime_flags import background_runtime_disabled
from app.bootstrap.paths import global_cache_dir, global_python_console_history_path
from app.bootstrap.runtime_module_probe import load_cached_runtime_modules
from app.bootstrap.startup_facade import StartupCapabilityFacade
from app.core import constants
from app.core.models import CapabilityProbeReport, LoadedProject, RuntimeIssueReport
from app.debug.debug_models import DebugExceptionPolicy
from app.debug.debug_session import DebugSession
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.examples.example_project_service import ExampleProjectService
from app.intelligence.diagnostics_service import CodeDiagnostic
from app.intelligence.outline_service import OutlineSymbol
from app.persistence.autosave_store import AutosaveStore
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.settings_service import SettingsService
from app.plugins.api_broker import PluginApiBroker
from app.plugins.builtin_workflows import register_builtin_workflow_providers
from app.plugins.contributions import DeclarativeContributionManager
from app.plugins.runtime_manager import PluginRuntimeManager
from app.plugins.workflow_adapters import run_pytest_with_workflow
from app.plugins.workflow_broker import WorkflowBroker
from app.plugins.workflow_catalog import WorkflowProviderCatalog
from app.run.process_supervisor import ProcessEvent
from app.run.problem_parser import ProblemEntry
from app.run.run_service import RunService
from app.shell.action_registry import ShellActionRegistry
from app.shell.command_broker import CommandBroker
from app.shell.console_model import ConsoleModel
from app.shell.debug_control_workflow import DebugControlWorkflow
from app.shell.debug_inspector_workflow import DebugInspectorWorkflow, MainWindowDebugInspectorHost
from app.shell.diagnostics_search_coordinator import DiagnosticsOrchestrator
from app.shell.editor_tab_content_registry import EditorTabContentRegistry
from app.shell.editor_tab_factory import EditorTabFactory
from app.shell.editor_tab_workflow import build_editor_tab_workflow
from app.shell.editor_workspace_controller import EditorWorkspaceController
from app.shell.events import ShellEventBus
from app.shell.file_project_commands_workflow import build_file_project_commands_workflow
from app.shell.help_controller import ShellHelpController
from app.shell.intelligence_cache_workflow import build_intelligence_cache_workflow
from app.shell.intelligence_composition import bootstrap_intelligence_runtime
from app.shell.layout_persistence import (
    DEFAULT_OUTLINE_COLLAPSED,
    DEFAULT_OUTLINE_FOLLOW_CURSOR,
    DEFAULT_OUTLINE_SORT_MODE,
)
from app.shell.lint_workflow import build_lint_workflow
from app.shell.local_history_workflow import LocalHistoryWorkflow, MainWindowLocalHistoryEditorHost
from app.shell.main_thread_dispatcher import MainThreadDispatcher
from app.shell.main_window_layout import build_layout_shell, configure_window_frame
from app.shell.menu_wiring import build_main_window_menus, connect_test_explorer_navigation
from app.shell.menus import MenuStubRegistry
from app.shell.output_tail_buffer import OutputTailBuffer
from app.shell.plugin_activation_workflow import PluginActivationWorkflow
from app.shell.plugin_dialog_workflow import build_plugin_dialog_workflow
from app.shell.project_controller import ProjectController
from app.shell.project_inventory_orchestrator import ProjectInventoryOrchestrator
from app.shell.project_load_host import MainWindowProjectLoadHost
from app.shell.project_load_workflow import ProjectLoadWorkflow
from app.shell.project_rescan_workflow import MainWindowProjectRescanHost, ProjectRescanWorkflow
from app.shell.project_tree_action_coordinator import ProjectTreeActionCoordinator
from app.shell.project_tree_controller import ProjectTreeController
from app.shell.project_tree_ui_workflow import build_project_tree_ui_workflow
from app.shell.python_style_workflow import build_python_style_workflow
from app.shell.python_tooling_status_controller import PythonToolingStatusController
from app.shell.repl_event_workflow import MainWindowReplEventHost, ReplEvent, ReplEventWorkflow
from app.shell.repl_session_manager import ReplSessionManager
from app.shell.run_config_controller import RunConfigController
from app.shell.run_debug_presenter import MainWindowRunDebugPresenterHost, RunDebugPresenter
from app.shell.run_event_workflow import MainWindowRunEventHost, RunEventWorkflow
from app.shell.run_session_controller import RunSessionController
from app.shell.runtime_onboarding_workflow import (
    MainWindowRuntimeOnboardingHost,
    RuntimeOnboardingWorkflow,
)
from app.shell.runtime_support_workflow import RuntimeSupportWorkflow
from app.shell.shell_composition import build_save_workflow
from app.shell.shell_composition import (
    build_external_file_change_workflow,
    build_find_replace_workflow,
    build_project_tree_action_workflow,
    build_python_console_workflow,
    build_realtime_lint_runner,
    build_run_launch_workflow,
    build_semantic_navigation_workflow,
    build_settings_apply_workflow,
    build_shell_theme_workflow,
)
from app.shell.shell_composition_context import ShellCompositionContext, ShellCompositionTimers
from app.shell.shell_layout_workflow import build_shell_layout_workflow
from app.shell.shell_preferences_runtime import build_shell_preferences_runtime
from app.shell.shell_theme_workflow import ShellThemeWorkflow
from app.shell.shortcut_preferences import build_effective_shortcut_map
from app.shell.source_root_workflow import build_source_root_workflow
from app.shell.status_bar import create_shell_status_bar
from app.shell.test_runner_workflow import ActiveTestEditor, TestRunnerWorkflow
from app.shell.toolbar import build_run_toolbar_widget
from app.support.diagnostics import ProjectHealthReport
from app.templates.template_service import TemplateService


def _focus_bottom_tab(window: Any, widget: QWidget | None) -> None:
    bottom_tabs = getattr(window, "_bottom_tabs_widget", None)
    if bottom_tabs is None or widget is None:
        return
    index = bottom_tabs.indexOf(widget)
    if index < 0:
        return
    bottom_tabs.setCurrentIndex(index)


def install_layout_foundation(ctx: ShellCompositionContext) -> None:
    """Wire core shell infrastructure, preferences, and layout-related defaults."""
    window = ctx.w
    window._state_root = ctx.state_root
    window._logger = get_subsystem_logger("shell")
    window._startup_capability_facade = StartupCapabilityFacade()
    window._python_tooling_status_controller = PythonToolingStatusController(
        current_project_root=window._current_project_root
    )
    window._python_console_history_path = global_python_console_history_path(window._state_root)
    window._settings_service = SettingsService(state_root=window._state_root)
    window._shell_preferences_runtime = build_shell_preferences_runtime(window)
    window._stored_lint_diagnostics: dict[str, list[CodeDiagnostic]] = {}
    window._stored_runtime_problems: list[ProblemEntry] = []
    window._known_runtime_modules: frozenset[str] | None = load_cached_runtime_modules(
        state_root=window._state_root,
    )
    window._menu_registry: MenuStubRegistry | None = None
    window._command_broker = CommandBroker()
    window._action_registry: ShellActionRegistry | None = None
    window._event_bus = ShellEventBus()
    window._plugin_runtime_manager = PluginRuntimeManager(state_root=window._state_root)
    window._plugin_api_broker = PluginApiBroker(window._plugin_runtime_manager)
    window._workflow_broker = WorkflowBroker(window._plugin_api_broker)
    window._workflow_provider_catalog = WorkflowProviderCatalog([])
    window._plugin_safe_mode = window._shell_preferences_runtime.load_plugin_safe_mode()
    window._declarative_contribution_manager = DeclarativeContributionManager(
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
    window._status_controller = None
    window._startup_report: CapabilityProbeReport | None = ctx.startup_report
    window._toolbar = None
    window._top_splitter = None
    window._vertical_splitter = None
    window._close_tab_shortcut = None
    window._keep_preview_open_shortcut = None
    window._theme_mode: str = constants.UI_THEME_MODE_DEFAULT
    window._ui_font_weight: str = constants.UI_THEME_FONT_WEIGHT_DEFAULT
    window._dark_chrome_palette: str = constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT
    window._loaded_project: LoadedProject | None = None
    window._plugin_dialog_workflow = build_plugin_dialog_workflow(window)
    window._plugin_activation_workflow = PluginActivationWorkflow(
        state_root=window._state_root,
        project_root_provider=lambda: None
        if window._loaded_project is None
        else window._loaded_project.project_root,
        safe_mode_enabled=lambda: window._plugin_safe_mode,
        contribution_manager=window._declarative_contribution_manager,
        runtime_manager=window._plugin_runtime_manager,
        plugin_api_broker=window._plugin_api_broker,
        workflow_broker=window._workflow_broker,
        on_catalog_changed=lambda catalog: setattr(window, "_workflow_provider_catalog", catalog),
    )
    window._project_tree_structure_signature: tuple[str, ...] | None = None
    window._outline_panel = None
    window._explorer_splitter = None
    window._outline_symbols_by_path: dict[str, tuple[OutlineSymbol, ...]] = {}
    window._outline_collapsed: bool = DEFAULT_OUTLINE_COLLAPSED
    window._outline_follow_cursor: bool = DEFAULT_OUTLINE_FOLLOW_CURSOR
    window._outline_sort_mode: str = DEFAULT_OUTLINE_SORT_MODE
    window._zoom_delta: int = 0
    window._pending_project_tree_preview_path: str | None = None


def install_persistence(ctx: ShellCompositionContext) -> None:
    """Wire settings-backed stores, save workflow, and editor preference loading."""
    window = ctx.w
    (
        window._editor_tab_width,
        window._editor_font_size,
        window._editor_font_family,
        window._editor_indent_style,
        window._editor_indent_size,
        window._editor_detect_indentation_from_file,
        window._editor_format_on_save,
        window._editor_organize_imports_on_save,
        window._editor_trim_trailing_whitespace_on_save,
        window._editor_insert_final_newline_on_save,
        window._editor_enable_preview,
        window._editor_auto_save,
        window._editor_exit_behavior,
        window._editor_hover_tooltip_enabled,
        window._editor_auto_reindent_flat_python_paste,
    ) = window._shell_preferences_runtime.load_editor_preferences()
    (
        window._completion_enabled,
        window._completion_auto_trigger,
        window._completion_min_chars,
    ) = window._shell_preferences_runtime.load_completion_preferences()
    window._reported_completion_degradation_reasons: set[str] = set()
    (
        window._diagnostics_enabled,
        window._diagnostics_realtime,
        window._quick_fixes_enabled,
        window._quick_fix_require_preview_for_multifile,
    ) = window._shell_preferences_runtime.load_diagnostics_preferences()
    (
        window._auto_open_console_on_run_output,
        window._auto_open_problems_on_run_failure,
    ) = window._shell_preferences_runtime.load_output_preferences()
    window._intelligence_runtime_settings = window._shell_preferences_runtime.load_intelligence_runtime_settings()
    window._local_history_retention_policy = window._shell_preferences_runtime.load_local_history_retention_policy()
    window._theme_mode = ShellThemeWorkflow.load_theme_mode(window._settings_service)
    window._ui_font_weight = ShellThemeWorkflow.load_ui_font_weight(window._settings_service)
    window._dark_chrome_palette = ShellThemeWorkflow.load_dark_chrome_palette(window._settings_service)
    window._shortcut_overrides = window._shell_preferences_runtime.load_shortcut_overrides()
    window._effective_shortcuts = build_effective_shortcut_map(window._shortcut_overrides)
    window._syntax_color_overrides = ShellThemeWorkflow.load_syntax_color_overrides(window._settings_service)
    window._lint_rule_overrides = window._shell_preferences_runtime.load_lint_rule_overrides()
    window._selected_linter = window._shell_preferences_runtime.load_selected_linter()
    window._symbol_cache_db_path = str(global_cache_dir(window._state_root) / "symbols.sqlite3")
    window._import_update_policy = window._shell_preferences_runtime.load_import_update_policy()
    ctx.local_history_store = LocalHistoryStore(
        state_root=window._state_root,
        retention_policy=window._local_history_retention_policy,
    )
    ctx.autosave_store = AutosaveStore(
        state_root=window._state_root,
        history_store=ctx.local_history_store,
    )
    window._python_style_workflow = build_python_style_workflow(window)
    window._pending_realtime_lint_file_path: str | None = None


def install_editors(ctx: ShellCompositionContext) -> None:
    """Wire editor workspace, tab factory, and core editor workflows."""
    window = ctx.w
    window._workspace_controller = EditorWorkspaceController()
    window._editor_manager = EditorManager()
    window._editor_widgets_by_path = window._workspace_controller.editor_widgets_by_path
    window._markdown_panes_by_path: dict[str, MarkdownEditorPane] = {}
    window._tab_content_registry = EditorTabContentRegistry(window._markdown_panes_by_path)
    window._editor_tab_factory = EditorTabFactory(window)
    window._indent_source_by_path: dict[str, tuple[str, int, str]] = {}
    window._debug_exception_policy = DebugExceptionPolicy()
    window._tree_clipboard_paths: list[str] = []
    window._tree_clipboard_cut: bool = False
    window._project_tree_controller: ProjectTreeController[CodeEditorWidget] = ProjectTreeController()


def install_run_debug(ctx: ShellCompositionContext) -> None:
    """Wire run, debug, REPL, and runtime onboarding."""
    window = ctx.w
    window._console_model = ConsoleModel()
    window._run_event_queue: queue.Queue[ProcessEvent] = queue.Queue()
    window._active_run_output_tail = OutputTailBuffer(max_chars=300_000, max_chunks=6_000)
    window._active_transient_entry_file_path: str | None = None
    window._debug_session = DebugSession()
    window._debug_execution_editor = None
    window._is_shutting_down = False
    window._latest_health_report: ProjectHealthReport | None = None
    window._latest_import_issue_report = RuntimeIssueReport(workflow="import", issues=[])
    window._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=[])
    window._latest_package_issue_report = RuntimeIssueReport(workflow="package", issues=[])
    window._latest_run_issue_ids: tuple[str, ...] = ()
    window._run_event_workflow = RunEventWorkflow(MainWindowRunEventHost(window))
    window._run_service = RunService(
        on_event=window._run_event_workflow.enqueue_run_event,
        state_root=window._state_root,
    )
    window._run_session_controller = RunSessionController(window._run_service)
    window._run_debug_presenter = RunDebugPresenter(MainWindowRunDebugPresenterHost(window))
    window._run_config_controller = RunConfigController()
    window._debug_control_workflow = DebugControlWorkflow(window)
    window._debug_inspector_workflow = DebugInspectorWorkflow(MainWindowDebugInspectorHost(window))
    window._active_named_run_config_name: str | None = None
    window._repl_event_queue: queue.Queue[ReplEvent] = queue.Queue()
    window._repl_event_workflow = ReplEventWorkflow(MainWindowReplEventHost(window))
    window._repl_manager = ReplSessionManager(
        on_output=window._repl_event_workflow.enqueue_output,
        on_session_ended=window._repl_event_workflow.enqueue_ended,
        on_session_started=window._repl_event_workflow.enqueue_started,
        state_root=window._state_root,
    )
    window._main_thread_dispatcher = MainThreadDispatcher(window)
    window._runtime_onboarding_workflow = RuntimeOnboardingWorkflow(MainWindowRuntimeOnboardingHost(window))
    window._latest_runtime_issue_report = window._runtime_onboarding_workflow.build_runtime_issue_report()


def install_intelligence(ctx: ShellCompositionContext) -> None:
    """Wire intelligence runtime, diagnostics, lint, and semantic navigation."""
    window = ctx.w
    bootstrap_intelligence_runtime(window, symbol_cache_db_path=window._symbol_cache_db_path)
    window._template_service = TemplateService()
    register_builtin_workflow_providers(
        window._workflow_broker,
        template_service=window._template_service,
    )
    window._example_project_service = ExampleProjectService()
    window._runtime_support_workflow = RuntimeSupportWorkflow(
        parent=window,
        state_root=window._state_root,
        background_tasks=window._background_tasks,
        workflow_broker=window._workflow_broker,
        loaded_project=lambda: window._loaded_project,
        startup_report=lambda: window._startup_report,
        latest_health_report=lambda: window._latest_health_report,
        set_latest_health_report=lambda report: setattr(window, "_latest_health_report", report),
        latest_import_issue_report=lambda: window._latest_import_issue_report,
        latest_run_issue_report=lambda: window._latest_run_issue_report,
        latest_package_issue_report=lambda: window._latest_package_issue_report,
        set_latest_package_issue_report=lambda report: setattr(window, "_latest_package_issue_report", report),
        set_latest_runtime_issue_report=lambda report: setattr(window, "_latest_runtime_issue_report", report),
        set_latest_import_issue_report=lambda report: setattr(window, "_latest_import_issue_report", report),
        set_latest_run_issue_report=lambda report: setattr(window, "_latest_run_issue_report", report),
        clear_active_run_config=lambda: (
            setattr(window, "_active_named_run_config_name", None),
            setattr(window, "_latest_run_issue_ids", ()),
        ),
        build_runtime_issue_report=window._runtime_onboarding_workflow.build_runtime_issue_report,
        open_runtime_center_dialog=window._runtime_onboarding_workflow.open_runtime_center_dialog,
        active_run_session_log_path=lambda: window._run_session_controller.session_store.log_path,
        known_runtime_modules=lambda: window._known_runtime_modules,
        resolve_theme_tokens=lambda: window._shell_theme_workflow.resolve_theme_tokens(),
    )
    window._intelligence_cache_workflow = build_intelligence_cache_workflow(window)
    window._project_inventory_orchestrator = ProjectInventoryOrchestrator()
    window._semantic_session.set_inventory_snapshot_provider(
        lambda: window._project_inventory_orchestrator.snapshot
    )
    window._lint_workflow = build_lint_workflow(window)
    window._diagnostics_orchestrator = DiagnosticsOrchestrator(
        diagnostics_enabled=lambda: window._diagnostics_enabled,
        diagnostics_realtime=lambda: window._diagnostics_realtime,
        set_pending_realtime_file_path=lambda file_path: setattr(
            window, "_pending_realtime_lint_file_path", file_path
        ),
        get_pending_realtime_file_path=lambda: window._pending_realtime_lint_file_path,
        start_realtime_timer=window._realtime_lint_timer.start,
        get_active_tab_file_path=window._editor_manager.active_file_path,
        render_lint_for_file=lambda file_path, trigger: window._lint_workflow.render_diagnostics_for_file(
            file_path,
            trigger=trigger,
        ),
        get_open_editor_paths=window._workspace_controller.open_editor_paths,
        render_merged_problems_panel=lambda: window._problems_controller.render_merged_problems_panel(),
        set_known_runtime_modules=lambda modules: setattr(window, "_known_runtime_modules", modules),
        run_background_task=window._background_tasks.run,
        state_root=lambda: window._state_root,
        logger=window._logger,
        show_runtime_probe_warning=lambda message: QMessageBox.warning(
            window,
            "Refresh Runtime Modules",
            message,
        ),
    )
    window._settings_apply_workflow = build_settings_apply_workflow(window)
    window._python_console_workflow = build_python_console_workflow(window)
    window._find_replace_workflow = build_find_replace_workflow(window)
    window._semantic_navigation_workflow = build_semantic_navigation_workflow(window)


def install_editor_project_wiring(ctx: ShellCompositionContext) -> None:
    """Wire editor/project workflows that depend on run, debug, and intelligence."""
    window = ctx.w
    assert ctx.local_history_store is not None
    assert ctx.autosave_store is not None
    window._local_history_workflow = LocalHistoryWorkflow(
        host=MainWindowLocalHistoryEditorHost(window),
        local_history_store=ctx.local_history_store,
        autosave_store=ctx.autosave_store,
        editor_manager=window._editor_manager,
        logger=window._logger,
        background_tasks=window._background_tasks,
        retention_policy=window._local_history_retention_policy,
    )
    window._save_workflow = build_save_workflow(window)
    window._project_controller = ProjectController(
        state_root=window._state_root,
        logger=window._logger,
        dispatch_to_main_thread=window._dispatch_to_main_thread,
    )
    window._file_project_commands_workflow = build_file_project_commands_workflow(window)
    window._project_load_workflow = ProjectLoadWorkflow(MainWindowProjectLoadHost(window))
    window._project_rescan_workflow = ProjectRescanWorkflow(MainWindowProjectRescanHost(window))
    window._source_root_workflow = build_source_root_workflow(window)
    window._external_file_change_workflow = build_external_file_change_workflow(window)
    window._editor_tab_workflow = build_editor_tab_workflow(window)
    window._project_tree_ui_workflow = build_project_tree_ui_workflow(window)
    window._project_tree_action_coordinator = ProjectTreeActionCoordinator(
        project_tree_controller=window._project_tree_controller,
        editor_widgets_by_path=window._editor_widgets_by_path,
        tab_index_for_path=window._editor_tab_workflow.tab_index_for_path,
        remove_tab_at_index=lambda tab_index: window._editor_tabs_widget.removeTab(tab_index)
        if window._editor_tabs_widget is not None
        else None,
        release_editor_widget=window._project_tree_ui_workflow.release_editor_widget,
        close_editor_file=window._editor_manager.close_file,
        breakpoint_store=window._debug_control_workflow.breakpoint_store,
        refresh_breakpoints_list=window._debug_control_workflow.refresh_breakpoints_list,
        remap_editor_paths=window._editor_manager.remap_paths_for_move,
        update_tab_path_and_name=window._project_tree_ui_workflow.update_tab_path_and_name,
        apply_breakpoints_to_widget=lambda widget, breakpoints: widget.set_breakpoints(breakpoints),
        update_widget_language=window._project_tree_ui_workflow.update_widget_language_for_path,
        maybe_rewrite_imports=window._project_tree_ui_workflow.maybe_rewrite_imports_for_move,
        refresh_project=window._project_tree_ui_workflow.refresh_project_tree,
        record_deleted_path=window._local_history_workflow.record_deleted_path,
        remap_file_lineage=window._local_history_workflow.remap_file_lineage,
    )
    window._project_tree_action_workflow = build_project_tree_action_workflow(window)
    window._shell_layout_workflow = build_shell_layout_workflow(window)


def install_theme_and_finalize(ctx: ShellCompositionContext) -> None:
    """Build physical shell layout, theme, menus, and post-install refresh hooks."""
    window = ctx.w
    window._shell_theme_workflow = build_shell_theme_workflow(window)
    window._help_controller = ShellHelpController(
        state_root=window._state_root,
        resolve_theme_tokens=window._shell_theme_workflow.resolve_theme_tokens,
        reveal_path_in_file_manager=window._project_tree_ui_workflow.reveal_path_in_file_manager,
        get_effective_shortcuts=lambda: window._effective_shortcuts,
    )
    configure_window_frame(window)
    build_layout_shell(window)
    window._run_launch_workflow = build_run_launch_workflow(window)

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

    window._test_runner_workflow = TestRunnerWorkflow(
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
        focus_run_log_tab=lambda: _focus_bottom_tab(window, window._run_log_panel),
        focus_problems_tab=lambda: _focus_bottom_tab(window, window._problems_panel),
        show_warning=lambda title, message: QMessageBox.warning(window, title, message),
        show_information=lambda title, message: QMessageBox.information(window, title, message),
        record_debug_target=window._run_launch_workflow.record_debug_target_from_dict,
        auto_open_console_on_output=lambda: window._auto_open_console_on_run_output,
        auto_open_problems_on_failure=lambda: window._auto_open_problems_on_run_failure,
        logger=window._logger,
    )
    connect_test_explorer_navigation(window)
    window._shell_preferences_runtime.configure_close_tab_shortcut()
    window._shell_preferences_runtime.configure_keep_preview_open_shortcut()
    window._menu_registry = build_main_window_menus(window, shortcut_overrides=window._effective_shortcuts)
    if window._menu_registry is not None:
        window._action_registry = ShellActionRegistry(
            menu_registry=window._menu_registry,
            command_broker=window._command_broker,
        )
    window._status_controller = create_shell_status_bar(
        window,
        startup_report=ctx.startup_report,
        on_startup_activated=window._runtime_onboarding_workflow.handle_runtime_center_action,
    )
    window._run_launch_workflow.install_active_run_config_indicator()
    window._refresh_python_tooling_status()
    window._toolbar = build_run_toolbar_widget(window._menu_registry)
    if window._toolbar is not None:
        center_panel = window.findChild(QWidget, "shell.centerPanel")
        if center_panel is not None:
            center_layout = center_panel.layout()
            if isinstance(center_layout, QVBoxLayout):
                center_layout.insertWidget(0, window._toolbar, 0)
    window._shell_theme_workflow.apply_theme_styles()
    window._editor_tab_workflow.apply_runtime_intelligence_preferences_to_open_editors()
    window._shell_preferences_runtime.sync_theme_menu_check_state()
    window._sync_auto_save_menu_state()
    window._shell_layout_workflow.restore_from_settings()
    window._file_project_commands_workflow.refresh_open_recent_menu()
    window._refresh_save_action_states()
    window._run_event_workflow.refresh_run_action_states()
    window._editor_tab_workflow.refresh_markdown_action_states()
    window._test_runner_workflow.refresh_discovery()
    window._plugin_activation_workflow.reload()


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

    window._composition_timers = timers
    window._project_tree_preview_click_timer = timers.project_tree_preview_click
    window._auto_save_to_file_timer = timers.auto_save_to_file
    window._realtime_lint_timer = timers.realtime_lint
    window._outline_refresh_timer = timers.outline_refresh
    window._run_event_timer = timers.run_event
    window._repl_event_timer = timers.repl_event
    window._external_change_poll_timer = timers.external_change_poll
    window._restore_project_timer = timers.restore_project
    window._auto_start_repl_timer = timers.auto_start_repl
    window._runtime_probe_timer = timers.runtime_probe
    window._startup_probe_refresh_timer = timers.startup_probe_refresh
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


__all__ = [
    "connect_composition_timers",
    "create_composition_timers",
    "install_editor_project_wiring",
    "install_editors",
    "install_intelligence",
    "install_layout_foundation",
    "install_persistence",
    "install_run_debug",
    "install_theme_and_finalize",
    "start_composition_timers",
]
