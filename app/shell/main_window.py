"""Main Qt shell composition and top-level workflow wiring."""

from __future__ import annotations

import queue
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Callable, Mapping, Optional, Protocol, TypeVar, cast

from PySide2.QtCore import QEvent, QPoint, QSize, QTimer, Qt, QUrl
from PySide2.QtGui import QCloseEvent, QDesktopServices, QIcon, QKeySequence
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.paths import global_cache_dir, global_python_console_history_path
from app.bootstrap.runtime_module_probe import load_cached_runtime_modules, probe_and_cache_runtime_modules
from app.bootstrap.startup_facade import StartupCapabilityFacade
from app.core import constants
from app.core.errors import AppValidationError, ProjectManifestValidationError
from app.core.models import CapabilityProbeReport, LoadedProject, RuntimeIssueReport
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugExecutionState, DebugSourceMap
from app.debug.debug_session import DebugSession
from app.intelligence.cache_controls import (
    IntelligenceRuntimeSettings,
    rebuild_symbol_cache,
)
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity, analyze_python_file
from app.intelligence.outline_service import (
    OutlineSymbol,
    build_outline_from_source,
)
from app.intelligence.semantic_session import SemanticSession
from app.intelligence.symbol_index import SymbolIndexWorker
from app.intelligence.completion_models import (
    CompletionItem,
    CompletionResolveRequest,
    CompletionResolveResult,
)
from app.intelligence.runtime_introspection import RuntimeIntrospectionCoordinator
from app.editors.editor_manager import EditorManager
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editorconfig import resolve_editorconfig_indentation
from app.editors.find_replace_bar import FindReplaceBar
from app.editors.markdown_editor_pane import MarkdownEditorPane, MarkdownPreviewMode
from app.editors.markdown_rendering import is_markdown_path
from app.editors.quick_open_dialog import QuickOpenDialog
from app.editors.indentation import detect_indentation_style_and_size
from app.editors.quick_open import QuickOpenCandidate
from app.editors.search_panel import SearchMatch, SearchWorker
from app.editors.text_editing import FlatPythonIndentRepairResult
from app.persistence.autosave_store import AutosaveStore
from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.settings_service import SettingsService
from app.persistence.settings_store import project_settings_has_overrides
from app.shell.clear_console_policy import (
    MainWindowClearConsoleHost,
    clear_run_output_sinks,
    prepare_new_run,
)
from app.shell.console_model import ConsoleModel
from app.shell.exit_status import describe_exit_code
from app.shell.output_tail_buffer import OutputTailBuffer
from app.run.problem_parser import ProblemEntry, parse_traceback_problems
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService
from app.run.runtime_launch import (
    build_runpy_bootstrap_payload,
    is_freecad_runtime_executable,
    resolve_runtime_executable,
)
from app.shell.run_log_panel import RunInfo, RunLogPanel
from app.shell.test_runner_workflow import ActiveTestEditor, TestRunnerWorkflow
from app.shell.plugin_activation_workflow import PluginActivationWorkflow
from app.packaging.layout import resolve_entry_path
from app.packaging.packager import package_project
from app.plugins.api_broker import PluginApiBroker
from app.plugins.builtin_workflows import register_builtin_workflow_providers
from app.plugins.contributions import DeclarativeContributionManager
from app.plugins.registry_store import (
    clear_registry_entry_failures,
    record_registry_entry_failure,
)
from app.plugins.runtime_manager import PluginRuntimeManager
from app.plugins.security_policy import merge_plugin_safe_mode, plugin_safe_mode_enabled
from app.plugins.workflow_adapters import (
    analyze_python_with_workflow,
    list_templates_with_workflow,
    run_pytest_with_workflow,
)
from app.plugins.workflow_broker import WorkflowBroker
from app.plugins.workflow_catalog import WorkflowProviderCatalog
from app.support.diagnostics import ProjectHealthReport
from app.support.runtime_explainer import (
    HELP_TOPIC_GETTING_STARTED,
    HELP_TOPIC_HEADLESS_NOTES,
    build_project_health_issue_report,
    build_startup_issue_report,
    explain_runtime_message,
    merge_runtime_issue_reports,
)
from app.templates.template_service import TemplateMetadata, TemplateService
from app.examples.example_project_service import ExampleProjectService
from app.shell.layout_persistence import (
    DEFAULT_EXPLORER_SPLITTER_SIZES,
    DEFAULT_OUTLINE_COLLAPSED,
    DEFAULT_OUTLINE_FOLLOW_CURSOR,
    DEFAULT_OUTLINE_SORT_MODE,
    DEFAULT_TOP_SPLITTER_SIZES,
    DEFAULT_VERTICAL_SPLITTER_SIZES,
    ShellLayoutState,
    merge_layout_into_settings,
    parse_shell_layout_state,
)
from app.shell.local_history_workflow import LocalHistoryWorkflow
from app.shell.settings_dialog import SettingsDialog
from app.shell.python_tooling_status_controller import PythonToolingStatusController
from app.shell.settings_models import (
    EditorSettingsSnapshot,
    MainWindowSettingsSnapshot,
    merge_import_update_policy,
    merge_editor_settings_snapshot_for_scope,
    merge_last_project_path,
    merge_theme_mode,
    parse_editor_settings_snapshot,
    parse_effective_editor_settings_snapshot,
    parse_effective_main_window_settings,
)
from app.shell.shortcut_preferences import (
    build_effective_shortcut_map,
    close_tab_shortcut_id,
    keep_preview_open_shortcut_id,
)
from app.shell.icon_provider import (
    file_icon,
    file_type_icon_map,
    filename_icon_map,
    folder_icon,
    folder_open_icon,
    new_file_icon,
    new_folder_icon,
    refresh_icon,
)
from app.shell.test_explorer_panel import TestExplorerPanel
from app.shell.debug_panel import DebugPanelWidget
from app.shell.outline import OutlinePanel
from app.shell.problems_panel import ProblemsPanel, ResultItem
from app.shell.plugins_panel import PluginManagerDialog
from app.shell.dependency_panel import DependencyInspectorDialog
from app.shell.dependency_wizard_dialog import AddDependencyWizardDialog
from app.shell.python_console_widget import PythonConsoleWidget
from app.shell.python_console_history import load_python_console_history, save_python_console_history
from app.shell.runtime_center_dialog import RuntimeCenterDialog
from app.shell.search_sidebar_widget import SearchSidebarWidget
from app.shell.theme_tokens import ShellThemeTokens
from app.project.project_tree_widget import ProjectTreeWidget
from app.project.project_tree_presenter import ProjectTreeDisplayNode
from app.project.file_excludes import (
    compute_effective_excludes,
    load_effective_exclude_patterns,
)
from app.python_tools.black_adapter import format_python_text
from app.python_tools.isort_adapter import organize_imports_text
from app.project.file_inventory import iter_python_files
from app.project.file_operation_models import ImportUpdatePolicy
from app.project.project_service import (
    ProjectRootState,
    assess_project_root,
    create_blank_project,
    enumerate_project_entries,
    open_project,
)
from app.project.project_manifest import (
    set_project_default_entry,
)
from app.project.recent_projects import load_recent_projects
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.main_thread_dispatcher import MainThreadDispatcher
from app.shell.action_registry import ShellActionRegistry
from app.shell.command_broker import CommandBroker
from app.shell.debug_control_workflow import DebugControlWorkflow
from app.shell.events import (
    ProjectOpenFailedEvent,
    RunProcessExitEvent,
    RunProcessOutputEvent,
    RunProcessStateEvent,
    ShellEventBus,
)
from app.shell.menu_wiring import build_main_window_menus, connect_test_explorer_navigation
from app.shell.menus import MenuStubRegistry
from app.shell.project_controller import ProjectController
from app.shell.project_load_host import MainWindowProjectLoadHost
from app.shell.project_load_workflow import ProjectLoadWorkflow
from app.shell.file_dialogs import choose_existing_directory, choose_open_files
from app.shell.project_tree_controller import ProjectTreeController
from app.shell.project_tree_presenter import ProjectTreePresenter as ShellProjectTreePresenter
from app.shell.problems_controller import ProblemsController
from app.shell.python_style_workflow import PythonStyleWorkflow
from app.shell.repl_session_manager import ReplSessionManager
from app.shell.run_session_controller import RunSessionController
from app.shell.run_output_coordinator import RunOutputCoordinator
from app.shell.run_config_controller import RunConfigController
from app.shell.run_debug_presenter import RunDebugPresenter
from app.shell.runtime_support_workflow import RuntimeSupportWorkflow
from app.shell.save_workflow import SaveWorkflow
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
from app.shell.shell_theme_workflow import ShellThemeWorkflow
from app.shell.settings_apply_workflow import capture_settings_apply_baseline
from app.shell.document_safety import DocumentCloseIntent, DocumentScope
from app.shell.editor_intelligence_controller import EditorIntelligenceController
from app.shell.editor_tab_factory import EditorTabFactory
from app.shell.editor_tab_bar import MiddleClickTabBar
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator
from app.shell.editor_workspace_controller import EditorWorkspaceController
from app.shell.project_tree_action_coordinator import ProjectTreeActionCoordinator
from app.shell.diagnostics_search_coordinator import DiagnosticsOrchestrator
from app.shell.help_controller import ShellHelpController
from app.shell.main_window_layout import (
    build_layout_shell,
    configure_window_frame,
)
from app.shell.status_bar import (
    ShellStatusBarController,
    create_shell_status_bar,
    map_startup_report_to_status,
)
from app.shell.toolbar import build_run_toolbar_widget
from app.shell.toolbar_icons import icon_run
from app.shell.welcome_widget import WelcomeWidget

TREE_ROLE_ABSOLUTE_PATH = 256
TREE_ROLE_IS_DIRECTORY = 257
TREE_ROLE_RELATIVE_PATH = 258
EVENT_QUEUE_BATCH_LIMIT = 200

# Run/debug sessions write log and manifest files under cbcs/runs/ and cbcs/logs/
# every time the user starts a session. Those churn must NOT trigger the project
# reload cascade (which clears the file tree, restarts the symbol indexer, etc.),
# so they are excluded from the structure signature used by external-change polling.
PROJECT_TREE_SIGNATURE_IGNORED_PREFIXES: tuple[str, ...] = (
    f"{constants.PROJECT_META_DIRNAME}/{constants.PROJECT_RUNS_DIRNAME}/",
    f"{constants.PROJECT_META_DIRNAME}/{constants.PROJECT_LOGS_DIRNAME}/",
)


def _filter_tree_signature_entries(relative_paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        path for path in relative_paths
        if not any(path.startswith(prefix) for prefix in PROJECT_TREE_SIGNATURE_IGNORED_PREFIXES)
    )


ShellEventT = TypeVar("ShellEventT")
ReplEvent = tuple[str, object, object]


class _ConnectableSignal(Protocol):
    def connect(self, slot: Callable[..., object]) -> object:
        ...


