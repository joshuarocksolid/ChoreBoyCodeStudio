"""Phased install helpers for main-window shell composition."""

# pyright: reportInvalidTypeForm=false

from __future__ import annotations

import queue

from PySide2.QtWidgets import QVBoxLayout, QWidget

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.paths import global_cache_dir, global_python_console_history_path
from app.bootstrap.runtime_module_probe import load_cached_runtime_modules
from app.bootstrap.startup_facade import StartupCapabilityFacade
from app.core import constants
from app.debug.debug_models import DebugExceptionPolicy
from app.debug.debug_session import DebugSession
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.examples.example_project_service import ExampleProjectService
from app.persistence.autosave_store import AutosaveStore
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.settings_service import SettingsService
from app.plugins.api_broker import PluginApiBroker
from app.plugins.builtin_workflows import register_builtin_workflow_providers
from app.plugins.runtime_manager import PluginRuntimeManager
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
from app.shell.editor_tab_content_registry import EditorTabContentRegistry
from app.shell.editor_tab_factory import EditorTabFactory
from app.shell.editor_tab_workflow import build_editor_tab_workflow
from app.shell.editor_workspace_controller import EditorWorkspaceController
from app.shell.events import ShellEventBus
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
from app.shell.output_tail_buffer import OutputTailBuffer
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
from app.shell.shell_composition import (
    build_declarative_contribution_manager,
    build_diagnostics_orchestrator,
    build_external_file_change_workflow,
    build_file_project_commands_workflow,
    build_find_replace_workflow,
    build_plugin_activation_workflow,
    build_project_tree_action_workflow,
    build_python_console_workflow,
    build_run_launch_workflow,
    build_runtime_support_workflow,
    build_save_workflow,
    build_semantic_navigation_workflow,
    build_settings_apply_workflow,
    build_shell_theme_workflow,
    build_test_runner_workflow,
    connect_composition_timers,
    create_composition_timers,
    start_composition_timers,
)
from app.shell.shell_composition_context import (
    ShellCompositionContext,
    ShellDiagnosticsLatchState,
    ShellRuntimeIssueState,
    bind_private_attrs,
)
from app.shell.shell_layout_workflow import build_shell_layout_workflow
from app.shell.shell_preferences_runtime import build_shell_preferences_runtime
from app.shell.shell_theme_workflow import ShellThemeWorkflow
from app.shell.shortcut_preferences import build_effective_shortcut_map
from app.shell.source_root_workflow import build_source_root_workflow
from app.shell.status_bar import create_shell_status_bar
from app.shell.toolbar import build_run_toolbar_widget
from app.templates.template_service import TemplateService


def install_layout_foundation(ctx: ShellCompositionContext) -> None:
    """Wire core shell infrastructure, preferences, and layout-related defaults."""
    window = ctx.w
    state_root = ctx.state_root
    logger = get_subsystem_logger("shell")
    settings_service = SettingsService(state_root=state_root)
    bind_private_attrs(
        window,
        {
            "_state_root": state_root,
            "_logger": logger,
            "_startup_capability_facade": StartupCapabilityFacade(),
            "_python_console_history_path": global_python_console_history_path(state_root),
            "_settings_service": settings_service,
            "_stored_lint_diagnostics": {},
            "_stored_runtime_problems": [],
            "_menu_registry": None,
            "_command_broker": CommandBroker(),
            "_action_registry": None,
            "_event_bus": ShellEventBus(),
            "_plugin_runtime_manager": PluginRuntimeManager(state_root=state_root),
            "_status_controller": None,
            "_startup_report": ctx.startup_report,
            "_toolbar": None,
            "_top_splitter": None,
            "_vertical_splitter": None,
            "_close_tab_shortcut": None,
            "_keep_preview_open_shortcut": None,
            "_theme_mode": constants.UI_THEME_MODE_DEFAULT,
            "_ui_font_weight": constants.UI_THEME_FONT_WEIGHT_DEFAULT,
            "_dark_chrome_palette": constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT,
            "_loaded_project": None,
            "_project_tree_structure_signature": None,
            "_outline_panel": None,
            "_explorer_splitter": None,
            "_outline_symbols_by_path": {},
            "_outline_collapsed": DEFAULT_OUTLINE_COLLAPSED,
            "_outline_follow_cursor": DEFAULT_OUTLINE_FOLLOW_CURSOR,
            "_outline_sort_mode": DEFAULT_OUTLINE_SORT_MODE,
            "_zoom_delta": 0,
            "_pending_project_tree_preview_path": None,
        },
    )
    window._python_tooling_status_controller = PythonToolingStatusController(
        current_project_root=window._current_project_root
    )
    window._shell_preferences_runtime = build_shell_preferences_runtime(window)
    window._plugin_api_broker = PluginApiBroker(window._plugin_runtime_manager)
    window._workflow_broker = WorkflowBroker(window._plugin_api_broker)
    window._workflow_provider_catalog = WorkflowProviderCatalog([])
    window._plugin_safe_mode = window._shell_preferences_runtime.load_plugin_safe_mode()
    window._plugin_dialog_workflow = build_plugin_dialog_workflow(window)
    contribution_manager = build_declarative_contribution_manager(ctx)
    window._declarative_contribution_manager = contribution_manager
    window._plugin_activation_workflow = build_plugin_activation_workflow(
        ctx,
        contribution_manager=contribution_manager,
    )
    ctx.diagnostics_latches = ShellDiagnosticsLatchState(
        known_runtime_modules=load_cached_runtime_modules(state_root=state_root),
    )
    ctx.diagnostics_latches.bind_to_window(window)


