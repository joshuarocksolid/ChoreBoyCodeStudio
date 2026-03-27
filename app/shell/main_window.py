"""Main Qt shell composition and top-level workflow wiring."""

from __future__ import annotations

import queue
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from typing import Any, Callable, Mapping, Optional, TypeVar, cast

from PySide2.QtCore import QEvent, QPoint, QSize, QTimer, Qt
from PySide2.QtGui import QCloseEvent, QColor, QFont, QFontMetrics, QIcon, QKeySequence, QMouseEvent
from PySide2.QtWidgets import (
    QApplication,
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
    QTabBar,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QStyle,
    QStyleOptionTab,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.paths import global_cache_dir, global_python_console_history_path, project_logs_dir
from app.bootstrap.runtime_module_probe import load_cached_runtime_modules, probe_and_cache_runtime_modules
from app.core import constants
from app.core.errors import AppValidationError, ProjectManifestValidationError
from app.core.models import CapabilityProbeReport, LoadedProject, RuntimeIssue, RuntimeIssueReport
from app.debug.debug_breakpoints import build_breakpoint, breakpoint_key
from app.debug.debug_command_service import (
    continue_command,
    evaluate_command,
    expand_variable_command,
    select_frame_command,
    step_into_command,
    step_out_command,
    step_over_command,
    update_breakpoints_command,
    update_exception_policy_command,
)
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugExecutionState, DebugSourceMap
from app.debug.debug_session import DebugSession
from app.intelligence.code_actions import apply_quick_fixes, plan_safe_fixes_for_file
from app.intelligence.cache_controls import (
    IntelligenceRuntimeSettings,
    rebuild_symbol_cache,
    should_refresh_index_after_save,
)
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity, analyze_python_file, find_unresolved_imports
from app.intelligence.lint_profile import LINT_SEVERITY_ERROR, LINT_SEVERITY_INFO, resolve_lint_rule_settings
from app.intelligence.outline_service import build_file_outline
from app.intelligence.semantic_session import SemanticSession
from app.intelligence.symbol_index import SymbolIndexWorker
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_service import CompletionRequest
from app.editors.editor_manager import EditorManager, OpenedTabResult
from app.editors.editor_tab import EditorTabState
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editorconfig import resolve_editorconfig_indentation
from app.editors.find_replace_bar import FindOptions, FindReplaceBar
from app.editors.quick_open_dialog import QuickOpenDialog
from app.editors.formatting_service import format_text_basic
from app.editors.indentation import detect_indentation_style_and_size
from app.editors.quick_open import QuickOpenCandidate
from app.editors.search_panel import SearchMatch, SearchWorker
from app.persistence.autosave_store import AutosaveStore
from app.persistence.history_models import LocalHistoryFileSummary
from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.settings_service import SettingsService
from app.persistence.settings_store import project_settings_has_overrides
from app.run.console_model import ConsoleModel
from app.run.exit_status import describe_exit_code
from app.run.output_tail_buffer import OutputTailBuffer
from app.run.problem_parser import ProblemEntry, parse_traceback_problems
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService
from app.run.test_runner_service import PytestRunResult, run_pytest_project, run_pytest_target
from app.run.runtime_launch import (
    build_runpy_bootstrap_payload,
    is_freecad_runtime_executable,
    resolve_runtime_executable,
)
from app.shell.run_log_panel import RunInfo, RunLogPanel
from app.packaging.config import resolve_project_package_config
from app.packaging.layout import resolve_entry_path
from app.packaging.packager import package_project
from app.plugins.api_broker import PluginApiBroker
from app.plugins.builtin_workflows import register_builtin_workflow_providers
from app.plugins.contributions import DeclarativeContributionManager
from app.plugins.discovery import discover_installed_plugins
from app.plugins.project_config import load_project_plugin_config
from app.plugins.registry_store import (
    clear_registry_entry_failures,
    load_plugin_registry,
    record_registry_entry_failure,
)
from app.plugins.runtime_manager import PluginRuntimeManager
from app.plugins.security_policy import merge_plugin_safe_mode, plugin_safe_mode_enabled
from app.plugins.workflow_adapters import (
    analyze_python_with_workflow,
    format_python_with_workflow,
    list_templates_with_workflow,
    organize_imports_with_workflow,
    package_project_with_workflow,
    run_pytest_with_workflow,
)
from app.plugins.workflow_broker import WorkflowBroker
from app.plugins.workflow_catalog import WorkflowProviderCatalog
from app.support.diagnostics import ProjectHealthReport, run_project_health_check
from app.support.runtime_explainer import (
    HELP_TOPIC_GETTING_STARTED,
    HELP_TOPIC_HEADLESS_NOTES,
    build_import_issue_report,
    build_project_health_issue_report,
    build_startup_issue_report,
    explain_runtime_message,
    merge_runtime_issue_reports,
)
from app.support.preflight import build_run_preflight
from app.support.support_bundle import build_support_bundle
from app.templates.template_service import TemplateMetadata, TemplateService
from app.examples.example_project_service import ExampleProjectService
from app.shell.layout_persistence import (
    DEFAULT_TOP_SPLITTER_SIZES,
    DEFAULT_VERTICAL_SPLITTER_SIZES,
    ShellLayoutState,
    merge_layout_into_settings,
    parse_shell_layout_state,
)
from app.shell.history_restore_picker import (
    HISTORY_RESTORE_ACTION_OPEN_TIMELINE,
    HISTORY_RESTORE_ACTION_RESTORE_LATEST,
    HistoryRestorePickerDialog,
)
from app.shell.local_history_dialog import DraftRecoveryDialog, LocalHistoryDialog
from app.shell.session_persistence import SessionFileState, SessionState, load_session_file, save_session_file
from app.shell.settings_dialog import SettingsDialog
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
from app.shell.activity_bar import ActivityBar
from app.shell.icons import explorer_icon, search_icon
from app.shell.debug_panel_widget import DebugPanelWidget
from app.shell.problems_panel import ProblemsPanel, ResultItem, tab_diagnostic_icon
from app.shell.plugins_panel import PluginManagerDialog
from app.shell.python_console_widget import PythonConsoleWidget
from app.shell.package_wizard_dialog import PackageProjectWizard
from app.shell.python_console_history import load_python_console_history, save_python_console_history
from app.shell.runtime_center_dialog import RuntimeCenterDialog
from app.shell.search_sidebar_widget import SearchSidebarWidget
from app.shell.style_sheet import build_shell_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, apply_syntax_token_overrides, tokens_from_palette
from app.shell.toolbar_icons import ensure_tab_close_icons
from app.project.project_tree import build_project_tree
from app.project.run_configs import (
    RunConfiguration,
    env_overrides_to_text,
)
from app.project.project_tree_widget import ProjectTreeWidget
from app.project.project_tree_presenter import ProjectTreeDisplayNode, build_project_tree_display
from app.project.file_excludes import (
    compute_effective_excludes,
    parse_global_exclude_patterns,
    parse_project_exclude_patterns,
)
from app.python_tools.black_adapter import format_python_text
from app.python_tools.config import resolve_python_tooling_settings
from app.python_tools.isort_adapter import organize_imports_text
from app.python_tools.models import (
    PYTHON_TOOLING_STATUS_CONFIG_ERROR,
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
    PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE,
    PYTHON_TOOLING_STATUS_UNCHANGED,
    PythonTextTransformResult,
)
from app.python_tools.vendor_runtime import initialize_python_tooling_runtime
from app.project.file_operation_models import ImportUpdatePolicy
from app.project.project_service import create_blank_project, enumerate_project_entries, open_project
from app.project.project_manifest import set_project_default_entry
from app.project.recent_projects import load_recent_projects
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.main_thread_dispatcher import MainThreadDispatcher
from app.shell.action_registry import ShellActionRegistry
from app.shell.command_broker import CommandBroker
from app.shell.events import (
    ProjectOpenFailedEvent,
    ProjectOpenedEvent,
    RunProcessExitEvent,
    RunProcessOutputEvent,
    RunProcessStateEvent,
    RunSessionStartedEvent,
    ShellEventBus,
)
from app.shell.menus import MenuCallbacks, MenuStubRegistry, build_menu_stubs
from app.shell.project_controller import ProjectController
from app.shell.file_dialogs import choose_existing_directory, choose_open_files
from app.shell.project_tree_controller import ProjectTreeController
from app.shell.repl_session_manager import ReplSessionManager
from app.shell.run_session_controller import RunSessionController, RunSessionStartFailureReason
from app.shell.run_output_coordinator import RunOutputCoordinator
from app.shell.run_config_controller import RunConfigController
from app.shell.editor_intelligence_controller import EditorIntelligenceController
from app.shell.editor_workspace_controller import EditorWorkspaceController
from app.shell.project_tree_action_coordinator import ProjectTreeActionCoordinator
from app.shell.diagnostics_search_coordinator import DiagnosticsOrchestrator, SearchResultsCoordinator
from app.shell.help_controller import ShellHelpController
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
PYTHON_STYLE_SAVE_GUARDRAIL_CHAR_LIMIT = 250_000
ShellEventT = TypeVar("ShellEventT")
ReplEvent = tuple[str, object, object]


class _MiddleClickTabBar(QTabBar):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tab_double_click_callback: Callable[[int], None] | None = None

    def set_tab_double_click_callback(self, callback: Callable[[int], None] | None) -> None:
        self._tab_double_click_callback = callback

    def mousePressEvent(self, arg__1: QMouseEvent) -> None:
        if arg__1.button() == Qt.MiddleButton:
            tab_index = self.tabAt(arg__1.pos())
            if tab_index >= 0:
                self.tabCloseRequested.emit(tab_index)
        else:
            super().mousePressEvent(arg__1)

    def mouseDoubleClickEvent(self, arg__1: QMouseEvent) -> None:  # noqa: N802 - Qt signature
        tab_index = self.tabAt(arg__1.pos())
        if tab_index >= 0 and self._tab_double_click_callback is not None:
            self._tab_double_click_callback(tab_index)
            arg__1.accept()
            return
        super().mouseDoubleClickEvent(arg__1)

    def paintEvent(self, arg__1: QEvent) -> None:  # noqa: N802 - Qt signature
        painter = QStylePainter(self)
        option = QStyleOptionTab()
        for index in range(self.count()):
            self.initStyleOption(option, index)
            data = self.tabData(index)
            is_preview = isinstance(data, dict) and bool(data.get("is_preview"))
            if is_preview:
                preview_font = QFont(self.font())
                preview_font.setItalic(True)
                option.fontMetrics = QFontMetrics(preview_font)
                painter.save()
                painter.setFont(preview_font)
            painter.drawControl(QStyle.CE_TabBarTabShape, option)
            painter.drawControl(QStyle.CE_TabBarTabLabel, option)
            if is_preview:
                painter.restore()
        arg__1.accept()


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
        self._editor_tabs_widget: QTabWidget | None = None
        self._activity_bar: ActivityBar | None = None
        self._sidebar_stack: QStackedWidget | None = None
        self._search_sidebar: SearchSidebarWidget | None = None
        self._quick_open_dialog: QuickOpenDialog | None = None
        self._history_restore_picker_dialog: HistoryRestorePickerDialog | None = None
        self._plugin_manager_dialog: PluginManagerDialog | None = None
        self._bottom_tabs_widget: QTabWidget | None = None
        self._run_log_panel: RunLogPanel | None = None
        self._python_console_widget: PythonConsoleWidget | None = None
        self._python_console_container: QWidget | None = None
        self._debug_panel: DebugPanelWidget | None = None
        self._problems_panel: ProblemsPanel | None = None
        self._problems_tab_widget: QTabWidget | None = None
        self._state_root = state_root
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
        self._is_applying_theme_styles = False
        self._theme_mode: str = constants.UI_THEME_MODE_DEFAULT
        self._system_dark_theme_preference: bool | None = None
        self._loaded_project: LoadedProject | None = None
        self._project_tree_structure_signature: tuple[str, ...] | None = None
        self._workspace_controller = EditorWorkspaceController()
        self._editor_manager = EditorManager()
        self._editor_widgets_by_path = self._workspace_controller.editor_widgets_by_path
        self._breakpoints_by_file: dict[str, set[int]] = {}
        self._breakpoint_specs_by_key: dict[tuple[str, int], DebugBreakpoint] = {}
        self._debug_exception_policy = DebugExceptionPolicy()
        self._last_debug_target: dict[str, object] | None = None
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
        self._theme_mode = self._load_theme_mode()
        self._shortcut_overrides = self._load_shortcut_overrides()
        self._effective_shortcuts = build_effective_shortcut_map(self._shortcut_overrides)
        self._help_controller = ShellHelpController(
            state_root=self._state_root,
            resolve_theme_tokens=self._resolve_theme_tokens,
            reveal_path_in_file_manager=self._reveal_path_in_file_manager,
            get_effective_shortcuts=lambda: self._effective_shortcuts,
        )
        self._syntax_color_overrides = self._load_syntax_color_overrides()
        self._lint_rule_overrides = self._load_lint_rule_overrides()
        self._selected_linter = self._load_selected_linter()
        self._symbol_cache_db_path = str(global_cache_dir(self._state_root) / "symbols.sqlite3")
        self._local_history_store = LocalHistoryStore(
            state_root=self._state_root,
            retention_policy=self._local_history_retention_policy,
        )
        self._autosave_store = AutosaveStore(
            state_root=self._state_root,
            history_store=self._local_history_store,
        )
        self._pending_autosave_payloads: dict[str, str] = {}
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self._flush_pending_autosaves)
        self._auto_save_to_file_timer = QTimer(self)
        self._auto_save_to_file_timer.setSingleShot(True)
        self._auto_save_to_file_timer.setInterval(1000)
        self._auto_save_to_file_timer.timeout.connect(self._flush_auto_save_to_file)
        self._pending_realtime_lint_file_path: str | None = None
        self._realtime_lint_timer = QTimer(self)
        self._realtime_lint_timer.setSingleShot(True)
        self._realtime_lint_timer.setInterval(300)
        self._realtime_lint_timer.timeout.connect(self._run_scheduled_realtime_lint)
        self._console_model = ConsoleModel()
        self._run_event_queue: queue.Queue[ProcessEvent] = queue.Queue()
        self._active_run_output_tail = OutputTailBuffer(max_chars=300_000, max_chunks=6_000)
        self._active_run_session_log_path: str | None = None
        self._active_run_session_info: RunInfo | None = None
        self._active_transient_entry_file_path: str | None = None
        self._debug_session = DebugSession()
        self._debug_execution_editor: CodeEditorWidget | None = None
        self._active_search_worker: SearchWorker | None = None
        self._active_symbol_index_worker: SymbolIndexWorker | None = None
        self._is_shutting_down = False
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
        self._run_config_controller = RunConfigController()
        self._active_named_run_config_name: str | None = None
        self._repl_event_queue: queue.Queue[ReplEvent] = queue.Queue()
        self._repl_manager = ReplSessionManager(
            on_output=self._enqueue_repl_output,
            on_session_ended=self._enqueue_repl_ended,
            on_session_started=self._enqueue_repl_started,
            state_root=self._state_root,
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
        self._logger = get_subsystem_logger("shell")
        self._diagnostics_orchestrator = DiagnosticsOrchestrator(
            diagnostics_enabled=lambda: self._diagnostics_enabled,
            diagnostics_realtime=lambda: self._diagnostics_realtime,
            set_pending_realtime_file_path=lambda file_path: setattr(
                self, "_pending_realtime_lint_file_path", file_path
            ),
            get_pending_realtime_file_path=lambda: self._pending_realtime_lint_file_path,
            start_realtime_timer=self._realtime_lint_timer.start,
            get_active_tab_file_path=lambda: cast(
                str | None,
                getattr(self._editor_manager.active_tab(), "file_path", None),
            ),
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
        self._search_results_coordinator = SearchResultsCoordinator(
            set_search_results=self._set_search_results,
            dispatch_to_main_thread=self._dispatch_to_main_thread,
        )
        self._project_controller = ProjectController(state_root=self._state_root, logger=self._logger)
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
            breakpoints_by_file=self._breakpoints_by_file,
            refresh_breakpoints_list=self._refresh_breakpoints_list,
            remap_editor_paths=self._editor_manager.remap_paths_for_move,
            update_tab_path_and_name=self._update_tab_path_and_name,
            apply_breakpoints_to_widget=lambda widget, breakpoints: widget.set_breakpoints(breakpoints),
            update_widget_language=self._update_widget_language_for_path,
            maybe_rewrite_imports=self._maybe_rewrite_imports_for_move,
            reload_project=self._reload_current_project,
            record_deleted_path=self._record_deleted_local_history_path,
            remap_file_lineage=self._remap_local_history_file_lineage,
        )

        self._configure_window_frame()
        self._build_layout_shell()
        self._configure_close_tab_shortcut()
        self._configure_keep_preview_open_shortcut()
        self._menu_registry = build_menu_stubs(
            self,
            callbacks=MenuCallbacks(
                on_open_project=self._handle_open_project_action,
                on_open_file=self._handle_open_file_action,
                on_new_window=self._handle_new_window_action,
                on_file_menu_about_to_show=self._refresh_open_recent_menu,
                on_save=self._handle_save_action,
                on_save_all=self._handle_save_all_action,
                on_toggle_auto_save=self._handle_toggle_auto_save,
                on_open_settings=self._handle_open_settings_action,
                on_run=self._handle_run_action,
                on_debug=self._handle_debug_action,
                on_run_project=self._handle_run_project_action,
                on_debug_project=self._handle_debug_project_action,
                on_run_pytest_project=self._handle_run_pytest_project_action,
                on_run_pytest_current_file=self._handle_run_pytest_current_file_action,
                on_debug_pytest_current_file=self._handle_debug_pytest_current_file_action,
                on_run_with_config=self._handle_run_with_configuration_action,
                on_manage_run_configs=self._handle_manage_run_configurations_action,
                on_stop=self._handle_stop_action,
                on_restart=self._handle_restart_action,
                on_rerun_last_debug_target=self._handle_rerun_last_debug_target_action,
                on_continue_debug=self._handle_continue_debug_action,
                on_pause_debug=self._handle_pause_debug_action,
                on_step_over=self._handle_step_over_action,
                on_step_into=self._handle_step_into_action,
                on_step_out=self._handle_step_out_action,
                on_toggle_breakpoint=self._handle_toggle_breakpoint_action,
                on_remove_all_breakpoints=self._handle_remove_all_breakpoints_action,
                on_debug_exception_stops=self._handle_debug_exception_settings_action,
                on_start_python_console=self._handle_start_python_console_action,
                on_clear_console=self._handle_clear_console_action,
                on_reset_layout=self._handle_reset_layout_action,
                on_set_theme_system=lambda: self._handle_set_theme(constants.UI_THEME_MODE_SYSTEM),
                on_set_theme_light=lambda: self._handle_set_theme(constants.UI_THEME_MODE_LIGHT),
                on_set_theme_dark=lambda: self._handle_set_theme(constants.UI_THEME_MODE_DARK),
                on_zoom_in=self._handle_zoom_in,
                on_zoom_out=self._handle_zoom_out,
                on_zoom_reset=self._handle_zoom_reset,
                on_format_current_file=self._handle_format_current_file_action,
                on_organize_imports_current_file=self._handle_organize_imports_action,
                on_lint_current_file=self._handle_lint_current_file_action,
                on_apply_safe_fixes=self._handle_apply_safe_fixes_action,
                on_open_plugin_manager=self._handle_open_plugin_manager_action,
                on_rebuild_intelligence_cache=self._handle_rebuild_intelligence_cache_action,
                on_refresh_runtime_modules=self._handle_refresh_runtime_modules_action,
                on_runtime_center=self._handle_runtime_center_action,
                on_project_health_check=self._handle_project_health_check_action,
                on_generate_support_bundle=self._handle_generate_support_bundle_action,
                on_package_project=self._handle_package_project_action,
                on_new_project=self._handle_new_project_action,
                on_new_project_from_template=self._handle_new_project_from_template_action,
                on_quick_open=self._handle_quick_open_action,
                on_open_global_history=self._handle_open_global_history_action,
                on_find=self._handle_find_action,
                on_replace=self._handle_replace_action,
                on_go_to_line=self._handle_go_to_line_action,
                on_find_in_files=self._handle_find_in_files_action,
                on_find_references=self._handle_find_references_action,
                on_rename_symbol=self._handle_rename_symbol_action,
                on_toggle_comment=self._handle_toggle_comment_action,
                on_indent=self._handle_indent_action,
                on_outdent=self._handle_outdent_action,
                on_go_to_definition=self._handle_go_to_definition_action,
                on_signature_help=self._handle_signature_help_action,
                on_hover_info=self._handle_hover_info_action,
                on_analyze_imports=self._handle_analyze_imports_action,
                on_show_outline=self._handle_show_outline_action,
                on_set_language_mode=self._handle_set_language_mode_action,
                on_clear_language_override=self._handle_clear_language_override_action,
                on_inspect_token=self._handle_inspect_token_action,
                on_headless_notes=self._handle_headless_notes_action,
                on_help_load_example_project=self._handle_load_example_project_action,
                on_help_open_app_log=self._handle_open_app_log_action,
                on_help_open_log_folder=self._handle_open_log_folder_action,
                on_help_runtime_onboarding=self._handle_runtime_onboarding_action,
                on_help_getting_started=self._handle_getting_started_action,
                on_help_shortcuts=self._handle_shortcuts_action,
                on_help_about=self._handle_about_action,
            ),
            shortcut_overrides=self._effective_shortcuts,
        )
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
        self._refresh_python_tooling_status()
        self._toolbar = build_run_toolbar_widget(
            self._menu_registry,
            on_target_summary_clicked=self._handle_manage_run_configurations_action,
        )
        if self._toolbar is not None:
            center_panel = self.findChild(QWidget, "shell.centerPanel")
            if center_panel is not None:
                center_layout = center_panel.layout()
                if isinstance(center_layout, QVBoxLayout):
                    center_layout.insertWidget(0, self._toolbar, 0)
        self._apply_theme_styles()
        self._apply_runtime_intelligence_preferences_to_open_editors()
        self._sync_theme_menu_check_state()
        self._sync_auto_save_menu_state()
        self._restore_layout_from_settings()
        self._refresh_open_recent_menu()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        self._reload_plugin_contributions()
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

    def _try_restore_last_project(self) -> None:
        """Attempt to reopen the last project from the previous session."""
        if self._is_shutting_down or self._loaded_project is not None:
            return
        try:
            settings = self._settings_service.load_global()
        except Exception:
            return
        last_path = settings.get(constants.LAST_PROJECT_PATH_KEY)
        if not isinstance(last_path, str) or not last_path.strip():
            return
        project_root = Path(last_path.strip())
        if not project_root.is_dir() or not (project_root / constants.PROJECT_META_DIRNAME / constants.PROJECT_MANIFEST_FILENAME).is_file():
            return
        opened = self._open_project_by_path(str(project_root))
        if opened and self._should_show_runtime_onboarding():
            QTimer.singleShot(0, self._handle_runtime_onboarding_action)

    def set_startup_report(self, report: Optional[CapabilityProbeReport]) -> None:
        """Extension seam for startup status refresh from bootstrap updates."""
        self._startup_report = report
        self._latest_runtime_issue_report = self._build_runtime_issue_report()
        self._refresh_welcome_project_list()
        if self._status_controller is None:
            return
        self._status_controller.set_startup_report(report)

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
            self._handle_headless_notes_action()
            return
        if topic_id == "packaging_backup":
            self._help_controller.show_packaging_backup(parent=self)
            return
        if topic_id == HELP_TOPIC_GETTING_STARTED:
            self._handle_getting_started_action()
            return
        self._handle_getting_started_action()

    def _open_runtime_center_dialog(
        self,
        *,
        title: str = "Runtime Center",
        report: RuntimeIssueReport | None = None,
    ) -> None:
        dialog = RuntimeCenterDialog(
            title=title,
            report=report or self._latest_runtime_issue_report,
            tokens=self._resolve_theme_tokens(),
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
        except Exception:
            return False, False
        onboarding_payload = settings_payload.get(constants.UI_ONBOARDING_SETTINGS_KEY)
        if not isinstance(onboarding_payload, Mapping):
            return False, False
        return (
            bool(onboarding_payload.get(constants.UI_ONBOARDING_RUNTIME_GUIDE_DISMISSED_KEY, False)),
            bool(onboarding_payload.get(constants.UI_ONBOARDING_RUNTIME_GUIDE_COMPLETED_KEY, False)),
        )

    def _should_show_runtime_onboarding(self) -> bool:
        return not self._runtime_onboarding_dismissed and not self._runtime_onboarding_completed

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
        except Exception:
            recent_paths = []
        widget.set_recent_projects(recent_paths)
        startup_status = map_startup_report_to_status(self._startup_report)
        widget.set_runtime_summary(startup_status.text, startup_status.details)
        widget.set_project_health_available(self._loaded_project is not None)
        widget.set_onboarding_visible(force_show_onboarding or self._should_show_runtime_onboarding())

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
            lambda: self._invoke_welcome_action(self._handle_project_health_check_action, close_after_action)
        )
        widget.example_project_requested.connect(
            lambda: self._invoke_welcome_action(self._handle_load_example_project_action, close_after_action)
        )
        widget.headless_notes_requested.connect(
            lambda: self._invoke_welcome_action(self._handle_headless_notes_action, close_after_action)
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

        layout_state = ShellLayoutState(
            width=self.width(),
            height=self.height(),
            top_splitter_sizes=(int(top_sizes[0]), int(top_sizes[1])),
            vertical_splitter_sizes=(int(vertical_sizes[0]), int(vertical_sizes[1])),
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
        self._persist_layout_to_settings()

    def _load_import_update_policy(self) -> ImportUpdatePolicy:
        settings_payload = self._settings_service.load_global()
        raw_value = settings_payload.get(constants.UI_IMPORT_UPDATE_POLICY_KEY, constants.UI_IMPORT_UPDATE_POLICY_DEFAULT)
        try:
            return ImportUpdatePolicy(str(raw_value))
        except ValueError:
            return ImportUpdatePolicy.ASK

    def _resolve_theme_tokens(self) -> ShellThemeTokens:
        palette = self.palette()
        mode = self._theme_mode
        if mode in (constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK):
            base_tokens = tokens_from_palette(palette, force_mode=mode)
        else:
            base_tokens = tokens_from_palette(palette, prefer_dark=self._system_prefers_dark_theme())
        theme_key = (
            constants.UI_SYNTAX_COLORS_DARK_KEY
            if base_tokens.is_dark
            else constants.UI_SYNTAX_COLORS_LIGHT_KEY
        )
        syntax_overrides = self._syntax_color_overrides.get(theme_key, {})
        return apply_syntax_token_overrides(base_tokens, syntax_overrides)

    def _apply_theme_styles(self) -> None:
        if self._is_applying_theme_styles:
            return
        self._is_applying_theme_styles = True
        try:
            tokens = self._resolve_theme_tokens()
            close_normal, close_hover = ensure_tab_close_icons(
                tokens.text_muted, tokens.text_primary,
            )
            tokens = replace(
                tokens,
                tab_close_icon_path=close_normal,
                tab_close_icon_hover_path=close_hover,
            )
            self.setStyleSheet(build_shell_style_sheet(tokens))
            for editor_widget in self._editor_widgets_by_path.values():
                editor_widget.apply_theme(tokens)
            if self._python_console_widget is not None:
                self._python_console_widget.apply_theme(tokens)
            self._apply_explorer_theme(tokens)
            if self._run_log_panel is not None:
                self._run_log_panel.apply_theme(tokens)
            if self._search_sidebar is not None:
                self._search_sidebar.apply_theme_tokens(
                    match_bg=tokens.search_match_bg,
                    text_primary=tokens.text_primary,
                    text_muted=tokens.text_muted,
                    badge_bg=tokens.badge_bg,
                )
        finally:
            self._is_applying_theme_styles = False

    def _apply_explorer_theme(self, tokens: ShellThemeTokens) -> None:
        self._tree_file_icon = file_icon(tokens.icon_primary)
        self._tree_file_icon_map = file_type_icon_map()
        self._tree_filename_icon_map = filename_icon_map()
        self._tree_folder_icon = folder_icon(tokens.icon_muted)
        self._tree_folder_open_icon = folder_open_icon(tokens.icon_muted)
        self._tree_entrypoint_icon = icon_run(tokens.debug_running_color)
        if self._explorer_new_file_btn is not None:
            self._explorer_new_file_btn.setIcon(new_file_icon(tokens.icon_primary, tokens.icon_muted))
        if self._explorer_new_folder_btn is not None:
            self._explorer_new_folder_btn.setIcon(new_folder_icon(tokens.icon_primary, tokens.icon_muted))
        if self._explorer_refresh_btn is not None:
            self._explorer_refresh_btn.setIcon(refresh_icon(tokens.icon_primary))
        if self._loaded_project is not None:
            self._populate_project_tree(self._loaded_project, preserve_state=True)

    def _system_prefers_dark_theme(self) -> bool:
        cached_preference = self._system_dark_theme_preference
        if cached_preference is not None:
            return cached_preference
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            self._system_dark_theme_preference = False
            return False
        if result.returncode != 0:
            self._system_dark_theme_preference = False
            return False
        self._system_dark_theme_preference = "prefer-dark" in result.stdout
        return self._system_dark_theme_preference

    def _load_theme_mode(self) -> str:
        settings_payload = self._settings_service.load_global()
        snapshot = parse_editor_settings_snapshot(settings_payload)
        return snapshot.theme_mode

    def _load_shortcut_overrides(self) -> dict[str, str]:
        settings_payload = self._settings_service.load_global()
        snapshot = parse_editor_settings_snapshot(settings_payload)
        return dict(snapshot.shortcut_overrides)

    def _load_syntax_color_overrides(self) -> dict[str, dict[str, str]]:
        settings_payload = self._settings_service.load_global()
        snapshot = parse_editor_settings_snapshot(settings_payload)
        return {
            constants.UI_SYNTAX_COLORS_LIGHT_KEY: dict(snapshot.syntax_color_overrides_light),
            constants.UI_SYNTAX_COLORS_DARK_KEY: dict(snapshot.syntax_color_overrides_dark),
        }

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
        self._system_dark_theme_preference = None
        self._persist_theme_mode(mode)
        if self._quick_open_dialog is not None:
            self._quick_open_dialog.deleteLater()
            self._quick_open_dialog = None
        self._apply_theme_styles()
        self._sync_theme_menu_check_state()
        self._logger.info("Theme mode changed to %s.", mode)

    def _sync_theme_menu_check_state(self) -> None:
        if self._menu_registry is None:
            return
        _mode_to_action_id = {
            constants.UI_THEME_MODE_SYSTEM: "shell.action.view.theme.system",
            constants.UI_THEME_MODE_LIGHT: "shell.action.view.theme.light",
            constants.UI_THEME_MODE_DARK: "shell.action.view.theme.dark",
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
        runtime_status = initialize_python_tooling_runtime()
        project_root = self._current_project_root()
        if project_root is None:
            return runtime_status.is_available, "no_project", None, None

        settings = resolve_python_tooling_settings(
            project_root=project_root,
            file_path=str(Path(project_root) / "__cbcs_python_tooling_status__.py"),
        )
        if settings.pyproject_path is None:
            return runtime_status.is_available, "defaults", None, None
        if settings.config_error is not None:
            return runtime_status.is_available, "pyproject_error", str(settings.pyproject_path), settings.config_error
        return runtime_status.is_available, "pyproject", str(settings.pyproject_path), None

    def _settings_dialog_python_tooling_copy(self) -> tuple[str, str, str, str]:
        runtime_status = initialize_python_tooling_runtime()
        runtime_text = (
            "Black/isort/tomli: available"
            if runtime_status.is_available
            else "Black/isort/tomli: unavailable"
        )
        runtime_details = f"{runtime_status.message} Vendor root: {runtime_status.vendor_root}"
        _runtime_available, config_state, config_path, config_error = self._current_python_tooling_status_context()
        if config_state == "no_project":
            config_text = "Project pyproject.toml: no project"
            config_details = "Open a project to detect project-local formatter/import settings."
        elif config_state == "defaults":
            config_text = "Project pyproject.toml: not detected"
            config_details = "No project-local pyproject.toml was found for Python tooling."
        elif config_state == "pyproject_error":
            config_text = "Project pyproject.toml: parse error"
            config_details = f"Path: {config_path}. Error: {config_error}"
        else:
            config_text = "Project pyproject.toml: detected"
            config_details = f"Path: {config_path}"
        return runtime_text, runtime_details, config_text, config_details

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

    def _load_editor_preferences(self) -> tuple[int, int, str, str, int, bool, bool, bool, bool, bool, bool, bool]:
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

        for file_path in file_paths:
            self._open_file_in_editor(file_path, preview=False)

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
            tokens=self._resolve_theme_tokens(),
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
        )
        if merged_global_settings != global_settings_payload:
            self._settings_service.save_global(merged_global_settings)
        if project_root is not None and merged_project_settings != project_settings_payload:
            self._settings_service.save_project(project_root, merged_project_settings)

        if updated_snapshot.theme_mode != previous_theme_mode:
            self._handle_set_theme(updated_snapshot.theme_mode)

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
        ) = self._load_editor_preferences()
        self._sync_auto_save_menu_state()
        if not self._editor_auto_save:
            self._auto_save_to_file_timer.stop()
        (
            self._completion_enabled,
            self._completion_auto_trigger,
            self._completion_min_chars,
        ) = self._load_completion_preferences()
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
        self._local_history_retention_policy = self._load_local_history_retention_policy()
        self._local_history_store.set_retention_policy(self._local_history_retention_policy, apply_now=True)
        self._shortcut_overrides = self._load_shortcut_overrides()
        self._syntax_color_overrides = self._load_syntax_color_overrides()
        self._lint_rule_overrides = self._load_lint_rule_overrides()
        self._selected_linter = self._load_selected_linter()
        if not self._diagnostics_enabled or not self._diagnostics_realtime:
            self._realtime_lint_timer.stop()
            self._pending_realtime_lint_file_path = None
        self._intelligence_runtime_settings = self._load_intelligence_runtime_settings()
        if not self._intelligence_runtime_settings.cache_enabled:
            if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
                self._active_symbol_index_worker.cancel()
        elif self._loaded_project is not None:
            self._start_symbol_indexing(self._loaded_project.project_root)
        self._apply_editor_preferences_to_open_editors()
        self._apply_runtime_intelligence_preferences_to_open_editors()
        self._apply_shortcut_overrides_runtime()
        self._apply_theme_styles()
        if previous_enable_preview and not self._editor_enable_preview:
            self._cancel_pending_project_tree_preview()
            self._promote_existing_preview_tab()
        lint_profile_changed = self._lint_rule_overrides != previous_lint_rule_overrides
        diagnostics_enabled_changed = self._diagnostics_enabled != previous_diagnostics_enabled
        selected_linter_changed = self._selected_linter != previous_selected_linter
        if self._diagnostics_enabled and (
            lint_profile_changed or diagnostics_enabled_changed or selected_linter_changed
        ):
            self._relint_open_python_files()
        if not self._diagnostics_enabled:
            self._stored_lint_diagnostics.clear()
            self._render_merged_problems_panel()
        effective_excludes = self._load_effective_exclude_patterns(project_root)
        if effective_excludes != previous_effective_excludes:
            self._reload_current_project()
            if self._search_sidebar is not None and self._loaded_project is not None:
                self._search_sidebar.set_exclude_patterns(
                    compute_effective_excludes(
                        self._load_effective_exclude_patterns(self._loaded_project.project_root),
                        self._loaded_project.metadata.exclude_patterns,
                    )
                )
        if self._loaded_project is not None:
            self.set_project_placeholder(self._loaded_project.metadata.name)
        self._logger.info("Updated settings from dialog.")

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
            tokens = self._resolve_theme_tokens()
            self._quick_open_dialog = QuickOpenDialog(
                self,
                tokens=tokens,
                icon_map=self._tree_file_icon_map,
                filename_icon_map=self._tree_filename_icon_map,
            )
            self._quick_open_dialog.file_preview_requested.connect(
                lambda file_path: self._open_file_in_editor(file_path, preview=True)
            )
            self._quick_open_dialog.file_selected.connect(
                lambda file_path: self._open_file_in_editor(file_path, preview=False)
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

    def _handle_open_global_history_action(self) -> None:
        history_store = getattr(self, "_local_history_store", None)
        if history_store is None:
            return

        def task(cancel_event):  # type: ignore[no-untyped-def]
            summaries = history_store.list_global_history_files()
            if cancel_event.is_set():
                return None
            return summaries

        def on_success(payload: object) -> None:
            if not isinstance(payload, list):
                return
            summaries = payload
            if not summaries:
                QMessageBox.information(
                    self,
                    "Global History",
                    "No saved local-history entries are available yet.",
                )
                return

            if self._history_restore_picker_dialog is None:
                self._history_restore_picker_dialog = HistoryRestorePickerDialog(self)

            self._history_restore_picker_dialog.set_entries(summaries)
            result = self._history_restore_picker_dialog.open_dialog()
            if result != QDialog.Accepted:
                return

            selected_entry = self._history_restore_picker_dialog.selected_entry()
            if selected_entry is None:
                return

            if self._history_restore_picker_dialog.requested_action == HISTORY_RESTORE_ACTION_RESTORE_LATEST:
                latest_content = history_store.load_checkpoint_content(selected_entry.latest_revision_id)
                if latest_content is None:
                    QMessageBox.warning(self, "Global History", "Could not load the latest saved revision.")
                    return
                self._restore_local_history_content_to_buffer(selected_entry.file_path, latest_content)
                return

            if self._history_restore_picker_dialog.requested_action == HISTORY_RESTORE_ACTION_OPEN_TIMELINE:
                self._show_local_history_for_entry(selected_entry)

        def on_error(exc: Exception) -> None:
            self._logger.warning("Failed to load global history entries: %s", exc)
            QMessageBox.warning(self, "Global History", f"Could not load global history:\n{exc}")

        self._background_tasks.run(
            key="global_history_list",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_find_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            return
        if self._find_replace_bar is None:
            return
        initial = editor_widget.selected_text() or editor_widget.word_under_cursor()
        self._find_replace_bar.open_find(initial)

    def _handle_replace_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            return
        if self._find_replace_bar is None:
            return
        initial = editor_widget.selected_text() or editor_widget.word_under_cursor()
        self._find_replace_bar.open_find_replace(initial)

    def _handle_find_bar_find(self, text: str, options: FindOptions) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None or self._find_replace_bar is None:
            return
        total = editor_widget.highlight_all_matches(text, options)
        if total > 0:
            current, total = editor_widget.find_next()
            self._find_replace_bar.update_match_count(current, total)
        else:
            self._find_replace_bar.update_match_count(0, 0)

    def _handle_find_bar_next(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None or self._find_replace_bar is None:
            return
        current, total = editor_widget.find_next()
        self._find_replace_bar.update_match_count(current, total)

    def _handle_find_bar_prev(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None or self._find_replace_bar is None:
            return
        current, total = editor_widget.find_previous()
        self._find_replace_bar.update_match_count(current, total)

    def _handle_find_bar_replace(self, replacement: str) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None or self._find_replace_bar is None:
            return
        query = self._find_replace_bar.find_text()
        options = self._find_replace_bar.find_options()
        current, total = editor_widget.replace_current_match(replacement, query, options)
        self._find_replace_bar.update_match_count(current, total)

    def _handle_find_bar_replace_all(self, replacement: str) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None or self._find_replace_bar is None:
            return
        query = self._find_replace_bar.find_text()
        options = self._find_replace_bar.find_options()
        editor_widget.replace_all_matches(query, replacement, options)
        self._find_replace_bar.update_match_count(0, 0)

    def _handle_find_bar_close(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is not None:
            editor_widget.clear_search_highlights()
            editor_widget.setFocus()

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

    def _handle_find_in_files_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Find in Files", "Open a project first.")
            return
        if self._activity_bar is not None:
            self._activity_bar.set_active_view("search")
            self._handle_sidebar_view_changed("search")
        editor_widget = self._active_editor_widget()
        initial = ""
        if editor_widget is not None:
            initial = editor_widget.selected_text() or editor_widget.word_under_cursor()
        if self._search_sidebar is not None and initial:
            self._search_sidebar.focus_search(initial)

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

        if not self._handle_save_all_action():
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
                self._record_local_history_transaction(
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

    def _handle_go_to_definition_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Go To Definition", "Open a project first.")
            return
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Go To Definition", "Open a file tab first.")
            return
        symbol_name = editor_widget.word_under_cursor()
        if not symbol_name:
            QMessageBox.information(self, "Go To Definition", "Place cursor on a symbol first.")
            return
        project_root = self._loaded_project.project_root
        current_file_path = active_tab.file_path
        source_text = editor_widget.toPlainText()
        cursor_position = editor_widget.textCursor().position()

        def on_success(lookup) -> None:  # type: ignore[no-untyped-def]
            if not lookup.found:
                if lookup.metadata.unsupported_reason:
                    QMessageBox.information(
                        self,
                        "Go To Definition",
                        f"No semantic definition found for '{symbol_name}'. The symbol may be dynamic or unresolved.",
                    )
                else:
                    QMessageBox.information(self, "Go To Definition", f"No definition found for '{symbol_name}'.")
                return
            location = self._choose_definition_location(lookup.locations)
            if location is None:
                return
            selected_location = cast(Any, location)
            self._open_file_at_line(str(selected_location.file_path), int(selected_location.line_number))

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Go To Definition", f"Lookup failed: {exc}")

        self._intelligence_controller.request_lookup_definition(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_signature_help_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Signature Help", "Open a file tab first.")
            return

        tooltip_text = self._build_inline_signature_text(
            file_path=active_tab.file_path,
            source_text=editor_widget.toPlainText(),
            cursor_position=editor_widget.textCursor().position(),
        )
        if not tooltip_text:
            QMessageBox.information(self, "Signature Help", "No callable signature information available.")
            return
        editor_widget.show_calltip(tooltip_text)

    def _handle_hover_info_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Hover Info", "Open a file tab first.")
            return

        tooltip_text = self._build_inline_hover_text(
            file_path=active_tab.file_path,
            source_text=editor_widget.toPlainText(),
            cursor_position=editor_widget.textCursor().position(),
        )
        if not tooltip_text:
            QMessageBox.information(self, "Hover Info", "No symbol info available.")
            return
        editor_widget.show_calltip(tooltip_text)

    def _choose_definition_location(self, locations: list[object]):  # type: ignore[no-untyped-def]
        if not locations:
            return None
        if len(locations) == 1:
            return locations[0]

        labels: list[str] = []
        by_label: dict[str, object] = {}
        for location in locations:
            file_path = str(getattr(location, "file_path", ""))
            line_number = int(getattr(location, "line_number", 0) or 0)
            symbol_kind = str(getattr(location, "symbol_kind", "symbol"))
            label = f"{Path(file_path).name}:{line_number} ({symbol_kind})"
            labels.append(label)
            by_label[label] = location
        selected_label, ok = QInputDialog.getItem(
            self,
            "Choose Definition Target",
            "Multiple definition targets found:",
            labels,
            0,
            editable=False,
        )
        if not ok or not selected_label:
            return None
        return by_label.get(selected_label)

    def _build_inline_signature_text(
        self,
        *,
        file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> str | None:
        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        return self._intelligence_controller.build_inline_signature_text(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )

    def _build_inline_hover_text(
        self,
        *,
        file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> str | None:
        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        return self._intelligence_controller.build_inline_hover_text(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )

    def _format_inline_signature_text(self, signature) -> str | None:  # type: ignore[no-untyped-def]
        return self._intelligence_controller.format_inline_signature_text(signature)

    def _format_inline_hover_text(self, hover_info) -> str | None:  # type: ignore[no-untyped-def]
        return self._intelligence_controller.format_inline_hover_text(hover_info)

    def _request_inline_signature_text_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
        cursor_position: int,
        request_generation: int,
    ) -> None:
        project_root = None if self._loaded_project is None else self._loaded_project.project_root

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            generation, signature = payload
            active_widget = self._editor_widgets_by_path.get(file_path)
            if active_widget is not editor_widget:
                return
            editor_widget.show_calltip_for_request(
                request_generation=generation,
                text=self._format_inline_signature_text(signature),
            )

        def on_error(exc: Exception) -> None:
            self._logger.warning("Signature-help request failed for %s: %s", file_path, exc)

        self._intelligence_controller.request_signature_help(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def _request_inline_hover_text_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
        cursor_position: int,
        request_generation: int,
    ) -> None:
        project_root = None if self._loaded_project is None else self._loaded_project.project_root

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            generation, hover_info = payload
            active_widget = self._editor_widgets_by_path.get(file_path)
            if active_widget is not editor_widget:
                return
            editor_widget.show_hover_text_for_request(
                request_generation=generation,
                text=self._format_inline_hover_text(hover_info),
            )

        def on_error(exc: Exception) -> None:
            self._logger.warning("Hover request failed for %s: %s", file_path, exc)

        self._intelligence_controller.request_hover_info(
            project_root=project_root,
            current_file_path=file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            request_generation=request_generation,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_analyze_imports_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Analyze Imports", "Open a project first.")
            return
        project_root = self._loaded_project.project_root
        source_overrides: dict[str, str] = {}
        for path, widget in self._editor_widgets_by_path.items():
            source_overrides[path] = widget.toPlainText()

        known_modules = self._known_runtime_modules

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return find_unresolved_imports(
                project_root,
                source_overrides=source_overrides,
                known_runtime_modules=known_modules,
                allow_runtime_import_probe=True,
                lint_rule_overrides=self._lint_rule_overrides,
            )

        def on_success(diagnostics) -> None:  # type: ignore[no-untyped-def]
            if self._problems_panel is None:
                return
            _, unresolved_import_severity = resolve_lint_rule_settings("PY200", self._lint_rule_overrides)
            if unresolved_import_severity == LINT_SEVERITY_ERROR:
                diagnostic_severity = DiagnosticSeverity.ERROR
            elif unresolved_import_severity == LINT_SEVERITY_INFO:
                diagnostic_severity = DiagnosticSeverity.INFO
            else:
                diagnostic_severity = DiagnosticSeverity.WARNING
            import_diags = [
                CodeDiagnostic(
                    code="PY200",
                    severity=diagnostic_severity,
                    file_path=d.file_path,
                    line_number=d.line_number,
                    message=d.message,
                )
                for d in diagnostics
            ]
            self._problems_panel.set_diagnostics(import_diags)
            self._update_problems_tab_title(self._problems_panel.problem_count())
            self._focus_problems_tab()
            self._latest_import_issue_report = build_import_issue_report(
                project_root,
                diagnostics,
                known_runtime_modules=known_modules,
                allow_runtime_import_probe=True,
            )
            self._latest_runtime_issue_report = self._build_runtime_issue_report()
            if self._latest_import_issue_report.issues:
                self._open_runtime_center_dialog(
                    title="Import Analysis",
                    report=self._latest_import_issue_report,
                )

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Analyze Imports", f"Import analysis failed: {exc}")

        self._background_tasks.run(key="analyze_imports", task=task, on_success=on_success, on_error=on_error)

    def _handle_show_outline_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Outline", "Open a Python file first.")
            return
        symbols = build_file_outline(active_tab.file_path)
        if self._problems_panel is None:
            return
        result_items = [
            ResultItem(
                label=f"{symbol.kind} {symbol.name}",
                file_path=active_tab.file_path,
                line_number=symbol.line_number,
            )
            for symbol in symbols
        ]
        self._problems_panel.set_results("Outline", result_items)
        self._update_problems_tab_title(self._problems_panel.problem_count())
        self._focus_problems_tab()

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

    def _handle_open_app_log_action(self) -> None:
        self._help_controller.open_app_log(parent=self)

    def _handle_open_log_folder_action(self) -> None:
        self._help_controller.open_log_folder(parent=self)

    def _handle_getting_started_action(self) -> None:
        self._help_controller.show_getting_started(parent=self)

    def _handle_shortcuts_action(self) -> None:
        self._help_controller.show_shortcuts(parent=self)

    def _handle_headless_notes_action(self) -> None:
        self._help_controller.show_headless_notes(parent=self)

    def _handle_about_action(self) -> None:
        self._help_controller.show_about(parent=self)

    def _open_project_by_path(self, project_root: str) -> bool:
        started_at = time.perf_counter()
        return self._project_controller.open_project_by_path(
            project_root,
            confirm_proceed=self._confirm_proceed_with_unsaved_changes,
            on_loaded=lambda loaded_project: self._apply_loaded_project(loaded_project, started_at=started_at),
            on_error=self._show_open_project_error,
            exclude_patterns=self._load_effective_exclude_patterns(project_root),
        )

    def _load_global_exclude_patterns(self) -> list[str]:
        settings_payload = self._settings_service.load_global()
        return parse_global_exclude_patterns(settings_payload)

    def _load_project_exclude_patterns(self, project_root: str | None) -> list[str]:
        if not project_root:
            return []
        project_settings_payload = self._settings_service.load_project(project_root)
        return parse_project_exclude_patterns(project_settings_payload)

    def _load_effective_exclude_patterns(self, project_root: str | None = None) -> list[str]:
        global_patterns = self._load_global_exclude_patterns()
        project_patterns = self._load_project_exclude_patterns(project_root)
        return compute_effective_excludes(global_patterns, project_patterns)

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
        self._cancel_pending_project_tree_preview()
        previous_project_root = self._loaded_project.project_root if self._loaded_project is not None else None
        if previous_project_root is not None:
            self._persist_session_state(project_root=previous_project_root)
        self._loaded_project = loaded_project
        self._latest_health_report = None
        self._latest_import_issue_report = RuntimeIssueReport(workflow="import", issues=[])
        self._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=[])
        self._latest_package_issue_report = RuntimeIssueReport(workflow="package", issues=[])
        self._latest_run_issue_ids = ()
        self._latest_runtime_issue_report = self._build_runtime_issue_report()
        self._active_named_run_config_name = None
        self._lint_rule_overrides = self._load_lint_rule_overrides()
        self._selected_linter = self._load_selected_linter()
        self._reload_plugin_contributions()
        self._refresh_python_tooling_status()
        self._show_editor_screen()
        self.set_project_placeholder(loaded_project.metadata.name)
        self.setWindowTitle(f"ChoreBoy Code Studio v{constants.APP_VERSION} — {loaded_project.metadata.name}")
        self._logger.info("Project loaded: %s", loaded_project.project_root)
        self._update_explorer_buttons_enabled()
        self._populate_project_tree(loaded_project)
        self._project_tree_structure_signature = tuple(entry.relative_path for entry in loaded_project.entries)
        self._reset_editor_tabs()
        self._stored_lint_diagnostics.clear()
        if self._search_sidebar is not None:
            self._search_sidebar.set_project_root(loaded_project.project_root)
            effective_excludes = compute_effective_excludes(
                self._load_effective_exclude_patterns(loaded_project.project_root),
                loaded_project.metadata.exclude_patterns,
            )
            self._search_sidebar.set_exclude_patterns(effective_excludes)
        self._breakpoints_by_file.clear()
        self._restore_session_state(loaded_project.project_root)
        self._lint_all_open_files()
        self._refresh_breakpoints_list()
        self._refresh_open_recent_menu()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        if self._intelligence_runtime_settings.force_full_reindex_on_open:
            self._rebuild_intelligence_cache()
        self._start_symbol_indexing(loaded_project.project_root)
        self._logger.info(
            "Project open telemetry: root=%s files=%s elapsed_ms=%.2f",
            loaded_project.project_root,
            len(loaded_project.entries),
            (time.perf_counter() - started_at) * 1000.0,
        )
        self._event_bus.publish(
            ProjectOpenedEvent(
                project_root=loaded_project.project_root,
                project_name=loaded_project.metadata.name,
            )
        )
        self._persist_last_project_path(loaded_project.project_root)

    def _persist_last_project_path(self, project_root: str) -> None:
        try:
            self._settings_service.update_global(
                lambda settings: merge_last_project_path(settings, project_root)
            )
        except Exception as exc:
            self._logger.warning("Failed to persist last project path: %s", exc)

    def _persist_session_state(self, project_root: str | None = None) -> None:
        target_project_root = project_root
        if target_project_root is None:
            if self._loaded_project is None:
                return
            target_project_root = self._loaded_project.project_root

        open_files: list[SessionFileState] = []
        for file_path in self._editor_manager.open_paths():
            cursor_line = 1
            cursor_column = 1
            scroll_position = 0
            editor_widget = self._editor_widgets_by_path.get(file_path)
            if editor_widget is not None:
                cursor = editor_widget.textCursor()
                cursor_line = cursor.blockNumber() + 1
                cursor_column = cursor.positionInBlock() + 1
                scroll_position = editor_widget.verticalScrollBar().value()
            open_files.append(
                SessionFileState(
                    file_path=file_path,
                    cursor_line=cursor_line,
                    cursor_column=cursor_column,
                    scroll_position=scroll_position,
                    breakpoints=tuple(sorted(self._breakpoints_by_file.get(file_path, set()))),
                )
            )

        active_tab = self._editor_manager.active_tab()
        active_file_path = None if active_tab is None else active_tab.file_path
        session_state = SessionState(open_files=tuple(open_files), active_file_path=active_file_path)
        try:
            save_session_file(target_project_root, session_state)
        except Exception as exc:
            self._logger.warning("Failed to persist project session state for %s: %s", target_project_root, exc)

    def _restore_session_state(self, project_root: str) -> None:
        try:
            session_state = load_session_file(project_root)
        except Exception as exc:
            self._logger.warning("Failed to load project session state for %s: %s", project_root, exc)
            return
        if session_state is None:
            return

        self._breakpoints_by_file.clear()
        self._breakpoint_specs_by_key.clear()
        for file_state in session_state.open_files:
            if file_state.breakpoints:
                self._breakpoints_by_file[file_state.file_path] = set(file_state.breakpoints)
                for line_number in file_state.breakpoints:
                    self._ensure_breakpoint_spec(file_state.file_path, line_number)

        for file_state in session_state.open_files:
            if not self._open_file_in_editor(file_state.file_path):
                self._breakpoints_by_file.pop(file_state.file_path, None)
                continue
            editor_widget = self._editor_widgets_by_path.get(file_state.file_path)
            if editor_widget is None:
                continue
            self._restore_editor_cursor_and_scroll(editor_widget, file_state)

        if session_state.active_file_path is not None and self._editor_tabs_widget is not None:
            active_index = self._tab_index_for_path(session_state.active_file_path)
            if active_index >= 0:
                self._editor_tabs_widget.setCurrentIndex(active_index)
        self._refresh_breakpoints_list()

    def _restore_editor_cursor_and_scroll(self, editor_widget: CodeEditorWidget, file_state: SessionFileState) -> None:
        target_line = max(1, file_state.cursor_line)
        target_column = max(1, file_state.cursor_column)
        document = editor_widget.document()
        block = document.findBlockByNumber(target_line - 1)
        if block.isValid():
            max_column_offset = max(0, block.length() - 1)
            column_offset = min(target_column - 1, max_column_offset)
            target_position = block.position() + column_offset
        else:
            target_position = max(0, document.characterCount() - 1)
        cursor = editor_widget.textCursor()
        cursor.setPosition(target_position)
        editor_widget.setTextCursor(cursor)
        scroll_position = max(0, file_state.scroll_position)
        QTimer.singleShot(0, lambda widget=editor_widget, value=scroll_position: widget.verticalScrollBar().setValue(value))

    def _confirm_proceed_with_unsaved_changes(self, action_description: str) -> bool:
        dirty_tabs = [tab for tab in self._editor_manager.all_tabs() if tab.is_dirty]
        if not dirty_tabs:
            return True

        response = QMessageBox.warning(
            self,
            "Unsaved changes",
            (
                f"You have {len(dirty_tabs)} unsaved file(s) before {action_description}.\n"
                "Would you like to save changes first?"
            ),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )

        if response == QMessageBox.Cancel:
            return False
        if response == QMessageBox.Discard:
            return True

        return self._handle_save_all_action()

    def _handle_save_action(self) -> bool:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return False
        return self._save_tab(active_tab.file_path)

    def _handle_save_all_action(self) -> bool:
        any_failure = False
        for tab in self._editor_manager.all_tabs():
            if not tab.is_dirty:
                continue
            if not self._save_tab(tab.file_path):
                any_failure = True
        self._refresh_save_action_states()
        return not any_failure

    def _handle_toggle_auto_save(self, checked: bool) -> None:
        self._editor_auto_save = checked
        self._settings_service.update_global(
            lambda payload: _merge_auto_save_setting(payload, checked)
        )
        if not checked:
            self._auto_save_to_file_timer.stop()

    def _sync_auto_save_menu_state(self) -> None:
        if self._menu_registry is None:
            return
        action = self._menu_registry.action("shell.action.file.autoSave")
        if action is not None:
            action.blockSignals(True)
            action.setChecked(self._editor_auto_save)
            action.blockSignals(False)

    def _schedule_auto_save_to_file(self) -> None:
        self._auto_save_to_file_timer.start()

    def _flush_auto_save_to_file(self) -> None:
        if not self._editor_auto_save:
            return
        for tab in self._editor_manager.all_tabs():
            if not tab.is_dirty:
                continue
            try:
                self._save_tab(
                    tab.file_path,
                    show_style_warnings=False,
                    checkpoint_source="auto_save_to_file",
                )
            except Exception:
                self._logger.warning("Auto-save to file failed for %s", tab.file_path, exc_info=True)

    def _save_tab(
        self,
        file_path: str,
        *,
        show_style_warnings: bool = True,
        checkpoint_source: str = "save",
    ) -> bool:
        path_existed_before_save = Path(file_path).expanduser().resolve().exists()
        self._apply_save_transforms(file_path, show_style_warnings=show_style_warnings)
        try:
            saved_tab = self._editor_manager.save_tab(file_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            self._logger.warning("Save failed for %s: %s", file_path, exc)
            return False

        if self._editor_tabs_widget is not None:
            tab_index = self._tab_index_for_path(saved_tab.file_path)
            if tab_index >= 0:
                self._refresh_tab_presentation(saved_tab.file_path)

        self._pending_autosave_payloads.pop(saved_tab.file_path, None)
        self._record_local_history_checkpoint(
            saved_tab.file_path,
            saved_tab.current_content,
            source=checkpoint_source,
        )
        project_id, project_root = self._local_history_context_for_path(saved_tab.file_path)
        self._autosave_store.delete_draft(
            saved_tab.file_path,
            project_id=project_id,
            project_root=project_root,
        )
        if not path_existed_before_save and project_id is not None:
            self._reload_current_project()
        self._refresh_save_action_states()
        self._update_editor_status_for_path(saved_tab.file_path)
        if should_refresh_index_after_save(
            self._intelligence_runtime_settings,
            has_loaded_project=self._loaded_project is not None,
        ) and self._loaded_project is not None:
            self._start_symbol_indexing(self._loaded_project.project_root)
        if saved_tab.file_path.lower().endswith(".py"):
            self._render_lint_diagnostics_for_file(saved_tab.file_path, trigger="save")
        self._logger.info("Saved file: %s", saved_tab.file_path)
        return True

    def _local_history_context_for_path(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        loaded_project = self._loaded_project
        if loaded_project is None:
            return (None, None)
        metadata = getattr(loaded_project, "metadata", None)
        project_id = None if metadata is None else getattr(metadata, "project_id", None)
        normalized_file_path = Path(file_path).expanduser().resolve()
        project_root = Path(loaded_project.project_root).expanduser().resolve()
        try:
            normalized_file_path.relative_to(project_root)
        except ValueError:
            return (None, None)
        return (project_id, str(project_root))

    def _record_local_history_checkpoint(
        self,
        file_path: str,
        content: str,
        *,
        source: str,
        label: str = "",
        transaction_id: Optional[str] = None,
    ) -> None:
        history_store = getattr(self, "_local_history_store", None)
        if history_store is None:
            return
        project_id, project_root = self._local_history_context_for_path(file_path)
        try:
            checkpoint = history_store.create_checkpoint(
                file_path,
                content,
                project_id=project_id,
                project_root=project_root,
                source=source,
                label=label,
                transaction_id=transaction_id,
            )
        except Exception:
            self._logger.warning("Local history checkpoint failed for %s", file_path, exc_info=True)
            return
        if checkpoint is None:
            skip_reason = history_store.checkpoint_skip_reason(
                file_path,
                content,
                project_root=project_root,
            )
            if skip_reason == "excluded":
                self.statusBar().showMessage(
                    f"Local history skipped for {Path(file_path).name}: file matches a local-history exclude pattern.",
                    5000,
                )
            elif skip_reason == "too_large":
                max_bytes = self._local_history_retention_policy.max_tracked_file_bytes
                self.statusBar().showMessage(
                    (
                        f"Local history skipped for {Path(file_path).name}: "
                        f"file exceeds the {max_bytes} byte tracking limit."
                    ),
                    5000,
                )
            self._logger.info("Local history checkpoint skipped for %s", file_path)

    def _record_local_history_transaction(
        self,
        payloads_by_path: Mapping[str, str],
        *,
        source: str,
        label: str,
    ) -> None:
        normalized_payloads = {path: payload for path, payload in payloads_by_path.items() if payload is not None}
        if not normalized_payloads:
            return
        transaction_id = None
        if len(normalized_payloads) > 1:
            transaction_id = f"txn_{uuid.uuid4().hex}"
        for file_path, payload in normalized_payloads.items():
            self._record_local_history_checkpoint(
                file_path,
                payload,
                source=source,
                label=label,
                transaction_id=transaction_id,
            )

    def _capture_text_history_snapshots(self, target_paths: list[str]) -> dict[str, str]:
        snapshots: dict[str, str] = {}
        for target_path in target_paths:
            path = Path(target_path).expanduser().resolve()
            if path.is_file():
                candidate_paths = [path]
            elif path.is_dir():
                candidate_paths = sorted(child for child in path.rglob("*") if child.is_file())
            else:
                continue
            for candidate in candidate_paths:
                try:
                    snapshots[str(candidate.resolve())] = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
        return snapshots

    def _filter_snapshots_for_paths(
        self,
        snapshots_by_path: Mapping[str, str],
        accepted_paths: list[str],
    ) -> dict[str, str]:
        accepted_prefixes = [str(Path(path).expanduser().resolve()) for path in accepted_paths]
        filtered: dict[str, str] = {}
        for file_path, payload in snapshots_by_path.items():
            normalized_path = str(Path(file_path).expanduser().resolve())
            if any(
                normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
                for prefix in accepted_prefixes
            ):
                filtered[normalized_path] = payload
        return filtered

    def _record_deleted_local_history_path(self, deleted_path: str) -> None:
        history_store = getattr(self, "_local_history_store", None)
        if history_store is None:
            return
        project_id, project_root = self._local_history_context_for_path(deleted_path)
        if project_id is None:
            return
        try:
            history_store.record_deleted_path(
                project_id=project_id,
                project_root=project_root,
                deleted_path=deleted_path,
            )
        except Exception:
            self._logger.warning("Local history delete tracking failed for %s", deleted_path, exc_info=True)

    def _remap_local_history_file_lineage(self, path_mapping: dict[str, str]) -> None:
        history_store = getattr(self, "_local_history_store", None)
        if history_store is None or not path_mapping:
            return
        first_path = next(iter(path_mapping.values()))
        project_id, project_root = self._local_history_context_for_path(first_path)
        if project_id is None:
            return
        try:
            history_store.remap_file_lineage(
                project_id=project_id,
                project_root=project_root,
                path_mapping=path_mapping,
            )
        except Exception:
            self._logger.warning("Local history path remap failed for %s", path_mapping, exc_info=True)

    def _current_text_for_history_path(self, file_path: str) -> str:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is not None:
            return tab_state.current_content
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def _restore_local_history_content_to_buffer(self, file_path: str, content: str) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            target_path = Path(file_path).expanduser().resolve()
            if target_path.exists():
                self._open_file_in_editor(file_path, preview=False)
            else:
                self._open_restored_history_buffer(file_path, content)
            tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            QMessageBox.warning(self, "Local History", f"Could not open {Path(file_path).name} for restore.")
            return
        self._apply_text_to_open_tab(file_path, content)
        updated_tab = self._editor_manager.update_tab_content(file_path, content)
        tab_index = self._tab_index_for_path(file_path)
        if self._editor_tabs_widget is not None and tab_index >= 0:
            self._refresh_tab_presentation(updated_tab.file_path)
        self._schedule_autosave(updated_tab.file_path, updated_tab.current_content)

    def _show_local_history_for_entry(self, summary: LocalHistoryFileSummary) -> None:
        self._show_local_history_for_path(
            summary.file_path,
            project_id=summary.project_id,
            project_root=summary.project_root,
            file_name=Path(summary.display_path or summary.file_path).name,
        )

    def _show_local_history_for_path(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> None:
        history_store = getattr(self, "_local_history_store", None)
        if history_store is None:
            return
        if project_id is None and project_root is None:
            project_id, project_root = self._local_history_context_for_path(file_path)
        checkpoints = history_store.list_checkpoints(
            file_path,
            project_id=project_id,
            project_root=project_root,
            include_deleted=True,
        )
        if not checkpoints:
            QMessageBox.information(self, "Local History", "No local-history entries are available for this file yet.")
            return
        dialog = LocalHistoryDialog(
            file_name=file_name or Path(file_path).name,
            checkpoints=checkpoints,
            current_text=self._current_text_for_history_path(file_path),
            checkpoint_content_loader=history_store.load_checkpoint_content,
            restore_to_buffer=lambda content: self._restore_local_history_content_to_buffer(file_path, content),
            parent=self,
        )
        dialog.exec_()

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

    def _python_tooling_failure_message(self, action_label: str, result: PythonTextTransformResult) -> str:
        if result.status == PYTHON_TOOLING_STATUS_SYNTAX_ERROR:
            return f"{action_label} skipped because the file contains Python syntax errors."
        if result.status == PYTHON_TOOLING_STATUS_CONFIG_ERROR:
            details = f"\n\n{result.error_message}" if result.error_message else ""
            return f"{action_label} skipped because project-local pyproject settings could not be parsed.{details}"
        if result.status == PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE:
            details = f"\n\n{result.error_message}" if result.error_message else ""
            return f"{action_label} is unavailable because the vendored Python tooling could not be loaded.{details}"
        details = f"\n\n{result.error_message}" if result.error_message else ""
        return f"{action_label} failed.{details}"

    def _should_skip_python_style_on_save(self, source_text: str) -> bool:
        return len(source_text) > PYTHON_STYLE_SAVE_GUARDRAIL_CHAR_LIMIT

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

    def _consume_save_python_tool_result(
        self,
        *,
        action_label: str,
        current_text: str,
        result: PythonTextTransformResult,
        warning_messages: list[str],
    ) -> str:
        if result.status in {PYTHON_TOOLING_STATUS_FORMATTED, PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED}:
            return result.formatted_text
        if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
            return current_text
        warning_messages.append(self._python_tooling_failure_message(action_label, result))
        return current_text

    def _apply_save_transforms(self, file_path: str, *, show_style_warnings: bool) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return

        original_text = tab_state.current_content
        transformed_text = format_text_basic(
            original_text,
            trim_trailing_whitespace=self._editor_trim_trailing_whitespace_on_save,
            ensure_final_newline=self._editor_insert_final_newline_on_save,
        ).formatted_text

        warning_messages: list[str] = []
        is_python_file = file_path.lower().endswith(".py")
        should_run_python_style = is_python_file and (
            self._editor_organize_imports_on_save or self._editor_format_on_save
        )
        if should_run_python_style:
            if self._should_skip_python_style_on_save(transformed_text):
                warning_messages.append(
                    "Python style automation was skipped on save because the file exceeds the size guardrail."
                )
            else:
                project_root = self._resolve_python_tooling_project_root(file_path)
                if self._editor_organize_imports_on_save:
                    try:
                        _provider, organize_result = organize_imports_with_workflow(
                            self._workflow_broker,
                            source_text=transformed_text,
                            file_path=file_path,
                            project_root=project_root,
                        )
                    except Exception as exc:
                        warning_messages.append(f"Organize Imports on save failed: {exc}")
                    else:
                        transformed_text = self._consume_save_python_tool_result(
                            action_label="Organize Imports on save",
                            current_text=transformed_text,
                            result=organize_result,
                            warning_messages=warning_messages,
                        )
                if self._editor_format_on_save:
                    try:
                        _provider, format_result = format_python_with_workflow(
                            self._workflow_broker,
                            source_text=transformed_text,
                            file_path=file_path,
                            project_root=project_root,
                        )
                    except Exception as exc:
                        warning_messages.append(f"Formatting on save failed: {exc}")
                    else:
                        transformed_text = self._consume_save_python_tool_result(
                            action_label="Formatting on save",
                            current_text=transformed_text,
                            result=format_result,
                            warning_messages=warning_messages,
                        )

        if transformed_text != original_text:
            self._apply_text_to_open_tab(file_path, transformed_text)
        if show_style_warnings and warning_messages:
            QMessageBox.warning(self, "Save formatting", "\n\n".join(warning_messages))

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

    def _resolve_active_named_run_config(self) -> RunConfiguration | None:
        loaded_project = self._loaded_project
        active_name = self._active_named_run_config_name
        if loaded_project is None or not active_name:
            return None
        configs = self._run_config_controller.load_configs(loaded_project)
        for config in configs:
            if config.name == active_name:
                return config
        self._active_named_run_config_name = None
        return None

    def _update_run_target_summary(self) -> None:
        toolbar = self._toolbar
        if toolbar is None or not hasattr(toolbar, "set_target_summary"):
            return
        active_tab = self._editor_manager.active_tab()
        active_file_label = "open a Python file"
        active_file_detail = "F5 Run needs an open Python file."
        if active_tab is not None:
            active_file_path = Path(active_tab.file_path).expanduser().resolve()
            if active_file_path.suffix.lower() == ".py":
                active_file_label = active_file_path.name
                active_file_detail = str(active_file_path)
                if active_tab.is_dirty:
                    active_file_detail += " (dirty buffer runs through a transient file)"
            else:
                active_file_label = f"{active_file_path.name} (not Python)"
                active_file_detail = f"{active_file_path}\nOpen a Python file before using F5 Run."

        project_label = "open project"
        project_detail = "Shift+F5 Run Project needs an open project."
        if self._loaded_project is not None:
            project_label = self._loaded_project.metadata.default_entry
            project_detail = (
                f"Project root: {self._loaded_project.project_root}\n"
                f"Default entry: {self._loaded_project.metadata.default_entry}\n"
                f"Project working directory: {self._loaded_project.metadata.working_directory or '.'}"
            )

        active_config = self._resolve_active_named_run_config()
        config_label = "none"
        config_detail = "No named run configuration is currently selected."
        if active_config is not None:
            config_label = active_config.name
            config_detail = (
                f"Name: {active_config.name}\n"
                f"Entry: {active_config.entry_file}\n"
                f"Working directory: {active_config.working_directory or '.'}\n"
                f"Env overrides: {env_overrides_to_text(active_config.env_overrides) or '(none)'}"
            )

        summary_text = f"Targets: F5 {active_file_label} | Shift+F5 {project_label} | Config {config_label}"
        summary_tooltip = (
            f"F5 Run: {active_file_detail}\n\n"
            f"Shift+F5 Run Project:\n{project_detail}\n\n"
            f"Active named configuration:\n{config_detail}\n\n"
            "Click to manage run configurations."
        )
        toolbar.set_target_summary(
            summary_text,
            tooltip=summary_tooltip,
            enabled=self._loaded_project is not None,
        )

    def _show_run_preflight_result(self, title: str, summary: str, issues: list[Any]) -> None:
        report = RuntimeIssueReport(workflow="run", issues=list(issues))
        self._open_runtime_center_dialog(title=title, report=report)
        self._append_console_line(summary, stream="system")

    def _ensure_run_preflight_ready(
        self,
        *,
        title: str,
        entry_file: str,
        working_directory: str | None = None,
        config_name: str | None = None,
    ) -> bool:
        result = build_run_preflight(
            loaded_project=self._loaded_project,
            entry_file=entry_file,
            working_directory=working_directory,
            config_name=config_name,
        )
        if result.is_ready:
            return True
        self._show_run_preflight_result(title, result.summary, result.issues)
        return False

    def _handle_run_action(self) -> bool:
        return self._start_active_file_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)

    def _handle_debug_action(self) -> bool:
        return self._start_active_file_session(mode=constants.RUN_MODE_PYTHON_DEBUG)

    def _handle_run_project_action(self) -> bool:
        entry_file = self._resolve_project_entry_for_project_run()
        if entry_file is None:
            return False
        if not self._ensure_run_preflight_ready(title="Run Project", entry_file=entry_file):
            return False
        return self._start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, entry_file=entry_file)

    def _handle_debug_project_action(self) -> bool:
        entry_file = self._resolve_project_entry_for_project_run()
        if entry_file is None:
            return False
        if not self._ensure_run_preflight_ready(title="Debug Project", entry_file=entry_file):
            return False
        started = self._start_session(
            mode=constants.RUN_MODE_PYTHON_DEBUG,
            entry_file=entry_file,
            breakpoints=self._build_debug_breakpoints_for_launch(),
            debug_exception_policy=self._debug_exception_policy,
        )
        if started:
            self._last_debug_target = {"kind": "project"}
        return started

    def _start_active_file_session(self, *, mode: str) -> bool:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Run unavailable", "Open a file tab before running.")
            return False
        entry_path = Path(active_tab.file_path).expanduser().resolve()
        active_file_path = str(entry_path)
        if entry_path.suffix.lower() != ".py":
            QMessageBox.warning(self, "Run unavailable", "Active file must be a Python file.")
            return False
        transient_entry_file: str | None = None
        entry_file = active_file_path
        skip_save = False
        source_maps: list[DebugSourceMap] | None = None
        if active_tab.is_dirty:
            transient_entry_file = self._write_transient_entry_file(
                source_file_path=active_tab.file_path,
                source_content=active_tab.current_content,
            )
            entry_file = transient_entry_file
            skip_save = True
            source_maps = [DebugSourceMap(runtime_path=transient_entry_file, source_path=active_file_path)]
        breakpoints: list[DebugBreakpoint] | None = None
        if mode == constants.RUN_MODE_PYTHON_DEBUG:
            breakpoints = self._build_debug_breakpoints_for_launch(
                active_file_path=active_file_path,
                remapped_active_path=transient_entry_file,
            )
        started = self._start_session(
            mode=mode,
            entry_file=entry_file,
            breakpoints=breakpoints,
            debug_exception_policy=self._debug_exception_policy if mode == constants.RUN_MODE_PYTHON_DEBUG else None,
            source_maps=source_maps,
            skip_save=skip_save,
        )
        if started and mode == constants.RUN_MODE_PYTHON_DEBUG:
            self._last_debug_target = {"kind": "active_file", "file_path": active_file_path}
        if transient_entry_file is not None:
            if started:
                self._active_transient_entry_file_path = transient_entry_file
            else:
                self._delete_transient_entry_file(transient_entry_file)
        return started

    def _write_transient_entry_file(self, *, source_file_path: str, source_content: str) -> str:
        source_name = Path(source_file_path).name
        safe_stem = Path(source_name).stem or "buffer"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".py",
            prefix=f"cbcs_{safe_stem}_",
            delete=False,
        ) as handle:
            handle.write(source_content)
            return str(Path(handle.name).resolve())

    def _delete_transient_entry_file(self, path: str) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            self._logger.warning("Failed to delete transient run file: %s", path)

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
        candidates: list[str] = []
        for candidate in sorted(project_root.rglob("*.py")):
            if constants.PROJECT_META_DIRNAME in candidate.parts:
                continue
            if candidate.is_file():
                candidates.append(candidate.relative_to(project_root).as_posix())
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
            )
        except (ProjectManifestValidationError, ValueError) as exc:
            QMessageBox.warning(self, "Entry point", str(exc))
            return False
        self._loaded_project = replace(loaded_project, metadata=updated_metadata)
        self._populate_project_tree(self._loaded_project, preserve_state=True)
        return True

    def _handle_run_pytest_project_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Run Project Tests", "Open a project first.")
            return
        project_root = self._loaded_project.project_root
        self._append_console_line(f"Running pytest in {project_root}", stream="system")

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return run_pytest_with_workflow(
                self._workflow_broker,
                project_root=project_root,
            )

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            provider, result = payload
            self._append_console_line(f"Pytest completed via {provider.title}", stream="system")
            self._handle_pytest_run_result(result)

        def on_error(exc: Exception) -> None:
            self._append_console_line(f"Pytest run failed to start: {exc}", stream="stderr")
            QMessageBox.warning(self, "Run Project Tests", f"Pytest run failed: {exc}")

        self._background_tasks.run(
            key="run_pytest_project",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_run_pytest_current_file_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Run Current File Tests", "Open a project first.")
            return
        loaded_project = self._loaded_project
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Run Current File Tests", "Open a file tab first.")
            return
        target_path = Path(active_tab.file_path).expanduser().resolve()
        project_root_path = Path(loaded_project.project_root).expanduser().resolve()
        try:
            target_path.relative_to(project_root_path)
        except ValueError:
            QMessageBox.warning(
                self,
                "Run Current File Tests",
                "Current file is outside project root and cannot be run as a test target.",
            )
            return
        self._append_console_line(f"Running pytest for {target_path}", stream="system")

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return run_pytest_with_workflow(
                self._workflow_broker,
                project_root=loaded_project.project_root,
                target_path=str(target_path),
            )

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            provider, result = payload
            self._append_console_line(f"Pytest completed via {provider.title}", stream="system")
            self._handle_pytest_run_result(result)

        def on_error(exc: Exception) -> None:
            self._append_console_line(f"Pytest target run failed to start: {exc}", stream="stderr")
            QMessageBox.warning(self, "Run Current File Tests", f"Pytest run failed: {exc}")

        self._background_tasks.run(
            key="run_pytest_target",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_debug_pytest_current_file_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Debug Current Test", "Open a project first.")
            return
        loaded_project = self._loaded_project
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Debug Current Test", "Open a file tab first.")
            return
        target_path = Path(active_tab.file_path).expanduser().resolve()
        project_root_path = Path(loaded_project.project_root).expanduser().resolve()
        try:
            target_path.relative_to(project_root_path)
        except ValueError:
            QMessageBox.warning(
                self,
                "Debug Current Test",
                "Current file is outside project root and cannot be debugged as a pytest target.",
            )
            return
        run_tests_path = project_root_path / "run_tests.py"
        if not run_tests_path.is_file():
            QMessageBox.warning(
                self,
                "Debug Current Test",
                "This project does not contain `run_tests.py`, so the pytest debug flow is unavailable.",
            )
            return
        started = self._start_session(
            mode=constants.RUN_MODE_PYTHON_DEBUG,
            entry_file=str(run_tests_path),
            argv=["-q", "--import-mode=importlib", str(target_path)],
            breakpoints=self._build_debug_breakpoints_for_launch(),
            debug_exception_policy=self._debug_exception_policy,
        )
        if started:
            self._last_debug_target = {"kind": "current_test", "target_path": str(target_path)}

    def _handle_rerun_last_debug_target_action(self) -> None:
        target = self._last_debug_target
        if not target:
            QMessageBox.information(self, "Rerun Last Debug Target", "No previous debug target is available yet.")
            return
        kind = str(target.get("kind", "")).strip()
        if kind == "project":
            self._handle_debug_project_action()
            return
        if kind == "active_file":
            file_path = str(target.get("file_path", "")).strip()
            if not file_path:
                return
            if not self._open_file_in_editor(file_path, preview=False):
                QMessageBox.warning(self, "Rerun Last Debug Target", "The previous debug file could not be reopened.")
                return
            if self._editor_tabs_widget is not None:
                index = self._tab_index_for_path(file_path)
                if index >= 0:
                    self._editor_tabs_widget.setCurrentIndex(index)
            self._handle_debug_action()
            return
        if kind == "current_test":
            file_path = str(target.get("target_path", "")).strip()
            if file_path and self._open_file_in_editor(file_path, preview=False) and self._editor_tabs_widget is not None:
                index = self._tab_index_for_path(file_path)
                if index >= 0:
                    self._editor_tabs_widget.setCurrentIndex(index)
            self._handle_debug_pytest_current_file_action()

    def _handle_run_with_configuration_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Run With Configuration", "Open a project first.")
            return
        configs = self._run_config_controller.load_configs(self._loaded_project)
        if not configs:
            QMessageBox.information(
                self,
                "Run With Configuration",
                "No run configurations are defined. Use 'Manage Run Configurations...' first.",
            )
            return
        names = [config.name for config in configs]
        selected_name, accepted = QInputDialog.getItem(
            self,
            "Run With Configuration",
            "Select run configuration:",
            names,
            0,
            False,
        )
        if not accepted or not selected_name:
            return
        selected_config = next((config for config in configs if config.name == selected_name), None)
        if selected_config is None:
            QMessageBox.warning(self, "Run With Configuration", "Selected configuration could not be resolved.")
            return
        self._active_named_run_config_name = selected_config.name
        self._refresh_run_action_states()
        if not self._ensure_run_preflight_ready(
            title=f"Run Configuration: {selected_config.name}",
            entry_file=selected_config.entry_file,
            working_directory=selected_config.working_directory,
            config_name=selected_config.name,
        ):
            return
        self._start_session(
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            entry_file=selected_config.entry_file,
            argv=selected_config.argv,
            working_directory=selected_config.working_directory,
            env_overrides=selected_config.env_overrides,
        )

    def _handle_manage_run_configurations_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Manage Run Configurations", "Open a project first.")
            return
        existing_configs = self._run_config_controller.load_configs(self._loaded_project)
        choices = [config.name for config in existing_configs]
        create_label = "<Create new configuration>"
        choices.append(create_label)
        selected_name, accepted_selection = QInputDialog.getItem(
            self,
            "Manage Run Configurations",
            "Select configuration to edit:",
            choices,
            0,
            False,
        )
        if not accepted_selection or not selected_name:
            return
        selected_config = next((config for config in existing_configs if config.name == selected_name), None)
        if selected_config is not None:
            action_choice, accepted_action = QInputDialog.getItem(
                self,
                "Manage Run Configurations",
                f"Action for '{selected_config.name}':",
                ["Edit", "Delete"],
                0,
                False,
            )
            if not accepted_action or not action_choice:
                return
            if action_choice == "Delete":
                confirm = QMessageBox.question(
                    self,
                    "Manage Run Configurations",
                    f"Delete run configuration '{selected_config.name}'?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if confirm != QMessageBox.Yes:
                    return
                try:
                    self._run_config_controller.delete_config(
                        loaded_project=self._loaded_project,
                        existing_configs=existing_configs,
                        config_name=selected_config.name,
                    )
                except AppValidationError as exc:
                    QMessageBox.warning(self, "Manage Run Configurations", str(exc))
                    return
                if self._active_named_run_config_name == selected_config.name:
                    self._active_named_run_config_name = None
                self._reload_current_project()
                self._refresh_run_action_states()
                QMessageBox.information(
                    self,
                    "Manage Run Configurations",
                    f"Deleted configuration '{selected_config.name}'.",
                )
                return
        if selected_name == create_label or selected_config is None:
            selected_config = self._run_config_controller.build_default_config(self._loaded_project)

        config_name, accepted_name = QInputDialog.getText(
            self,
            "Manage Run Configurations",
            "Configuration name:",
            QLineEdit.Normal,
            selected_config.name,
        )
        if not accepted_name or not config_name.strip():
            return
        entry_file, accepted_entry = QInputDialog.getText(
            self,
            "Manage Run Configurations",
            "Entry file (relative to project root):",
            QLineEdit.Normal,
            selected_config.entry_file,
        )
        if not accepted_entry or not entry_file.strip():
            return
        argv_text, accepted_argv = QInputDialog.getText(
            self,
            "Manage Run Configurations",
            "Arguments (space-separated):",
            QLineEdit.Normal,
            " ".join(selected_config.argv),
        )
        if not accepted_argv:
            return
        working_directory_text, accepted_working_directory = QInputDialog.getText(
            self,
            "Manage Run Configurations",
            "Working directory override (blank uses project default):",
            QLineEdit.Normal,
            "" if selected_config.working_directory is None else selected_config.working_directory,
        )
        if not accepted_working_directory:
            return
        env_overrides_text, accepted_env = QInputDialog.getText(
            self,
            "Manage Run Configurations",
            "Env overrides (comma-separated KEY=VALUE):",
            QLineEdit.Normal,
            env_overrides_to_text(selected_config.env_overrides),
        )
        if not accepted_env:
            return

        try:
            updated_config = self._run_config_controller.parse_config_input(
                name=config_name,
                entry_file=entry_file,
                argv_text=argv_text,
                working_directory_text=working_directory_text,
                env_overrides_text=env_overrides_text,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Manage Run Configurations", str(exc))
            return
        try:
            self._run_config_controller.upsert_config(
                loaded_project=self._loaded_project,
                existing_configs=existing_configs,
                updated_config=updated_config,
            )
        except AppValidationError as exc:
            QMessageBox.warning(self, "Manage Run Configurations", str(exc))
            return
        self._reload_current_project()
        self._active_named_run_config_name = updated_config.name
        self._refresh_run_action_states()
        QMessageBox.information(
            self,
            "Manage Run Configurations",
            f"Saved configuration '{updated_config.name}'.",
        )

    def _handle_pytest_run_result(self, result: PytestRunResult) -> None:
        if result.stdout.strip():
            for line in result.stdout.splitlines():
                self._append_console_line(line, stream="stdout")
        if result.stderr.strip():
            for line in result.stderr.splitlines():
                self._append_console_line(line, stream="stderr")
        if self._auto_open_console_on_run_output and (result.stdout.strip() or result.stderr.strip()):
            self._focus_run_log_tab()
        if result.failures:
            self._set_problems(result.failures)
            if self._auto_open_problems_on_run_failure:
                self._focus_problems_tab()
        else:
            self._set_problems([])
        status = "passed" if result.succeeded else "failed"
        self._append_console_line(
            f"Pytest run {status} (code={result.return_code}, elapsed_ms={result.elapsed_ms:.2f}).",
            stream="system",
        )

    def _handle_start_python_console_action(self) -> bool:
        self._repl_manager.restart()
        self._focus_python_console_tab()
        return True

    def _prepare_for_session_start(self) -> None:
        self._active_run_output_tail.clear()
        self._clear_problems()
        self._debug_session = DebugSession()
        self._clear_debug_execution_indicator()
        if self._run_log_panel is not None:
            self._run_log_panel.begin_run()

    def _start_session(
        self,
        *,
        mode: str,
        entry_file: str | None = None,
        argv: list[str] | None = None,
        working_directory: str | None = None,
        env_overrides: dict[str, str] | None = None,
        breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None = None,
        debug_exception_policy: DebugExceptionPolicy | None = None,
        source_maps: list[DebugSourceMap] | None = None,
        skip_save: bool = False,
    ) -> bool:
        result = self._run_session_controller.start_session(
            loaded_project=self._loaded_project,
            mode=mode,
            entry_file=entry_file,
            argv=argv,
            working_directory=working_directory,
            env_overrides=env_overrides,
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
            source_maps=source_maps,
            skip_save=skip_save,
            save_all=self._handle_save_all_action,
            before_start=self._prepare_for_session_start,
            append_console_line=lambda text, stream: self._append_console_line(text, stream=stream),
            append_python_console_line=self._append_python_console_line,
        )
        if not result.started:
            if result.failure_reason == RunSessionStartFailureReason.NO_PROJECT:
                QMessageBox.warning(self, "Run unavailable", result.error_message or "No project is loaded.")
            elif result.failure_reason == RunSessionStartFailureReason.SAVE_FAILED:
                QMessageBox.warning(self, "Run cancelled", result.error_message or "Save was cancelled.")
            elif result.failure_reason == RunSessionStartFailureReason.ALREADY_RUNNING:
                pass
            elif result.error_message:
                QMessageBox.warning(self, "Run failed to start", result.error_message)
            self._set_run_status("idle")
            self._refresh_run_action_states()
            return False

        if result.session is not None:
            self._active_run_session_log_path = result.session.log_file_path
            self._active_run_session_info = RunInfo(
                run_id=result.session.run_id,
                mode=result.session.mode,
                entry_file=result.session.entry_file,
            )
            self._event_bus.publish(
                RunSessionStartedEvent(
                    run_id=result.session.run_id,
                    mode=result.session.mode,
                    entry_file=result.session.entry_file,
                    project_root=result.session.project_root,
                )
            )
        if self._debug_panel is not None:
            self._debug_panel.set_command_input_enabled(
                self._run_session_controller.active_session_mode == constants.RUN_MODE_PYTHON_DEBUG
            )
        self._set_run_status("running")
        if self._auto_open_console_on_run_output:
            self._focus_run_log_tab()
        self._refresh_run_action_states()
        return True

    def _handle_stop_action(self) -> None:
        self._run_session_controller.stop_session(lambda text, stream: self._append_console_line(text, stream=stream))
        self._set_run_status("stopping")
        self._refresh_run_action_states()

    def _handle_restart_action(self) -> None:
        if self._run_service.supervisor.is_running():
            self._run_service.stop_run()
        if self._run_session_controller.active_session_mode == constants.RUN_MODE_PYTHON_DEBUG:
            self._handle_rerun_last_debug_target_action()
        else:
            self._handle_run_action()

    def _handle_continue_debug_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        command_name, arguments = continue_command()
        self._send_debug_command(command_name, arguments)

    def _handle_pause_debug_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        _paused, error_message = self._run_session_controller.pause_session(
            append_python_console_line=self._append_python_console_line,
            append_debug_output_line=self._append_debug_output_line,
        )
        if error_message is not None:
            QMessageBox.warning(self, "Pause failed", error_message)

    def _handle_step_over_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        command_name, arguments = step_over_command()
        self._send_debug_command(command_name, arguments)

    def _handle_step_into_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        command_name, arguments = step_into_command()
        self._send_debug_command(command_name, arguments)

    def _handle_step_out_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        command_name, arguments = step_out_command()
        self._send_debug_command(command_name, arguments)

    def _handle_toggle_breakpoint_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            return
        line_number = editor_widget.textCursor().blockNumber() + 1
        editor_widget.toggle_breakpoint(line_number)

    def _handle_remove_all_breakpoints_action(self) -> None:
        self._breakpoints_by_file.clear()
        self._breakpoint_specs_by_key.clear()
        for editor_widget in self._editor_widgets_by_path.values():
            editor_widget.set_breakpoints(set())
        self._refresh_breakpoints_list()
        self._sync_breakpoints_to_active_debug_session()
        self._refresh_run_action_states()

    def _handle_editor_breakpoint_toggled(self, file_path: str, line_number: int, enabled: bool) -> None:
        breakpoints = self._breakpoints_by_file.setdefault(file_path, set())
        if enabled:
            breakpoints.add(line_number)
            self._ensure_breakpoint_spec(file_path, line_number)
        else:
            breakpoints.discard(line_number)
            self._breakpoint_specs_by_key.pop(breakpoint_key(file_path, line_number), None)
        if not breakpoints:
            self._breakpoints_by_file.pop(file_path, None)
        self._refresh_breakpoints_list()
        self._sync_breakpoints_to_active_debug_session()
        self._refresh_run_action_states()

    def _refresh_breakpoints_list(self) -> None:
        if self._debug_panel is None:
            return
        self._debug_panel.set_breakpoints(self._display_breakpoints())

    def _ensure_breakpoint_spec(self, file_path: str, line_number: int) -> DebugBreakpoint:
        key = breakpoint_key(file_path, line_number)
        existing = self._breakpoint_specs_by_key.get(key)
        if existing is not None:
            return existing
        created = build_breakpoint(file_path=file_path, line_number=line_number)
        self._breakpoint_specs_by_key[key] = created
        return created

    def _all_breakpoints(self) -> list[DebugBreakpoint]:
        breakpoints = list(self._breakpoint_specs_by_key.values())
        return sorted(breakpoints, key=lambda breakpoint: (breakpoint.file_path, breakpoint.line_number))

    def _display_breakpoints(self) -> list[DebugBreakpoint]:
        verified_by_id = {
            breakpoint.breakpoint_id: breakpoint
            for breakpoint in self._debug_session.state.breakpoints
        }
        display_breakpoints: list[DebugBreakpoint] = []
        for breakpoint in self._all_breakpoints():
            verified = verified_by_id.get(breakpoint.breakpoint_id)
            if verified is None:
                display_breakpoints.append(breakpoint)
                continue
            display_breakpoints.append(
                DebugBreakpoint(
                    breakpoint_id=breakpoint.breakpoint_id,
                    file_path=breakpoint.file_path,
                    line_number=breakpoint.line_number,
                    enabled=breakpoint.enabled,
                    condition=breakpoint.condition,
                    hit_condition=breakpoint.hit_condition,
                    verified=verified.verified,
                    verification_message=verified.verification_message,
                )
            )
        return display_breakpoints

    def _build_debug_breakpoints_for_launch(
        self,
        *,
        active_file_path: str | None = None,
        remapped_active_path: str | None = None,
    ) -> list[DebugBreakpoint]:
        launch_breakpoints: list[DebugBreakpoint] = []
        for breakpoint in self._all_breakpoints():
            file_path = breakpoint.file_path
            if active_file_path and remapped_active_path and file_path == active_file_path:
                file_path = remapped_active_path
            launch_breakpoints.append(
                DebugBreakpoint(
                    breakpoint_id=breakpoint.breakpoint_id,
                    file_path=file_path,
                    line_number=breakpoint.line_number,
                    enabled=breakpoint.enabled,
                    condition=breakpoint.condition,
                    hit_condition=breakpoint.hit_condition,
                    verified=breakpoint.verified,
                    verification_message=breakpoint.verification_message,
                )
            )
        return launch_breakpoints

    def _handle_clear_console_action(self) -> None:
        self._console_model.clear()
        if self._run_log_panel is not None:
            self._run_log_panel.clear()
        if self._python_console_widget is not None:
            self._python_console_widget.clear_console()
        if self._debug_panel is not None:
            self._debug_panel.clear_output()

    def _handle_format_current_file_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Format Current File", "Open a file tab first.")
            return

        source_text = editor_widget.toPlainText()
        if active_tab.file_path.lower().endswith(".py"):
            try:
                provider, result = format_python_with_workflow(
                    self._workflow_broker,
                    source_text=source_text,
                    file_path=active_tab.file_path,
                    project_root=self._resolve_python_tooling_project_root(active_tab.file_path),
                )
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Format Current File",
                    f"Formatting failed: {exc}",
                )
                return
            if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
                QMessageBox.information(self, "Format Current File", "File is already formatted.")
                return
            if result.status != PYTHON_TOOLING_STATUS_FORMATTED:
                QMessageBox.warning(
                    self,
                    "Format Current File",
                    self._python_tooling_failure_message("Formatting", result),
                )
                return
            editor_widget.replace_document_text(result.formatted_text)
            QMessageBox.information(
                self,
                "Format Current File",
                f"Formatting applied via {provider.title}.",
            )
            return

        result = format_text_basic(source_text)
        if not result.changed:
            QMessageBox.information(self, "Format Current File", "File is already formatted.")
            return

        editor_widget.replace_document_text(result.formatted_text)
        QMessageBox.information(self, "Format Current File", "Formatting applied.")

    def _handle_organize_imports_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Organize Imports", "Open a file tab first.")
            return
        if not active_tab.file_path.lower().endswith(".py"):
            QMessageBox.information(
                self,
                "Organize Imports",
                "Organize Imports is currently available for Python files only.",
            )
            return

        try:
            provider, result = organize_imports_with_workflow(
                self._workflow_broker,
                source_text=editor_widget.toPlainText(),
                file_path=active_tab.file_path,
                project_root=self._resolve_python_tooling_project_root(active_tab.file_path),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Organize Imports", f"Organize Imports failed: {exc}")
            return
        if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
            QMessageBox.information(self, "Organize Imports", "Imports are already organized.")
            return
        if result.status != PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED:
            QMessageBox.warning(
                self,
                "Organize Imports",
                self._python_tooling_failure_message("Organize Imports", result),
            )
            return

        editor_widget.replace_document_text(result.formatted_text)
        QMessageBox.information(self, "Organize Imports", f"Imports organized via {provider.title}.")

    def _handle_lint_current_file_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Lint Current File", "Open a file tab first.")
            return
        if not active_tab.file_path.lower().endswith(".py"):
            QMessageBox.information(self, "Lint Current File", "Linting is currently available for Python files only.")
            return
        self._render_lint_diagnostics_for_file(active_tab.file_path, trigger="manual")

    def _handle_apply_safe_fixes_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Apply Safe Fixes", "Open a file tab first.")
            return
        self._apply_safe_fixes_for_file(active_tab.file_path)

    def _handle_open_plugin_manager_action(self) -> None:
        if self._plugin_manager_dialog is None:
            self._plugin_manager_dialog = PluginManagerDialog(
                state_root=self._state_root,
                project_root=None if self._loaded_project is None else self._loaded_project.project_root,
                on_plugins_changed=self._reload_plugin_contributions,
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

    def _handle_plugin_safe_mode_changed(self, enabled: bool) -> None:
        self._set_plugin_safe_mode(enabled)
        self._reload_plugin_contributions()

    def _reload_plugin_contributions(self) -> None:
        if self._plugin_safe_mode:
            self._declarative_contribution_manager.clear()
            self._plugin_runtime_manager.stop()
            self._workflow_provider_catalog = WorkflowProviderCatalog([])
            self._workflow_broker.set_plugin_catalog(self._workflow_provider_catalog)
            return
        registry = load_plugin_registry(self._state_root)
        enabled_map = {
            (entry.plugin_id, entry.version): entry.enabled
            for entry in registry.entries
        }
        project_plugin_config = None
        if self._loaded_project is not None:
            try:
                project_plugin_config = load_project_plugin_config(self._loaded_project.project_root)
            except Exception:
                project_plugin_config = None
        discovered_plugins = discover_installed_plugins(
            state_root=self._state_root,
            include_bundled=True,
        )
        effective_enabled_map = dict(enabled_map)
        if project_plugin_config is not None:
            for discovered in discovered_plugins:
                default_enabled = effective_enabled_map.get((discovered.plugin_id, discovered.version), True)
                pinned_version = project_plugin_config.pinned_versions.get(discovered.plugin_id)
                if pinned_version is not None and pinned_version != discovered.version:
                    effective_enabled_map[(discovered.plugin_id, discovered.version)] = False
                    continue
                if discovered.plugin_id in project_plugin_config.enabled_plugins:
                    effective_enabled_map[(discovered.plugin_id, discovered.version)] = True
                if discovered.plugin_id in project_plugin_config.disabled_plugins:
                    effective_enabled_map[(discovered.plugin_id, discovered.version)] = False
        self._declarative_contribution_manager.apply(
            discovered_plugins,
            enabled_map=effective_enabled_map,
        )
        self._workflow_provider_catalog = WorkflowProviderCatalog.from_plugins(
            discovered_plugins,
            enabled_map=effective_enabled_map,
            project_config=project_plugin_config,
        )
        self._workflow_broker.set_plugin_catalog(
            self._workflow_provider_catalog,
            project_config=project_plugin_config,
        )
        self._plugin_api_broker.reload_runtime_plugins()

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
            self._reload_plugin_contributions()

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
            _provider, diagnostics = analyze_python_with_workflow(
                self._workflow_broker,
                file_path=file_path,
                project_root=project_root,
                source=buffer_source,
                known_runtime_modules=self._known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
                selected_linter=self._selected_linter,
                lint_rule_overrides=self._lint_rule_overrides,
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
        self._stored_lint_diagnostics[file_path] = diagnostics
        self._push_diagnostics_to_editor(file_path, diagnostics)
        self._update_tab_diagnostic_indicator(file_path, diagnostics)
        self._render_merged_problems_panel()
        active_tab = self._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path == file_path:
            self._update_status_bar_diagnostics(diagnostics)

    def _push_diagnostics_to_editor(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        editor_widget = self._editor_widgets_by_path.get(file_path)
        if editor_widget is None:
            return
        editor_widget.set_diagnostics(diagnostics)

    def _update_tab_diagnostic_indicator(self, file_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        if self._editor_tabs_widget is None:
            return
        tab_index = self._tab_index_for_path(file_path)
        if tab_index < 0:
            return
        has_error = any(d.severity == DiagnosticSeverity.ERROR for d in diagnostics)
        has_warning = any(d.severity == DiagnosticSeverity.WARNING for d in diagnostics)
        if has_error:
            icon = tab_diagnostic_icon(DiagnosticSeverity.ERROR, "#E03131")
        elif has_warning:
            icon = tab_diagnostic_icon(DiagnosticSeverity.WARNING, "#D97706")
        else:
            icon = QIcon()
        self._editor_tabs_widget.setTabIcon(tab_index, icon)

    def _clear_all_tab_diagnostic_indicators(self) -> None:
        if self._editor_tabs_widget is None:
            return
        empty = QIcon()
        for index in range(self._editor_tabs_widget.count()):
            self._editor_tabs_widget.setTabIcon(index, empty)

    def _update_status_bar_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        if self._status_controller is None:
            return
        errors = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.ERROR)
        warnings = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.WARNING)
        self._status_controller.set_diagnostics_counts(errors, warnings)

    def _render_merged_problems_panel(self) -> None:
        """Rebuild the Problems panel from stored lint + runtime state."""
        if self._problems_panel is None:
            return
        all_diags = [d for diags in self._stored_lint_diagnostics.values() for d in diags]
        self._problems_panel.set_quick_fixes_enabled(self._quick_fixes_enabled)
        self._problems_panel.set_diagnostics(all_diags, self._stored_runtime_problems)
        self._update_problems_tab_title(self._problems_panel.problem_count())

    def _update_problems_tab_title(self, count: int) -> None:
        if self._problems_tab_widget is None or self._problems_panel is None:
            return
        index = self._problems_tab_widget.indexOf(self._problems_panel)
        if index < 0:
            return
        title = f"Problems ({count})" if count > 0 else "Problems"
        self._problems_tab_widget.setTabText(index, title)

    def _apply_safe_fixes_for_file(self, file_path: str) -> None:
        if not self._quick_fixes_enabled:
            QMessageBox.information(self, "Apply Safe Fixes", "Quick fixes are currently disabled in Settings.")
            return
        if not file_path.lower().endswith(".py"):
            QMessageBox.information(self, "Apply Safe Fixes", "Safe fixes currently support Python files only.")
            return
        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        _provider, diagnostics = analyze_python_with_workflow(
            self._workflow_broker,
            file_path=file_path,
            project_root=project_root,
            known_runtime_modules=self._known_runtime_modules,
            allow_runtime_import_probe=True,
            selected_linter=self._selected_linter,
            lint_rule_overrides=self._lint_rule_overrides,
        )
        fixes = plan_safe_fixes_for_file(file_path, diagnostics, project_root=project_root)
        if not fixes:
            QMessageBox.information(self, "Apply Safe Fixes", "No safe fixes available for current file.")
            return

        affected_paths = {fix.file_path for fix in fixes}
        affected_paths.update(fix.target_path for fix in fixes if fix.target_path)
        should_confirm = self._quick_fix_require_preview_for_multifile or len(affected_paths) > 1
        if should_confirm:
            preview = "\n".join(f"- {fix.title}" for fix in fixes[:20])
            if len(fixes) > 20:
                preview += f"\n- ... and {len(fixes) - 20} more"
            confirm = QMessageBox.question(
                self,
                "Apply Safe Fixes",
                f"Apply {len(fixes)} safe fix(es)?\n\n{preview}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirm != QMessageBox.Yes:
                return

        try:
            changed_lines = apply_quick_fixes(fixes)
        except OSError as exc:
            QMessageBox.warning(self, "Apply Safe Fixes", f"Failed to apply fixes: {exc}")
            return

        if changed_lines <= 0:
            QMessageBox.information(self, "Apply Safe Fixes", "No changes were applied.")
            return

        affected_files = sorted(path for path in affected_paths if path)
        self._record_local_history_transaction(
            self._capture_text_history_snapshots(affected_files),
            source="quick_fix",
            label="Apply Safe Fixes",
        )
        self._refresh_open_tabs_from_disk(affected_files)
        if self._loaded_project is not None and any(path != file_path for path in affected_files):
            self._reload_current_project()
        self._render_lint_diagnostics_for_file(file_path, trigger="manual")
        QMessageBox.information(self, "Apply Safe Fixes", f"Applied {changed_lines} safe fix(es).")

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

    def _send_debug_command(self, command_name: str, arguments: dict[str, object] | None = None) -> None:
        try:
            self._run_service.send_debug_command(command_name, arguments)
        except Exception as exc:
            QMessageBox.warning(self, "Debug command failed", str(exc))
            return
        self._append_debug_output_line("[debug] %s" % (command_name.replace("_", " "),))

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
            except Exception:
                pass

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
            if not self._is_debug_navigation_target_allowed(frame.file_path):
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

    def _handle_debug_refresh_stack(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        selected_frame = self._debug_session.state.selected_frame
        if selected_frame is None:
            return
        command_name, arguments = select_frame_command(selected_frame.frame_id)
        self._send_debug_command(command_name, arguments)

    def _handle_debug_refresh_locals(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        selected_frame = self._debug_session.state.selected_frame
        if selected_frame is None:
            return
        command_name, arguments = select_frame_command(selected_frame.frame_id)
        self._send_debug_command(command_name, arguments)

    def _handle_debug_navigate_preview(self, file_path: str, line_number: int) -> None:
        if not self._is_debug_navigation_target_allowed(file_path):
            return
        self._open_file_at_line(file_path, line_number, preview=True)

    def _handle_debug_navigate_permanent(self, file_path: str, line_number: int) -> None:
        if not self._is_debug_navigation_target_allowed(file_path):
            return
        self._open_file_at_line(file_path, line_number, preview=False)

    def _is_debug_navigation_target_allowed(self, file_path: str) -> bool:
        if self._loaded_project is None:
            return True
        candidate_path = Path(file_path).expanduser().resolve()
        project_root_path = Path(self._loaded_project.project_root).expanduser().resolve()
        try:
            candidate_path.relative_to(project_root_path)
            return True
        except ValueError:
            return False

    def _handle_debug_watch_evaluate(self, expression: str) -> None:
        if not self._run_service.supervisor.is_running():
            return
        frame_id = 0
        selected_frame = self._debug_session.state.selected_frame
        if selected_frame is not None:
            frame_id = selected_frame.frame_id
        command_name, arguments = evaluate_command(expression, frame_id=frame_id)
        self._send_debug_command(command_name, arguments)

    def _handle_debug_command_submit(self, command_text: str) -> None:
        if not command_text.strip():
            return
        if self._run_session_controller.active_session_mode != constants.RUN_MODE_PYTHON_DEBUG:
            return
        if not self._run_service.supervisor.is_running():
            return
        self._handle_debug_watch_evaluate(command_text.strip())

    def _handle_debug_breakpoint_remove(self, file_path: str, line_number: int) -> None:
        breakpoints = self._breakpoints_by_file.get(file_path, set())
        breakpoints.discard(line_number)
        if not breakpoints:
            self._breakpoints_by_file.pop(file_path, None)
        self._breakpoint_specs_by_key.pop(breakpoint_key(file_path, line_number), None)
        editor_widget = self._editor_widgets_by_path.get(file_path)
        if editor_widget is not None:
            editor_widget.set_breakpoints(self._breakpoints_by_file.get(file_path, set()))
        self._refresh_breakpoints_list()
        self._sync_breakpoints_to_active_debug_session()
        self._refresh_run_action_states()

    def _handle_debug_breakpoint_toggle(self, file_path: str, line_number: int, enabled: bool) -> None:
        spec = self._ensure_breakpoint_spec(file_path, line_number)
        self._breakpoint_specs_by_key[breakpoint_key(file_path, line_number)] = DebugBreakpoint(
            breakpoint_id=spec.breakpoint_id,
            file_path=spec.file_path,
            line_number=spec.line_number,
            enabled=enabled,
            condition=spec.condition,
            hit_condition=spec.hit_condition,
            verified=spec.verified,
            verification_message=spec.verification_message,
        )
        self._refresh_breakpoints_list()
        self._sync_breakpoints_to_active_debug_session()
        self._refresh_run_action_states()

    def _handle_debug_breakpoint_edit(self, file_path: str, line_number: int) -> None:
        spec = self._ensure_breakpoint_spec(file_path, line_number)
        condition, accepted = QInputDialog.getText(
            self,
            "Breakpoint Condition",
            "Pause only when this expression is truthy (leave blank for always):",
            QLineEdit.Normal,
            spec.condition,
        )
        if not accepted:
            return
        hit_value = spec.hit_condition or 0
        hit_condition, accepted = QInputDialog.getInt(
            self,
            "Breakpoint Hit Count",
            "Pause after this many hits (0 disables threshold):",
            hit_value,
            0,
            999999,
            1,
        )
        if not accepted:
            return
        self._breakpoint_specs_by_key[breakpoint_key(file_path, line_number)] = DebugBreakpoint(
            breakpoint_id=spec.breakpoint_id,
            file_path=spec.file_path,
            line_number=spec.line_number,
            enabled=spec.enabled,
            condition=condition.strip(),
            hit_condition=hit_condition or None,
            verified=spec.verified,
            verification_message=spec.verification_message,
        )
        self._refresh_breakpoints_list()
        self._sync_breakpoints_to_active_debug_session()
        self._refresh_run_action_states()

    def _sync_breakpoints_to_active_debug_session(self) -> None:
        if not (self._run_service.is_debug_mode and self._run_service.is_debug_paused):
            return
        command_name, arguments = update_breakpoints_command(self._all_breakpoints())
        self._send_debug_command(command_name, arguments)

    def _handle_debug_exception_settings_action(self) -> None:
        current_value = "Raised + uncaught" if self._debug_exception_policy.stop_on_raised_exceptions else "Uncaught only"
        if not self._debug_exception_policy.stop_on_uncaught_exceptions:
            current_value = "Disabled"
        selection, accepted = QInputDialog.getItem(
            self,
            "Debug Exception Stops",
            "Pause on exceptions:",
            ["Disabled", "Uncaught only", "Raised + uncaught"],
            ["Disabled", "Uncaught only", "Raised + uncaught"].index(current_value),
            False,
        )
        if not accepted or not selection:
            return
        self._debug_exception_policy = DebugExceptionPolicy(
            stop_on_uncaught_exceptions=selection != "Disabled",
            stop_on_raised_exceptions=selection == "Raised + uncaught",
        )
        if self._run_service.is_debug_mode and self._run_service.is_debug_paused:
            command_name, arguments = update_exception_policy_command(self._debug_exception_policy)
            self._send_debug_command(command_name, arguments)

    def _handle_debug_variable_expand(self, variables_reference: int) -> None:
        if variables_reference <= 0:
            return
        if not self._run_service.supervisor.is_running():
            return
        command_name, arguments = expand_variable_command(variables_reference)
        self._send_debug_command(command_name, arguments)

    def _handle_debug_frame_selected(self, frame_id: int) -> None:
        if frame_id <= 0:
            return
        if not self._run_service.supervisor.is_running():
            return
        command_name, arguments = select_frame_command(frame_id)
        self._send_debug_command(command_name, arguments)

    def _handle_project_health_check_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Health check unavailable", "Open a project before running diagnostics.")
            return

        project_root = self._loaded_project.project_root
        state_root = self._state_root

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return run_project_health_check(project_root, state_root=state_root)

        def on_success(report) -> None:  # type: ignore[no-untyped-def]
            self._latest_health_report = report
            self._latest_runtime_issue_report = self._build_runtime_issue_report()
            self._open_runtime_center_dialog(title="Project Health Check")

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Project health check", f"Health check failed: {exc}")

        self._background_tasks.run(key="project_health_check", task=task, on_success=on_success, on_error=on_error)

    def _handle_generate_support_bundle_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Support bundle unavailable", "Open a project before generating support bundle.")
            return
        project_root = self._loaded_project.project_root
        state_root = self._state_root
        latest_run_log_path = self._resolve_latest_run_log_path()
        latest_report = self._latest_health_report
        startup_report = self._startup_report
        latest_import_issue_report = self._latest_import_issue_report
        latest_run_issue_report = self._latest_run_issue_report
        latest_package_issue_report = self._latest_package_issue_report

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            report = latest_report
            if report is None:
                report = run_project_health_check(project_root, state_root=state_root)
            reports_for_bundle = [
                build_startup_issue_report(startup_report)
                if startup_report is not None
                else RuntimeIssueReport(workflow="startup", issues=[]),
                build_project_health_issue_report(report),
            ]
            if latest_import_issue_report.issues:
                reports_for_bundle.append(latest_import_issue_report)
            if latest_run_issue_report.issues:
                reports_for_bundle.append(latest_run_issue_report)
            if latest_package_issue_report.issues:
                reports_for_bundle.append(latest_package_issue_report)
            runtime_issue_report = merge_runtime_issue_reports(
                *reports_for_bundle,
                workflow="runtime_center",
            )
            bundle_path = build_support_bundle(
                project_root,
                diagnostics_report=report,
                runtime_issue_report=runtime_issue_report,
                workflow_provider_metrics=self._workflow_broker.list_provider_metrics(),
                state_root=state_root,
                destination_dir=project_root,
                last_run_log_path=latest_run_log_path,
            )
            return (report, runtime_issue_report, bundle_path)

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            report, runtime_issue_report, bundle_path = payload
            self._latest_health_report = report
            self._latest_runtime_issue_report = runtime_issue_report
            QMessageBox.information(self, "Support bundle created", f"Bundle written to:\n{bundle_path}")

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Support bundle", f"Support bundle generation failed: {exc}")

        self._background_tasks.run(key="support_bundle", task=task, on_success=on_success, on_error=on_error)

    def _handle_package_project_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Package unavailable", "Open a project before packaging.")
            return
        project_root = self._loaded_project.project_root
        project_metadata = self._loaded_project.metadata
        try:
            package_config = resolve_project_package_config(
                project_root=project_root,
                project_metadata=project_metadata,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Package Project",
                f"Unable to load cbcs/package.json:\n{exc}",
            )
            return
        wizard = PackageProjectWizard(
            project_root=project_root,
            project_metadata=project_metadata,
            package_config=package_config,
            parent=self,
        )
        if wizard.exec_() != QDialog.Accepted:
            return
        output_dir = wizard.output_dir
        selected_profile = wizard.selected_profile
        reviewed_package_config = wizard.build_package_config()

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return package_project_with_workflow(
                self._workflow_broker,
                project_root=project_root,
                project_name=project_metadata.name,
                entry_file=project_metadata.default_entry,
                output_dir=output_dir,
                profile=selected_profile,
                package_config=reviewed_package_config.to_dict(),
                project_metadata=project_metadata.to_dict(),
                known_runtime_modules=self._known_runtime_modules,
            )

        def on_success(result) -> None:  # type: ignore[no-untyped-def]
            provider, result = result
            self._latest_package_issue_report = result.validation.issue_report
            self._latest_runtime_issue_report = self._build_runtime_issue_report()
            if result.success:
                QMessageBox.information(
                    self,
                    "Package created",
                    f"Project packaged via {provider.title} to:\n{result.artifact_root}\n\n"
                    f"Generated files:\n"
                    f"- package_manifest.json\n"
                    f"- package_report.json\n"
                    f"- {Path(result.readme_path).name}\n"
                    f"- {Path(result.install_notes_path).name}\n"
                    + (
                        f"- {Path(result.launcher_path).name}\n"
                        if result.launcher_path
                        else ""
                    ),
                )
                if result.validation.issue_report.issues:
                    self._open_runtime_center_dialog(
                        title="Packaging Report",
                        report=result.validation.issue_report,
                    )
            else:
                if not result.validation.issue_report.issues:
                    self._latest_package_issue_report = RuntimeIssueReport(
                        workflow="package",
                        issues=[
                            RuntimeIssue(
                                issue_id="package.export_failed",
                                workflow="package",
                                severity="blocking",
                                title="Packaging failed",
                                summary=result.error or "Packaging failed unexpectedly.",
                                why_it_happened=(
                                    "The export step encountered a filesystem or packaging problem after the initial validation checks."
                                ),
                                next_steps=[
                                    "Review the packaging error details.",
                                    "Choose a different output location if the destination may be restricted or stale.",
                                    "Re-run packaging after fixing the reported issue.",
                                ],
                                help_topic="packaging_backup",
                                evidence={
                                    "artifact_root": result.artifact_root,
                                    "profile": result.profile,
                                },
                            )
                        ],
                    )
                    self._latest_runtime_issue_report = self._build_runtime_issue_report()
                self._open_runtime_center_dialog(
                    title="Packaging Failed",
                    report=self._latest_package_issue_report,
                )

        def on_error(exc: Exception) -> None:
            self._latest_package_issue_report = RuntimeIssueReport(
                workflow="package",
                issues=[
                    RuntimeIssue(
                        issue_id="package.export_exception",
                        workflow="package",
                        severity="blocking",
                        title="Packaging failed unexpectedly",
                        summary=str(exc),
                        why_it_happened="The packaging workflow raised an unexpected exception before it could finish cleanly.",
                        next_steps=[
                            "Review the error details and retry packaging.",
                            "Choose a different output location if the destination may be restricted.",
                            "Generate a support bundle if the error persists.",
                        ],
                        help_topic="packaging_backup",
                        evidence={"project_root": project_root, "output_dir": output_dir},
                    )
                ],
            )
            self._latest_runtime_issue_report = self._build_runtime_issue_report()
            self._open_runtime_center_dialog(
                title="Packaging Failed",
                report=self._latest_package_issue_report,
            )

        self._background_tasks.run(key="package_project", task=task, on_success=on_success, on_error=on_error)

    def _resolve_latest_run_log_path(self) -> str | None:
        if self._active_run_session_log_path and Path(self._active_run_session_log_path).exists():
            return self._active_run_session_log_path
        if self._loaded_project is None:
            return None
        log_dir = project_logs_dir(self._loaded_project.project_root)
        if not log_dir.exists():
            return None
        candidate_logs = sorted(log_dir.glob("run_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidate_logs:
            return None
        return str(candidate_logs[0].resolve())

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
            has_breakpoints=bool(self._breakpoints_by_file),
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
        rerun_last_debug_action = self._menu_registry.action("shell.action.run.rerunLastDebugTarget")
        if rerun_last_debug_action is not None:
            rerun_last_debug_action.setEnabled(
                self._last_debug_target is not None and not self._run_service.supervisor.is_running()
            )
        exception_settings_action = self._menu_registry.action("shell.action.run.debugExceptionStops")
        if exception_settings_action is not None:
            exception_settings_action.setEnabled(
                self._loaded_project is not None and not self._run_service.supervisor.is_running()
            )
        self._update_run_target_summary()

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
        run_session_controller = getattr(self, "_run_session_controller", None)
        get_active_session_mode = (
            (lambda: getattr(run_session_controller, "active_session_mode", None))
            if run_session_controller is not None
            else (lambda: getattr(self, "_active_session_mode", None))
        )
        set_active_session_mode = getattr(run_session_controller, "set_active_session_mode", None)
        if set_active_session_mode is None:
            set_active_session_mode = lambda mode: setattr(self, "_active_session_mode", mode)
        output_tail = getattr(self, "_active_run_output_tail", None)
        append_output_tail = output_tail.append if output_tail is not None else (lambda _chunk: None)
        coordinator = RunOutputCoordinator(
            is_shutting_down=lambda: self._is_shutting_down,
            get_active_session_mode=get_active_session_mode,
            set_active_session_mode=set_active_session_mode,
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
        active_session = self._active_run_session_info
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
                self._delete_transient_entry_file(transient_entry_file)
                self._active_transient_entry_file_path = None

    def _append_console_line(self, text: str, *, stream: str = "stdout") -> None:
        self._console_model.append(stream, text)
        if self._run_log_panel is not None:
            self._run_log_panel.append_live_line(text, stream=stream)

    def _finalize_run_log(self, return_code: int | None = None) -> None:
        panel = getattr(self, "_run_log_panel", None)
        if panel is None:
            return
        cached = getattr(self, "_active_run_session_info", None)
        run_info = RunInfo(
            run_id=cached.run_id if cached else "",
            mode=cached.mode if cached else "",
            entry_file=cached.entry_file if cached else "",
            exit_code=return_code,
        )
        active_log_path = getattr(self, "_active_run_session_log_path", None)
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

    def _set_search_results(self, matches: list[SearchMatch], query: str) -> None:
        if self._problems_panel is None:
            return
        search_items = [
            ResultItem(
                label=match.line_text.strip(),
                file_path=match.absolute_path,
                line_number=match.line_number,
                tooltip=match.absolute_path,
            )
            for match in matches
        ]
        self._problems_panel.set_results(f"Search: {query}", search_items)
        self._update_problems_tab_title(self._problems_panel.problem_count())

    def _schedule_search_results_update(self, matches: list[SearchMatch], query: str) -> None:
        coordinator = getattr(self, "_search_results_coordinator", None)
        if coordinator is None:
            self._dispatch_to_main_thread(lambda: self._set_search_results(matches, query))
            return
        coordinator.schedule_results_update(matches, query)

    def _handle_search_worker_done(self, started_at: float, query: str) -> None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self._logger.info("Find in files telemetry: query=%r elapsed_ms=%.2f", query, elapsed_ms)
        self._dispatch_to_main_thread(lambda: setattr(self, "_active_search_worker", None))

    def _start_symbol_indexing(self, project_root: str) -> None:
        if not self._intelligence_runtime_settings.cache_enabled:
            return
        if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
            self._active_symbol_index_worker.cancel()
        self._symbol_index_generation += 1
        generation = self._symbol_index_generation
        started_at = time.perf_counter()
        self._active_symbol_index_worker = SymbolIndexWorker(
            project_root=project_root,
            cache_db_path=self._symbol_cache_db_path,
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
        if self._confirm_proceed_with_unsaved_changes("exiting"):
            self._is_shutting_down = True
            self._begin_shutdown_teardown()
            self._stop_active_run_before_close()
            if self._editor_auto_save:
                self._flush_auto_save_to_file()
            self._flush_pending_autosaves()
            if self._status_controller is not None:
                self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            self._persist_layout_to_settings()
            self._persist_session_state()
            self._persist_python_console_history()
            event.accept()
            return
        event.ignore()

    def _begin_shutdown_teardown(self) -> None:
        self._autosave_timer.stop()
        self._auto_save_to_file_timer.stop()
        self._realtime_lint_timer.stop()
        self._project_tree_preview_click_timer.stop()
        self._pending_project_tree_preview_path = None
        self._pending_realtime_lint_file_path = None
        if hasattr(self, "_run_event_timer"):
            self._run_event_timer.stop()
        if hasattr(self, "_external_change_poll_timer"):
            self._external_change_poll_timer.stop()
        if hasattr(self, "_restore_project_timer"):
            self._restore_project_timer.stop()
        if hasattr(self, "_auto_start_repl_timer"):
            self._auto_start_repl_timer.stop()
        if hasattr(self, "_runtime_probe_timer"):
            self._runtime_probe_timer.stop()
        self._drain_run_event_queue()
        self._background_tasks.cancel_all()
        self._background_tasks.shutdown(wait=False)
        if hasattr(self, "_semantic_session"):
            self._intelligence_controller.cancel_all()
            self._intelligence_controller.shutdown()
        if self._active_search_worker is not None and self._active_search_worker.is_running():
            self._active_search_worker.cancel()
        self._active_search_worker = None
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
        if event.type() == QEvent.PaletteChange and not self._is_applying_theme_styles:
            self._apply_theme_styles()
        super().changeEvent(event)

    def _configure_window_frame(self) -> None:
        self.setObjectName("shell.mainWindow")
        self.setWindowTitle(f"ChoreBoy Code Studio v{constants.APP_VERSION}")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

    def _build_layout_shell(self) -> None:
        central = QWidget(self)
        central.setObjectName("shell.centralWidget")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        vertical_splitter = QSplitter(Qt.Vertical, central)
        vertical_splitter.setObjectName("shell.verticalSplitter")
        self._vertical_splitter = vertical_splitter

        top_splitter = QSplitter(Qt.Horizontal, vertical_splitter)
        top_splitter.setObjectName("shell.topSplitter")
        self._top_splitter = top_splitter
        top_splitter.addWidget(self._build_left_panel())
        top_splitter.addWidget(self._build_center_panel())
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 3)

        vertical_splitter.addWidget(top_splitter)
        vertical_splitter.addWidget(self._build_bottom_panel())
        vertical_splitter.setStretchFactor(0, 4)
        vertical_splitter.setStretchFactor(1, 2)
        top_splitter.setSizes(list(DEFAULT_TOP_SPLITTER_SIZES))
        vertical_splitter.setSizes(list(DEFAULT_VERTICAL_SPLITTER_SIZES))

        layout.addWidget(vertical_splitter)
        self.setCentralWidget(central)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("shell.leftRegion")
        outer_layout = QHBoxLayout(panel)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._activity_bar = ActivityBar(panel)
        tokens = self._resolve_theme_tokens()
        normal = QColor(tokens.text_muted)
        active = QColor(tokens.text_primary)
        self._activity_bar.add_view("explorer", "\U0001F4C1", "Explorer", icon=explorer_icon(color_normal=normal, color_active=active))
        self._activity_bar.add_view("search", "\U0001F50D", "Search", icon=search_icon(color_normal=normal, color_active=active))
        self._activity_bar.view_changed.connect(self._handle_sidebar_view_changed)
        outer_layout.addWidget(self._activity_bar)

        self._sidebar_stack = QStackedWidget(panel)
        self._sidebar_stack.setObjectName("shell.sidebarStack")
        outer_layout.addWidget(self._sidebar_stack, 1)

        explorer_page = self._build_explorer_page()
        self._sidebar_stack.addWidget(explorer_page)

        self._search_sidebar = SearchSidebarWidget(panel)
        self._search_sidebar.preview_file_at_line.connect(self._handle_search_preview_file_at_line)
        self._search_sidebar.open_file_at_line.connect(self._handle_search_open_file_at_line)
        self._sidebar_stack.addWidget(self._search_sidebar)

        self._sidebar_stack.setCurrentIndex(0)
        panel.setMinimumWidth(220)
        return panel

    def _build_explorer_page(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("shell.explorerPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget(page)
        header.setObjectName("shell.explorerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 6, 6)
        header_layout.setSpacing(2)

        title_label = QLabel("EXPLORER", header)
        title_label.setObjectName("shell.leftRegion.title")
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header_layout.addWidget(title_label)

        self._explorer_new_file_btn = self._make_explorer_button(
            header, "New File", new_file_icon("#495057", "#3366FF"),
        )
        self._explorer_new_file_btn.clicked.connect(self._handle_explorer_new_file)
        header_layout.addWidget(self._explorer_new_file_btn)

        self._explorer_new_folder_btn = self._make_explorer_button(
            header, "New Folder", new_folder_icon("#495057", "#3366FF"),
        )
        self._explorer_new_folder_btn.clicked.connect(self._handle_explorer_new_folder)
        header_layout.addWidget(self._explorer_new_folder_btn)

        self._explorer_refresh_btn = self._make_explorer_button(
            header, "Refresh Explorer", refresh_icon("#495057"),
        )
        self._explorer_refresh_btn.clicked.connect(self._reload_current_project)
        header_layout.addWidget(self._explorer_refresh_btn)

        layout.addWidget(header)

        self._project_placeholder_label = QLabel("No project loaded.", page)
        self._project_placeholder_label.setObjectName("shell.leftRegion.body")
        self._project_placeholder_label.setWordWrap(True)
        self._project_placeholder_label.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self._project_placeholder_label)

        self._project_tree_widget = ProjectTreeWidget(page)
        self._project_tree_widget.setObjectName("shell.projectTree")
        self._project_tree_widget.setHeaderHidden(True)
        self._project_tree_widget.setIndentation(16)
        self._project_tree_widget.setIconSize(QSize(16, 16))
        self._project_tree_widget.itemActivated.connect(self._handle_project_tree_item_activation)
        self._project_tree_widget.itemClicked.connect(self._handle_project_tree_item_click)
        self._project_tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._project_tree_widget.customContextMenuRequested.connect(self._show_project_tree_context_menu)
        self._project_tree_widget.set_drop_callback(self._handle_project_tree_drop)
        self._project_tree_widget.itemExpanded.connect(self._handle_tree_item_expanded)
        self._project_tree_widget.itemCollapsed.connect(self._handle_tree_item_collapsed)
        self._project_tree_widget.deleteRequested.connect(self._handle_project_tree_delete_key)
        layout.addWidget(self._project_tree_widget, 1)
        self._update_explorer_buttons_enabled()
        return page

    def _handle_sidebar_view_changed(self, view_id: str) -> None:
        if self._sidebar_stack is None:
            return
        if view_id == "explorer":
            self._sidebar_stack.setCurrentIndex(0)
        elif view_id == "search":
            self._sidebar_stack.setCurrentIndex(1)
            if self._search_sidebar is not None:
                self._search_sidebar.focus_search()

    def _handle_search_open_file_at_line(self, file_path: str, line_number: int) -> None:
        self._open_file_at_line(file_path, line_number, preview=False)

    def _handle_search_preview_file_at_line(self, file_path: str, line_number: int) -> None:
        self._open_file_at_line(file_path, line_number, preview=True)

    @staticmethod
    def _make_explorer_button(parent: QWidget, tooltip: str, icon: QIcon) -> QToolButton:
        btn = QToolButton(parent)
        btn.setObjectName("shell.explorerAction")
        btn.setToolTip(tooltip)
        btn.setIcon(icon)
        btn.setFixedSize(QSize(24, 24))
        btn.setAutoRaise(True)
        return btn

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
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            item.setIcon(0, self._tree_folder_open_icon)

    def _handle_tree_item_collapsed(self, item: QTreeWidgetItem) -> None:
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            item.setIcon(0, self._tree_folder_icon)

    def _build_center_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("shell.centerPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 0, 4, 4)
        panel_layout.setSpacing(0)

        self._center_stack = QStackedWidget(panel)
        self._center_stack.setObjectName("shell.centerStack")

        # Page 0: Welcome screen
        self._welcome_widget = WelcomeWidget(self._center_stack)
        self._connect_welcome_widget_actions(self._welcome_widget)
        self._center_stack.addWidget(self._welcome_widget)

        # Page 1: Editor area (find/replace + tabs)
        editor_page = QWidget(self._center_stack)
        editor_page.setObjectName("shell.editorPage")
        editor_layout = QVBoxLayout(editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        self._find_replace_bar = FindReplaceBar(editor_page)
        self._find_replace_bar.find_requested.connect(self._handle_find_bar_find)
        self._find_replace_bar.find_next_requested.connect(self._handle_find_bar_next)
        self._find_replace_bar.find_previous_requested.connect(self._handle_find_bar_prev)
        self._find_replace_bar.replace_requested.connect(self._handle_find_bar_replace)
        self._find_replace_bar.replace_all_requested.connect(self._handle_find_bar_replace_all)
        self._find_replace_bar.close_requested.connect(self._handle_find_bar_close)
        editor_layout.addWidget(self._find_replace_bar, 0)

        self._editor_tabs_widget = QTabWidget(editor_page)
        tab_bar = _MiddleClickTabBar(self._editor_tabs_widget)
        tab_bar.set_tab_double_click_callback(self._handle_editor_tab_header_double_click)
        tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_editor_tab_context_menu)
        self._editor_tabs_widget.setTabBar(tab_bar)
        self._editor_tabs_widget.setObjectName("shell.editorTabs")
        self._editor_tabs_widget.currentChanged.connect(self._handle_editor_tab_changed)
        self._editor_tabs_widget.setTabsClosable(True)
        self._editor_tabs_widget.tabCloseRequested.connect(self._handle_tab_close_requested)
        self._editor_tabs_widget.setMinimumWidth(480)
        editor_layout.addWidget(self._editor_tabs_widget, 1)

        self._center_stack.addWidget(editor_page)

        # Start on the welcome page
        self._center_stack.setCurrentIndex(0)
        self._refresh_welcome_project_list()

        panel_layout.addWidget(self._center_stack, 1)
        return panel

    def _build_bottom_panel(self) -> QWidget:
        tabs = QTabWidget(self)
        tabs.setObjectName("shell.bottomRegion.tabs")
        self._bottom_tabs_widget = tabs
        tabs.setMinimumHeight(60)

        self._python_console_container = QWidget(tabs)
        self._python_console_container.setObjectName("shell.bottom.pythonConsoleContainer")
        container_layout = QVBoxLayout(self._python_console_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        console_toolbar = QHBoxLayout()
        console_toolbar.setContentsMargins(2, 1, 2, 1)
        console_toolbar.addStretch()
        clear_btn = QToolButton(self._python_console_container)
        clear_btn.setText("Clear")
        clear_btn.setObjectName("shell.bottom.pythonConsole.clearBtn")
        clear_btn.setToolTip("Clear the Python Console display")
        clear_btn.setAutoRaise(True)
        console_toolbar.addWidget(clear_btn)
        container_layout.addLayout(console_toolbar)

        self._python_console_widget = PythonConsoleWidget(self._python_console_container)
        self._python_console_widget.setObjectName("shell.bottom.pythonConsole")
        self._python_console_widget.input_submitted.connect(self._handle_python_console_submit)
        self._python_console_widget.interrupt_requested.connect(self._handle_python_console_interrupt)
        self._python_console_widget.restart_requested.connect(self._handle_start_python_console_action)
        self._restore_python_console_history()
        clear_btn.clicked.connect(self._python_console_widget.clear_console)
        container_layout.addWidget(self._python_console_widget)

        repl_index = tabs.addTab(self._python_console_container, "Python Console")
        tabs.setTabToolTip(repl_index, "Interactive REPL session output appears here.")

        self._debug_panel = DebugPanelWidget(tabs)
        self._debug_panel.navigate_requested.connect(self._handle_debug_navigate_preview)
        self._debug_panel.navigate_permanent_requested.connect(self._handle_debug_navigate_permanent)
        self._debug_panel.frame_selected_requested.connect(self._handle_debug_frame_selected)
        self._debug_panel.variable_expand_requested.connect(self._handle_debug_variable_expand)
        self._debug_panel.watch_evaluate_requested.connect(self._handle_debug_watch_evaluate)
        self._debug_panel.breakpoint_remove_requested.connect(self._handle_debug_breakpoint_remove)
        self._debug_panel.breakpoint_toggle_requested.connect(self._handle_debug_breakpoint_toggle)
        self._debug_panel.breakpoint_edit_requested.connect(self._handle_debug_breakpoint_edit)
        self._debug_panel.refresh_stack_requested.connect(self._handle_debug_refresh_stack)
        self._debug_panel.refresh_locals_requested.connect(self._handle_debug_refresh_locals)
        self._debug_panel.command_submitted.connect(self._handle_debug_command_submit)
        tabs.addTab(self._debug_panel, "Debug")

        self._problems_panel = ProblemsPanel(tabs)
        self._problems_panel.item_preview_requested.connect(self._handle_problem_item_preview)
        self._problems_panel.item_activated.connect(self._handle_problem_item_activation)
        self._problems_panel.context_menu_requested.connect(
            lambda fp, _code: self._apply_safe_fixes_for_file(fp)
        )
        self._problems_tab_widget = tabs
        problems_index = tabs.addTab(self._problems_panel, "Problems")
        tabs.setTabToolTip(problems_index, "Tracebacks and diagnostics for quick navigation.")

        self._run_log_panel = RunLogPanel(tabs)
        self._run_log_panel.open_log_requested.connect(
            lambda file_path: self._open_file_in_editor(
                file_path,
                preview=self._editor_enable_preview,
            )
        )
        run_log_index = tabs.addTab(self._run_log_panel, "Run Log")
        tabs.setTabToolTip(run_log_index, "Run/Debug output (stdout/stderr) and per-run log.")
        return tabs

    def _create_placeholder_panel(self, title: str, body: str, object_name: str) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName(object_name)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title_label = QLabel(title, panel)
        title_label.setObjectName(f"{object_name}.title")

        body_label = QLabel(body, panel)
        body_label.setObjectName(f"{object_name}.body")
        body_label.setWordWrap(True)
        body_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        layout.addWidget(title_label)
        layout.addWidget(body_label, 1)
        return panel

    def _populate_project_tree(self, loaded_project: LoadedProject, *, preserve_state: bool = False) -> None:
        if self._project_tree_widget is None:
            return

        expanded_paths: set[str] = set()
        selected_paths: set[str] = set()
        if preserve_state:
            expanded_paths, selected_paths = self._capture_project_tree_state()
        self._project_tree_widget.clear()
        root_nodes = build_project_tree(loaded_project.entries)
        display_nodes = build_project_tree_display(root_nodes)
        for display_node in display_nodes:
            root_item = self._build_tree_item(display_node)
            self._project_tree_widget.addTopLevelItem(root_item)
            if not preserve_state and display_node.is_directory:
                root_item.setExpanded(True)
                root_item.setIcon(0, self._tree_folder_open_icon)
        if preserve_state:
            self._restore_project_tree_state(expanded_paths=expanded_paths, selected_paths=selected_paths)

    def _capture_project_tree_state(self) -> tuple[set[str], set[str]]:
        if self._project_tree_widget is None:
            return (set(), set())
        expanded_paths: set[str] = set()
        selected_paths: set[str] = set()
        for item in self._iter_project_tree_items():
            relative_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
            if not relative_path:
                continue
            if item.isExpanded():
                expanded_paths.add(relative_path)
            if item.isSelected():
                selected_paths.add(relative_path)
        return (expanded_paths, selected_paths)

    def _restore_project_tree_state(self, *, expanded_paths: set[str], selected_paths: set[str]) -> None:
        if self._project_tree_widget is None:
            return
        for item in self._iter_project_tree_items():
            relative_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
            if not relative_path:
                continue
            if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
                item.setExpanded(relative_path in expanded_paths)
                item.setIcon(0, self._tree_folder_open_icon if item.isExpanded() else self._tree_folder_icon)
            item.setSelected(relative_path in selected_paths)

    def _iter_project_tree_items(self) -> list[QTreeWidgetItem]:
        if self._project_tree_widget is None:
            return []
        collected: list[QTreeWidgetItem] = []
        for index in range(self._project_tree_widget.topLevelItemCount()):
            root_item = self._project_tree_widget.topLevelItem(index)
            if root_item is None:
                continue
            collected.extend(self._collect_tree_descendants(root_item))
        return collected

    def _collect_tree_descendants(self, root_item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        collected = [root_item]
        for child_index in range(root_item.childCount()):
            child_item = root_item.child(child_index)
            if child_item is None:
                continue
            collected.extend(self._collect_tree_descendants(child_item))
        return collected

    def _build_tree_item(self, node: ProjectTreeDisplayNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.display_label])
        item.setData(0, TREE_ROLE_ABSOLUTE_PATH, node.absolute_path)
        item.setData(0, TREE_ROLE_IS_DIRECTORY, node.is_directory)
        item.setData(0, TREE_ROLE_RELATIVE_PATH, node.relative_path)
        if node.is_directory:
            item.setIcon(0, self._tree_folder_icon)
        else:
            filename = Path(node.absolute_path).name.lower()
            icon = self._tree_filename_icon_map.get(filename)
            if icon is None:
                ext = Path(node.absolute_path).suffix.lower()
                icon = self._tree_file_icon_map.get(ext, self._tree_file_icon)
            item.setIcon(0, icon)
            if (
                self._loaded_project is not None
                and node.relative_path == self._loaded_project.metadata.default_entry
            ):
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setIcon(0, self._tree_entrypoint_icon)

        for child_node in node.children:
            item.addChild(self._build_tree_item(child_node))
        return item

    def _handle_project_tree_item_click(self, item: QTreeWidgetItem, _column: int) -> None:
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            return
        absolute_path = str(item.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
        if not absolute_path:
            return
        if not self._editor_enable_preview:
            self._cancel_pending_project_tree_preview()
            self._open_file_in_editor(absolute_path, preview=False)
            return
        self._pending_project_tree_preview_path = absolute_path
        self._project_tree_preview_click_timer.start()

    def _open_pending_project_tree_preview(self) -> None:
        preview_path = self._pending_project_tree_preview_path
        self._pending_project_tree_preview_path = None
        if not preview_path:
            return
        self._open_file_in_editor(preview_path, preview=True)

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
        self._open_file_in_editor(str(absolute_path), preview=False)

    def _get_selected_tree_paths(self) -> list[tuple[str, str, bool]]:
        """Return (absolute_path, relative_path, is_directory) for each selected tree item."""
        if self._project_tree_widget is None:
            return []
        entries: list[tuple[str, str, bool]] = []
        for item in self._project_tree_widget.selectedItems():
            abs_path = str(item.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
            rel_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
            is_dir = bool(item.data(0, TREE_ROLE_IS_DIRECTORY))
            if abs_path:
                entries.append((abs_path, rel_path, is_dir))
        return entries

    def _show_project_tree_context_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        if self._project_tree_widget is None:
            return
        item = self._project_tree_widget.itemAt(position)
        if item is None:
            return

        selected = self._get_selected_tree_paths()
        if not selected:
            return

        if len(selected) > 1:
            self._show_bulk_context_menu(position, selected)
        else:
            self._show_single_item_context_menu(position, selected[0])

    def _show_single_item_context_menu(
        self, position: object, entry: tuple[str, str, bool],
    ) -> None:
        assert self._project_tree_widget is not None
        absolute_path, relative_path, is_directory = entry

        menu = QMenu(self)
        new_file_action = menu.addAction("New File…")
        new_folder_action = menu.addAction("New Folder…")
        menu.addSeparator()
        rename_action = menu.addAction("Rename…")
        delete_action = menu.addAction("Move to Trash")
        duplicate_action = menu.addAction("Duplicate")
        menu.addSeparator()
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        copy_path_action = menu.addAction("Copy Path")
        copy_relative_path_action = menu.addAction("Copy Relative Path")
        reveal_action = menu.addAction("Reveal in File Manager")
        local_history_action = None
        if not is_directory:
            local_history_action = menu.addAction("Local History...")
        run_file_action = None
        set_entry_point_action = None
        if (
            not is_directory
            and self._loaded_project is not None
            and Path(absolute_path).suffix.lower() == ".py"
        ):
            menu.addSeparator()
            run_file_action = menu.addAction("Run")
            assert run_file_action is not None
            run_file_action.setEnabled(not self._run_service.supervisor.is_running())
            set_entry_point_action = menu.addAction("Set as Entry Point")
            assert set_entry_point_action is not None
            if relative_path == self._loaded_project.metadata.default_entry:
                set_entry_point_action.setEnabled(False)

        assert paste_action is not None
        paste_action.setEnabled(len(self._tree_clipboard_paths) > 0)
        chosen = menu.exec_(self._project_tree_widget.viewport().mapToGlobal(position))
        if chosen is None:
            return

        if chosen == new_file_action:
            self._handle_tree_new_file(absolute_path if is_directory else str(Path(absolute_path).parent))
        elif chosen == new_folder_action:
            self._handle_tree_new_folder(absolute_path if is_directory else str(Path(absolute_path).parent))
        elif chosen == rename_action:
            self._handle_tree_rename(absolute_path)
        elif chosen == delete_action:
            self._handle_tree_delete(absolute_path)
        elif chosen == duplicate_action:
            self._handle_tree_duplicate(absolute_path)
        elif chosen == copy_action:
            self._tree_clipboard_paths = [absolute_path]
            self._tree_clipboard_cut = False
        elif chosen == cut_action:
            self._tree_clipboard_paths = [absolute_path]
            self._tree_clipboard_cut = True
        elif chosen == paste_action:
            self._handle_tree_paste(absolute_path if is_directory else str(Path(absolute_path).parent))
        elif chosen == copy_path_action:
            QApplication.clipboard().setText(absolute_path)
        elif chosen == copy_relative_path_action:
            QApplication.clipboard().setText(relative_path)
        elif chosen == reveal_action:
            self._reveal_path_in_file_manager(absolute_path)
        elif not is_directory and local_history_action is not None and chosen == local_history_action:
            self._show_local_history_for_path(absolute_path)
        elif run_file_action is not None and chosen == run_file_action:
            self._handle_tree_run_file(absolute_path)
        elif set_entry_point_action is not None and chosen == set_entry_point_action:
            self._set_project_entry_point(relative_path)

    def _handle_tree_run_file(self, absolute_path: str) -> bool:
        entry_path = Path(absolute_path).expanduser().resolve()
        if entry_path.suffix.lower() != ".py":
            return False
        return self._start_session(
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            entry_file=str(entry_path),
        )

    def _show_bulk_context_menu(
        self, position: object, selected: list[tuple[str, str, bool]],
    ) -> None:
        assert self._project_tree_widget is not None
        abs_paths = [entry[0] for entry in selected]

        menu = QMenu(self)
        delete_action = menu.addAction(f"Move {len(selected)} Items to Trash")
        duplicate_action = menu.addAction(f"Duplicate {len(selected)} Items")
        menu.addSeparator()
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        copy_path_action = menu.addAction("Copy Paths")
        copy_relative_path_action = menu.addAction("Copy Relative Paths")

        assert paste_action is not None
        paste_action.setEnabled(len(self._tree_clipboard_paths) > 0)
        chosen = menu.exec_(self._project_tree_widget.viewport().mapToGlobal(position))
        if chosen is None:
            return

        if chosen == delete_action:
            self._handle_tree_bulk_delete(abs_paths)
        elif chosen == duplicate_action:
            self._handle_tree_bulk_duplicate(abs_paths)
        elif chosen == copy_action:
            self._tree_clipboard_paths = list(abs_paths)
            self._tree_clipboard_cut = False
        elif chosen == cut_action:
            self._tree_clipboard_paths = list(abs_paths)
            self._tree_clipboard_cut = True
        elif chosen == paste_action:
            first_abs, _, first_is_dir = selected[0]
            dest = first_abs if first_is_dir else str(Path(first_abs).parent)
            self._handle_tree_paste(dest)
        elif chosen == copy_path_action:
            QApplication.clipboard().setText("\n".join(abs_paths))
        elif chosen == copy_relative_path_action:
            rel_paths = [entry[1] for entry in selected]
            QApplication.clipboard().setText("\n".join(rel_paths))

    def _handle_tree_new_file(self, destination_directory: str) -> None:
        file_name, ok = QInputDialog.getText(self, "New File", "File name:", QLineEdit.Normal, "")
        if not ok or not file_name.strip():
            return
        error_message = self._project_tree_action_coordinator.handle_new_file(destination_directory, file_name.strip())
        if error_message is not None:
            QMessageBox.warning(self, "New File", error_message)

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
        confirmation = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move '{Path(target_path).name}' to trash?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        delete_snapshots = self._capture_text_history_snapshots([target_path])
        error_message = self._project_tree_action_coordinator.handle_delete(target_path)
        if error_message is not None:
            QMessageBox.warning(self, "Move to Trash", error_message)
            return
        self._record_local_history_transaction(
            delete_snapshots,
            source="delete",
            label=f"Delete '{Path(target_path).name}'",
        )

    def _handle_tree_duplicate(self, source_path: str) -> None:
        error_message = self._project_tree_action_coordinator.handle_duplicate(source_path)
        if error_message is not None:
            QMessageBox.warning(self, "Duplicate", error_message)

    def _handle_tree_bulk_delete(self, paths: list[str]) -> None:
        names = "\n".join(f"  • {Path(p).name}" for p in paths)
        confirmation = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move {len(paths)} items to trash?\n\n{names}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        delete_snapshots = self._capture_text_history_snapshots(paths)
        failed, deleted_paths = self._project_tree_action_coordinator.handle_bulk_delete(paths)
        self._record_local_history_transaction(
            self._filter_snapshots_for_paths(delete_snapshots, deleted_paths),
            source="delete",
            label="Bulk delete from project tree",
        )
        if failed:
            QMessageBox.warning(self, "Move to Trash", "\n".join(failed))

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
        from PySide2.QtCore import QUrl
        from PySide2.QtGui import QDesktopServices

        target = Path(path).expanduser().resolve()
        reveal_target = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(reveal_target)))

    def _release_editor_widget(self, widget: CodeEditorWidget) -> None:
        if self._debug_execution_editor is widget:
            self._clear_debug_execution_indicator()
        widget.deleteLater()

    def _close_deleted_editor_paths(self, deleted_path: str) -> None:
        self._project_tree_action_coordinator.close_deleted_editor_paths(deleted_path)

    def _apply_path_move_updates(self, source_path: str, destination_path: str) -> None:
        self._project_tree_action_coordinator.apply_path_move_updates(source_path, destination_path)

    def _update_widget_language_for_path(self, widget: CodeEditorWidget, new_path: str) -> None:
        widget.set_language_for_path(new_path)

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
        self._record_local_history_transaction(
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

    def _reload_current_project(self) -> None:
        if self._loaded_project is None:
            return
        self._loaded_project = open_project(
            self._loaded_project.project_root,
            exclude_patterns=self._load_effective_exclude_patterns(self._loaded_project.project_root),
        )
        self._reload_plugin_contributions()
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
        self._project_tree_structure_signature = tuple(entry.relative_path for entry in self._loaded_project.entries)
        self._start_symbol_indexing(self._loaded_project.project_root)

    def _open_file_in_editor(self, file_path: str, *, preview: bool = False) -> bool:
        if self._editor_tabs_widget is None:
            return False

        started_at = time.perf_counter()
        try:
            use_preview = preview and self._editor_enable_preview
            opened_result = self._editor_manager.open_file(file_path, preview=use_preview)
        except ValueError as exc:
            QMessageBox.warning(self, "Unable to open file", str(exc))
            return False
        return self._materialize_opened_editor_tab(opened_result, started_at=started_at, restore_draft=True)

    def _open_restored_history_buffer(self, file_path: str, content: str) -> bool:
        if self._editor_tabs_widget is None:
            return False
        opened_result = self._editor_manager.open_file_with_content(
            file_path,
            content,
            original_content="",
            preview=False,
            last_known_mtime=None,
        )
        return self._materialize_opened_editor_tab(opened_result, started_at=None, restore_draft=False)

    def _materialize_opened_editor_tab(
        self,
        opened_result: OpenedTabResult,
        *,
        started_at: Optional[float],
        restore_draft: bool,
    ) -> bool:
        if self._editor_tabs_widget is None:
            return False

        if opened_result.closed_preview_path:
            self._remove_tab_widget_for_path(opened_result.closed_preview_path)

        if opened_result.was_already_open:
            existing_index = self._tab_index_for_path(opened_result.tab.file_path)
            if existing_index >= 0:
                self._editor_tabs_widget.setCurrentIndex(existing_index)
                self._refresh_tab_presentation(opened_result.tab.file_path)
            self._refresh_save_action_states()
            self._update_editor_status_for_path(opened_result.tab.file_path)
            return True

        editor_widget = CodeEditorWidget(self._editor_tabs_widget)
        editor_widget.setObjectName("shell.editorTabs.textEditor")
        editor_widget.set_editor_preferences(
            tab_width=self._editor_tab_width,
            font_point_size=self._effective_font_size(),
            font_family=self._editor_font_family,
            indent_style=self._editor_indent_style,
            indent_size=self._editor_indent_size,
        )
        editor_widget.set_completion_preferences(
            enabled=self._completion_enabled,
            auto_trigger=self._completion_auto_trigger,
            min_chars=self._completion_min_chars,
        )
        self._apply_runtime_intelligence_preferences_to_editor(editor_widget)
        editor_widget.apply_theme(self._resolve_theme_tokens())
        editor_widget.setPlainText(opened_result.tab.current_content)
        editor_widget.set_language_for_path(opened_result.tab.file_path)
        tab_file_path = opened_result.tab.file_path

        def completion_requester(
            prefix: str,
            source_text: str,
            cursor_position: int,
            manual_trigger: bool,
            request_generation: int,
        ) -> None:
            self._request_editor_completions_async(
                file_path=tab_file_path,
                editor_widget=editor_widget,
                prefix=prefix,
                source_text=source_text,
                cursor_position=cursor_position,
                manual_trigger=manual_trigger,
                request_generation=request_generation,
            )

        def hover_requester(source_text: str, cursor_position: int, request_generation: int) -> None:
            self._request_inline_hover_text_async(
                file_path=tab_file_path,
                editor_widget=editor_widget,
                source_text=source_text,
                cursor_position=cursor_position,
                request_generation=request_generation,
            )

        def signature_requester(source_text: str, cursor_position: int, request_generation: int) -> None:
            self._request_inline_signature_text_async(
                file_path=tab_file_path,
                editor_widget=editor_widget,
                source_text=source_text,
                cursor_position=cursor_position,
                request_generation=request_generation,
            )

        def on_breakpoint_toggled(line_number: int, enabled: bool) -> None:
            self._handle_editor_breakpoint_toggled(tab_file_path, line_number, enabled)

        def on_text_changed() -> None:
            self._handle_editor_text_changed(tab_file_path, editor_widget)

        def on_cursor_position_changed() -> None:
            self._handle_editor_cursor_position_changed(tab_file_path, editor_widget)

        def on_completion_accepted(item: CompletionItem) -> None:
            self._intelligence_controller.record_completion_acceptance(item)

        editor_widget.set_breakpoint_toggled_callback(on_breakpoint_toggled)
        editor_widget.set_completion_requester(completion_requester)
        editor_widget.set_completion_accepted_callback(on_completion_accepted)
        editor_widget.set_hover_requester(hover_requester)
        editor_widget.set_signature_help_requester(signature_requester)
        editor_widget.set_breakpoints(self._breakpoints_by_file.get(opened_result.tab.file_path, set()))
        editor_widget.textChanged.connect(on_text_changed)
        editor_widget.cursorPositionChanged.connect(on_cursor_position_changed)
        self._workspace_controller.register_editor(opened_result.tab.file_path, editor_widget)

        tab_index = self._editor_tabs_widget.addTab(editor_widget, opened_result.tab.display_name)
        self._editor_tabs_widget.setTabToolTip(tab_index, opened_result.tab.file_path)
        self._editor_tabs_widget.setCurrentIndex(tab_index)
        self._refresh_tab_presentation(opened_result.tab.file_path)
        if restore_draft:
            self._maybe_restore_draft(opened_result.tab, editor_widget)
        self._apply_detected_indentation_for_widget(
            opened_result.tab.file_path,
            editor_widget,
            editor_widget.toPlainText(),
        )
        self._handle_editor_tab_changed(tab_index)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(opened_result.tab.file_path)
        if started_at is not None:
            self._logger.info(
                "File open telemetry: file=%s elapsed_ms=%.2f",
                opened_result.tab.file_path,
                (time.perf_counter() - started_at) * 1000.0,
            )
        return True

    def _open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        if not self._open_file_in_editor(file_path, preview=preview):
            return
        editor_widget = self._editor_widgets_by_path.get(str(Path(file_path).expanduser().resolve()))
        if editor_widget is None or line_number is None:
            return
        editor_widget.go_to_line(line_number)

    def _tab_index_for_path(self, file_path: str) -> int:
        if self._editor_tabs_widget is None:
            return -1

        normalized_path = str(Path(file_path).expanduser().resolve())
        for index in range(self._editor_tabs_widget.count()):
            if self._editor_tabs_widget.tabToolTip(index) == normalized_path:
                return index
        return -1

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
        self._refresh_save_action_states()
        self._refresh_run_action_states()

    def _refresh_tab_presentation(self, file_path: str) -> None:
        if self._editor_tabs_widget is None:
            return
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        tab_index = self._tab_index_for_path(file_path)
        if tab_index < 0:
            return
        suffix = " *" if tab_state.is_dirty else ""
        self._editor_tabs_widget.setTabText(tab_index, f"{tab_state.display_name}{suffix}")
        tab_bar = self._editor_tabs_widget.tabBar()
        if isinstance(tab_bar, QTabBar):
            tab_bar.setTabData(
                tab_index,
                {"is_preview": tab_state.is_preview, "file_path": tab_state.file_path},
            )
            tab_bar.update()

    def _promote_preview_tab(self, file_path: str) -> bool:
        promoted_tab = self._editor_manager.promote_tab(file_path)
        if promoted_tab is None:
            return False
        if not promoted_tab.is_preview:
            self._refresh_tab_presentation(promoted_tab.file_path)
        return True

    def _promote_existing_preview_tab(self) -> bool:
        preview_tab = self._editor_manager.preview_tab()
        if preview_tab is None:
            return False
        return self._promote_preview_tab(preview_tab.file_path)

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
            self._schedule_autosave(tab_state.file_path, tab_state.current_content)
            if self._editor_auto_save:
                self._schedule_auto_save_to_file()
        else:
            self._pending_autosave_payloads.pop(tab_state.file_path, None)
            self._autosave_store.delete_draft(tab_state.file_path)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(tab_state.file_path)
        self._schedule_realtime_lint(tab_state.file_path)

    def _handle_editor_cursor_position_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None or self._status_controller is None:
            return
        self._status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=editor_widget.textCursor().blockNumber() + 1,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )

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
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return None
        return self._editor_widgets_by_path.get(active_tab.file_path)

    def _advance_editor_buffer_revision(self, file_path: str) -> int:
        return self._workspace_controller.advance_buffer_revision(file_path)

    def _editor_buffer_revision(self, file_path: str) -> int | None:
        return self._workspace_controller.buffer_revision(file_path)

    def _request_editor_completions(
        self,
        *,
        file_path: str,
        source_text: str,
        cursor_position: int,
        manual_trigger: bool,
    ) -> list[CompletionItem]:
        started_at = time.perf_counter()
        request = CompletionRequest(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if self._loaded_project is None else self._loaded_project.project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._completion_min_chars,
            max_results=100,
        )
        completions = self._intelligence_controller.complete_blocking(request=request)
        if self._intelligence_runtime_settings.metrics_logging_enabled:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if elapsed_ms > 150.0:
                self._logger.warning(
                    "Completion latency warning: file=%s elapsed_ms=%.2f count=%s",
                    file_path,
                    elapsed_ms,
                    len(completions),
                )
            else:
                self._logger.info(
                    "Completion telemetry: file=%s elapsed_ms=%.2f count=%s",
                    file_path,
                    elapsed_ms,
                    len(completions),
                )
        return completions

    def _request_editor_completions_async(
        self,
        *,
        file_path: str,
        editor_widget: CodeEditorWidget,
        prefix: str,
        source_text: str,
        cursor_position: int,
        manual_trigger: bool,
        request_generation: int,
    ) -> None:
        started_at = time.perf_counter()
        request = CompletionRequest(
            source_text=source_text,
            cursor_position=cursor_position,
            current_file_path=file_path,
            project_root=None if self._loaded_project is None else self._loaded_project.project_root,
            trigger_is_manual=manual_trigger,
            min_prefix_chars=self._completion_min_chars,
            max_results=100,
        )

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            generation, completion_prefix, completions = payload
            active_widget = self._editor_widgets_by_path.get(file_path)
            if active_widget is not editor_widget:
                return
            if self._intelligence_runtime_settings.metrics_logging_enabled:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                if elapsed_ms > 150.0:
                    self._logger.warning(
                        "Completion latency warning: file=%s elapsed_ms=%.2f count=%s",
                        file_path,
                        elapsed_ms,
                        len(completions),
                    )
                else:
                    self._logger.info(
                        "Completion telemetry: file=%s elapsed_ms=%.2f count=%s",
                        file_path,
                        elapsed_ms,
                        len(completions),
                    )
            editor_widget.show_completion_items_for_request(
                request_generation=generation,
                prefix=completion_prefix,
                items=completions,
            )

        def on_error(exc: Exception) -> None:
            self._logger.warning("Async completion request failed for %s: %s", file_path, exc)

        self._intelligence_controller.request_completion(
            request=request,
            prefix=prefix,
            request_generation=request_generation,
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
        self._update_editor_status_for_path(tab_path)
        self._check_for_external_file_change(tab_path)
        self._render_lint_diagnostics_for_file(tab_path, trigger="tab_change")

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
        local_history_action = menu.addAction("Local History...")
        menu.addSeparator()
        close_action = menu.addAction("Close")
        chosen = menu.exec_(tab_bar.mapToGlobal(position))
        if chosen == local_history_action:
            self._show_local_history_for_path(file_path)
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
            response = QMessageBox.warning(
                self,
                "Unsaved changes",
                f"'{tab_state.display_name}' has unsaved changes.\nSave before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if response == QMessageBox.Cancel:
                return
            if response == QMessageBox.Save:
                if not self._save_tab(file_path):
                    return

        self._editor_tabs_widget.removeTab(tab_index)
        widget = self._workspace_controller.pop_editor(file_path)
        if widget is not None:
            self._release_editor_widget(widget)
        self._editor_manager.close_file(file_path)
        self._breakpoints_by_file.pop(file_path, None)
        self._stored_lint_diagnostics.pop(file_path, None)
        self._render_merged_problems_panel()
        self._refresh_breakpoints_list()
        self._refresh_save_action_states()
        self._refresh_run_action_states()

    def _close_active_tab(self) -> None:
        if self._editor_tabs_widget is None:
            return
        tab_index = self._editor_tabs_widget.currentIndex()
        if tab_index >= 0:
            self._handle_tab_close_requested(tab_index)

    def _reset_editor_tabs(self) -> None:
        if self._editor_tabs_widget is not None:
            self._editor_tabs_widget.clear()
        self._autosave_timer.stop()
        self._auto_save_to_file_timer.stop()
        self._realtime_lint_timer.stop()
        self._pending_autosave_payloads.clear()
        self._pending_realtime_lint_file_path = None
        self._clear_debug_execution_indicator()
        self._workspace_controller.clear()
        self._editor_manager = EditorManager()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        if self._status_controller is not None:
            self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)

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
            editor_widget.set_editor_preferences(
                tab_width=max(1, editorconfig_indent.tab_width),
                font_point_size=self._effective_font_size(),
                font_family=self._editor_font_family,
                indent_style=editorconfig_indent.indent_style,
                indent_size=max(1, editorconfig_indent.indent_size),
            )
            return
        if not self._editor_detect_indentation_from_file:
            return
        if not file_path.lower().endswith((".py", ".json", ".md", ".txt")):
            return
        detected = detect_indentation_style_and_size(source_text)
        if detected is None:
            return
        style, size = detected
        editor_widget.set_editor_preferences(
            tab_width=self._editor_tab_width,
            font_point_size=self._effective_font_size(),
            font_family=self._editor_font_family,
            indent_style=style,
            indent_size=size,
        )

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
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._editor_widgets_by_path.get(file_path)
        if tab_state is None or editor_widget is None:
            return

        current_mtime = self._editor_manager.current_disk_mtime(file_path)
        if current_mtime is None or current_mtime == tab_state.last_known_mtime:
            return

        try:
            disk_content = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            self._editor_manager.acknowledge_disk_mtime(file_path, current_mtime)
            return

        if disk_content == tab_state.current_content:
            tab_state.mark_saved(last_known_mtime=current_mtime)
            self._refresh_save_action_states()
            return

        if tab_state.is_dirty:
            message = (
                "This file changed on disk while you have unsaved changes.\n\n"
                "Reloading will discard editor changes."
            )
        else:
            message = "This file changed on disk. Reload the file from disk?"

        choice = QMessageBox.question(
            self,
            "External file change detected",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No if tab_state.is_dirty else QMessageBox.Yes,
        )

        if choice == QMessageBox.Yes:
            if tab_state.is_dirty and tab_state.current_content != disk_content:
                self._record_local_history_checkpoint(
                    file_path,
                    tab_state.current_content,
                    source="external_reload_discarded_buffer",
                    label="Discarded buffer during disk reload",
                )
            editor_widget.blockSignals(True)
            editor_widget.setPlainText(disk_content)
            editor_widget.blockSignals(False)
            self._apply_detected_indentation_for_widget(file_path, editor_widget, disk_content)
            refreshed_tab = self._editor_manager.update_tab_content(file_path, disk_content)
            refreshed_tab.mark_saved(last_known_mtime=current_mtime)
            tab_index = self._tab_index_for_path(file_path)
            if self._editor_tabs_widget is not None and tab_index >= 0:
                self._refresh_tab_presentation(file_path)
            self._pending_autosave_payloads.pop(file_path, None)
            self._record_local_history_checkpoint(
                file_path,
                disk_content,
                source="external_reload",
                label="Reloaded from disk after external change",
            )
            project_id, project_root = self._local_history_context_for_path(file_path)
            self._autosave_store.delete_draft(
                file_path,
                project_id=project_id,
                project_root=project_root,
            )
            self._refresh_save_action_states()
            self._update_editor_status_for_path(file_path)
            return

        self._editor_manager.acknowledge_disk_mtime(file_path, current_mtime)
        if not tab_state.is_dirty:
            tab_state.original_content = disk_content
            self._handle_editor_text_changed(file_path, editor_widget)

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
        return tuple(entry.relative_path for entry in entries)

    def _maybe_restore_draft(self, tab_state: EditorTabState, editor_widget: CodeEditorWidget) -> None:
        project_id, project_root = self._local_history_context_for_path(tab_state.file_path)
        draft_entry = self._autosave_store.load_draft(
            tab_state.file_path,
            project_id=project_id,
            project_root=project_root,
        )
        if draft_entry is None or draft_entry.content == tab_state.current_content:
            return

        dialog = DraftRecoveryDialog(
            file_name=tab_state.display_name,
            disk_text=tab_state.current_content,
            draft_text=draft_entry.content,
            parent=self,
        )
        response = dialog.exec_()
        if response != QDialog.Accepted:
            if dialog.discard_draft:
                self._autosave_store.delete_draft(
                    tab_state.file_path,
                    project_id=project_id,
                    project_root=project_root,
                )
            return

        editor_widget.replace_document_text(draft_entry.content)
        updated_tab = self._editor_manager.update_tab_content(tab_state.file_path, draft_entry.content)
        tab_index = self._tab_index_for_path(tab_state.file_path)
        if self._editor_tabs_widget is not None and tab_index >= 0:
            self._refresh_tab_presentation(updated_tab.file_path)
        self._schedule_autosave(updated_tab.file_path, updated_tab.current_content)

    def _schedule_autosave(self, file_path: str, content: str) -> None:
        self._pending_autosave_payloads[file_path] = content
        self._autosave_timer.start()

    def _schedule_realtime_lint(self, file_path: str) -> None:
        if self._is_shutting_down:
            return
        self._diagnostics_orchestrator.schedule_realtime_lint(file_path)

    def _run_scheduled_realtime_lint(self) -> None:
        if self._is_shutting_down:
            return
        self._diagnostics_orchestrator.run_scheduled_realtime_lint()

    def _flush_pending_autosaves(self) -> None:
        if not self._pending_autosave_payloads:
            return
        pending_items = list(self._pending_autosave_payloads.items())
        self._pending_autosave_payloads.clear()
        for file_path, content in pending_items:
            try:
                project_id, project_root = self._local_history_context_for_path(file_path)
                self._autosave_store.save_draft(
                    file_path,
                    content,
                    project_id=project_id,
                    project_root=project_root,
                )
            except OSError as exc:
                self._logger.warning("Autosave draft write failed for %s: %s", file_path, exc)


def _merge_auto_save_setting(payload: Mapping[str, Any], enabled: bool) -> dict[str, Any]:
    merged = dict(payload)
    editor = dict(merged.get(constants.UI_EDITOR_SETTINGS_KEY, {}))
    editor[constants.UI_EDITOR_AUTO_SAVE_KEY] = enabled
    merged[constants.UI_EDITOR_SETTINGS_KEY] = editor
    return merged