class MainWindow(QMainWindow):
    """Top-level editor window shell with extension seams for later tasks."""

    def __init__(self, startup_report: Optional[CapabilityProbeReport] = None, state_root: str | None = None) -> None:
        super().__init__()
        _app_icon_path = str(Path(__file__).resolve().parents[2] / "app" / "ui" / "icons" / "Python_Icon.png")
        if Path(_app_icon_path).is_file():
            self.setWindowIcon(QIcon(_app_icon_path))
        self._project_placeholder_label: QLabel | None = None
        self._center_stack: QStackedWidget | None = None
        self._welcome_widget: WelcomeWidget | None = None
        self._project_tree_widget: ProjectTreeWidget | None = None
        self._explorer_new_file_btn: QToolButton | None = None
        self._explorer_new_folder_btn: QToolButton | None = None
        self._explorer_refresh_btn: QToolButton | None = None
        self._tree_file_icon = file_icon("#495057")
        self._tree_file_icon_map = file_type_icon_map()
        self._tree_filename_icon_map = filename_icon_map()
        self._tree_folder_icon = folder_icon("#3366FF")
        self._tree_folder_open_icon = folder_open_icon("#3366FF")
        self._tree_entrypoint_icon = icon_run("#16A34A")
        self._project_tree_presenter = ShellProjectTreePresenter(
            self,
            absolute_path_role=TREE_ROLE_ABSOLUTE_PATH,
            is_directory_role=TREE_ROLE_IS_DIRECTORY,
            relative_path_role=TREE_ROLE_RELATIVE_PATH,
        )
        self._editor_tabs_widget: QTabWidget | None = None
        self._editor_tabs_coordinator = EditorTabsCoordinator(self)
        self._activity_bar: ActivityBar | None = None
        self._sidebar_stack: QStackedWidget | None = None
        self._search_sidebar: SearchSidebarWidget | None = None
        self._test_explorer_panel: TestExplorerPanel | None = None
        self._quick_open_dialog: QuickOpenDialog | None = None
        self._local_history_workflow: LocalHistoryWorkflow
        self._plugin_activation_workflow: PluginActivationWorkflow
        self._debug_control_workflow: DebugControlWorkflow
        self._editor_tab_factory: EditorTabFactory
        self._save_workflow: SaveWorkflow
        self._python_style_workflow: PythonStyleWorkflow
        self._semantic_navigation_workflow: Any
        self._plugin_manager_dialog: PluginManagerDialog | None = None
        self._dependency_inspector_dialog: DependencyInspectorDialog | None = None
        self._bottom_tabs_widget: QTabWidget | None = None
        self._run_log_panel: RunLogPanel | None = None
        self._python_console_widget: PythonConsoleWidget | None = None
        self._python_console_container: QWidget | None = None
        self._debug_panel: DebugPanelWidget | None = None
        self._problems_panel: ProblemsPanel | None = None
        self._problems_tab_widget: QTabWidget | None = None
        self._problems_controller = ProblemsController(self)
        self._test_runner_workflow: TestRunnerWorkflow
        self._runtime_support_workflow: RuntimeSupportWorkflow
        self._state_root = state_root
        self._logger = get_subsystem_logger("shell")
        self._startup_capability_facade = StartupCapabilityFacade()
        self._python_tooling_status_controller = PythonToolingStatusController(
            current_project_root=self._current_project_root
        )
        self._python_console_history_path = global_python_console_history_path(self._state_root)
        self._settings_service = SettingsService(state_root=self._state_root)
        (
            self._runtime_onboarding_dismissed,
            self._runtime_onboarding_completed,
        ) = self._load_runtime_onboarding_state()
        self._stored_lint_diagnostics: dict[str, list[CodeDiagnostic]] = {}
        self._stored_runtime_problems: list[ProblemEntry] = []
        self._known_runtime_modules: frozenset[str] | None = load_cached_runtime_modules(
            state_root=self._state_root,
        )
        self._menu_registry: MenuStubRegistry | None = None
        self._command_broker = CommandBroker()
        self._action_registry: ShellActionRegistry | None = None
        self._event_bus = ShellEventBus()
        self._plugin_runtime_manager = PluginRuntimeManager(state_root=self._state_root)
        self._plugin_api_broker = PluginApiBroker(self._plugin_runtime_manager)
        self._workflow_broker = WorkflowBroker(self._plugin_api_broker)
        self._workflow_provider_catalog = WorkflowProviderCatalog([])
        self._plugin_safe_mode = self._load_plugin_safe_mode()
        self._declarative_contribution_manager = DeclarativeContributionManager(
            register_runtime_command=lambda command_id, handler, replace: self.register_runtime_command(
                command_id=command_id,
                handler=handler,
                replace=replace,
            ),
            register_runtime_menu_command=lambda **kwargs: self.register_runtime_menu_command(**kwargs),
            unregister_runtime_menu_command=self.unregister_runtime_menu_command,
            execute_runtime_command=self.execute_runtime_command,
            subscribe_shell_event=lambda event_type, handler: self.subscribe_shell_event(event_type, handler),
            unsubscribe_shell_event=lambda event_type, handler: self.unsubscribe_shell_event(event_type, handler),
            emit_message=lambda message: QMessageBox.information(self, "Plugin Command", message),
            execute_plugin_runtime_command=lambda command_id, payload, activation_event: self._plugin_api_broker.invoke_runtime_command_for_event(
                command_id,
                payload,
                activation_event=activation_event,
            ),
            on_runtime_command_success=self._clear_plugin_runtime_failure,
            on_runtime_command_failure=self._record_plugin_runtime_failure,
        )
        self._status_controller: ShellStatusBarController | None = None
        self._startup_report: CapabilityProbeReport | None = startup_report
        self._toolbar = None
        self._top_splitter: QSplitter | None = None
        self._vertical_splitter: QSplitter | None = None
        self._close_tab_shortcut: QShortcut | None = None
        self._keep_preview_open_shortcut: QShortcut | None = None
        self._theme_mode: str = constants.UI_THEME_MODE_DEFAULT
        self._ui_font_weight: str = constants.UI_THEME_FONT_WEIGHT_DEFAULT
        self._dark_chrome_palette: str = constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT
        self._loaded_project: LoadedProject | None = None
        self._plugin_activation_workflow = PluginActivationWorkflow(
            state_root=self._state_root,
            project_root_provider=lambda: None
            if self._loaded_project is None
            else self._loaded_project.project_root,
            safe_mode_enabled=lambda: self._plugin_safe_mode,
            contribution_manager=self._declarative_contribution_manager,
            runtime_manager=self._plugin_runtime_manager,
            plugin_api_broker=self._plugin_api_broker,
            workflow_broker=self._workflow_broker,
            on_catalog_changed=lambda catalog: setattr(self, "_workflow_provider_catalog", catalog),
        )
        self._project_tree_structure_signature: tuple[str, ...] | None = None
        self._workspace_controller = EditorWorkspaceController()
        self._editor_manager = EditorManager()
        self._editor_widgets_by_path = self._workspace_controller.editor_widgets_by_path
        self._markdown_panes_by_path: dict[str, MarkdownEditorPane] = {}
        self._editor_tab_factory = EditorTabFactory(self)
        self._indent_source_by_path: dict[str, tuple[str, int, str]] = {}
        self._debug_exception_policy = DebugExceptionPolicy()
        self._tree_clipboard_paths: list[str] = []
        self._tree_clipboard_cut: bool = False
        self._import_update_policy = self._load_import_update_policy()
        (
            self._editor_tab_width,
            self._editor_font_size,
            self._editor_font_family,
            self._editor_indent_style,
            self._editor_indent_size,
            self._editor_detect_indentation_from_file,
            self._editor_format_on_save,
            self._editor_organize_imports_on_save,
            self._editor_trim_trailing_whitespace_on_save,
            self._editor_insert_final_newline_on_save,
            self._editor_enable_preview,
            self._editor_auto_save,
            self._editor_exit_behavior,
            self._editor_hover_tooltip_enabled,
            self._editor_auto_reindent_flat_python_paste,
        ) = self._load_editor_preferences()
        self._pending_project_tree_preview_path: str | None = None
        self._project_tree_preview_click_timer = QTimer(self)
        self._project_tree_preview_click_timer.setSingleShot(True)
        self._project_tree_preview_click_timer.setInterval(175)
        self._project_tree_preview_click_timer.timeout.connect(self._open_pending_project_tree_preview)
        self._zoom_delta: int = 0
        (
            self._completion_enabled,
            self._completion_auto_trigger,
            self._completion_min_chars,
        ) = self._load_completion_preferences()
        self._reported_completion_degradation_reasons: set[str] = set()
        (
            self._diagnostics_enabled,
            self._diagnostics_realtime,
            self._quick_fixes_enabled,
            self._quick_fix_require_preview_for_multifile,
        ) = self._load_diagnostics_preferences()
        (
            self._auto_open_console_on_run_output,
            self._auto_open_problems_on_run_failure,
        ) = self._load_output_preferences()
        self._intelligence_runtime_settings = self._load_intelligence_runtime_settings()
        self._local_history_retention_policy = self._load_local_history_retention_policy()
        self._theme_mode = ShellThemeWorkflow.load_theme_mode(self._settings_service)
        self._ui_font_weight = ShellThemeWorkflow.load_ui_font_weight(self._settings_service)
        self._dark_chrome_palette = ShellThemeWorkflow.load_dark_chrome_palette(self._settings_service)
        self._shortcut_overrides = self._load_shortcut_overrides()
        self._effective_shortcuts = build_effective_shortcut_map(self._shortcut_overrides)
        self._syntax_color_overrides = ShellThemeWorkflow.load_syntax_color_overrides(self._settings_service)
        self._lint_rule_overrides = self._load_lint_rule_overrides()
        self._selected_linter = self._load_selected_linter()
        self._symbol_cache_db_path = str(global_cache_dir(self._state_root) / "symbols.sqlite3")
        local_history_store = LocalHistoryStore(
            state_root=self._state_root,
            retention_policy=self._local_history_retention_policy,
        )
        autosave_store = AutosaveStore(
            state_root=self._state_root,
            history_store=local_history_store,
        )
        self._save_workflow = SaveWorkflow(self)
        self._python_style_workflow = PythonStyleWorkflow(self)
        self._auto_save_to_file_timer = QTimer(self)
        self._auto_save_to_file_timer.setSingleShot(True)
        self._auto_save_to_file_timer.setInterval(1000)
        self._auto_save_to_file_timer.timeout.connect(self._save_workflow.flush_auto_save_to_file)
        self._pending_realtime_lint_file_path: str | None = None
        self._realtime_lint_timer = QTimer(self)
        self._realtime_lint_timer.setSingleShot(True)
        self._realtime_lint_timer.setInterval(300)
        self._outline_panel: OutlinePanel | None = None
        self._explorer_splitter: QSplitter | None = None
        self._outline_symbols_by_path: dict[str, tuple[OutlineSymbol, ...]] = {}
        self._outline_refresh_timer = QTimer(self)
        self._outline_refresh_timer.setSingleShot(True)
        self._outline_refresh_timer.setInterval(300)
        self._outline_refresh_timer.timeout.connect(self._refresh_outline_for_active_tab)
        self._outline_collapsed: bool = DEFAULT_OUTLINE_COLLAPSED
        self._outline_follow_cursor: bool = DEFAULT_OUTLINE_FOLLOW_CURSOR
        self._outline_sort_mode: str = DEFAULT_OUTLINE_SORT_MODE
        self._console_model = ConsoleModel()
        self._run_event_queue: queue.Queue[ProcessEvent] = queue.Queue()
        self._active_run_output_tail = OutputTailBuffer(max_chars=300_000, max_chunks=6_000)
        self._active_transient_entry_file_path: str | None = None
        self._debug_session = DebugSession()
        self._debug_execution_editor: CodeEditorWidget | None = None
        self._active_symbol_index_worker: SymbolIndexWorker | None = None
        self._is_shutting_down = False
        self._suppress_tree_reveal = False
        self._symbol_index_generation = 0
        self._latest_health_report: ProjectHealthReport | None = None
        self._latest_import_issue_report = RuntimeIssueReport(workflow="import", issues=[])
        self._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=[])
        self._latest_package_issue_report = RuntimeIssueReport(workflow="package", issues=[])
        self._latest_run_issue_ids: tuple[str, ...] = ()
        self._latest_runtime_issue_report: RuntimeIssueReport = self._build_runtime_issue_report()
        self._run_output_coordinator: RunOutputCoordinator | None = None
        self._run_service = RunService(on_event=self._enqueue_run_event, state_root=self._state_root)
        self._run_session_controller = RunSessionController(self._run_service)
        self._run_debug_presenter = RunDebugPresenter(self)
        self._run_config_controller = RunConfigController()
        self._debug_control_workflow = DebugControlWorkflow(self)
        self._active_named_run_config_name: str | None = None
        self._repl_event_queue: queue.Queue[ReplEvent] = queue.Queue()
        self._repl_manager = ReplSessionManager(
            on_output=self._enqueue_repl_output,
            on_session_ended=self._enqueue_repl_ended,
            on_session_started=self._enqueue_repl_started,
            state_root=self._state_root,
        )
        self._runtime_introspection_coordinator = RuntimeIntrospectionCoordinator(
            runner_port=self._repl_manager,
        )
        self._template_service = TemplateService()
        register_builtin_workflow_providers(
            self._workflow_broker,
            template_service=self._template_service,
        )
        self._example_project_service = ExampleProjectService()
        self._main_thread_dispatcher = MainThreadDispatcher(self)
        self._semantic_session = SemanticSession(
            dispatch_to_main_thread=self._dispatch_to_main_thread,
            cache_db_path=self._symbol_cache_db_path,
            state_root=self._state_root,
        )
        self._intelligence_controller = EditorIntelligenceController(
            semantic_session=self._semantic_session,
        )
        self._background_tasks = GeneralTaskScheduler(
            dispatch_to_main_thread=self._dispatch_to_main_thread
        )
        self._runtime_support_workflow = RuntimeSupportWorkflow(
            parent=self,
            state_root=self._state_root,
            background_tasks=self._background_tasks,
            workflow_broker=self._workflow_broker,
            loaded_project=lambda: self._loaded_project,
            startup_report=lambda: self._startup_report,
            latest_health_report=lambda: self._latest_health_report,
            set_latest_health_report=lambda report: setattr(self, "_latest_health_report", report),
            latest_import_issue_report=lambda: self._latest_import_issue_report,
            latest_run_issue_report=lambda: self._latest_run_issue_report,
            latest_package_issue_report=lambda: self._latest_package_issue_report,
            set_latest_package_issue_report=lambda report: setattr(self, "_latest_package_issue_report", report),
            set_latest_runtime_issue_report=lambda report: setattr(self, "_latest_runtime_issue_report", report),
            build_runtime_issue_report=self._build_runtime_issue_report,
            open_runtime_center_dialog=lambda **kwargs: self._open_runtime_center_dialog(**kwargs),
            active_run_session_log_path=lambda: self._run_session_controller.session_store.log_path,
            known_runtime_modules=lambda: self._known_runtime_modules,
        )
        self._local_history_workflow = LocalHistoryWorkflow(
            parent=self,
            local_history_store=local_history_store,
            autosave_store=autosave_store,
            loaded_project=lambda: self._loaded_project,
            editor_manager=self._editor_manager,
            editor_widget_for_path=self._workspace_controller.widget_for_path,
            open_file_in_editor=lambda file_path: self._editor_tab_factory.open_file_in_editor(file_path, preview=False),
            open_restored_history_buffer=self._editor_tab_factory.open_restored_history_buffer,
            apply_text_to_open_tab=self._apply_text_to_open_tab,
            tab_index_for_path=self._tab_index_for_path,
            refresh_tab_presentation=self._refresh_tab_presentation,
            set_current_tab_index=lambda tab_index: self._editor_tabs_widget.setCurrentIndex(tab_index)
            if self._editor_tabs_widget is not None
            else None,
            show_status_message=lambda message, timeout: self.statusBar().showMessage(message, timeout),
            logger=self._logger,
            background_tasks=self._background_tasks,
            retention_policy=self._local_history_retention_policy,
            ensure_breakpoint_spec=self._debug_control_workflow.ensure_breakpoint_spec,
            breakpoint_store=self._debug_control_workflow.breakpoint_store,
            refresh_breakpoints_list=self._debug_control_workflow.refresh_breakpoints_list,
            capture_tree_state=lambda: self._get_project_tree_presenter().capture_full_state(),
            restore_tree_state=lambda tree_state: self._get_project_tree_presenter().restore_full_state(tree_state),
            reveal_tree_path=lambda file_path: self._get_project_tree_presenter().reveal_path(file_path),
            set_tree_reveal_suppressed=lambda suppressed: setattr(self, "_suppress_tree_reveal", suppressed),
        )
        self._diagnostics_orchestrator = DiagnosticsOrchestrator(
            diagnostics_enabled=lambda: self._diagnostics_enabled,
            diagnostics_realtime=lambda: self._diagnostics_realtime,
            set_pending_realtime_file_path=lambda file_path: setattr(
                self, "_pending_realtime_lint_file_path", file_path
            ),
            get_pending_realtime_file_path=lambda: self._pending_realtime_lint_file_path,
            start_realtime_timer=self._realtime_lint_timer.start,
            get_active_tab_file_path=self._editor_manager.active_file_path,
            render_lint_for_file=lambda file_path, trigger: self._render_lint_diagnostics_for_file(
                file_path,
                trigger=trigger,
            ),
            get_open_editor_paths=self._workspace_controller.open_editor_paths,
            render_merged_problems_panel=self._render_merged_problems_panel,
            set_known_runtime_modules=lambda modules: setattr(self, "_known_runtime_modules", modules),
            run_background_task=self._background_tasks.run,
            state_root=lambda: self._state_root,
            logger=self._logger,
            show_runtime_probe_warning=lambda message: QMessageBox.warning(
                self,
                "Refresh Runtime Modules",
                message,
            ),
        )
        self._realtime_lint_timer.timeout.connect(
            build_realtime_lint_runner(
                is_shutting_down=lambda: self._is_shutting_down,
                orchestrator=self._diagnostics_orchestrator,
            )
        )
        self._project_controller = ProjectController(
            state_root=self._state_root,
            logger=self._logger,
            dispatch_to_main_thread=self._dispatch_to_main_thread,
        )
        self._project_load_workflow = ProjectLoadWorkflow(MainWindowProjectLoadHost(self))
        self._project_tree_controller: ProjectTreeController[CodeEditorWidget] = ProjectTreeController()
        self._project_tree_action_coordinator = ProjectTreeActionCoordinator(
            project_tree_controller=self._project_tree_controller,
            editor_widgets_by_path=self._editor_widgets_by_path,
            tab_index_for_path=self._tab_index_for_path,
            remove_tab_at_index=lambda tab_index: self._editor_tabs_widget.removeTab(tab_index)
            if self._editor_tabs_widget is not None
            else None,
            release_editor_widget=self._release_editor_widget,
            close_editor_file=self._editor_manager.close_file,
            breakpoint_store=self._debug_control_workflow.breakpoint_store,
            refresh_breakpoints_list=self._debug_control_workflow.refresh_breakpoints_list,
            remap_editor_paths=self._editor_manager.remap_paths_for_move,
            update_tab_path_and_name=self._update_tab_path_and_name,
            apply_breakpoints_to_widget=lambda widget, breakpoints: widget.set_breakpoints(breakpoints),
            update_widget_language=self._update_widget_language_for_path,
            maybe_rewrite_imports=self._maybe_rewrite_imports_for_move,
            reload_project=self._refresh_project_tree_from_disk,
            record_deleted_path=self._local_history_workflow.record_deleted_path,
            remap_file_lineage=self._local_history_workflow.remap_file_lineage,
        )
        self._project_tree_action_workflow = build_project_tree_action_workflow(self)
        self._external_file_change_workflow = build_external_file_change_workflow(self)
        self._settings_apply_workflow = build_settings_apply_workflow(self)
        self._python_console_workflow = build_python_console_workflow(self)
        self._find_replace_workflow = build_find_replace_workflow(self)
        self._semantic_navigation_workflow = build_semantic_navigation_workflow(self)
        self._shell_theme_workflow = build_shell_theme_workflow(self)
        self._help_controller = ShellHelpController(
            state_root=self._state_root,
            resolve_theme_tokens=self._shell_theme_workflow.resolve_theme_tokens,
            reveal_path_in_file_manager=self._reveal_path_in_file_manager,
            get_effective_shortcuts=lambda: self._effective_shortcuts,
        )

        self._configure_window_frame()
        self._build_layout_shell()
        self._run_launch_workflow = build_run_launch_workflow(self)

        def active_test_editor() -> ActiveTestEditor | None:
            active_tab = self._editor_manager.active_tab()
            editor_widget = self._active_editor_widget()
            if active_tab is None or editor_widget is None:
                return None
            return ActiveTestEditor(
                file_path=active_tab.file_path,
                source_text=active_tab.current_content,
                cursor_line=editor_widget.textCursor().blockNumber() + 1,
            )

        self._test_runner_workflow = TestRunnerWorkflow(
            loaded_project_provider=lambda: self._loaded_project,
            active_editor_provider=active_test_editor,
            workflow_broker=self._workflow_broker,
            background_tasks=self._background_tasks,
            test_explorer_panel=self._test_explorer_panel,
            run_pytest_with_workflow=run_pytest_with_workflow,
            start_debug_session=self._run_launch_workflow.start_session,
            build_debug_breakpoints=self._debug_control_workflow.build_debug_breakpoints_for_launch,
            debug_exception_policy_provider=lambda: self._debug_exception_policy,
            append_console_line=lambda text, stream: self._append_console_line(text, stream=stream),
            set_problems=self._set_problems,
            focus_run_log_tab=self._focus_run_log_tab,
            focus_problems_tab=self._focus_problems_tab,
            show_warning=lambda title, message: QMessageBox.warning(self, title, message),
            show_information=lambda title, message: QMessageBox.information(self, title, message),
            record_debug_target=self._run_launch_workflow.record_debug_target_from_dict,
            auto_open_console_on_output=lambda: self._auto_open_console_on_run_output,
            auto_open_problems_on_failure=lambda: self._auto_open_problems_on_run_failure,
            logger=self._logger,
        )

        connect_test_explorer_navigation(self)
        self._configure_close_tab_shortcut()
        self._configure_keep_preview_open_shortcut()
        self._menu_registry = build_main_window_menus(self, shortcut_overrides=self._effective_shortcuts)
        if self._menu_registry is not None:
            self._action_registry = ShellActionRegistry(
                menu_registry=self._menu_registry,
                command_broker=self._command_broker,
            )
        self._status_controller = create_shell_status_bar(
            self,
            startup_report=startup_report,
            on_startup_activated=self._handle_runtime_center_action,
        )
        self._run_launch_workflow.install_active_run_config_indicator()
        self._refresh_python_tooling_status()
        self._toolbar = build_run_toolbar_widget(self._menu_registry)
        if self._toolbar is not None:
            center_panel = self.findChild(QWidget, "shell.centerPanel")
            if center_panel is not None:
                center_layout = center_panel.layout()
                if isinstance(center_layout, QVBoxLayout):
                    center_layout.insertWidget(0, self._toolbar, 0)
        self._shell_theme_workflow.apply_theme_styles()
        self._apply_runtime_intelligence_preferences_to_open_editors()
        self._sync_theme_menu_check_state()
        self._sync_auto_save_menu_state()
        self._restore_layout_from_settings()
        self._refresh_open_recent_menu()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        self._refresh_markdown_action_states()
        self._test_runner_workflow.refresh_discovery()
        self._plugin_activation_workflow.reload()
        self._run_event_timer = QTimer(self)
        self._run_event_timer.setInterval(50)
        self._run_event_timer.timeout.connect(self._process_queued_run_events)
        self._run_event_timer.start()
        self._repl_event_timer = QTimer(self)
        self._repl_event_timer.setInterval(50)
        self._repl_event_timer.timeout.connect(self._process_queued_repl_events)
        self._repl_event_timer.start()
        self._external_change_poll_timer = QTimer(self)
        self._external_change_poll_timer.setInterval(1000)
        self._external_change_poll_timer.timeout.connect(self._poll_external_file_changes)
        self._external_change_poll_timer.start()
        self._restore_project_timer = QTimer(self)
        self._restore_project_timer.setSingleShot(True)
        self._restore_project_timer.timeout.connect(self._try_restore_last_project)
        self._restore_project_timer.start(0)
        self._auto_start_repl_timer = QTimer(self)
        self._auto_start_repl_timer.setSingleShot(True)
        self._auto_start_repl_timer.timeout.connect(self._auto_start_repl)
        self._auto_start_repl_timer.start(100)
        self._runtime_probe_timer = QTimer(self)
        self._runtime_probe_timer.setSingleShot(True)
        self._runtime_probe_timer.timeout.connect(self._start_runtime_module_probe)
        self._runtime_probe_timer.start(200)
        self._startup_probe_refresh_timer = QTimer(self)
        self._startup_probe_refresh_timer.setSingleShot(True)
        self._startup_probe_refresh_timer.timeout.connect(self._refresh_startup_capability_report_async)
        self._startup_probe_refresh_timer.start(0)
        self._startup_capability_facade.set_refresh_callback(self._handle_startup_report_refresh)

    def _try_restore_last_project(self) -> None:
        """Attempt to reopen the last project from the previous session.

        Accepts both canonical projects (with ``cbcs/project.json``) and
        importable roots so users who never explicitly initialized a
        project still get the same auto-reopen behavior they had before.
        """
        if self._is_shutting_down or self._loaded_project is not None:
            return
        try:
            settings = self._settings_service.load_global()
        except Exception as exc:
            self._logger.debug("Skipped last-project restore; global settings failed to load: %s", exc)
            return
        last_path = settings.get(constants.LAST_PROJECT_PATH_KEY)
        if not isinstance(last_path, str) or not last_path.strip():
            return
        project_root = Path(last_path.strip())
        if not project_root.is_dir():
            return
        try:
            assessment = assess_project_root(project_root)
        except Exception as exc:
            self._logger.debug("Skipped last-project restore; project assessment failed for %s: %s", project_root, exc)
            return
        if assessment.state not in (ProjectRootState.CANONICAL, ProjectRootState.IMPORTABLE):
            return
        self._open_project_by_path(str(project_root))

    def set_startup_report(self, report: Optional[CapabilityProbeReport]) -> None:
        """Extension seam for startup status refresh from bootstrap updates."""
        self._startup_report = report
        self._latest_runtime_issue_report = self._build_runtime_issue_report()
        self._refresh_welcome_project_list()
        if self._status_controller is None:
            return
        self._status_controller.set_startup_report(report)

    def _refresh_startup_capability_report_async(self) -> None:
        def task(cancel_event):  # type: ignore[no-untyped-def]
            report = self._startup_capability_facade.refresh_report()
            if cancel_event.is_set():
                return None
            return report

        def on_success(report: object) -> None:
            if not isinstance(report, CapabilityProbeReport):
                return
            self.set_startup_report(report)

        def on_error(exc: Exception) -> None:
            self._logger.warning("Deferred startup capability probe failed: %s", exc)

        self._background_tasks.run(
            key="startup_capability_refresh",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_startup_report_refresh(self, report: CapabilityProbeReport) -> None:
        self._dispatch_to_main_thread(lambda: self.set_startup_report(report))

    def _build_runtime_issue_report(self) -> RuntimeIssueReport:
        reports: list[RuntimeIssueReport] = []
        startup_issues = (
            build_startup_issue_report(self._startup_report)
            if self._startup_report is not None
            else RuntimeIssueReport(workflow="startup", issues=[])
        )
        reports.append(startup_issues)
        if self._latest_health_report is not None:
            reports.append(build_project_health_issue_report(self._latest_health_report))
        if self._latest_import_issue_report.issues:
            reports.append(self._latest_import_issue_report)
        if self._latest_run_issue_report.issues:
            reports.append(self._latest_run_issue_report)
        if self._latest_package_issue_report.issues:
            reports.append(self._latest_package_issue_report)
        return merge_runtime_issue_reports(*reports, workflow="runtime_center")

    def _open_runtime_help_topic(self, topic_id: str) -> None:
        if topic_id == HELP_TOPIC_HEADLESS_NOTES:
            self._help_controller.show_headless_notes(parent=self)
            return
        if topic_id == "packaging_backup":
            self._help_controller.show_packaging_backup(parent=self)
            return
        if topic_id == HELP_TOPIC_GETTING_STARTED:
            self._help_controller.show_getting_started(parent=self)
            return
        self._help_controller.show_getting_started(parent=self)

    def _open_runtime_center_dialog(
        self,
        *,
        title: str = "Runtime Center",
        report: RuntimeIssueReport | None = None,
    ) -> None:
        dialog = RuntimeCenterDialog(
            title=title,
            report=report or self._latest_runtime_issue_report,
            tokens=self._shell_theme_workflow.resolve_theme_tokens(),
            open_help_topic=self._open_runtime_help_topic,
            parent=self,
        )
        dialog.exec_()

    def _handle_runtime_center_action(self) -> None:
        self._latest_runtime_issue_report = self._build_runtime_issue_report()
        self._open_runtime_center_dialog()

    def _load_runtime_onboarding_state(self) -> tuple[bool, bool]:
        try:
            settings_payload = self._settings_service.load_global()
        except Exception as exc:
            self._logger.debug("Runtime onboarding state unavailable; using defaults: %s", exc)
            return False, False
        onboarding_payload = settings_payload.get(constants.UI_ONBOARDING_SETTINGS_KEY)
        if not isinstance(onboarding_payload, Mapping):
            return False, False
        return (
            bool(onboarding_payload.get(constants.UI_ONBOARDING_RUNTIME_GUIDE_DISMISSED_KEY, False)),
            bool(onboarding_payload.get(constants.UI_ONBOARDING_RUNTIME_GUIDE_COMPLETED_KEY, False)),
        )

    def _persist_runtime_onboarding_state(self, *, dismissed: bool | None = None, completed: bool | None = None) -> None:
        if dismissed is not None:
            self._runtime_onboarding_dismissed = dismissed
        if completed is not None:
            self._runtime_onboarding_completed = completed
        try:
            self._settings_service.update_global(
                lambda settings: self._merge_runtime_onboarding_settings(
                    settings,
                    dismissed=self._runtime_onboarding_dismissed,
                    completed=self._runtime_onboarding_completed,
                )
            )
        except Exception as exc:
            self._logger.warning("Failed to persist runtime onboarding state: %s", exc)
        self._refresh_welcome_project_list()

    def _merge_runtime_onboarding_settings(
        self,
        settings: Mapping[str, Any],
        *,
        dismissed: bool,
        completed: bool,
    ) -> dict[str, Any]:
        updated = dict(settings)
        existing = settings.get(constants.UI_ONBOARDING_SETTINGS_KEY)
        onboarding_payload = dict(existing) if isinstance(existing, Mapping) else {}
        onboarding_payload[constants.UI_ONBOARDING_RUNTIME_GUIDE_DISMISSED_KEY] = dismissed
        onboarding_payload[constants.UI_ONBOARDING_RUNTIME_GUIDE_COMPLETED_KEY] = completed
        updated[constants.UI_ONBOARDING_SETTINGS_KEY] = onboarding_payload
        return updated

    def _refresh_welcome_widget_state(
        self,
        widget: WelcomeWidget,
        *,
        force_show_onboarding: bool = False,
    ) -> None:
        try:
            recent_paths = load_recent_projects(state_root=self._state_root)
        except Exception as exc:
            self._logger.debug("Recent projects unavailable for welcome widget: %s", exc)
            recent_paths = []
        widget.set_recent_projects(recent_paths)
        startup_status = map_startup_report_to_status(self._startup_report)
        widget.set_runtime_summary(startup_status.text, startup_status.details)
        widget.set_project_health_available(self._loaded_project is not None)
        widget.set_onboarding_visible(force_show_onboarding)

    def _connect_welcome_widget_actions(
        self,
        widget: WelcomeWidget,
        *,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        widget.new_project_requested.connect(
            lambda: self._invoke_welcome_action(self._handle_new_project_action, close_after_action)
        )
        widget.open_project_requested.connect(
            lambda: self._invoke_welcome_action(self._handle_open_project_action, close_after_action)
        )
        widget.project_selected.connect(
            lambda project_path: self._handle_welcome_project_selected(project_path, close_after_action)
        )
        widget.runtime_center_requested.connect(
            lambda: self._invoke_welcome_action(self._handle_runtime_center_action, close_after_action)
        )
        widget.getting_started_requested.connect(
            lambda: self._invoke_welcome_action(self._handle_getting_started_action, close_after_action)
        )
        widget.project_health_requested.connect(
            lambda: self._invoke_welcome_action(
                self._runtime_support_workflow.handle_project_health_check_action,
                close_after_action,
            )
        )
        widget.example_project_requested.connect(
            lambda: self._invoke_welcome_action(self._handle_load_example_project_action, close_after_action)
        )
        widget.headless_notes_requested.connect(
            lambda: self._invoke_welcome_action(
                lambda: self._help_controller.show_headless_notes(parent=self),
                close_after_action,
            )
        )
        widget.dismiss_onboarding_requested.connect(
            lambda: self._handle_runtime_onboarding_dismiss_action(close_after_action=close_after_action)
        )
        widget.complete_onboarding_requested.connect(
            lambda: self._handle_runtime_onboarding_complete_action(close_after_action=close_after_action)
        )

    def _invoke_welcome_action(
        self,
        action: Callable[[], None],
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        if close_after_action is not None:
            close_after_action()
        action()

    def _handle_welcome_project_selected(
        self,
        project_path: str,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        opened = self._open_project_by_path(project_path)
        if opened and close_after_action is not None:
            close_after_action()

    def _handle_runtime_onboarding_dismiss_action(
        self,
        *,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        self._persist_runtime_onboarding_state(dismissed=True, completed=False)
        if close_after_action is not None:
            close_after_action()

    def _handle_runtime_onboarding_complete_action(
        self,
        *,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        self._persist_runtime_onboarding_state(dismissed=False, completed=True)
        if close_after_action is not None:
            close_after_action()

    def _handle_runtime_onboarding_action(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("shell.runtimeOnboardingDialog")
        dialog.setWindowTitle("Runtime Onboarding")
        dialog.resize(760, 720)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        onboarding_widget = WelcomeWidget(dialog)
        self._connect_welcome_widget_actions(onboarding_widget, close_after_action=dialog.accept)
        self._refresh_welcome_widget_state(onboarding_widget, force_show_onboarding=True)
        layout.addWidget(onboarding_widget)
        dialog.exec_()

    def set_project_placeholder(self, project_text: str) -> None:
        """Extension seam for T09/T10 project-shell wiring."""
        if self._project_placeholder_label is not None:
            self._project_placeholder_label.setText(project_text)
        if self._status_controller is not None:
            status_text = f"Project: {project_text}"
            loaded_project = self._loaded_project
            if loaded_project is not None:
                try:
                    project_settings_payload = self._settings_service.load_project(loaded_project.project_root)
                    if project_settings_has_overrides(project_settings_payload):
                        status_text = f"{status_text} (project overrides)"
                except Exception as exc:
                    self._logger.warning(
                        "Unable to evaluate project settings override state for %s: %s",
                        loaded_project.project_root,
                        exc,
                    )
            self._status_controller.set_project_state_text(status_text)

    def _restore_layout_from_settings(self) -> None:
        settings_payload = self._settings_service.load_global()
        layout_state = parse_shell_layout_state(settings_payload)
        self.resize(layout_state.width, layout_state.height)
        if self._top_splitter is not None:
            self._top_splitter.setSizes(list(layout_state.top_splitter_sizes))
        if self._vertical_splitter is not None:
            self._vertical_splitter.setSizes(list(layout_state.vertical_splitter_sizes))
        if self._explorer_splitter is not None:
            explorer_sizes = layout_state.explorer_splitter_sizes or DEFAULT_EXPLORER_SPLITTER_SIZES
            self._explorer_splitter.setSizes(list(explorer_sizes))
        self._outline_collapsed = bool(layout_state.outline_collapsed)
        self._outline_follow_cursor = bool(layout_state.outline_follow_cursor)
        self._outline_sort_mode = layout_state.outline_sort_mode
        self._apply_outline_layout_state()

    def _persist_layout_to_settings(self) -> None:
        top_sizes = tuple(self._top_splitter.sizes()) if self._top_splitter is not None else DEFAULT_TOP_SPLITTER_SIZES
        vertical_sizes = (
            tuple(self._vertical_splitter.sizes())
            if self._vertical_splitter is not None
            else DEFAULT_VERTICAL_SPLITTER_SIZES
        )
        if len(top_sizes) != 2:
            top_sizes = DEFAULT_TOP_SPLITTER_SIZES
        if len(vertical_sizes) != 2:
            vertical_sizes = DEFAULT_VERTICAL_SPLITTER_SIZES
        explorer_sizes_tuple: tuple[int, int] | None = None
        if self._explorer_splitter is not None:
            raw_explorer = tuple(self._explorer_splitter.sizes())
            if len(raw_explorer) == 2:
                explorer_sizes_tuple = (int(raw_explorer[0]), int(raw_explorer[1]))

        layout_state = ShellLayoutState(
            width=self.width(),
            height=self.height(),
            top_splitter_sizes=(int(top_sizes[0]), int(top_sizes[1])),
            vertical_splitter_sizes=(int(vertical_sizes[0]), int(vertical_sizes[1])),
            explorer_splitter_sizes=explorer_sizes_tuple,
            outline_collapsed=bool(self._outline_collapsed),
            outline_follow_cursor=bool(self._outline_follow_cursor),
            outline_sort_mode=self._outline_sort_mode,
        )
        self._settings_service.update_global(
            lambda settings_payload: merge_layout_into_settings(settings_payload, layout_state)
        )

    def _handle_reset_layout_action(self) -> None:
        self.resize(ShellLayoutState().width, ShellLayoutState().height)
        if self._top_splitter is not None:
            self._top_splitter.setSizes(list(DEFAULT_TOP_SPLITTER_SIZES))
        if self._vertical_splitter is not None:
            self._vertical_splitter.setSizes(list(DEFAULT_VERTICAL_SPLITTER_SIZES))
        if self._explorer_splitter is not None:
            self._explorer_splitter.setSizes(list(DEFAULT_EXPLORER_SPLITTER_SIZES))
        self._outline_collapsed = DEFAULT_OUTLINE_COLLAPSED
        self._outline_follow_cursor = DEFAULT_OUTLINE_FOLLOW_CURSOR
        self._outline_sort_mode = DEFAULT_OUTLINE_SORT_MODE
        self._apply_outline_layout_state()
        self._persist_layout_to_settings()

    def _apply_outline_layout_state(self) -> None:
        if self._outline_panel is None:
            return
        self._outline_panel.set_follow_cursor(self._outline_follow_cursor)
        self._outline_panel.set_sort_mode(self._outline_sort_mode)
        self._outline_panel.set_collapsed(self._outline_collapsed)
        self._apply_explorer_splitter_handle_state()

    def _apply_explorer_splitter_handle_state(self) -> None:
        """Disable the explorer splitter handle when the outline is collapsed.

        The collapsed outline is a fixed-height strip; letting the handle stay
        active invites the user to drag a divider that has nothing to give.
        """
        if self._explorer_splitter is None:
            return
        collapsed = bool(self._outline_collapsed)
        self._explorer_splitter.setHandleWidth(0 if collapsed else 1)
        handle = self._explorer_splitter.handle(1)
        if handle is not None:
            handle.setEnabled(not collapsed)

    def _handle_outline_collapsed_changed(self, collapsed: bool) -> None:
        if bool(collapsed) == self._outline_collapsed:
            return
        self._outline_collapsed = bool(collapsed)
        self._apply_explorer_splitter_handle_state()
        self._persist_layout_to_settings()

    def _handle_outline_follow_cursor_changed(self, follow: bool) -> None:
        if bool(follow) == self._outline_follow_cursor:
            return
        self._outline_follow_cursor = bool(follow)
        self._persist_layout_to_settings()
        if follow:
            self._refresh_outline_for_active_tab()

    def _handle_outline_sort_mode_changed(self, mode: str) -> None:
        if not isinstance(mode, str) or mode == self._outline_sort_mode:
            return
        self._outline_sort_mode = mode
        self._persist_layout_to_settings()

    def _handle_outline_hide_requested(self) -> None:
        if self._outline_panel is None:
            return
        if not self._outline_collapsed:
            self._outline_panel.set_collapsed(True)

    def _load_import_update_policy(self) -> ImportUpdatePolicy:
        settings_payload = self._settings_service.load_global()
        raw_value = settings_payload.get(constants.UI_IMPORT_UPDATE_POLICY_KEY, constants.UI_IMPORT_UPDATE_POLICY_DEFAULT)
        try:
            return ImportUpdatePolicy(str(raw_value))
        except ValueError:
            return ImportUpdatePolicy.ASK

    def current_theme_tokens(self) -> ShellThemeTokens:
        """Public accessor used by child dialogs to inherit shell theming."""
        return self._shell_theme_workflow.resolve_theme_tokens()

    def _load_shortcut_overrides(self) -> dict[str, str]:
        settings_payload = self._settings_service.load_global()
        snapshot = parse_editor_settings_snapshot(settings_payload)
        return dict(snapshot.shortcut_overrides)

    def _load_lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        snapshot = self._load_effective_editor_settings_snapshot()
        return {code: dict(value) for code, value in snapshot.lint_rule_overrides.items()}

    def _load_selected_linter(self) -> str:
        return self._load_effective_editor_settings_snapshot().selected_linter

    def _configure_close_tab_shortcut(self) -> None:
        if self._close_tab_shortcut is None:
            self._close_tab_shortcut = QShortcut(QKeySequence(), self)
            self._close_tab_shortcut.activated.connect(self._close_active_tab)
        close_tab_sequence = self._effective_shortcuts.get(close_tab_shortcut_id(), "")
        self._close_tab_shortcut.setKey(QKeySequence(close_tab_sequence))

    def _configure_keep_preview_open_shortcut(self) -> None:
        if self._keep_preview_open_shortcut is None:
            self._keep_preview_open_shortcut = QShortcut(QKeySequence(), self)
            self._keep_preview_open_shortcut.activated.connect(self._handle_keep_preview_open_shortcut)
        keep_open_sequence = self._effective_shortcuts.get(keep_preview_open_shortcut_id(), "")
        self._keep_preview_open_shortcut.setKey(QKeySequence(keep_open_sequence))

    def _apply_shortcut_overrides_runtime(self) -> None:
        self._effective_shortcuts = build_effective_shortcut_map(self._shortcut_overrides)
        if self._menu_registry is not None:
            for action_id, action in self._menu_registry.actions.items():
                if action is None:
                    continue
                action.setShortcut(QKeySequence(self._effective_shortcuts.get(action_id, "")))
        self._configure_close_tab_shortcut()
        self._configure_keep_preview_open_shortcut()

    def _persist_theme_mode(self, mode: str) -> None:
        self._settings_service.update_global(
            lambda settings_payload: merge_theme_mode(settings_payload, mode)
        )

    def _handle_set_theme(self, mode: str) -> None:
        if mode == self._theme_mode:
            return
        self._theme_mode = mode
        self._shell_theme_workflow.invalidate_system_dark_theme_preference()
        self._persist_theme_mode(mode)
        if self._quick_open_dialog is not None:
            self._quick_open_dialog.deleteLater()
            self._quick_open_dialog = None
        self._shell_theme_workflow.apply_theme_styles()
        self._sync_theme_menu_check_state()
        self._logger.info("Theme mode changed to %s.", mode)

    def _sync_theme_menu_check_state(self) -> None:
        if self._menu_registry is None:
            return
        _mode_to_action_id = {
            constants.UI_THEME_MODE_SYSTEM: "shell.action.view.theme.system",
            constants.UI_THEME_MODE_LIGHT: "shell.action.view.theme.light",
            constants.UI_THEME_MODE_DARK: "shell.action.view.theme.dark",
            constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT: "shell.action.view.theme.high_contrast_light",
            constants.UI_THEME_MODE_HIGH_CONTRAST_DARK: "shell.action.view.theme.high_contrast_dark",
        }
        active_id = _mode_to_action_id.get(self._theme_mode, _mode_to_action_id[constants.UI_THEME_MODE_SYSTEM])
        for action_id in _mode_to_action_id.values():
            action = self._menu_registry.action(action_id)
            if action is not None:
                action.setChecked(action_id == active_id)

    def _handle_zoom_in(self) -> None:
        if self._editor_font_size + self._zoom_delta < 72:
            self._zoom_delta += 1
            self._apply_editor_preferences_to_open_editors()

    def _handle_zoom_out(self) -> None:
        if self._editor_font_size + self._zoom_delta > 8:
            self._zoom_delta -= 1
            self._apply_editor_preferences_to_open_editors()

    def _handle_zoom_reset(self) -> None:
        if self._zoom_delta != 0:
            self._zoom_delta = 0
            self._apply_editor_preferences_to_open_editors()

    def _save_import_update_policy(self, policy: ImportUpdatePolicy) -> None:
        self._settings_service.update_global(
            lambda settings_payload: merge_import_update_policy(settings_payload, policy.value)
        )
        self._import_update_policy = policy

    def _current_project_root(self) -> str | None:
        if self._loaded_project is None:
            return None
        return self._loaded_project.project_root

    def _current_python_tooling_status_context(self) -> tuple[bool, str, str | None, str | None]:
        return self._python_tooling_status_controller.current_status_context()

    def _settings_dialog_python_tooling_copy(self) -> tuple[str, str, str, str]:
        return self._python_tooling_status_controller.settings_dialog_copy()

    def _refresh_python_tooling_status(self) -> None:
        if self._status_controller is None:
            return
        runtime_available, config_state, config_path, config_error = self._current_python_tooling_status_context()
        self._status_controller.set_python_tooling_status(
            runtime_available=runtime_available,
            config_state=config_state,
            config_path=config_path,
            config_error=config_error,
        )

    def _load_effective_editor_settings_snapshot(self) -> EditorSettingsSnapshot:
        project_root = self._current_project_root()
        global_settings_payload = self._settings_service.load_global()
        project_settings_payload = None
        if project_root is not None:
            project_settings_payload = self._settings_service.load_project(project_root)
        return parse_effective_editor_settings_snapshot(
            global_settings_payload,
            project_settings_payload,
        )

    def _load_main_window_settings(self) -> MainWindowSettingsSnapshot:
        project_root = self._current_project_root()
        global_settings_payload = self._settings_service.load_global()
        project_settings_payload = None
        if project_root is not None:
            project_settings_payload = self._settings_service.load_project(project_root)
        return parse_effective_main_window_settings(
            global_settings_payload,
            project_settings_payload,
        )

    def _load_editor_preferences(
        self,
    ) -> tuple[int, int, str, str, int, bool, bool, bool, bool, bool, bool, bool, str, bool, bool]:
        return self._load_main_window_settings().editor_preferences

    def _load_completion_preferences(self) -> tuple[bool, bool, int]:
        return self._load_main_window_settings().completion_preferences

    def _load_diagnostics_preferences(self) -> tuple[bool, bool, bool, bool]:
        return self._load_main_window_settings().diagnostics_preferences

    def _load_output_preferences(self) -> tuple[bool, bool]:
        return self._load_main_window_settings().output_preferences

    def _load_local_history_retention_policy(self) -> LocalHistoryRetentionPolicy:
        return self._load_main_window_settings().local_history_retention_policy

    def _load_intelligence_runtime_settings(self) -> IntelligenceRuntimeSettings:
        return self._load_main_window_settings().intelligence_runtime_settings

    def _apply_preferences_bundle(self, bundle) -> None:
        main = bundle.main_window
        (
            self._editor_tab_width,
            self._editor_font_size,
            self._editor_font_family,
            self._editor_indent_style,
            self._editor_indent_size,
            self._editor_detect_indentation_from_file,
            self._editor_format_on_save,
            self._editor_organize_imports_on_save,
            self._editor_trim_trailing_whitespace_on_save,
            self._editor_insert_final_newline_on_save,
            self._editor_enable_preview,
            self._editor_auto_save,
            self._editor_exit_behavior,
            self._editor_hover_tooltip_enabled,
            self._editor_auto_reindent_flat_python_paste,
        ) = main.editor_preferences
        (
            self._completion_enabled,
            self._completion_auto_trigger,
            self._completion_min_chars,
        ) = main.completion_preferences
        (
            self._diagnostics_enabled,
            self._diagnostics_realtime,
            self._quick_fixes_enabled,
            self._quick_fix_require_preview_for_multifile,
        ) = main.diagnostics_preferences
        (
            self._auto_open_console_on_run_output,
            self._auto_open_problems_on_run_failure,
        ) = main.output_preferences
        self._local_history_retention_policy = bundle.local_history_retention_policy
        self._local_history_workflow.set_retention_policy(self._local_history_retention_policy, apply_now=True)
        self._shortcut_overrides = dict(bundle.shortcut_overrides)
        self._syntax_color_overrides = {
            theme: dict(overrides) for theme, overrides in bundle.syntax_color_overrides.items()
        }
        self._lint_rule_overrides = bundle.lint_rule_overrides
        self._selected_linter = bundle.selected_linter
        self._intelligence_runtime_settings = bundle.intelligence_runtime_settings

    def _load_plugin_safe_mode(self) -> bool:
        settings_payload = self._settings_service.load_global()
        return plugin_safe_mode_enabled(settings_payload)

    def _set_plugin_safe_mode(self, enabled: bool) -> None:
        self._settings_service.update_global(
            lambda payload: merge_plugin_safe_mode(payload, enabled=enabled)
        )
        self._plugin_safe_mode = bool(enabled)

    def _dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        if self._is_shutting_down:
            return
        self._main_thread_dispatcher.dispatch(callback)

    @property
    def menu_registry(self) -> MenuStubRegistry | None:
        return self._menu_registry

    @property
    def loaded_project(self) -> LoadedProject | None:
        """Return the currently loaded project, if any."""
        return self._loaded_project

    def register_runtime_command(
        self,
        *,
        command_id: str,
        handler: Callable[..., object],
        replace: bool = False,
    ) -> None:
        if self._action_registry is None:
            raise RuntimeError("Action registry is not ready.")
        self._action_registry.register_command(command_id, handler, replace=replace)

    def register_runtime_menu_command(
        self,
        *,
        command_id: str,
        menu_id: str,
        label: str,
        handler: Callable[..., object],
        shortcut: str | None = None,
        enabled: bool = True,
        status_tip: str | None = None,
        tool_tip: str | None = None,
        replace: bool = False,
    ) -> None:
        if self._action_registry is None:
            raise RuntimeError("Action registry is not ready.")
        self._action_registry.register_command(command_id, handler, replace=replace)
        self._action_registry.register_menu_action(
            action_id=command_id,
            menu_id=menu_id,
            label=label,
            shortcut=shortcut,
            enabled=enabled,
            status_tip=status_tip,
            tool_tip=tool_tip,
        )

    def unregister_runtime_menu_command(self, command_id: str) -> None:
        if self._action_registry is None:
            return
        self._action_registry.unregister_menu_action(command_id)
        self._action_registry.unregister_command(command_id)

    def execute_runtime_command(
        self,
        command_id: str,
        payload: dict[str, object] | None = None,
        activation_event: str | None = None,
    ) -> object:
        if payload is None and activation_event is None:
            return self._command_broker.invoke(command_id)
        if payload is None:
            return self._command_broker.invoke(command_id, {}, activation_event)
        return self._command_broker.invoke(command_id, payload, activation_event)

    def subscribe_shell_event(self, event_type: type[ShellEventT], handler: Callable[[ShellEventT], None]) -> None:
        self._event_bus.subscribe(event_type, handler)

    def unsubscribe_shell_event(self, event_type: type[ShellEventT], handler: Callable[[ShellEventT], None]) -> None:
        self._event_bus.unsubscribe(event_type, handler)

    def _handle_open_project_action(self) -> None:
        selected_path = choose_existing_directory(self, "Open Project", str(Path.home()))
        if not selected_path:
            return
        self._open_project_by_path(selected_path)

    def _handle_open_file_action(self) -> None:
        start_dir = str(Path.home())
        if self._loaded_project is not None:
            start_dir = self._loaded_project.project_root
        active_tab = self._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path:
            parent = Path(active_tab.file_path).parent
            if parent.is_dir():
                start_dir = str(parent)

        file_paths = choose_open_files(
            self,
            "Open File",
            start_dir,
            "Python Files (*.py);;"
            "JSON Files (*.json);;"
            "Shell Scripts (*.sh *.bash);;"
            "Markdown Files (*.md);;"
            "Text Files (*.txt);;"
            "All Files (*)",
        )
        if not file_paths:
            return

        # When no project is loaded, auto-open the first file's parent directory
        # as a project so the editor surface is populated and the file lives in a
        # navigable workspace. Mirrors how Atom/Sublime/VS Code (no folder open)
        # behave when a single file is opened from the menu.
        if self._loaded_project is None:
            self._maybe_open_parent_directory_as_project(file_paths[0])

        for file_path in file_paths:
            self._editor_tab_factory.open_file_in_editor(file_path, preview=False)

        # Always surface the editor screen — without this, opening a file from
        # the welcome page leaves the welcome page visible even though the tab
        # was actually added to the (hidden) editor stack.
        self._show_editor_screen()

    def _maybe_open_parent_directory_as_project(self, file_path: str) -> None:
        """Open ``file_path``'s parent directory as a project, when valid."""
        try:
            parent_dir = Path(file_path).expanduser().resolve().parent
        except OSError:
            return
        if not parent_dir.is_dir():
            return
        try:
            assessment = assess_project_root(parent_dir)
        except Exception as exc:
            self._logger.debug("Skipped parent project assessment for %s: %s", parent_dir, exc)
            return
        if assessment.state not in (ProjectRootState.CANONICAL, ProjectRootState.IMPORTABLE):
            return
        self._open_project_by_path(str(parent_dir))

    def _handle_new_window_action(self) -> None:
        repo_root = self._resolve_repo_root_for_launch()
        editor_boot = (repo_root / "run_editor.py").resolve()
        if not editor_boot.exists():
            QMessageBox.warning(
                self,
                "New Window unavailable",
                f"Editor boot script not found: {editor_boot}",
            )
            return
        command = self._build_new_window_command(repo_root=repo_root, editor_boot=editor_boot)
        try:
            subprocess.Popen(command, cwd=str(repo_root), start_new_session=True)
        except OSError as exc:
            QMessageBox.warning(self, "New Window unavailable", f"Unable to launch new window: {exc}")

    def _resolve_repo_root_for_launch(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _build_new_window_command(self, *, repo_root: Path, editor_boot: Path) -> list[str]:
        runtime_executable = resolve_runtime_executable(None)
        if is_freecad_runtime_executable(runtime_executable):
            payload = build_runpy_bootstrap_payload(
                script_path=str(editor_boot),
                path_entry=str(repo_root),
            )
            return [runtime_executable, "-c", payload]
        return [runtime_executable, str(editor_boot)]

    def _handle_new_project_action(self) -> None:
        project_details = self._prompt_for_new_project_destination()
        if project_details is None:
            return
        project_name, destination_path = project_details

        try:
            created_path = create_blank_project(destination_path, project_name=project_name)
        except AppValidationError as exc:
            QMessageBox.warning(self, "Failed to create project", str(exc))
            return

        self._open_project_by_path(str(created_path))

    def _handle_new_project_from_template_action(self) -> None:
        try:
            _provider, templates = list_templates_with_workflow(self._workflow_broker)
        except Exception as exc:
            QMessageBox.warning(self, "No templates available", f"Unable to load templates: {exc}")
            return
        if not templates:
            QMessageBox.warning(self, "No templates available", "No project templates were found.")
            return

        selected_template = self._prompt_for_template(templates)
        if selected_template is None:
            return

        project_details = self._prompt_for_new_project_destination()
        if project_details is None:
            return
        project_name, destination_path = project_details

        try:
            created_path = self._template_service.materialize_template(
                template_id=selected_template.template_id,
                destination_path=destination_path,
                project_name=project_name,
            )
        except AppValidationError as exc:
            QMessageBox.warning(self, "Failed to create project", str(exc))
            return

        self._open_project_by_path(str(created_path))

    def _prompt_for_new_project_destination(self) -> tuple[str, Path] | None:
        project_name, accepted_name = QInputDialog.getText(self, "New Project", "Project name:", QLineEdit.Normal, "")
        normalized_name = project_name.strip()
        if not accepted_name or not normalized_name:
            return None

        destination_parent = choose_existing_directory(self, "Choose Project Folder", str(Path.home()))
        if not destination_parent:
            return None

        return normalized_name, Path(destination_parent) / normalized_name

    def _handle_open_settings_action(self) -> None:
        global_settings_payload = self._settings_service.load_global()
        global_snapshot = parse_editor_settings_snapshot(global_settings_payload)
        project_root = self._current_project_root()
        project_settings_payload: dict[str, Any] = {}
        effective_snapshot = global_snapshot
        if project_root is not None:
            project_settings_payload = self._settings_service.load_project(project_root)
            effective_snapshot = parse_effective_editor_settings_snapshot(
                global_settings_payload,
                project_settings_payload,
            )

        previous_theme_mode = global_snapshot.theme_mode
        previous_lint_rule_overrides = dict(self._lint_rule_overrides)
        previous_diagnostics_enabled = self._diagnostics_enabled
        previous_selected_linter = self._selected_linter
        previous_enable_preview = self._editor_enable_preview
        previous_effective_excludes = self._load_effective_exclude_patterns(project_root)
        (
            python_tooling_runtime_text,
            python_tooling_runtime_details,
            python_tooling_config_text,
            python_tooling_config_details,
        ) = self._settings_dialog_python_tooling_copy()
        dialog = SettingsDialog(
            global_snapshot,
            self,
            tokens=self._shell_theme_workflow.resolve_theme_tokens(),
            project_snapshot=effective_snapshot if project_root is not None else None,
            project_scope_available=project_root is not None,
            python_tooling_runtime_text=python_tooling_runtime_text,
            python_tooling_runtime_details=python_tooling_runtime_details,
            python_tooling_config_text=python_tooling_config_text,
            python_tooling_config_details=python_tooling_config_details,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        selected_scope = dialog.selected_scope
        updated_snapshot = dialog.snapshot()
        merged_global_settings, merged_project_settings = merge_editor_settings_snapshot_for_scope(
            scope=selected_scope,
            global_settings_payload=global_settings_payload,
            project_settings_payload=project_settings_payload,
            snapshot=updated_snapshot,
            global_snapshot=dialog.global_scope_snapshot(),
            project_snapshot=dialog.project_scope_snapshot(),
        )
        if merged_global_settings != global_settings_payload:
            self._settings_service.save_global(merged_global_settings)
        if project_root is not None and merged_project_settings != project_settings_payload:
            self._settings_service.save_project(project_root, merged_project_settings)

        baseline = capture_settings_apply_baseline(
            theme_mode=previous_theme_mode,
            lint_rule_overrides=previous_lint_rule_overrides,
            diagnostics_enabled=previous_diagnostics_enabled,
            selected_linter=previous_selected_linter,
            enable_preview=previous_enable_preview,
            effective_excludes=previous_effective_excludes,
        )
        self._settings_apply_workflow.apply_after_settings_saved(
            updated_snapshot=updated_snapshot,
            baseline=baseline,
            project_root=project_root,
        )

    def _prompt_for_template(self, templates: list[TemplateMetadata]) -> TemplateMetadata | None:
        labels = [f"{template.display_name} ({template.template_id})" for template in templates]
        selected_label, ok = QInputDialog.getItem(self, "New Project", "Template:", labels, 0, editable=False)
        if not ok:
            return None
        for template in templates:
            if selected_label == f"{template.display_name} ({template.template_id})":
                return template
        return None

    def _handle_quick_open_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Quick Open unavailable", "Open a project first.")
            return

        open_paths = set(self._editor_manager.open_paths()) if self._editor_manager else set()
        candidates = [
            QuickOpenCandidate(
                relative_path=entry.relative_path,
                absolute_path=entry.absolute_path,
                is_open=entry.absolute_path in open_paths,
            )
            for entry in self._loaded_project.entries
            if not entry.is_directory
        ]

        if self._quick_open_dialog is None:
            tokens = self._shell_theme_workflow.resolve_theme_tokens()
            self._quick_open_dialog = QuickOpenDialog(
                self,
                tokens=tokens,
                icon_map=self._tree_file_icon_map,
                filename_icon_map=self._tree_filename_icon_map,
            )
            self._quick_open_dialog.file_preview_requested.connect(
                lambda file_path: self._editor_tab_factory.open_file_in_editor(file_path, preview=True)
            )
            self._quick_open_dialog.file_selected.connect(
                lambda file_path: self._editor_tab_factory.open_file_in_editor(file_path, preview=False)
            )
            self._quick_open_dialog.file_preview_at_line_requested.connect(
                lambda file_path, line_number: self._open_file_at_line(
                    file_path,
                    line_number,
                    preview=True,
                )
            )
            self._quick_open_dialog.file_selected_at_line.connect(
                lambda file_path, line_number: self._open_file_at_line(
                    file_path,
                    line_number,
                    preview=False,
                )
            )

        self._quick_open_dialog.set_candidates(candidates)
        self._quick_open_dialog.open_dialog()

    def _handle_toggle_comment_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            return
        editor_widget.toggle_comment_selection()

    def _handle_indent_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            return
        editor_widget.indent_selection()

    def _handle_outdent_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            return
        editor_widget.outdent_selection()

    def _handle_paste_reindented_flat_python_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(self, "Paste and Re-indent Flat Python", "Open a file tab first.")
            return
        result = editor_widget.paste_reindented_flat_python()
        self.statusBar().showMessage(_flat_python_repair_status_message(result), 4000)

    def _handle_reindent_flat_python_selection_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(self, "Re-indent Flat Python Selection", "Open a file tab first.")
            return
        result = editor_widget.reindent_flat_python_selection()
        self.statusBar().showMessage(_flat_python_repair_status_message(result), 4000)

    def _handle_paste_hint_repair_result(self, result: FlatPythonIndentRepairResult) -> None:
        """Surface flat-Python paste repair feedback in the status bar."""
        self.statusBar().showMessage(_flat_python_repair_status_message(result), 4000)

    def _enable_auto_reindent_flat_python_paste_from_hint(self) -> None:
        """Persist auto-re-indent ON and propagate to open editors. Called by the paste hint's "Always" button."""
        if self._editor_auto_reindent_flat_python_paste:
            return
        self._editor_auto_reindent_flat_python_paste = True
        try:
            self._settings_service.update_global(_enable_auto_reindent_flat_python_paste_in_payload)
        except Exception:
            self._logger.exception("Failed to persist auto-reindent flat-Python paste setting.")
        self._apply_editor_preferences_to_open_editors()

    def _handle_go_to_line_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(self, "Go To Line", "Open a file tab first.")
            return

        total_lines = max(1, editor_widget.document().blockCount())
        line_number, ok = QInputDialog.getInt(self, "Go To Line", "Line:", 1, 1, total_lines, 1)
        if not ok:
            return

        editor_widget.go_to_line(line_number)

    def _handle_find_references_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Find References", "Open a project first.")
            return
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Find References", "Open a file tab first.")
            return
        project_root = self._loaded_project.project_root
        current_file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()
        started_at = time.perf_counter()

        def on_success(result) -> None:  # type: ignore[no-untyped-def]
            if self._intelligence_runtime_settings.metrics_logging_enabled:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                if elapsed_ms > 1200.0:
                    self._logger.warning(
                        "References latency warning: file=%s symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        result.symbol_name,
                        elapsed_ms,
                        len(result.hits),
                    )
                else:
                    self._logger.info(
                        "References telemetry: file=%s symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        result.symbol_name,
                        elapsed_ms,
                        len(result.hits),
                    )
            if not result.symbol_name:
                QMessageBox.information(self, "Find References", "Place cursor on a symbol first.")
                return
            if not result.hits:
                if result.metadata.unsupported_reason:
                    if result.metadata.source == "semantic_unavailable":
                        QMessageBox.warning(
                            self,
                            "Find References",
                            (
                                "Semantic references are currently unavailable.\n\n"
                                f"Reason: {result.metadata.unsupported_reason}"
                            ),
                        )
                        return
                    QMessageBox.information(
                        self,
                        "Find References",
                        (
                            f"No semantic references found for '{result.symbol_name}'.\n\n"
                            "The symbol may be dynamic or unresolved. Use Find in Files for text search."
                        ),
                    )
                else:
                    QMessageBox.information(self, "Find References", f"No references found for '{result.symbol_name}'.")
                return

            if self._problems_panel is None:
                return
            ref_items = [
                ResultItem(
                    label=f"[{'def' if hit.is_definition else 'ref'}] {hit.line_text.strip()}",
                    file_path=hit.file_path,
                    line_number=hit.line_number,
                    tooltip=hit.file_path,
                )
                for hit in result.hits
            ]
            self._problems_panel.set_results(f"References: {result.symbol_name}", ref_items)
            self._update_problems_tab_title(self._problems_panel.problem_count())
            self._focus_problems_tab()

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Find References", f"Reference search failed: {exc}")

        self._intelligence_controller.request_find_references(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_rename_symbol_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Rename Symbol", "Open a project first.")
            return
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Rename Symbol", "Open a file tab first.")
            return

        old_symbol = editor_widget.word_under_cursor()
        if not old_symbol:
            QMessageBox.information(self, "Rename Symbol", "Place cursor on a symbol first.")
            return
        new_symbol, ok = QInputDialog.getText(self, "Rename Symbol", f"Rename '{old_symbol}' to:", QLineEdit.Normal, old_symbol)
        if not ok:
            return
        new_symbol = new_symbol.strip()
        if not new_symbol or new_symbol == old_symbol:
            return
        if not new_symbol.isidentifier():
            QMessageBox.warning(self, "Rename Symbol", "New name must be a valid Python identifier.")
            return

        if not self._save_workflow.handle_save_all_action():
            QMessageBox.warning(self, "Rename Symbol", "Fix save errors before renaming.")
            return
        project_root = self._loaded_project.project_root
        current_file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()
        started_at = time.perf_counter()

        def on_success(plan) -> None:  # type: ignore[no-untyped-def]
            if self._intelligence_runtime_settings.metrics_logging_enabled:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                hit_count = 0 if plan is None else len(plan.hits)
                if elapsed_ms > 800.0:
                    self._logger.warning(
                        "Rename planning latency warning: file=%s old_symbol=%s new_symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        old_symbol,
                        new_symbol,
                        elapsed_ms,
                        hit_count,
                    )
                else:
                    self._logger.info(
                        "Rename planning telemetry: file=%s old_symbol=%s new_symbol=%s elapsed_ms=%.2f hits=%s",
                        current_file_path,
                        old_symbol,
                        new_symbol,
                        elapsed_ms,
                        hit_count,
                    )
            if plan is None or not plan.preview_patches:
                QMessageBox.information(
                    self,
                    "Rename Symbol",
                    f"No safe semantic rename plan found for '{old_symbol}'.",
                )
                return

            preview_chunks = [patch.diff_text for patch in plan.preview_patches[:3]]
            preview_body = "\n\n".join(chunk for chunk in preview_chunks if chunk)
            if len(plan.preview_patches) > 3:
                preview_body += f"\n\n... and {len(plan.preview_patches) - 3} more file patch(es)"
            confidence_text = ""
            if plan.metadata and plan.metadata.confidence == "exact":
                confidence_text = "Confidence: proven by semantic engine"
            elif plan.metadata and plan.metadata.confidence == "approximate":
                confidence_text = "Confidence: approximate — review changes carefully"
            confirm = QMessageBox.question(
                self,
                "Rename Preview",
                (
                    f"Rename '{plan.old_symbol}' to '{plan.new_symbol}'?\n"
                    f"Occurrences: {len(plan.hits)} across {len(plan.touched_files)} file(s)\n"
                    f"{confidence_text}\n\n"
                    f"{preview_body}"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirm != QMessageBox.Yes:
                return

            def on_apply_success(result) -> None:  # type: ignore[no-untyped-def]
                self._local_history_workflow.record_transaction(
                    {patch.file_path: patch.updated_content for patch in plan.preview_patches},
                    source="semantic_rename",
                    label=f"Rename '{plan.old_symbol}' to '{plan.new_symbol}'",
                )
                self._refresh_open_tabs_from_disk(result.changed_files)
                self._reload_current_project()
                QMessageBox.information(
                    self,
                    "Rename Symbol",
                    f"Renamed {result.changed_occurrences} occurrence(s) across {len(result.changed_files)} file(s).",
                )

            def on_apply_error(exc: Exception) -> None:
                QMessageBox.warning(self, "Rename Symbol", f"Failed to apply rename: {exc}")

            self._intelligence_controller.request_apply_rename(
                plan=plan,
                on_success=on_apply_success,
                on_error=on_apply_error,
            )

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Rename Symbol", f"Rename planning failed: {exc}")

        self._intelligence_controller.request_rename_plan(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            new_symbol=new_symbol,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_set_language_mode_action(self) -> None:
        editor_widget = self._active_editor_widget()
        active_tab = self._editor_manager.active_tab()
        if editor_widget is None or active_tab is None:
            QMessageBox.warning(self, "Language Mode", "Open a file tab first.")
            return
        mode_items = [("auto", "Auto Detect")]
        mode_items.extend(editor_widget.available_language_modes())
        labels = [label for _key, label in mode_items]
        current_key = editor_widget.language_override_key() or "auto"
        current_index = next((index for index, (key, _label) in enumerate(mode_items) if key == current_key), 0)
        selected_label, ok = QInputDialog.getItem(
            self,
            "Language Mode",
            "Use syntax mode:",
            labels,
            current_index,
            False,
        )
        if not ok:
            return
        selected_key = next((key for key, label in mode_items if label == selected_label), "auto")
        if selected_key == "auto":
            editor_widget.clear_language_override()
        else:
            editor_widget.set_language_override(selected_key)
        self._update_editor_status_for_path(active_tab.file_path)

    def _handle_clear_language_override_action(self) -> None:
        editor_widget = self._active_editor_widget()
        active_tab = self._editor_manager.active_tab()
        if editor_widget is None or active_tab is None:
            QMessageBox.warning(self, "Language Mode", "Open a file tab first.")
            return
        editor_widget.clear_language_override()
        self._update_editor_status_for_path(active_tab.file_path)

    def _handle_inspect_token_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(self, "Token Inspector", "Open a file tab first.")
            return
        QMessageBox.information(self, "Token Inspector", editor_widget.describe_token_under_cursor())

    def _handle_load_example_project_action(self) -> None:
        project_details = self._prompt_for_new_project_destination()
        if project_details is None:
            return
        project_name, destination_path = project_details

        try:
            created_path = self._example_project_service.materialize_showcase(
                destination_path=destination_path,
                project_name=project_name,
            )
        except AppValidationError as exc:
            QMessageBox.warning(self, "Failed to load example project", str(exc))
            return

        self._open_project_by_path(str(created_path))

    def _open_project_by_path(self, project_root: str) -> bool:
        started_at = time.perf_counter()
        async_open = os.environ.get("CBCS_SYNC_PROJECT_OPEN") != "1"
        return self._project_controller.open_project_by_path(
            project_root,
            confirm_proceed=self._save_workflow.confirm_proceed_with_unsaved_changes,
            on_loading=lambda: self.statusBar().showMessage("Opening project… (scanning files)", 0),
            on_loaded=lambda loaded_project: self._apply_loaded_project(loaded_project, started_at=started_at),
            on_error=self._show_open_project_error,
            exclude_patterns=self._load_effective_exclude_patterns(project_root),
            async_open=async_open,
        )

    def _load_effective_exclude_patterns(self, project_root: str | None = None) -> list[str]:
        return load_effective_exclude_patterns(self._settings_service, project_root)

    def _refresh_open_recent_menu(self) -> None:
        self._project_controller.refresh_open_recent_menu(
            self._menu_registry,
            open_project_by_path=self._open_project_by_path,
        )

    def _refresh_welcome_project_list(self) -> None:
        if self._welcome_widget is None:
            return
        self._refresh_welcome_widget_state(self._welcome_widget)

    def _show_welcome_screen(self) -> None:
        """Switch the center stack back to the welcome page."""
        if self._center_stack is not None:
            self._refresh_welcome_project_list()
            self._center_stack.setCurrentIndex(0)

    def _show_editor_screen(self) -> None:
        """Switch the center stack to the editor page."""
        if self._center_stack is not None:
            self._center_stack.setCurrentIndex(1)

    def _show_open_project_error(self, project_root: str, details: str) -> None:
        self._logger.warning("Project open failed for %s: %s", project_root, details)
        self._event_bus.publish(
            ProjectOpenFailedEvent(project_root=project_root, error_message=details)
        )
        QMessageBox.critical(
            self,
            "Unable to open project",
            f"Could not open project:\n{project_root}\n\n{details}",
        )

    def _apply_loaded_project(self, loaded_project: LoadedProject, *, started_at: float) -> None:
        self._project_load_workflow.apply(loaded_project, started_at=started_at)
        self._maybe_prompt_import_source_roots()

    def _persist_last_project_path(self, project_root: str) -> None:
        try:
            self._settings_service.update_global(
                lambda settings: merge_last_project_path(settings, project_root)
            )
        except Exception as exc:
            self._logger.warning("Failed to persist last project path: %s", exc)

    def _get_project_tree_presenter(self) -> ShellProjectTreePresenter:
        presenter = getattr(self, "_project_tree_presenter", None)
        if presenter is None:
            presenter = ShellProjectTreePresenter(
                self,
                absolute_path_role=TREE_ROLE_ABSOLUTE_PATH,
                is_directory_role=TREE_ROLE_IS_DIRECTORY,
                relative_path_role=TREE_ROLE_RELATIVE_PATH,
            )
            self._project_tree_presenter = presenter
        return presenter

    def _get_editor_tabs_coordinator(self) -> EditorTabsCoordinator:
        coordinator = getattr(self, "_editor_tabs_coordinator", None)
        if coordinator is None:
            coordinator = EditorTabsCoordinator(self)
            self._editor_tabs_coordinator = coordinator
        return coordinator

    def _get_problems_controller(self) -> ProblemsController:
        controller = getattr(self, "_problems_controller", None)
        if controller is None:
            controller = ProblemsController(self)
            self._problems_controller = controller
        return controller

    def _sync_auto_save_menu_state(self) -> None:
        if self._menu_registry is None:
            return
        action = self._menu_registry.action("shell.action.file.autoSave")
        if action is not None:
            action.blockSignals(True)
            action.setChecked(self._editor_auto_save)
            action.blockSignals(False)

    def _resolve_python_tooling_project_root(self, file_path: str) -> str:
        normalized_file_path = Path(file_path).expanduser().resolve()
        if self._loaded_project is not None:
            project_root = Path(self._loaded_project.project_root).expanduser().resolve()
            try:
                normalized_file_path.relative_to(project_root)
            except ValueError:
                pass
            else:
                return str(project_root)
        return str(normalized_file_path.parent)

    def _apply_text_to_open_tab(self, file_path: str, replacement_text: str) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        editor_widget = self._editor_widgets_by_path.get(file_path)
        if editor_widget is not None:
            if editor_widget.toPlainText() != replacement_text:
                editor_widget.replace_document_text(replacement_text)
            return
        self._editor_manager.update_tab_content(file_path, replacement_text)

    def _refresh_save_action_states(self) -> None:
        if self._menu_registry is None:
            return

        save_action = self._menu_registry.action("shell.action.file.save")
        save_all_action = self._menu_registry.action("shell.action.file.saveAll")
        active_tab = self._editor_manager.active_tab()
        has_dirty_tabs = any(tab.is_dirty for tab in self._editor_manager.all_tabs())

        if save_action is not None:
            save_action.setEnabled(active_tab is not None)
        if save_all_action is not None:
            save_all_action.setEnabled(has_dirty_tabs)

    def _show_run_preflight_result(self, title: str, summary: str, issues: list[Any]) -> None:
        report = RuntimeIssueReport(workflow="run", issues=list(issues))
        self._open_runtime_center_dialog(title=title, report=report)
        self._append_console_line(summary, stream="system")

    def _resolve_project_entry_for_project_run(self) -> str | None:
        loaded_project = self._loaded_project
        if loaded_project is None:
            QMessageBox.warning(self, "Run unavailable", "Open a project before running.")
            return None
        project_root = Path(loaded_project.project_root).expanduser().resolve()
        default_entry = (loaded_project.metadata.default_entry or "").strip()
        resolved, _error = resolve_entry_path(root=project_root, entry_file=default_entry)
        if resolved is not None:
            return default_entry
        missing_label = default_entry if default_entry else "(empty)"
        replacement = self._prompt_for_project_entry_replacement(missing_label)
        if not replacement:
            return None
        if self._set_project_entry_point(replacement):
            return replacement.strip()
        return None

    def _prompt_for_project_entry_replacement(self, missing_entry: str) -> str | None:
        loaded_project = self._loaded_project
        if loaded_project is None:
            return None
        project_root = Path(loaded_project.project_root).expanduser().resolve()
        candidates: list[str] = [
            candidate.relative_to(project_root).as_posix()
            for candidate in iter_python_files(project_root)
            if candidate.is_file()
        ]
        if not candidates:
            QMessageBox.warning(
                self,
                "Entry point missing",
                f"'{missing_entry}' no longer exists and no Python files are available.",
            )
            return None

        selected, accepted = QInputDialog.getItem(
            self,
            "Entry point missing",
            f"'{missing_entry}' no longer exists.\nSelect a replacement entry file:",
            candidates,
            0,
            False,
        )
        if not accepted or not selected:
            return None
        return str(selected)

    def _handle_tree_mark_source_root(self, relative_path: str) -> None:
        loaded_project = self._loaded_project
        if loaded_project is None:
            return
        from app.project.project_manifest import append_project_source_root

        try:
            updated_metadata = append_project_source_root(
                loaded_project.manifest_path,
                relative_path,
                metadata_if_absent=None
                if loaded_project.manifest_materialized
                else loaded_project.metadata,
            )
        except (ProjectManifestValidationError, ValueError) as exc:
            QMessageBox.warning(self, "Sources Root", str(exc))
            return
        self._loaded_project = replace(loaded_project, metadata=updated_metadata, manifest_materialized=True)
        self._reload_current_project()

    def _handle_tree_unmark_source_root(self, relative_path: str) -> None:
        loaded_project = self._loaded_project
        if loaded_project is None:
            return
        from app.project.project_manifest import remove_project_source_root

        try:
            updated_metadata = remove_project_source_root(loaded_project.manifest_path, relative_path)
        except (ProjectManifestValidationError, ValueError) as exc:
            QMessageBox.warning(self, "Sources Root", str(exc))
            return
        self._loaded_project = replace(loaded_project, metadata=updated_metadata)
        self._reload_current_project()

    def _maybe_prompt_import_source_roots(self) -> None:
        loaded_project = self._loaded_project
        if loaded_project is None or loaded_project.metadata.source_roots:
            return
        from app.project.import_layout import detect_suggested_source_root

        suggested = detect_suggested_source_root(loaded_project.project_root)
        if suggested is None:
            return
        confirm = QMessageBox.question(
            self,
            "Import Roots",
            (
                f"This project looks like it uses a `{suggested}/` layout. "
                f"Mark `{suggested}` as a source root so local imports resolve correctly?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return
        self._handle_tree_mark_source_root(suggested)

    def _set_project_entry_point(self, relative_path: str) -> bool:
        loaded_project = self._loaded_project
        if loaded_project is None:
            return False
        normalized_relative = relative_path.strip()
        if not normalized_relative:
            return False
        project_root = Path(loaded_project.project_root).expanduser().resolve()
        entry_path = (project_root / normalized_relative).resolve()
        if not entry_path.exists() or not entry_path.is_file():
            QMessageBox.warning(self, "Entry point", "Selected entry file does not exist.")
            return False
        if entry_path.suffix.lower() != ".py":
            QMessageBox.warning(self, "Entry point", "Entry point must reference a Python file.")
            return False
        try:
            entry_path.relative_to(project_root)
        except ValueError:
            QMessageBox.warning(self, "Entry point", "Entry point must be inside the opened project.")
            return False

        try:
            updated_metadata = set_project_default_entry(
                loaded_project.manifest_path,
                default_entry=normalized_relative,
                metadata_if_absent=None
                if loaded_project.manifest_materialized
                else loaded_project.metadata,
            )
        except (ProjectManifestValidationError, ValueError) as exc:
            QMessageBox.warning(self, "Entry point", str(exc))
            return False
        self._loaded_project = replace(
            loaded_project,
            metadata=updated_metadata,
            manifest_materialized=True,
        )
        self._populate_project_tree(self._loaded_project, preserve_state=True)
        return True

    def _handle_start_python_console_action(self) -> bool:
        self._repl_manager.restart()
        self._focus_python_console_tab()
        return True

    def _prepare_for_session_start(self) -> None:
        prepare_new_run(MainWindowClearConsoleHost(self))

    def _handle_stop_action(self) -> None:
        self._run_session_controller.stop_session(lambda text, stream: self._append_console_line(text, stream=stream))
        self._set_run_status("stopping")
        self._refresh_run_action_states()

    def _handle_restart_action(self) -> None:
        if self._run_service.supervisor.is_running():
            self._run_service.stop_run()
        if self._run_session_controller.active_session_mode == constants.RUN_MODE_PYTHON_DEBUG:
            self._run_launch_workflow.handle_rerun_last_debug_target_action()
        else:
            self._run_launch_workflow.handle_run_action()

    def _handle_clear_console_action(self) -> None:
        clear_run_output_sinks(MainWindowClearConsoleHost(self))

    def _handle_open_plugin_manager_action(self) -> None:
        if self._plugin_manager_dialog is None:
            self._plugin_manager_dialog = PluginManagerDialog(
                state_root=self._state_root,
                project_root=None if self._loaded_project is None else self._loaded_project.project_root,
                activation_snapshot_provider=lambda: self._plugin_activation_workflow.snapshot(
                    project_root=None if self._loaded_project is None else self._loaded_project.project_root
                ),
                on_plugins_changed=self._plugin_activation_workflow.reload,
                safe_mode_enabled=self._plugin_safe_mode,
                on_safe_mode_changed=self._handle_plugin_safe_mode_changed,
                parent=self,
            )
            self._plugin_manager_dialog.finished.connect(
                lambda _result: setattr(self, "_plugin_manager_dialog", None)
            )
        self._plugin_manager_dialog.set_safe_mode_enabled(self._plugin_safe_mode)
        self._plugin_manager_dialog.set_project_root(
            None if self._loaded_project is None else self._loaded_project.project_root
        )
        self._plugin_manager_dialog.refresh_plugins()
        self._plugin_manager_dialog.show()
        self._plugin_manager_dialog.raise_()
        self._plugin_manager_dialog.activateWindow()

    def _handle_open_dependency_inspector_action(self) -> None:
        loaded_project = self._loaded_project
        if loaded_project is None:
            QMessageBox.warning(self, "Dependency Inspector", "Open a project first.")
            return
        dialog = self._dependency_inspector_dialog
        project_root = loaded_project.project_root
        if dialog is None or getattr(dialog, "_project_root", "") != project_root:
            dialog = DependencyInspectorDialog(project_root=project_root, parent=self)
            dialog.finished.connect(lambda _result: setattr(self, "_dependency_inspector_dialog", None))
            cast(_ConnectableSignal, dialog.dependency_changed).connect(self._reload_current_project)
            self._dependency_inspector_dialog = dialog
        dialog.refresh()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _handle_add_dependency_action(self) -> None:
        loaded_project = self._loaded_project
        if loaded_project is None:
            QMessageBox.warning(self, "Add Dependency", "Open a project first.")
            return
        dialog = AddDependencyWizardDialog(project_root=loaded_project.project_root, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        result = dialog.last_result
        if result is None:
            return
        QMessageBox.information(
            self,
            "Add Dependency",
            f"Added dependency '{result.name}' ({result.classification}).",
        )
        self._reload_current_project()
        if self._dependency_inspector_dialog is not None:
            self._dependency_inspector_dialog.refresh()

    def _handle_plugin_safe_mode_changed(self, enabled: bool) -> None:
        self._set_plugin_safe_mode(enabled)
        self._plugin_activation_workflow.reload()

    def _execute_plugin_runtime_command(self, command_id: str, payload: dict[str, object]) -> object:
        result = self._plugin_api_broker.invoke_runtime_command(command_id, payload)
        return self._plugin_api_broker.coerce_result_payload(result)

    def _record_plugin_runtime_failure(self, plugin_id: str, version: str, error_message: str) -> None:
        updated_registry = record_registry_entry_failure(
            plugin_id,
            version,
            error_message=error_message,
            disable_after_failures=constants.PLUGIN_DISABLE_AFTER_FAILURES_DEFAULT,
            state_root=self._state_root,
        )
        updated_entry = None
        for entry in updated_registry.entries:
            if entry.plugin_id == plugin_id and entry.version == version:
                updated_entry = entry
                break
        if updated_entry is not None and not updated_entry.enabled:
            QMessageBox.warning(
                self,
                "Plugin Disabled",
                f"{plugin_id}@{version} was disabled after repeated runtime failures.",
            )
            self._plugin_activation_workflow.reload()

    def _clear_plugin_runtime_failure(self, plugin_id: str, version: str) -> None:
        clear_registry_entry_failures(
            plugin_id,
            version,
            state_root=self._state_root,
        )

    def _render_lint_diagnostics_for_file(self, file_path: str, *, trigger: str) -> None:
        """Run diagnostics for *file_path* and update the editor + problems panel.

        *trigger* controls gating behaviour:
          "manual"     – always runs (user explicitly asked)
          "tab_change" – runs when diagnostics are enabled (regardless of realtime)
          "save"       – same as tab_change
          "realtime"   – only runs when realtime diagnostics are on
        """
        if not self._diagnostics_enabled:
            if trigger == "manual":
                QMessageBox.information(
                    self,
                    "Lint Current File",
                    "Diagnostics are currently disabled in Settings.",
                )
            return
        if trigger == "realtime" and not self._diagnostics_realtime:
            return
        if not file_path.lower().endswith(".py"):
            if trigger == "manual":
                QMessageBox.information(self, "Lint Current File", "Linting is currently available for Python files only.")
            return
        started_at = time.perf_counter()
        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        editor_widget = self._editor_widgets_by_path.get(file_path)
        buffer_source = editor_widget.toPlainText() if editor_widget is not None else None
        buffer_revision = None if editor_widget is None else self._editor_buffer_revision(file_path)
        allow_runtime_import_probe = trigger == "manual"
        key = f"lint::{file_path}"

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            project_metadata = None if self._loaded_project is None else self._loaded_project.metadata
            _provider, diagnostics = analyze_python_with_workflow(
                self._workflow_broker,
                file_path=file_path,
                project_root=project_root,
                source=buffer_source,
                known_runtime_modules=self._known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
                selected_linter=self._selected_linter,
                lint_rule_overrides=self._lint_rule_overrides,
                project_metadata=project_metadata,
            )
            return diagnostics

        def on_success(diagnostics) -> None:  # type: ignore[no-untyped-def]
            active_widget = self._editor_widgets_by_path.get(file_path)
            if editor_widget is not None and active_widget is not editor_widget:
                return
            if buffer_revision is not None and self._editor_buffer_revision(file_path) != buffer_revision:
                self._logger.info(
                    "Dropped stale diagnostics result for %s due to buffer revision change.",
                    file_path,
                )
                return
            if self._intelligence_runtime_settings.metrics_logging_enabled:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                if elapsed_ms > 180.0:
                    self._logger.warning(
                        "Diagnostics latency warning: file=%s elapsed_ms=%.2f count=%s",
                        file_path,
                        elapsed_ms,
                        len(diagnostics),
                    )
                else:
                    self._logger.info(
                        "Diagnostics telemetry: file=%s elapsed_ms=%.2f count=%s",
                        file_path,
                        elapsed_ms,
                        len(diagnostics),
                    )
            self._apply_lint_diagnostics_result(file_path, diagnostics)

        def on_error(exc: Exception) -> None:
            self._logger.warning("Diagnostics run failed for %s: %s", file_path, exc)
            if trigger == "manual":
                QMessageBox.warning(self, "Lint Current File", f"Diagnostics failed: {exc}")

        self._background_tasks.run(
            key=key,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _lint_all_open_files(self) -> None:
        """Run diagnostics for every open Python file and rebuild the problems panel."""
        if not self._diagnostics_enabled:
            return
        scheduled_any = False
        for file_path in self._workspace_controller.open_editor_paths():
            if not file_path.lower().endswith(".py"):
                continue
            scheduled_any = True
            self._render_lint_diagnostics_for_file(file_path, trigger="tab_change")
        if not scheduled_any:
            self._render_merged_problems_panel()
            active_tab = self._editor_manager.active_tab()
            if active_tab is not None:
                active_diags = self._stored_lint_diagnostics.get(active_tab.file_path, [])
                self._update_status_bar_diagnostics(active_diags)

    def _apply_lint_diagnostics_result(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        self._get_problems_controller().apply_lint_diagnostics_result(file_path, diagnostics)

    def _push_diagnostics_to_editor(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        self._get_problems_controller().push_diagnostics_to_editor(file_path, diagnostics)

    def _update_tab_diagnostic_indicator(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        self._get_problems_controller().update_tab_diagnostic_indicator(file_path, diagnostics)

    def _clear_all_tab_diagnostic_indicators(self) -> None:
        self._get_problems_controller().clear_all_tab_diagnostic_indicators()

    def _update_status_bar_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        self._get_problems_controller().update_status_bar_diagnostics(diagnostics)

    def _render_merged_problems_panel(self) -> None:
        """Rebuild the Problems panel from stored lint + runtime state."""
        self._get_problems_controller().render_merged_problems_panel()

    def _update_problems_tab_title(self, count: int) -> None:
        self._get_problems_controller().update_problems_tab_title(count)

    def _handle_rebuild_intelligence_cache_action(self) -> None:
        deleted = self._rebuild_intelligence_cache()
        if deleted is None:
            return
        if self._loaded_project is not None and self._intelligence_runtime_settings.cache_enabled:
            self._start_symbol_indexing(self._loaded_project.project_root)
        if deleted:
            QMessageBox.information(self, "Rebuild Intelligence Cache", "Cache rebuilt successfully.")
            return
        QMessageBox.information(self, "Rebuild Intelligence Cache", "No existing cache found. Reindex initialized.")

    # ------------------------------------------------------------------
    # Runtime module probe
    # ------------------------------------------------------------------

    def _start_runtime_module_probe(self, *, user_initiated: bool = False) -> None:
        orchestrator = getattr(self, "_diagnostics_orchestrator", None)
        if orchestrator is not None:
            orchestrator.start_runtime_module_probe(user_initiated=user_initiated)
            return

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return probe_and_cache_runtime_modules(state_root=self._state_root)

        def on_success(modules: object) -> None:
            if not isinstance(modules, frozenset):
                if user_initiated:
                    QMessageBox.warning(
                        self,
                        "Refresh Runtime Modules",
                        "Runtime module probe returned an unexpected result type."
                        " See app logs for details.",
                    )
                return
            if not modules:
                self._logger.warning(
                    "Runtime module probe returned an empty module set; unresolved-import diagnostics may be incomplete."
                )
                if user_initiated:
                    QMessageBox.warning(
                        self,
                        "Refresh Runtime Modules",
                        "Runtime module probe returned no modules."
                        " FreeCAD/runtime imports may still show unresolved until probing succeeds.",
                    )
                return
            self._known_runtime_modules = modules
            self._logger.info("Runtime module probe completed: %d modules discovered", len(modules))
            self._relint_open_python_files()

        def on_error(exc: Exception) -> None:
            self._logger.warning("Runtime module probe failed: %s", exc)
            if user_initiated:
                QMessageBox.warning(self, "Refresh Runtime Modules", f"Runtime module probe failed: {exc}")

        self._background_tasks.run(
            key="runtime_module_probe",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _relint_open_python_files(self) -> None:
        """Re-lint all currently open Python file tabs and refresh the problems panel."""
        orchestrator = getattr(self, "_diagnostics_orchestrator", None)
        if orchestrator is not None:
            orchestrator.relint_open_python_files()
            return
        for file_path in self._workspace_controller.open_editor_paths():
            if file_path.lower().endswith(".py"):
                self._render_lint_diagnostics_for_file(file_path, trigger="tab_change")
        self._render_merged_problems_panel()

    def _handle_refresh_runtime_modules_action(self) -> None:
        self._start_runtime_module_probe(user_initiated=True)

    def _handle_python_console_submit(self, command_text: str) -> None:
        if not command_text.strip():
            return
        if not self._repl_manager.is_running:
            self._repl_manager.start()
        try:
            self._repl_manager.send_input(command_text)
        except Exception as exc:
            self._logger.warning("REPL send_input failed: %s", exc)

    def _handle_python_console_interrupt(self) -> None:
        if self._repl_manager.is_running:
            try:
                self._repl_manager.send_input("\x03")
            except Exception as exc:
                self._logger.warning("REPL interrupt failed: %s", exc)

    def _restore_python_console_history(self) -> None:
        if self._python_console_widget is None:
            return
        entries = load_python_console_history(
            self._python_console_history_path,
            max_entries=200,
        )
        self._python_console_widget.set_history(entries)

    def _persist_python_console_history(self) -> None:
        if self._python_console_widget is None:
            return
        try:
            save_python_console_history(
                self._python_console_history_path,
                self._python_console_widget.history_snapshot(),
                max_entries=200,
            )
        except OSError as exc:
            self._logger.warning("Unable to persist python console history: %s", exc)

    def _append_python_console_line(self, text: str, stream: str = "stdout") -> None:
        if self._python_console_widget is None:
            return
        self._python_console_widget.append_output(text, stream)

    def _request_python_console_completion_async(
        self,
        line_buffer: str,
        cursor_offset: int,
        request_generation: int,
        trigger_kind: str,
        trigger_character: str,
    ) -> None:
        """Request live Python Console completions off the UI thread."""
        self._python_console_workflow.request_completion_async(
            line_buffer,
            cursor_offset,
            request_generation,
            trigger_kind,
            trigger_character,
        )

    def _append_debug_output_line(self, text: str) -> None:
        if self._debug_panel is None:
            return
        self._debug_panel.append_output(text)

    def _apply_debug_inspector_event(self) -> None:
        if self._debug_panel is None:
            return
        state = self._debug_session.state
        self._debug_panel.update_from_state(state)

        frame = state.selected_frame
        if state.execution_state == DebugExecutionState.PAUSED and frame is not None:
            if not self._debug_control_workflow.is_debug_navigation_target_allowed(frame.file_path):
                self._clear_debug_execution_indicator()
                return
            self._open_file_at_line(frame.file_path, frame.line_number)
            resolved = str(Path(frame.file_path).expanduser().resolve())
            editor = self._editor_widgets_by_path.get(resolved)
            if editor is not None:
                if self._debug_execution_editor is not None and self._debug_execution_editor is not editor:
                    self._clear_debug_execution_indicator()
                editor.set_debug_execution_line(frame.line_number)
                self._debug_execution_editor = editor
        elif state.execution_state in {DebugExecutionState.RUNNING, DebugExecutionState.EXITED}:
            self._clear_debug_execution_indicator()

    def _clear_debug_execution_indicator(self) -> None:
        if self._debug_execution_editor is None:
            return
        editor = self._debug_execution_editor
        self._debug_execution_editor = None
        try:
            editor.clear_debug_execution_line()
        except RuntimeError:
            # Widget wrapper may already be invalid while the window is closing.
            return

    def _focus_bottom_tab(self, widget: QWidget | None) -> None:
        bottom_tabs = getattr(self, "_bottom_tabs_widget", None)
        if bottom_tabs is None or widget is None:
            return
        index = bottom_tabs.indexOf(widget)
        if index < 0:
            return
        bottom_tabs.setCurrentIndex(index)

    def _focus_run_log_tab(self) -> None:
        self._focus_bottom_tab(self._run_log_panel)

    def _focus_python_console_tab(self) -> None:
        self._focus_bottom_tab(self._python_console_container)

    def _focus_problems_tab(self) -> None:
        self._focus_bottom_tab(self._problems_panel)

    def _set_run_status(self, status: str, *, return_code: int | None = None) -> None:
        status_controller = getattr(self, "_status_controller", None)
        if status_controller is None:
            return
        status_controller.set_run_status(status, return_code=return_code)

    def _refresh_run_action_states(self) -> None:
        self._run_session_controller.refresh_action_states(
            self._menu_registry,
            has_project=self._loaded_project is not None,
            has_active_file=self._has_active_python_file(),
            has_breakpoints=self._debug_control_workflow.breakpoint_store.has_any_breakpoints(),
            debug_execution_state=self._debug_session.state.execution_state,
        )
        if self._menu_registry is None:
            return
        debug_current_test_action = self._menu_registry.action("shell.action.run.debugPytestCurrentFile")
        if debug_current_test_action is not None:
            debug_current_test_action.setEnabled(
                self._loaded_project is not None
                and self._has_active_python_file()
                and not self._run_service.supervisor.is_running()
            )
        run_test_at_cursor_action = self._menu_registry.action("shell.action.run.pytestAtCursor")
        if run_test_at_cursor_action is not None:
            run_test_at_cursor_action.setEnabled(
                self._loaded_project is not None
                and self._has_active_python_file()
                and not self._run_service.supervisor.is_running()
            )
        debug_failed_test_action = self._menu_registry.action("shell.action.run.debugPytestFailed")
        if debug_failed_test_action is not None:
            test_runner_workflow = getattr(self, "_test_runner_workflow", None)
            debug_failed_test_action.setEnabled(
                self._loaded_project is not None
                and test_runner_workflow is not None
                and test_runner_workflow.has_failed_tests()
                and not self._run_service.supervisor.is_running()
            )
        rerun_last_debug_action = self._menu_registry.action("shell.action.run.rerunLastDebugTarget")
        if rerun_last_debug_action is not None:
            rerun_last_debug_action.setEnabled(
                self._run_launch_workflow.has_rerun_target()
                and not self._run_service.supervisor.is_running()
            )
        exception_settings_action = self._menu_registry.action("shell.action.run.debugExceptionStops")
        if exception_settings_action is not None:
            exception_settings_action.setEnabled(
                self._loaded_project is not None and not self._run_service.supervisor.is_running()
            )

    def _has_active_python_file(self) -> bool:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return False
        return Path(active_tab.file_path).suffix.lower() == ".py"

    def _enqueue_run_event(self, event: ProcessEvent) -> None:
        if self._is_shutting_down:
            return
        self._run_event_queue.put(event)

    # -- REPL event queue (separate from script/debug) --------------------

    def _enqueue_repl_output(self, text: str, stream: str) -> None:
        if self._is_shutting_down:
            return
        self._repl_event_queue.put(("output", text, stream))

    def _enqueue_repl_ended(self, return_code: int | None, terminated_by_user: bool) -> None:
        if self._is_shutting_down:
            return
        self._repl_event_queue.put(("ended", return_code, terminated_by_user))

    def _enqueue_repl_started(self) -> None:
        if self._is_shutting_down:
            return
        self._repl_event_queue.put(("started", None, False))

    def _process_queued_repl_events(self) -> None:
        if self._is_shutting_down:
            return
        processed = 0
        while processed < EVENT_QUEUE_BATCH_LIMIT:
            try:
                item = self._repl_event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                kind, arg1, arg2 = item
                if kind == "output":
                    text: str = arg1  # type: ignore[assignment]
                    stream: str = arg2  # type: ignore[assignment]
                    if text:
                        self._append_python_console_line(text, stream=stream)
                elif kind == "started":
                    self._runtime_introspection_coordinator.clear_cache()
                    if self._python_console_widget is not None:
                        self._python_console_widget.set_session_active(True)
                elif kind == "ended":
                    return_code: int | None = arg1  # type: ignore[assignment]
                    terminated_by_user: bool = arg2  # type: ignore[assignment]
                    if self._python_console_widget is not None:
                        self._python_console_widget.set_session_active(False)
                    if not terminated_by_user:
                        exit_detail = describe_exit_code(return_code)
                        if return_code is not None and return_code < 0:
                            self._append_python_console_line(
                                f"[system] Python console process was terminated by {exit_detail}. The script may have crashed in native code.",
                                stream="system",
                            )
                        else:
                            self._append_python_console_line(
                                f"[system] Python console session ended ({exit_detail}).",
                                stream="system",
                            )
            except Exception:
                self._logger.exception("Failed to process Python Console event")
            processed += 1

    def _auto_start_repl(self) -> None:
        self._repl_manager.start()

    def _get_run_output_coordinator(self) -> RunOutputCoordinator:
        coordinator = getattr(self, "_run_output_coordinator", None)
        if coordinator is not None:
            return coordinator
        output_tail = getattr(self, "_active_run_output_tail", None)
        append_output_tail = output_tail.append if output_tail is not None else (lambda _chunk: None)
        coordinator = RunOutputCoordinator(
            is_shutting_down=lambda: self._is_shutting_down,
            get_active_session_mode=lambda: self._run_session_controller.active_session_mode,
            set_active_session_mode=self._run_session_controller.set_active_session_mode,
            get_debug_session=lambda: self._debug_session,
            append_output_tail=append_output_tail,
            append_console_line=lambda text, stream: self._append_console_line(text, stream=stream),
            append_debug_output_line=self._append_debug_output_line,
            apply_debug_inspector_event=self._apply_debug_inspector_event,
            refresh_run_action_states=self._refresh_run_action_states,
            set_run_status=lambda status, return_code=None: self._set_run_status(status, return_code=return_code),
            focus_run_log_tab=self._focus_run_log_tab,
            focus_problems_tab=self._focus_problems_tab,
            set_debug_command_input_enabled=lambda enabled: (
                self._debug_panel.set_command_input_enabled(enabled)
                if self._debug_panel is not None
                else None
            ),
            finalize_run_log=self._finalize_run_log,
            update_problems_from_output=self._update_problems_from_output,
            auto_open_console_on_run_output_enabled=lambda: bool(
                getattr(self, "_auto_open_console_on_run_output", False)
            ),
            auto_open_problems_on_run_failure_enabled=lambda: bool(
                getattr(self, "_auto_open_problems_on_run_failure", False)
            ),
        )
        self._run_output_coordinator = coordinator
        return coordinator

    def _process_queued_run_events(self) -> None:
        if self._is_shutting_down:
            self._drain_run_event_queue()
            return
        processed = 0
        while processed < EVENT_QUEUE_BATCH_LIMIT:
            try:
                event = self._run_event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._apply_run_event(event)
            except Exception:
                self._logger.exception("Failed to process run event")
            processed += 1

    def _apply_run_event(self, event: ProcessEvent) -> None:
        active_session = self._run_session_controller.session_store.active_session
        run_id = active_session.run_id if active_session is not None else None
        mode = active_session.mode if active_session is not None else None
        self._get_run_output_coordinator().apply(event)
        if event.event_type == "output":
            self._event_bus.publish(
                RunProcessOutputEvent(
                    run_id=run_id,
                    mode=mode,
                    stream=event.stream or "stdout",
                    text=event.text or "",
                )
            )
        elif event.event_type == "state":
            self._event_bus.publish(
                RunProcessStateEvent(
                    run_id=run_id,
                    mode=mode,
                    state=event.state,
                    terminated_by_user=event.terminated_by_user,
                )
            )
        elif event.event_type == "exit":
            self._event_bus.publish(
                RunProcessExitEvent(
                    run_id=run_id,
                    mode=mode,
                    return_code=event.return_code,
                    terminated_by_user=event.terminated_by_user,
                )
            )
            transient_entry_file = getattr(self, "_active_transient_entry_file_path", None)
            if transient_entry_file:
                self._run_launch_workflow.delete_transient_entry_file(transient_entry_file)
                self._active_transient_entry_file_path = None

    def _append_console_line(self, text: str, *, stream: str = "stdout") -> None:
        self._console_model.append(stream, text)
        if self._run_log_panel is not None:
            self._run_log_panel.append_live_line(text, stream=stream)

    def _finalize_run_log(self, return_code: int | None = None) -> None:
        panel = getattr(self, "_run_log_panel", None)
        if panel is None:
            return
        active_session = self._run_session_controller.session_store.active_session
        run_info = RunInfo(
            run_id=active_session.run_id if active_session else "",
            mode=active_session.mode if active_session else "",
            entry_file=active_session.entry_file if active_session else "",
            exit_code=return_code,
        )
        active_log_path = self._run_session_controller.session_store.log_path
        log_path_str: str | None = None
        if active_log_path:
            log_path = Path(active_log_path)
            if log_path.exists():
                log_path_str = str(log_path)
        panel.end_run(run_info, log_path=log_path_str)

    def _update_problems_from_output(self) -> list[ProblemEntry]:
        output_text = self._active_run_output_tail.text()
        problems = parse_traceback_problems(output_text)
        run_issues = explain_runtime_message(output_text, workflow="run")
        issue_ids = tuple(issue.issue_id for issue in run_issues)
        if issue_ids != self._latest_run_issue_ids and run_issues:
            summaries = "; ".join(issue.title for issue in run_issues)
            self._append_console_line(
                f"[system] Runtime explanation available: {summaries}. Open Runtime Center for details.",
                stream="system",
            )
        self._latest_run_issue_ids = issue_ids
        self._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=run_issues)
        self._latest_runtime_issue_report = self._build_runtime_issue_report()
        self._set_problems(problems)
        return problems

    def _set_problems(self, problems: list[ProblemEntry]) -> None:
        self._stored_runtime_problems = problems
        self._render_merged_problems_panel()

    def _start_symbol_indexing(self, project_root: str, *, exclude_patterns: list[str] | None = None) -> None:
        if not self._intelligence_runtime_settings.cache_enabled:
            return
        if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
            self._active_symbol_index_worker.cancel()
        self._symbol_index_generation += 1
        generation = self._symbol_index_generation
        started_at = time.perf_counter()
        effective_excludes = exclude_patterns
        if effective_excludes is None and self._loaded_project is not None:
            effective_excludes = compute_effective_excludes(
                self._load_effective_exclude_patterns(self._loaded_project.project_root),
                self._loaded_project.metadata.exclude_patterns,
            )
        self._active_symbol_index_worker = SymbolIndexWorker(
            project_root=project_root,
            cache_db_path=self._symbol_cache_db_path,
            exclude_patterns=effective_excludes or (),
            on_done=lambda count: self._handle_symbol_index_done(project_root, count, started_at, generation),
            on_error=lambda message: self._handle_symbol_index_error(project_root, message, generation),
            should_commit=lambda: generation == self._symbol_index_generation,
        )
        self._active_symbol_index_worker.start()

    def _rebuild_intelligence_cache(self) -> bool | None:
        if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
            self._active_symbol_index_worker.cancel()
        self._symbol_index_generation += 1
        try:
            deleted = rebuild_symbol_cache(self._symbol_cache_db_path)
        except OSError as exc:
            QMessageBox.warning(self, "Rebuild Intelligence Cache", f"Unable to rebuild cache: {exc}")
            return None
        return deleted

    def _handle_symbol_index_done(
        self,
        project_root: str,
        symbol_count: int,
        started_at: float,
        generation: int,
    ) -> None:
        if generation != self._symbol_index_generation:
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if self._intelligence_runtime_settings.metrics_logging_enabled:
            if elapsed_ms > 2500.0:
                self._logger.warning(
                    "Symbol index latency warning: root=%s symbols=%s elapsed_ms=%.2f",
                    project_root,
                    symbol_count,
                    elapsed_ms,
                )
            else:
                self._logger.info(
                    "Symbol index telemetry: root=%s symbols=%s elapsed_ms=%.2f",
                    project_root,
                    symbol_count,
                    elapsed_ms,
                )
        self._dispatch_to_main_thread(lambda: setattr(self, "_active_symbol_index_worker", None))

    def _handle_symbol_index_error(self, project_root: str, message: str, generation: int) -> None:
        if generation != self._symbol_index_generation:
            return
        self._logger.warning("Symbol index failed for %s: %s", project_root, message)
        self._dispatch_to_main_thread(lambda: setattr(self, "_active_symbol_index_worker", None))

    def _clear_problems(self) -> None:
        self._stored_lint_diagnostics.clear()
        self._stored_runtime_problems = []
        self._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=[])
        self._latest_run_issue_ids = ()
        self._latest_runtime_issue_report = self._build_runtime_issue_report()
        if self._problems_panel is not None:
            self._problems_panel.clear()
            self._update_problems_tab_title(0)
        self._clear_all_tab_diagnostic_indicators()

    def _handle_problem_item_activation(self, file_path: str, line_number: int) -> None:
        if not file_path:
            return
        self._open_file_at_line(file_path, line_number, preview=False)

    def _handle_problem_item_preview(self, file_path: str, line_number: int) -> None:
        if not file_path:
            return
        self._open_file_at_line(file_path, line_number, preview=True)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt signature
        decision = self._save_workflow.request_unsaved_changes_decision(
            "exiting",
            scope=DocumentScope.APPLICATION,
            allow_keep_for_next_launch=True,
        )
        if not self._save_workflow.apply_unsaved_changes_decision(decision):
            event.ignore()
            return
        self._is_shutting_down = True
        self._begin_shutdown_teardown()
        self._stop_active_run_before_close()
        if self._status_controller is not None:
            self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
        self._persist_layout_to_settings()
        self._local_history_workflow.persist_session_state()
        self._persist_python_console_history()
        event.accept()

    def _begin_shutdown_teardown(self) -> None:
        self._local_history_workflow.stop_autosave_timer()
        self._auto_save_to_file_timer.stop()
        self._realtime_lint_timer.stop()
        self._project_tree_preview_click_timer.stop()
        self._pending_project_tree_preview_path = None
        self._pending_realtime_lint_file_path = None
        if hasattr(self, "_run_event_timer"):
            self._run_event_timer.stop()
        if hasattr(self, "_repl_event_timer"):
            self._repl_event_timer.stop()
        if hasattr(self, "_external_change_poll_timer"):
            self._external_change_poll_timer.stop()
        if hasattr(self, "_restore_project_timer"):
            self._restore_project_timer.stop()
        if hasattr(self, "_auto_start_repl_timer"):
            self._auto_start_repl_timer.stop()
        if hasattr(self, "_runtime_probe_timer"):
            self._runtime_probe_timer.stop()
        if hasattr(self, "_startup_probe_refresh_timer"):
            self._startup_probe_refresh_timer.stop()
        self._startup_capability_facade.set_refresh_callback(None)
        self._drain_run_event_queue()
        self._background_tasks.cancel_all()
        self._background_tasks.shutdown(wait=False)
        if hasattr(self, "_semantic_session"):
            self._intelligence_controller.cancel_all()
            self._intelligence_controller.shutdown()
        if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
            self._active_symbol_index_worker.cancel()
        self._active_symbol_index_worker = None
        self._clear_debug_execution_indicator()
        if self._debug_panel is not None:
            self._debug_panel.set_command_input_enabled(False)

    def _drain_run_event_queue(self) -> None:
        while True:
            try:
                self._run_event_queue.get_nowait()
            except queue.Empty:
                break

    def _stop_active_run_before_close(self) -> None:
        if self._run_service.supervisor.is_running():
            try:
                self._run_service.stop_run()
            except Exception as exc:
                self._logger.warning("Failed to stop active run during window close: %s", exc)

        self._repl_manager.shutdown()
        self._plugin_runtime_manager.stop()
        self._run_session_controller.clear_active_session_mode()
        self._set_run_status("idle")
        if self._python_console_widget is not None:
            self._python_console_widget.set_session_active(False)

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.type() == QEvent.PaletteChange and not self._shell_theme_workflow.host.is_applying_theme_styles:
            self._shell_theme_workflow.apply_theme_styles()
        super().changeEvent(event)

    def _configure_window_frame(self) -> None:
        configure_window_frame(self)

    def _build_layout_shell(self) -> None:
        build_layout_shell(self)

    def _handle_sidebar_view_changed(self, view_id: str) -> None:
        if self._sidebar_stack is None:
            return
        if view_id == "explorer":
            self._sidebar_stack.setCurrentIndex(0)
        elif view_id == "search":
            self._sidebar_stack.setCurrentIndex(1)
            if self._search_sidebar is not None:
                self._search_sidebar.focus_search()
        elif view_id == "test_explorer":
            self._sidebar_stack.setCurrentIndex(2)

    def _handle_search_open_file_at_line(self, file_path: str, line_number: int) -> None:
        self._open_file_at_line(file_path, line_number, preview=False)

    def _handle_search_preview_file_at_line(self, file_path: str, line_number: int) -> None:
        self._open_file_at_line(file_path, line_number, preview=True)

    def _update_explorer_buttons_enabled(self) -> None:
        has_project = self._loaded_project is not None
        if self._explorer_new_file_btn is not None:
            self._explorer_new_file_btn.setEnabled(has_project)
        if self._explorer_new_folder_btn is not None:
            self._explorer_new_folder_btn.setEnabled(has_project)
        if self._explorer_refresh_btn is not None:
            self._explorer_refresh_btn.setEnabled(has_project)

    def _selected_tree_directory(self) -> str | None:
        """Return the directory path for the selected tree item, or the project root."""
        if self._loaded_project is None:
            return None
        if self._project_tree_widget is None:
            return self._loaded_project.project_root
        current = self._project_tree_widget.currentItem()
        if current is None:
            return self._loaded_project.project_root
        abs_path = str(current.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
        is_dir = bool(current.data(0, TREE_ROLE_IS_DIRECTORY))
        if not abs_path:
            return self._loaded_project.project_root
        return abs_path if is_dir else str(Path(abs_path).parent)

    def _handle_explorer_new_file(self) -> None:
        target = self._selected_tree_directory()
        if target is not None:
            self._handle_tree_new_file(target)

    def _handle_explorer_new_folder(self) -> None:
        target = self._selected_tree_directory()
        if target is not None:
            self._handle_tree_new_folder(target)

    def _handle_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        self._get_project_tree_presenter().handle_item_expanded(item)
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            item.setIcon(0, self._tree_folder_open_icon)

    def _handle_tree_item_collapsed(self, item: QTreeWidgetItem) -> None:
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            item.setIcon(0, self._tree_folder_icon)

    def _populate_project_tree(self, loaded_project: LoadedProject, *, preserve_state: bool = False) -> None:
        self._get_project_tree_presenter().populate(loaded_project, preserve_state=preserve_state)

    def _capture_project_tree_state(self) -> tuple[set[str], set[str]]:
        return self._get_project_tree_presenter().capture_state()

    def _restore_project_tree_state(self, *, expanded_paths: set[str], selected_paths: set[str]) -> None:
        self._get_project_tree_presenter().restore_state(
            expanded_paths=expanded_paths,
            selected_paths=selected_paths,
        )

    def _iter_project_tree_items(self) -> list[QTreeWidgetItem]:
        return self._get_project_tree_presenter().iter_items()

    def _collect_tree_descendants(self, root_item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        return self._get_project_tree_presenter().collect_descendants(root_item)

    def _build_tree_item(self, node: ProjectTreeDisplayNode) -> QTreeWidgetItem:
        return self._get_project_tree_presenter().build_tree_item(node)

    def _handle_project_tree_item_click(self, item: QTreeWidgetItem, _column: int) -> None:
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            return
        absolute_path = str(item.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
        if not absolute_path:
            return
        if not self._editor_enable_preview:
            self._cancel_pending_project_tree_preview()
            self._editor_tab_factory.open_file_in_editor(absolute_path, preview=False)
            return
        self._pending_project_tree_preview_path = absolute_path
        self._project_tree_preview_click_timer.start()

    def _open_pending_project_tree_preview(self) -> None:
        preview_path = self._pending_project_tree_preview_path
        self._pending_project_tree_preview_path = None
        if not preview_path:
            return
        self._editor_tab_factory.open_file_in_editor(preview_path, preview=True)

    def _cancel_pending_project_tree_preview(self) -> None:
        self._pending_project_tree_preview_path = None
        if self._project_tree_preview_click_timer.isActive():
            self._project_tree_preview_click_timer.stop()

    def _handle_project_tree_item_activation(self, item: QTreeWidgetItem, _column: int) -> None:
        self._cancel_pending_project_tree_preview()
        is_directory = bool(item.data(0, TREE_ROLE_IS_DIRECTORY))
        absolute_path = item.data(0, TREE_ROLE_ABSOLUTE_PATH)
        if is_directory or not absolute_path:
            return
        self._editor_tab_factory.open_file_in_editor(str(absolute_path), preview=False)

    def _get_selected_tree_paths(self) -> list[tuple[str, str, bool]]:
        """Return (absolute_path, relative_path, is_directory) for each selected tree item."""
        return self._get_project_tree_presenter().selected_paths()

    def _tree_item_entry(self, item: QTreeWidgetItem | None) -> tuple[str, str, bool] | None:
        return self._get_project_tree_presenter().item_entry(item)

    def _show_project_tree_context_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        self._get_project_tree_presenter().show_context_menu(position)

    def _show_single_item_context_menu(
        self, position: object, entry: tuple[str, str, bool],
    ) -> None:
        self._get_project_tree_presenter().show_single_item_context_menu(position, entry)

    def _show_bulk_context_menu(
        self, position: object, selected: list[tuple[str, str, bool]],
    ) -> None:
        self._get_project_tree_presenter().show_bulk_context_menu(position, selected)

    def _handle_tree_new_file(self, destination_directory: str) -> None:
        file_name, ok = QInputDialog.getText(self, "New File", "File name:", QLineEdit.Normal, "")
        if not ok or not file_name.strip():
            return
        outcome = self._project_tree_action_coordinator.handle_new_file(destination_directory, file_name.strip())
        if outcome.error_message is not None:
            QMessageBox.warning(self, "New File", outcome.error_message)
            return
        if outcome.created_path is not None:
            self._editor_tab_factory.open_file_in_editor(outcome.created_path, preview=False)
            self._show_editor_screen()

    def _handle_tree_new_folder(self, destination_directory: str) -> None:
        folder_name, ok = QInputDialog.getText(self, "New Folder", "Folder name:", QLineEdit.Normal, "")
        if not ok or not folder_name.strip():
            return
        error_message = self._project_tree_action_coordinator.handle_new_folder(destination_directory, folder_name.strip())
        if error_message is not None:
            QMessageBox.warning(self, "New Folder", error_message)

    def _handle_tree_rename(self, source_path: str) -> None:
        source = Path(source_path)
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", QLineEdit.Normal, source.name)
        if not ok or not new_name.strip() or new_name.strip() == source.name:
            return
        error_message = self._project_tree_action_coordinator.handle_rename(source_path, new_name.strip())
        if error_message is not None:
            QMessageBox.warning(self, "Rename", error_message)

    def _handle_project_tree_delete_key(self) -> None:
        selected = self._get_selected_tree_paths()
        if not selected:
            return
        if len(selected) == 1:
            self._handle_tree_delete(selected[0][0])
        else:
            self._handle_tree_bulk_delete([entry[0] for entry in selected])

    def _handle_tree_delete(self, target_path: str) -> None:
        self._project_tree_action_workflow.delete_paths(target_path)

    def _handle_tree_duplicate(self, source_path: str) -> None:
        error_message = self._project_tree_action_coordinator.handle_duplicate(source_path)
        if error_message is not None:
            QMessageBox.warning(self, "Duplicate", error_message)

    def _handle_tree_bulk_delete(self, paths: list[str]) -> None:
        self._project_tree_action_workflow.bulk_delete(paths)

    def _handle_tree_bulk_duplicate(self, paths: list[str]) -> None:
        failed = self._project_tree_action_coordinator.handle_bulk_duplicate(paths)
        if failed:
            QMessageBox.warning(self, "Duplicate", "\n".join(failed))

    def _handle_tree_paste(self, destination_directory: str) -> None:
        failed, next_paths, next_cut = self._project_tree_action_coordinator.handle_paste(
            destination_directory=destination_directory,
            clipboard_paths=self._tree_clipboard_paths,
            clipboard_cut=self._tree_clipboard_cut,
        )
        self._tree_clipboard_paths = next_paths
        self._tree_clipboard_cut = next_cut
        if failed:
            QMessageBox.warning(self, "Paste", "\n".join(failed))

    def _handle_project_tree_drop(self, source_path: str, target_path: str) -> bool:
        error_message = self._project_tree_action_coordinator.handle_drop_move(source_path, target_path)
        if error_message is not None:
            QMessageBox.warning(self, "Move", error_message)
            return False
        return True

    def _reveal_path_in_file_manager(self, path: str) -> None:
        target = Path(path).expanduser().resolve()
        reveal_target = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(reveal_target)))

    def _release_editor_widget(self, widget: CodeEditorWidget) -> None:
        if self._debug_execution_editor is widget:
            self._clear_debug_execution_indicator()
        markdown_panes = getattr(self, "_markdown_panes_by_path", {})
        for file_path, markdown_pane in list(markdown_panes.items()):
            if markdown_pane.source_editor() is widget:
                markdown_panes.pop(file_path, None)
                markdown_pane.deleteLater()
                return
        widget.deleteLater()

    def _close_deleted_editor_paths(self, deleted_path: str) -> None:
        self._project_tree_action_coordinator.close_deleted_editor_paths(deleted_path)

    def _apply_path_move_updates(self, source_path: str, destination_path: str) -> None:
        self._project_tree_action_coordinator.apply_path_move_updates(source_path, destination_path)

    def _update_widget_language_for_path(self, widget: CodeEditorWidget, new_path: str) -> None:
        widget.set_language_for_path(new_path)
        markdown_panes = getattr(self, "_markdown_panes_by_path", {})
        for old_path, markdown_pane in list(markdown_panes.items()):
            if markdown_pane.source_editor() is widget:
                markdown_panes.pop(old_path, None)
                if is_markdown_path(new_path):
                    markdown_pane.set_file_path(new_path)
                    markdown_panes[new_path] = markdown_pane
                break

    def _update_tab_path_and_name(self, tab_index: int, new_path: str) -> None:
        if self._editor_tabs_widget is None:
            return
        self._editor_tabs_widget.setTabToolTip(tab_index, new_path)
        self._refresh_tab_presentation(new_path)

    def _maybe_rewrite_imports_for_move(self, source_path: str, destination_path: str) -> None:
        self._project_tree_controller.maybe_rewrite_imports_for_move(
            project_root=None if self._loaded_project is None else self._loaded_project.project_root,
            source_path=source_path,
            destination_path=destination_path,
            resolve_policy_for_operation=self._resolve_import_update_policy_for_operation,
            request_confirmation=self._request_import_rewrite_confirmation,
            show_warning=lambda details: self._show_import_update_warning(details),
            on_applied=self._handle_import_rewrites_applied,
        )

    def _handle_import_rewrites_applied(self, previews) -> None:  # type: ignore[no-untyped-def]
        payloads = {preview.file_path: preview.updated_content for preview in previews}
        self._local_history_workflow.record_transaction(
            payloads,
            source="import_rewrite",
            label="Update imports after move/rename",
        )
        self._refresh_open_tabs_from_disk(sorted(payloads.keys()))

    def _request_import_rewrite_confirmation(self, message: str) -> bool:
        answer = QMessageBox.question(
            self,
            "Update imports?",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return answer == QMessageBox.Yes

    def _show_import_update_warning(self, details: str) -> None:
        QMessageBox.warning(self, "Import update failed", details)

    def _resolve_import_update_policy_for_operation(self) -> ImportUpdatePolicy:
        if self._import_update_policy != ImportUpdatePolicy.ASK:
            return self._import_update_policy

        labels = [
            ("Ask every time (this operation only)", ImportUpdatePolicy.ASK),
            ("Always update imports", ImportUpdatePolicy.ALWAYS),
            ("Never update imports", ImportUpdatePolicy.NEVER),
        ]
        selected_label, ok = QInputDialog.getItem(
            self,
            "Import Update Policy",
            "Choose import update behavior:",
            [label for label, _ in labels],
            0,
            editable=False,
        )
        if not ok:
            return ImportUpdatePolicy.NEVER
        selected_policy = next(policy for label, policy in labels if label == selected_label)
        if selected_policy in {ImportUpdatePolicy.ALWAYS, ImportUpdatePolicy.NEVER}:
            persist = QMessageBox.question(
                self,
                "Remember preference?",
                "Use this choice as default for future moves/renames?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if persist == QMessageBox.Yes:
                self._save_import_update_policy(selected_policy)
        return selected_policy

    def _refresh_project_tree_from_disk(self) -> None:
        if self._loaded_project is None:
            return
        self._loaded_project = open_project(
            self._loaded_project.project_root,
            exclude_patterns=self._load_effective_exclude_patterns(self._loaded_project.project_root),
        )
        self._populate_project_tree(self._loaded_project, preserve_state=True)
        if self._search_sidebar is not None:
            self._search_sidebar.set_project_root(self._loaded_project.project_root)
            self._search_sidebar.set_exclude_patterns(
                compute_effective_excludes(
                    self._load_effective_exclude_patterns(self._loaded_project.project_root),
                    self._loaded_project.metadata.exclude_patterns,
                )
            )
        self._project_tree_structure_signature = _filter_tree_signature_entries(
            tuple(entry.relative_path for entry in self._loaded_project.entries)
        )

    def _reload_current_project(self) -> None:
        if self._loaded_project is None:
            return
        self._loaded_project = open_project(
            self._loaded_project.project_root,
            exclude_patterns=self._load_effective_exclude_patterns(self._loaded_project.project_root),
        )
        self._plugin_activation_workflow.reload()
        self._refresh_python_tooling_status()
        self._populate_project_tree(self._loaded_project, preserve_state=True)
        if self._search_sidebar is not None:
            self._search_sidebar.set_project_root(self._loaded_project.project_root)
            self._search_sidebar.set_exclude_patterns(
                compute_effective_excludes(
                    self._load_effective_exclude_patterns(self._loaded_project.project_root),
                    self._loaded_project.metadata.exclude_patterns,
                )
            )
        self._project_tree_structure_signature = _filter_tree_signature_entries(
            tuple(entry.relative_path for entry in self._loaded_project.entries)
        )
        effective_excludes = compute_effective_excludes(
            self._load_effective_exclude_patterns(self._loaded_project.project_root),
            self._loaded_project.metadata.exclude_patterns,
        )
        self._start_symbol_indexing(self._loaded_project.project_root, exclude_patterns=effective_excludes)
        test_runner_workflow = getattr(self, "_test_runner_workflow", None)
        if test_runner_workflow is not None:
            test_runner_workflow.refresh_discovery()

    def _open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        if not self._editor_tab_factory.open_file_in_editor(file_path, preview=preview):
            return
        editor_widget = self._editor_widgets_by_path.get(str(Path(file_path).expanduser().resolve()))
        if editor_widget is None or line_number is None:
            return
        editor_widget.go_to_line(line_number)

    def _refresh_outline_for_active_tab(self) -> None:
        if self._outline_panel is None:
            return
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            self._outline_panel.set_unsupported_language("python")
            return
        file_path = active_tab.file_path
        if Path(file_path).suffix.lower() not in {".py", ".pyw", ".pyi"}:
            self._outline_panel.set_unsupported_language(
                Path(file_path).suffix.lstrip(".") or "this"
            )
            self._outline_symbols_by_path.pop(file_path, None)
            return
        editor_widget = self._editor_widgets_by_path.get(
            str(Path(file_path).expanduser().resolve())
        )
        source = editor_widget.toPlainText() if editor_widget is not None else active_tab.current_content
        symbols = build_outline_from_source(source or "")
        self._outline_symbols_by_path[file_path] = symbols
        self._outline_panel.set_outline(symbols, file_path)
        if editor_widget is not None and self._outline_follow_cursor:
            line_number = editor_widget.textCursor().blockNumber() + 1
            self._outline_panel.highlight_symbol_at_line(line_number)

    def _handle_outline_symbol_activated(self, file_path: str, line_number: int) -> None:
        self._open_file_at_line(file_path, line_number)

    def _tab_index_for_path(self, file_path: str) -> int:
        return self._get_editor_tabs_coordinator().tab_index_for_path(file_path)

    def _remove_tab_widget_for_path(self, file_path: str) -> None:
        if self._editor_tabs_widget is None:
            return
        tab_index = self._tab_index_for_path(file_path)
        if tab_index < 0:
            return
        self._editor_tabs_widget.removeTab(tab_index)
        widget = self._workspace_controller.pop_editor(file_path)
        if widget is not None:
            self._release_editor_widget(widget)
        self._indent_source_by_path.pop(file_path, None)
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        if self._editor_tabs_widget.count() == 0 and self._status_controller is not None:
            self._status_controller.set_indent_status(style=None, size=None, source=None)

    def _refresh_tab_presentation(self, file_path: str) -> None:
        self._get_editor_tabs_coordinator().refresh_tab_presentation(file_path)

    def _promote_preview_tab(self, file_path: str) -> bool:
        return self._get_editor_tabs_coordinator().promote_preview_tab(file_path)

    def _promote_existing_preview_tab(self) -> bool:
        return self._get_editor_tabs_coordinator().promote_existing_preview_tab()

    def _active_markdown_pane(self) -> MarkdownEditorPane | None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return None
        return self._markdown_panes_by_path.get(active_tab.file_path)

    def _set_active_markdown_mode(self, mode: str) -> None:
        markdown_pane = self._active_markdown_pane()
        if markdown_pane is None:
            return
        markdown_pane.set_mode(mode)
        self._refresh_markdown_action_states()

    def _handle_markdown_show_source_action(self) -> None:
        self._set_active_markdown_mode(MarkdownPreviewMode.SOURCE)

    def _handle_markdown_show_preview_action(self) -> None:
        self._set_active_markdown_mode(MarkdownPreviewMode.PREVIEW)

    def _handle_markdown_show_split_action(self) -> None:
        self._set_active_markdown_mode(MarkdownPreviewMode.SPLIT)

    def _handle_markdown_toggle_preview_action(self) -> None:
        markdown_pane = self._active_markdown_pane()
        if markdown_pane is None:
            return
        markdown_pane.toggle_preview()
        self._refresh_markdown_action_states()

    def _refresh_markdown_action_states(self) -> None:
        if self._menu_registry is None:
            return
        markdown_pane = self._active_markdown_pane()
        enabled = markdown_pane is not None
        for action_id in (
            "shell.action.view.markdownTogglePreview",
            "shell.action.view.markdownShowSource",
            "shell.action.view.markdownShowPreview",
            "shell.action.view.markdownShowSplit",
        ):
            action = self._menu_registry.action(action_id)
            if action is not None:
                action.setEnabled(enabled)

    def _handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        if self._editor_manager.get_tab(file_path) is None:
            return
        self._advance_editor_buffer_revision(file_path)
        tab_state = self._editor_manager.update_tab_content(file_path, editor_widget.toPlainText())
        if tab_state.is_preview and tab_state.is_dirty:
            self._promote_preview_tab(file_path)
            refreshed_state = self._editor_manager.get_tab(file_path)
            if refreshed_state is not None:
                tab_state = refreshed_state
        if self._editor_tabs_widget is None:
            return

        tab_index = self._tab_index_for_path(tab_state.file_path)
        if tab_index < 0:
            return
        self._refresh_tab_presentation(tab_state.file_path)
        if tab_state.is_dirty:
            self._local_history_workflow.schedule_autosave(tab_state.file_path, tab_state.current_content)
            if self._editor_auto_save:
                self._auto_save_to_file_timer.start()
        else:
            self._local_history_workflow.discard_pending_autosave(tab_state.file_path)
            self._local_history_workflow.delete_draft(tab_state.file_path)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(tab_state.file_path)
        if not self._is_shutting_down:
            self._diagnostics_orchestrator.schedule_realtime_lint(tab_state.file_path)
        self._outline_refresh_timer.start()

    def _handle_editor_cursor_position_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None or self._status_controller is None:
            return
        line_number = editor_widget.textCursor().blockNumber() + 1
        self._status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=line_number,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )
        if self._outline_panel is not None and self._outline_follow_cursor:
            self._outline_panel.highlight_symbol_at_line(line_number)

    def _update_editor_status_for_path(self, file_path: str) -> None:
        if self._status_controller is None:
            return
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._editor_widgets_by_path.get(file_path)
        if tab_state is None or editor_widget is None:
            self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            return
        self._status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=editor_widget.textCursor().blockNumber() + 1,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )
    def _active_editor_widget(self) -> CodeEditorWidget | None:
        return cast(Optional[CodeEditorWidget], self._get_editor_tabs_coordinator().active_editor_widget())

    def _advance_editor_buffer_revision(self, file_path: str) -> int:
        return self._get_editor_tabs_coordinator().advance_buffer_revision(file_path)

    def _editor_buffer_revision(self, file_path: str) -> int | None:
        return self._get_editor_tabs_coordinator().buffer_revision(file_path)

    def _request_completion_item_resolve_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        item: CompletionItem,
        source_text: str,
        cursor_position: int,
        request_generation: int,
    ) -> None:
        requested_revision = self._editor_buffer_revision(file_path)
        request = CompletionResolveRequest(
            item=item,
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if self._loaded_project is None else self._loaded_project.project_root,
            context_fingerprint=item.context_fingerprint,
            buffer_revision=requested_revision,
            request_generation=request_generation,
        )

        def on_success(result: CompletionResolveResult) -> None:
            active_widget = self._editor_widgets_by_path.get(file_path)
            if active_widget is not editor_widget:
                return
            if self._editor_buffer_revision(file_path) != result.buffer_revision:
                return
            editor_widget.show_resolved_completion_item_for_request(
                request_generation=result.request_generation,
                item=result.item,
            )

        def on_error(exc: Exception) -> None:
            self._logger.warning("Completion item resolve failed for %s: %s", file_path, exc)

        self._intelligence_controller.request_completion_resolve(
            request=request,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_editor_tab_changed(self, tab_index: int) -> None:
        if tab_index < 0 or self._editor_tabs_widget is None:
            return

        tab_path = self._editor_tabs_widget.tabToolTip(tab_index)
        if not tab_path:
            return
        self._editor_manager.set_active_file(tab_path)
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        self._refresh_markdown_action_states()
        self._update_editor_status_for_path(tab_path)
        self._update_indent_status_for_path(tab_path)
        self._check_for_external_file_change(tab_path)
        self._render_lint_diagnostics_for_file(tab_path, trigger="tab_change")
        self._outline_refresh_timer.stop()
        self._refresh_outline_for_active_tab()
        if not self._suppress_tree_reveal:
            self._get_project_tree_presenter().reveal_path(tab_path)

    def _handle_editor_tab_header_double_click(self, tab_index: int) -> None:
        if self._editor_tabs_widget is None:
            return
        file_path = self._editor_tabs_widget.tabToolTip(tab_index)
        if not file_path:
            return
        self._promote_preview_tab(file_path)

    def _handle_keep_preview_open_shortcut(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return
        if not active_tab.is_preview:
            return
        self._promote_preview_tab(active_tab.file_path)

    def _show_editor_tab_context_menu(self, position: QPoint) -> None:
        if self._editor_tabs_widget is None:
            return
        tab_bar = self._editor_tabs_widget.tabBar()
        tab_index = tab_bar.tabAt(position)
        if tab_index < 0:
            return
        file_path = self._editor_tabs_widget.tabToolTip(tab_index)
        if not file_path:
            return

        menu = QMenu(self)
        markdown_source_action = None
        markdown_preview_action = None
        markdown_split_action = None
        markdown_pane = self._markdown_panes_by_path.get(file_path)
        if markdown_pane is not None:
            markdown_source_action = menu.addAction("Markdown: Show Source")
            markdown_preview_action = menu.addAction("Markdown: Show Preview")
            markdown_split_action = menu.addAction("Markdown: Show Split View")
            menu.addSeparator()
        local_history_action = menu.addAction("Local History...")
        menu.addSeparator()
        close_action = menu.addAction("Close")
        chosen = menu.exec_(tab_bar.mapToGlobal(position))
        if markdown_pane is not None and chosen == markdown_source_action:
            markdown_pane.set_mode(MarkdownPreviewMode.SOURCE)
            self._refresh_markdown_action_states()
        elif markdown_pane is not None and chosen == markdown_preview_action:
            markdown_pane.set_mode(MarkdownPreviewMode.PREVIEW)
            self._refresh_markdown_action_states()
        elif markdown_pane is not None and chosen == markdown_split_action:
            markdown_pane.set_mode(MarkdownPreviewMode.SPLIT)
            self._refresh_markdown_action_states()
        elif chosen == local_history_action:
            self._local_history_workflow.show_local_history_for_path(file_path)
        elif chosen == close_action:
            self._handle_tab_close_requested(tab_index)

    def _handle_tab_close_requested(self, tab_index: int) -> None:
        if self._editor_tabs_widget is None:
            return
        file_path = self._editor_tabs_widget.tabToolTip(tab_index)
        if not file_path:
            return

        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is not None and tab_state.is_dirty:
            decision = self._save_workflow.request_unsaved_changes_decision(
                "closing this tab",
                scope=DocumentScope.TAB,
                allow_keep_for_next_launch=False,
                dirty_buffers=(tab_state,),
            )
            if decision.intent is DocumentCloseIntent.CANCEL:
                return
            if not self._save_workflow.apply_unsaved_changes_decision(decision):
                return

        self._editor_tabs_widget.removeTab(tab_index)
        widget = self._workspace_controller.pop_editor(file_path)
        if widget is not None:
            self._release_editor_widget(widget)
        self._editor_manager.close_file(file_path)
        self._debug_control_workflow.breakpoint_store.clear_file(file_path)
        self._stored_lint_diagnostics.pop(file_path, None)
        self._render_merged_problems_panel()
        self._debug_control_workflow.refresh_breakpoints_list()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        self._refresh_markdown_action_states()

    def _close_active_tab(self) -> None:
        if self._editor_tabs_widget is None:
            return
        tab_index = self._editor_tabs_widget.currentIndex()
        if tab_index >= 0:
            self._handle_tab_close_requested(tab_index)

    def _reset_editor_tabs(self) -> None:
        if self._editor_tabs_widget is not None:
            for path in list(self._workspace_controller.open_editor_paths()):
                widget = self._workspace_controller.pop_editor(path)
                if widget is not None:
                    self._release_editor_widget(widget)
            self._editor_tabs_widget.clear()
        self._local_history_workflow.stop_autosave_timer()
        self._auto_save_to_file_timer.stop()
        self._realtime_lint_timer.stop()
        self._local_history_workflow.clear_pending_autosaves()
        self._pending_realtime_lint_file_path = None
        self._clear_debug_execution_indicator()
        self._workspace_controller.clear()
        self._editor_manager = EditorManager()
        self._markdown_panes_by_path.clear()
        self._local_history_workflow.set_editor_manager(self._editor_manager)
        self._indent_source_by_path.clear()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        self._refresh_markdown_action_states()
        if self._status_controller is not None:
            self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            self._status_controller.set_indent_status(style=None, size=None, source=None)

    def _effective_font_size(self) -> int:
        return max(8, min(72, self._editor_font_size + self._zoom_delta))

    def _apply_editor_preferences_to_open_editors(self) -> None:
        effective_size = self._effective_font_size()
        for file_path, editor_widget in self._editor_widgets_by_path.items():
            editor_widget.set_editor_preferences(
                tab_width=self._editor_tab_width,
                font_point_size=effective_size,
                font_family=self._editor_font_family,
                indent_style=self._editor_indent_style,
                indent_size=self._editor_indent_size,
                hover_tooltip_enabled=self._editor_hover_tooltip_enabled,
                auto_reindent_flat_python_paste=self._editor_auto_reindent_flat_python_paste,
            )
            self._apply_detected_indentation_for_widget(file_path, editor_widget, editor_widget.toPlainText())
            editor_widget.set_completion_preferences(
                enabled=self._completion_enabled,
                auto_trigger=self._completion_auto_trigger,
                min_chars=self._completion_min_chars,
            )

    def _apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        for editor_widget in self._editor_widgets_by_path.values():
            self._apply_runtime_intelligence_preferences_to_editor(editor_widget)

    def _apply_runtime_intelligence_preferences_to_editor(self, editor_widget: CodeEditorWidget) -> None:
        editor_widget.set_metrics_logging_enabled(self._intelligence_runtime_settings.metrics_logging_enabled)
        editor_widget.set_highlighting_policy(
            adaptive_mode=self._intelligence_runtime_settings.highlighting_adaptive_mode,
            reduced_threshold_chars=self._intelligence_runtime_settings.highlighting_reduced_threshold_chars,
            lexical_only_threshold_chars=self._intelligence_runtime_settings.highlighting_lexical_only_threshold_chars,
        )

    def _apply_detected_indentation_for_widget(
        self,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
    ) -> None:
        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        editorconfig_indent = resolve_editorconfig_indentation(file_path, project_root=project_root)
        if editorconfig_indent is not None:
            effective_style = editorconfig_indent.indent_style
            effective_size = max(1, editorconfig_indent.indent_size)
            editor_widget.set_editor_preferences(
                tab_width=max(1, editorconfig_indent.tab_width),
                font_point_size=self._effective_font_size(),
                font_family=self._editor_font_family,
                indent_style=effective_style,
                indent_size=effective_size,
                hover_tooltip_enabled=self._editor_hover_tooltip_enabled,
                auto_reindent_flat_python_paste=self._editor_auto_reindent_flat_python_paste,
            )
            self._record_indent_source(file_path, effective_style, effective_size, "editorconfig")
            return
        if not self._editor_detect_indentation_from_file or not file_path.lower().endswith(
            (".py", ".json", ".md", ".txt")
        ):
            self._record_indent_source(
                file_path, self._editor_indent_style, self._editor_indent_size, "user"
            )
            return
        detected = detect_indentation_style_and_size(source_text)
        if detected is None:
            self._record_indent_source(
                file_path, self._editor_indent_style, self._editor_indent_size, "user"
            )
            return
        style, size = detected
        editor_widget.set_editor_preferences(
            tab_width=self._editor_tab_width,
            font_point_size=self._effective_font_size(),
            font_family=self._editor_font_family,
            indent_style=style,
            indent_size=size,
            hover_tooltip_enabled=self._editor_hover_tooltip_enabled,
            auto_reindent_flat_python_paste=self._editor_auto_reindent_flat_python_paste,
        )
        self._record_indent_source(file_path, style, size, "auto")

    def _record_indent_source(
        self,
        file_path: str,
        style: str,
        size: int,
        source: str,
    ) -> None:
        self._indent_source_by_path[file_path] = (style, int(size), source)
        active_tab = self._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path == file_path:
            self._update_indent_status_for_path(file_path)

    def _update_indent_status_for_path(self, file_path: str | None) -> None:
        if self._status_controller is None:
            return
        if file_path is None:
            self._status_controller.set_indent_status(style=None, size=None, source=None)
            return
        record = self._indent_source_by_path.get(file_path)
        if record is None:
            self._status_controller.set_indent_status(style=None, size=None, source=None)
            return
        style, size, source = record
        self._status_controller.set_indent_status(style=style, size=size, source=source)

    def _refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        for file_path in file_paths:
            tab_state = self._editor_manager.get_tab(file_path)
            editor_widget = self._editor_widgets_by_path.get(file_path)
            if tab_state is None or editor_widget is None:
                continue
            try:
                refreshed = Path(file_path).read_text(encoding="utf-8")
            except OSError:
                continue
            editor_widget.blockSignals(True)
            editor_widget.setPlainText(refreshed)
            editor_widget.blockSignals(False)
            self._advance_editor_buffer_revision(file_path)
            self._apply_detected_indentation_for_widget(file_path, editor_widget, refreshed)
            updated_tab = self._editor_manager.update_tab_content(file_path, refreshed)
            updated_tab.mark_saved(last_known_mtime=self._editor_manager.current_disk_mtime(file_path))
            tab_index = self._tab_index_for_path(file_path)
            if self._editor_tabs_widget is not None and tab_index >= 0:
                self._refresh_tab_presentation(file_path)
        self._refresh_save_action_states()

    def _check_for_external_file_change(self, file_path: str) -> None:
        self._external_file_change_workflow.check_and_handle(file_path)

    def _poll_external_file_changes(self) -> None:
        stale_paths = self._editor_manager.stale_open_paths()
        if stale_paths:
            active_tab = self._editor_manager.active_tab()
            if active_tab is not None and active_tab.file_path in stale_paths:
                self._check_for_external_file_change(active_tab.file_path)

        loaded_project = self._loaded_project
        if loaded_project is None:
            return
        current_signature = self._scan_project_tree_signature(loaded_project)
        previous_signature = self._project_tree_structure_signature
        if previous_signature is None:
            self._project_tree_structure_signature = current_signature
            return
        if current_signature == previous_signature:
            return
        self._project_tree_structure_signature = current_signature
        self._reload_current_project()

    def _scan_project_tree_signature(self, loaded_project: LoadedProject) -> tuple[str, ...]:
        layered_excludes = self._load_effective_exclude_patterns(loaded_project.project_root)
        effective_excludes = compute_effective_excludes(
            layered_excludes,
            loaded_project.metadata.exclude_patterns,
        )
        entries = enumerate_project_entries(
            loaded_project.project_root,
            exclude_patterns=effective_excludes,
        )
        return _filter_tree_signature_entries(tuple(entry.relative_path for entry in entries))


def _enable_auto_reindent_flat_python_paste_in_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Settings-service updater that flips ``editor.auto_reindent_flat_python_paste`` on."""
    updated = dict(payload)
    editor_section_raw = updated.get(constants.UI_EDITOR_SETTINGS_KEY)
    editor_section: dict[str, Any] = (
        dict(editor_section_raw) if isinstance(editor_section_raw, dict) else {}
    )
    editor_section[constants.UI_EDITOR_AUTO_REINDENT_FLAT_PYTHON_PASTE_KEY] = True
    updated[constants.UI_EDITOR_SETTINGS_KEY] = editor_section
    return updated


def _flat_python_repair_status_message(result: FlatPythonIndentRepairResult) -> str:
    if result.reason == "not a flat Python paste":
        return "Inserted unchanged: not a flat Python paste."
    if result.reason == "no selection or recent paste":
        return "Select pasted Python lines before running re-indent."
    if result.changed and result.parse_ok:
        return "Re-indented flat Python paste."
    if result.changed:
        return f"Applied best-effort Python re-indent ({result.confidence} confidence)."
    return "Flat Python indentation did not need changes."