def install_persistence(ctx: ShellCompositionContext) -> None:
    """Wire settings-backed stores, save workflow, and editor preference loading."""
    window = ctx.w
    preferences = window._shell_preferences_runtime
    editor_prefs = preferences.load_editor_preferences()
    completion_prefs = preferences.load_completion_preferences()
    diagnostics_prefs = preferences.load_diagnostics_preferences()
    output_prefs = preferences.load_output_preferences()
    bind_private_attrs(
        window,
        {
            "_editor_tab_width": editor_prefs[0],
            "_editor_font_size": editor_prefs[1],
            "_editor_font_family": editor_prefs[2],
            "_editor_indent_style": editor_prefs[3],
            "_editor_indent_size": editor_prefs[4],
            "_editor_detect_indentation_from_file": editor_prefs[5],
            "_editor_format_on_save": editor_prefs[6],
            "_editor_organize_imports_on_save": editor_prefs[7],
            "_editor_trim_trailing_whitespace_on_save": editor_prefs[8],
            "_editor_insert_final_newline_on_save": editor_prefs[9],
            "_editor_enable_preview": editor_prefs[10],
            "_editor_auto_save": editor_prefs[11],
            "_editor_exit_behavior": editor_prefs[12],
            "_editor_hover_tooltip_enabled": editor_prefs[13],
            "_editor_auto_reindent_flat_python_paste": editor_prefs[14],
            "_completion_enabled": completion_prefs[0],
            "_completion_auto_trigger": completion_prefs[1],
            "_completion_min_chars": completion_prefs[2],
            "_reported_completion_degradation_reasons": set(),
            "_diagnostics_enabled": diagnostics_prefs[0],
            "_diagnostics_realtime": diagnostics_prefs[1],
            "_quick_fixes_enabled": diagnostics_prefs[2],
            "_quick_fix_require_preview_for_multifile": diagnostics_prefs[3],
            "_auto_open_console_on_run_output": output_prefs[0],
            "_auto_open_problems_on_run_failure": output_prefs[1],
            "_intelligence_runtime_settings": preferences.load_intelligence_runtime_settings(),
            "_local_history_retention_policy": preferences.load_local_history_retention_policy(),
            "_theme_mode": ShellThemeWorkflow.load_theme_mode(window._settings_service),
            "_ui_font_weight": ShellThemeWorkflow.load_ui_font_weight(window._settings_service),
            "_dark_chrome_palette": ShellThemeWorkflow.load_dark_chrome_palette(window._settings_service),
            "_shortcut_overrides": preferences.load_shortcut_overrides(),
            "_effective_shortcuts": build_effective_shortcut_map(preferences.load_shortcut_overrides()),
            "_syntax_color_overrides": ShellThemeWorkflow.load_syntax_color_overrides(window._settings_service),
            "_lint_rule_overrides": preferences.load_lint_rule_overrides(),
            "_selected_linter": preferences.load_selected_linter(),
            "_symbol_cache_db_path": str(global_cache_dir(window._state_root) / "symbols.sqlite3"),
            "_import_update_policy": preferences.load_import_update_policy(),
        },
    )
    ctx.local_history_store = LocalHistoryStore(
        state_root=window._state_root,
        retention_policy=window._local_history_retention_policy,
    )
    ctx.autosave_store = AutosaveStore(
        state_root=window._state_root,
        history_store=ctx.local_history_store,
    )
    window._python_style_workflow = build_python_style_workflow(window)


def install_editors(ctx: ShellCompositionContext) -> None:
    """Wire editor workspace, tab factory, and core editor workflows."""
    window = ctx.w
    workspace_controller = EditorWorkspaceController()
    editor_manager = EditorManager()
    markdown_panes_by_path: dict[str, MarkdownEditorPane] = {}
    bind_private_attrs(
        window,
        {
            "_workspace_controller": workspace_controller,
            "_editor_manager": editor_manager,
            "_editor_widgets_by_path": workspace_controller.editor_widgets_by_path,
            "_markdown_panes_by_path": markdown_panes_by_path,
            "_tab_content_registry": EditorTabContentRegistry(markdown_panes_by_path),
            "_editor_tab_factory": EditorTabFactory(window),
            "_indent_source_by_path": {},
            "_debug_exception_policy": DebugExceptionPolicy(),
            "_tree_clipboard_paths": [],
            "_tree_clipboard_cut": False,
            "_project_tree_controller": ProjectTreeController[CodeEditorWidget](),
        },
    )


def install_run_debug(ctx: ShellCompositionContext) -> None:
    """Wire run, debug, REPL, and runtime onboarding."""
    window = ctx.w
    ctx.runtime_issues = ShellRuntimeIssueState.create_initial()
    ctx.runtime_issues.bind_to_window(window)
    run_event_workflow = RunEventWorkflow(MainWindowRunEventHost(window))
    run_service = RunService(
        on_event=run_event_workflow.enqueue_run_event,
        state_root=window._state_root,
    )
    runtime_onboarding_workflow = RuntimeOnboardingWorkflow(MainWindowRuntimeOnboardingHost(window))
    bind_private_attrs(
        window,
        {
            "_console_model": ConsoleModel(),
            "_run_event_queue": queue.Queue[ProcessEvent](),
            "_active_run_output_tail": OutputTailBuffer(max_chars=300_000, max_chunks=6_000),
            "_active_transient_entry_file_path": None,
            "_debug_session": DebugSession(),
            "_debug_execution_editor": None,
            "_is_shutting_down": False,
            "_run_event_workflow": run_event_workflow,
            "_run_service": run_service,
            "_run_session_controller": RunSessionController(run_service),
            "_run_debug_presenter": RunDebugPresenter(MainWindowRunDebugPresenterHost(window)),
            "_run_config_controller": RunConfigController(),
            "_debug_control_workflow": DebugControlWorkflow(window),
            "_debug_inspector_workflow": DebugInspectorWorkflow(MainWindowDebugInspectorHost(window)),
            "_repl_event_queue": queue.Queue[ReplEvent](),
            "_repl_event_workflow": ReplEventWorkflow(MainWindowReplEventHost(window)),
            "_main_thread_dispatcher": MainThreadDispatcher(window),
            "_runtime_onboarding_workflow": runtime_onboarding_workflow,
        },
    )
    window._repl_manager = ReplSessionManager(
        on_output=window._repl_event_workflow.enqueue_output,
        on_session_ended=window._repl_event_workflow.enqueue_ended,
        on_session_started=window._repl_event_workflow.enqueue_started,
        state_root=window._state_root,
    )
    window._latest_runtime_issue_report = runtime_onboarding_workflow.build_runtime_issue_report()
    ctx.runtime_issues.latest_runtime_issue_report = window._latest_runtime_issue_report


def install_intelligence(ctx: ShellCompositionContext) -> None:
    """Wire intelligence runtime, diagnostics, lint, and semantic navigation."""
    window = ctx.w
    assert ctx.runtime_issues is not None
    assert ctx.diagnostics_latches is not None
    bootstrap_intelligence_runtime(window, symbol_cache_db_path=window._symbol_cache_db_path)
    window._template_service = TemplateService()
    register_builtin_workflow_providers(
        window._workflow_broker,
        template_service=window._template_service,
    )
    window._example_project_service = ExampleProjectService()
    window._runtime_support_workflow = build_runtime_support_workflow(
        ctx,
        runtime_issues=ctx.runtime_issues,
    )
    window._intelligence_cache_workflow = build_intelligence_cache_workflow(window)
    window._project_inventory_orchestrator = ProjectInventoryOrchestrator()
    window._semantic_session.set_inventory_snapshot_provider(
        lambda: window._project_inventory_orchestrator.snapshot
    )
    window._lint_workflow = build_lint_workflow(window)
    window._diagnostics_orchestrator = build_diagnostics_orchestrator(
        ctx,
        diagnostics_latches=ctx.diagnostics_latches,
    )
    window._settings_apply_workflow = build_settings_apply_workflow(ctx)
    window._python_console_workflow = build_python_console_workflow(ctx)
    window._find_replace_workflow = build_find_replace_workflow(ctx)
    window._semantic_navigation_workflow = build_semantic_navigation_workflow(ctx)


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
    window._save_workflow = build_save_workflow(ctx)
    window._project_controller = ProjectController(
        state_root=window._state_root,
        logger=window._logger,
        dispatch_to_main_thread=window._dispatch_to_main_thread,
    )
    window._file_project_commands_workflow = build_file_project_commands_workflow(ctx)
    window._project_load_workflow = ProjectLoadWorkflow(MainWindowProjectLoadHost(window))
    window._project_rescan_workflow = ProjectRescanWorkflow(MainWindowProjectRescanHost(window))
    window._source_root_workflow = build_source_root_workflow(window)
    window._external_file_change_workflow = build_external_file_change_workflow(ctx)
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
    window._project_tree_action_workflow = build_project_tree_action_workflow(ctx)
    window._shell_layout_workflow = build_shell_layout_workflow(window)


def install_theme_and_finalize(ctx: ShellCompositionContext) -> None:
    """Build physical shell layout, theme, menus, and post-install refresh hooks."""
    window = ctx.w
    window._shell_theme_workflow = build_shell_theme_workflow(ctx)
    window._help_controller = ShellHelpController(
        state_root=window._state_root,
        resolve_theme_tokens=window._shell_theme_workflow.resolve_theme_tokens,
        reveal_path_in_file_manager=window._project_tree_ui_workflow.reveal_path_in_file_manager,
        get_effective_shortcuts=lambda: window._effective_shortcuts,
    )
    configure_window_frame(window)
    build_layout_shell(window)
    window._run_launch_workflow = build_run_launch_workflow(ctx)
    window._test_runner_workflow = build_test_runner_workflow(ctx)
    connect_test_explorer_navigation(window)
    window._shell_preferences_runtime.configure_close_tab_shortcut()
    window._shell_preferences_runtime.configure_keep_preview_open_shortcut()
    menu_registry = build_main_window_menus(window, shortcut_overrides=window._effective_shortcuts)
    window._menu_registry = menu_registry
    if menu_registry is not None:
        window._action_registry = ShellActionRegistry(
            menu_registry=menu_registry,
            command_broker=window._command_broker,
        )
    window._status_controller = create_shell_status_bar(
        window,
        startup_report=ctx.startup_report,
        on_startup_activated=window._runtime_onboarding_workflow.handle_runtime_center_action,
    )
    window._run_launch_workflow.install_active_run_config_indicator()
    window._refresh_python_tooling_status()
    toolbar = build_run_toolbar_widget(menu_registry)
    window._toolbar = toolbar
    if toolbar is not None:
        center_panel = window.findChild(QWidget, "shell.centerPanel")
        if center_panel is not None:
            center_layout = center_panel.layout()
            if isinstance(center_layout, QVBoxLayout):
                center_layout.insertWidget(0, toolbar, 0)
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
