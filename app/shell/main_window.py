"""Main Qt shell composition and top-level workflow wiring."""

from __future__ import annotations

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
    QMessageBox,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.paths import global_cache_dir, global_python_console_history_path
from app.bootstrap.runtime_module_probe import load_cached_runtime_modules, probe_and_cache_runtime_modules
from app.bootstrap.startup_facade import StartupCapabilityFacade
from app.core import constants
from app.core.errors import AppValidationError, ProjectManifestValidationError
from app.core.models import CapabilityProbeReport, LoadedProject, RuntimeIssueReport
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap
from app.debug.debug_session import DebugSession
from app.intelligence.cache_controls import (
    IntelligenceRuntimeSettings,
    rebuild_symbol_cache,
)
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity, analyze_python_file
from app.intelligence.outline_service import OutlineSymbol
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
from app.editors.find_replace_bar import FindReplaceBar
from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.editors.markdown_rendering import is_markdown_path
from app.editors.quick_open_dialog import QuickOpenDialog
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
from app.shell.output_tail_buffer import OutputTailBuffer
from app.run.problem_parser import ProblemEntry
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService
from app.run.runtime_launch import (
    build_runpy_bootstrap_payload,
    is_freecad_runtime_executable,
    resolve_runtime_executable,
)
from app.shell.run_log_panel import RunLogPanel
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
from app.shell.runtime_onboarding_workflow import RuntimeOnboardingWorkflow
from app.shell.search_sidebar_widget import SearchSidebarWidget
from app.shell.theme_tokens import ShellThemeTokens
from app.project.project_tree_widget import ProjectTreeWidget
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
    open_project,
)
from app.project.project_manifest import (
    set_project_default_entry,
)
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.main_thread_dispatcher import MainThreadDispatcher
from app.shell.action_registry import ShellActionRegistry
from app.shell.command_broker import CommandBroker
from app.shell.debug_control_workflow import DebugControlWorkflow
from app.shell.debug_inspector_workflow import DebugInspectorWorkflow
from app.shell.events import (
    ProjectOpenFailedEvent,
    ShellEventBus,
)
from app.shell.menu_wiring import build_main_window_menus, connect_test_explorer_navigation
from app.shell.menus import MenuStubRegistry
from app.shell.project_controller import ProjectController
from app.shell.project_load_host import MainWindowProjectLoadHost
from app.shell.project_load_workflow import ProjectLoadWorkflow
from app.shell.project_rescan_workflow import MainWindowProjectRescanHost, ProjectRescanWorkflow
from app.shell.source_root_workflow import build_source_root_workflow
from app.shell.file_dialogs import choose_existing_directory, choose_open_files
from app.shell.project_tree_controller import ProjectTreeController
from app.shell.project_tree_presenter import ProjectTreePresenter as ShellProjectTreePresenter
from app.shell.tree_item_roles import TREE_ROLE_IS_DIRECTORY
from app.shell.problems_controller import ProblemsController
from app.shell.python_style_workflow import PythonStyleWorkflow
from app.shell.repl_event_workflow import ReplEventWorkflow
from app.shell.repl_session_manager import ReplSessionManager
from app.shell.run_debug_presenter import RunDebugPresenter
from app.shell.run_event_workflow import RunEventWorkflow
from app.shell.run_output_coordinator import RunOutputCoordinator
from app.shell.run_session_controller import RunSessionController
from app.shell.runtime_support_workflow import RuntimeSupportWorkflow
from app.shell.save_workflow import SaveWorkflow
from app.shell.shell_composition import (
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
from app.shell.document_safety import DocumentScope
from app.shell.editor_intelligence_controller import EditorIntelligenceController
from app.shell.editor_tab_factory import EditorTabFactory
from app.shell.editor_tab_workflow import EditorTabWorkflow
from app.shell.editor_tab_bar import MiddleClickTabBar
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator
from app.shell.editor_workspace_controller import EditorWorkspaceController
from app.shell.project_tree_action_coordinator import ProjectTreeActionCoordinator
from app.shell.diagnostics_search_coordinator import DiagnosticsOrchestrator
from app.shell.help_controller import ShellHelpController
from app.shell.main_window_composition import install_main_window_composition
from app.shell.main_window_layout import (
    build_layout_shell,
    configure_window_frame,
)
from app.shell.status_bar import (
    ShellStatusBarController,
    create_shell_status_bar,
)
from app.shell.toolbar import build_run_toolbar_widget
from app.shell.toolbar_icons import icon_run
from app.shell.welcome_widget import WelcomeWidget

ShellEventT = TypeVar("ShellEventT")


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
        self._project_tree_presenter = ShellProjectTreePresenter(self)
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
        self._debug_inspector_workflow: DebugInspectorWorkflow
        self._repl_event_workflow: ReplEventWorkflow
        self._run_event_workflow: RunEventWorkflow
        self._editor_tab_factory: EditorTabFactory
        self._editor_tab_workflow: EditorTabWorkflow
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
        self._runtime_onboarding_workflow: RuntimeOnboardingWorkflow
        install_main_window_composition(
            self,
            startup_report=startup_report,
            state_root=state_root,
        )

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
        self._runtime_onboarding_workflow.set_startup_report(report)

    def _refresh_startup_capability_report_async(self) -> None:
        self._runtime_onboarding_workflow.refresh_startup_capability_report_async()

    def _handle_startup_report_refresh(self, report: CapabilityProbeReport) -> None:
        self._runtime_onboarding_workflow.handle_startup_report_refresh(report)

    def _build_runtime_issue_report(self) -> RuntimeIssueReport:
        return self._runtime_onboarding_workflow.build_runtime_issue_report()

    def _open_runtime_center_dialog(
        self,
        *,
        title: str = "Runtime Center",
        report: RuntimeIssueReport | None = None,
    ) -> None:
        self._runtime_onboarding_workflow.open_runtime_center_dialog(title=title, report=report)

    def _handle_runtime_center_action(self) -> None:
        self._runtime_onboarding_workflow.handle_runtime_center_action()

    def _connect_welcome_widget_actions(
        self,
        widget: WelcomeWidget,
        *,
        close_after_action: Callable[[], None] | None = None,
    ) -> None:
        self._runtime_onboarding_workflow.connect_welcome_widget_actions(
            widget,
            close_after_action=close_after_action,
        )

    def _handle_runtime_onboarding_action(self) -> None:
        self._runtime_onboarding_workflow.handle_runtime_onboarding_action()

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
        self._editor_tab_workflow.handle_zoom_in()

    def _handle_zoom_out(self) -> None:
        self._editor_tab_workflow.handle_zoom_out()

    def _handle_zoom_reset(self) -> None:
        self._editor_tab_workflow.handle_zoom_reset()

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
        return self._project_controller.open_project_by_path(
            project_root,
            confirm_proceed=self._save_workflow.confirm_proceed_with_unsaved_changes,
            on_loading=lambda: self.statusBar().showMessage("Opening project… (scanning files)", 0),
            on_loaded=lambda loaded_project: self._apply_loaded_project(loaded_project, started_at=started_at),
            on_error=self._show_open_project_error,
            exclude_patterns=self._load_effective_exclude_patterns(project_root),
        )

    def _load_effective_exclude_patterns(self, project_root: str | None = None) -> list[str]:
        return load_effective_exclude_patterns(self._settings_service, project_root)

    def _refresh_open_recent_menu(self) -> None:
        self._project_controller.refresh_open_recent_menu(
            self._menu_registry,
            open_project_by_path=self._open_project_by_path,
        )

    def _refresh_welcome_project_list(self) -> None:
        self._runtime_onboarding_workflow.refresh_welcome_project_list()

    def _show_welcome_screen(self) -> None:
        """Switch the center stack back to the welcome page."""
        self._runtime_onboarding_workflow.show_welcome_screen()

    def _show_editor_screen(self) -> None:
        """Switch the center stack to the editor page."""
        self._runtime_onboarding_workflow.show_editor_screen()

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
        self._run_event_workflow.show_run_preflight_result(title, summary, issues)

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
        self._source_root_workflow.mark_source_root(relative_path)

    def _handle_tree_unmark_source_root(self, relative_path: str) -> None:
        self._source_root_workflow.unmark_source_root(relative_path)

    def _maybe_prompt_import_source_roots(self) -> None:
        self._source_root_workflow.maybe_prompt_import_source_roots()

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
        self._debug_inspector_workflow.append_debug_output_line(text)

    def _apply_debug_inspector_event(self) -> None:
        self._debug_inspector_workflow.apply_debug_inspector_event()

    def _clear_debug_execution_indicator(self) -> None:
        self._debug_inspector_workflow.clear_debug_execution_indicator()

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
        self._run_event_workflow.set_run_status(status, return_code=return_code)

    def _refresh_run_action_states(self) -> None:
        self._run_event_workflow.refresh_run_action_states()

    def _has_active_python_file(self) -> bool:
        return self._run_event_workflow.has_active_python_file()

    def _enqueue_run_event(self, event: ProcessEvent) -> None:
        self._run_event_workflow.enqueue_run_event(event)

    # -- REPL event queue (separate from script/debug) --------------------

    def _enqueue_repl_output(self, text: str, stream: str) -> None:
        self._repl_event_workflow.enqueue_output(text, stream)

    def _enqueue_repl_ended(self, return_code: int | None, terminated_by_user: bool) -> None:
        self._repl_event_workflow.enqueue_ended(return_code, terminated_by_user)

    def _enqueue_repl_started(self) -> None:
        self._repl_event_workflow.enqueue_started()

    def _process_queued_repl_events(self) -> None:
        self._repl_event_workflow.process_queued_events()

    def _auto_start_repl(self) -> None:
        self._repl_manager.start()

    def _get_run_output_coordinator(self) -> RunOutputCoordinator:
        return self._run_event_workflow.get_run_output_coordinator()

    def _process_queued_run_events(self) -> None:
        self._run_event_workflow.process_queued_run_events()

    def _apply_run_event(self, event: ProcessEvent) -> None:
        self._run_event_workflow.apply_run_event(event)

    def _append_console_line(self, text: str, *, stream: str = "stdout") -> None:
        self._run_event_workflow.append_console_line(text, stream=stream)

    def _finalize_run_log(self, return_code: int | None = None) -> None:
        self._run_event_workflow.finalize_run_log(return_code)

    def _update_problems_from_output(self) -> list[ProblemEntry]:
        return self._run_event_workflow.update_problems_from_output()

    def _set_problems(self, problems: list[ProblemEntry]) -> None:
        self._run_event_workflow.set_problems(problems)

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
        self._run_event_workflow.drain_run_event_queue()

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
        return self._project_tree_presenter.selected_destination_directory()

    def _handle_explorer_new_file(self) -> None:
        target = self._selected_tree_directory()
        if target is not None:
            self._handle_tree_new_file(target)

    def _handle_explorer_new_folder(self) -> None:
        target = self._selected_tree_directory()
        if target is not None:
            self._handle_tree_new_folder(target)

    def _handle_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        presenter = self._project_tree_presenter
        presenter.handle_item_expanded(item)
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            presenter.set_folder_icon(item, expanded=True)

    def _handle_tree_item_collapsed(self, item: QTreeWidgetItem) -> None:
        if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
            self._project_tree_presenter.set_folder_icon(item, expanded=False)

    def _populate_project_tree(self, loaded_project: LoadedProject, *, preserve_state: bool = False) -> None:
        self._project_tree_presenter.populate(loaded_project, preserve_state=preserve_state)

    def _iter_project_tree_items(self) -> list[QTreeWidgetItem]:
        return self._project_tree_presenter.iter_items()

    def _handle_project_tree_item_click(self, item: QTreeWidgetItem, _column: int) -> None:
        entry = self._project_tree_presenter.item_entry(item)
        if entry is None:
            return
        _, _, is_directory = entry
        if is_directory:
            return
        absolute_path = entry[0]
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
        entry = self._project_tree_presenter.item_entry(item)
        if entry is None:
            return
        absolute_path, _, is_directory = entry
        if is_directory or not absolute_path:
            return
        self._editor_tab_factory.open_file_in_editor(absolute_path, preview=False)

    def _get_selected_tree_paths(self) -> list[tuple[str, str, bool]]:
        """Return (absolute_path, relative_path, is_directory) for each selected tree item."""
        return self._project_tree_presenter.selected_paths()

    def _show_project_tree_context_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        self._project_tree_presenter.show_context_menu(position)

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
        self._project_rescan_workflow.rescan_from_disk()

    def _reload_current_project(self) -> None:
        self._project_rescan_workflow.rescan_from_disk(reload_plugins=True, reindex=True)

    def _open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        if not self._editor_tab_factory.open_file_in_editor(file_path, preview=preview):
            return
        editor_widget = self._editor_widgets_by_path.get(str(Path(file_path).expanduser().resolve()))
        if editor_widget is None or line_number is None:
            return
        editor_widget.go_to_line(line_number)

    def _refresh_outline_for_active_tab(self) -> None:
        self._editor_tab_workflow.refresh_outline_for_active_tab()

    def _handle_outline_symbol_activated(self, file_path: str, line_number: int) -> None:
        self._editor_tab_workflow.handle_outline_symbol_activated(file_path, line_number)

    def _tab_index_for_path(self, file_path: str) -> int:
        return self._editor_tab_workflow.tab_index_for_path(file_path)

    def _remove_tab_widget_for_path(self, file_path: str) -> None:
        self._editor_tab_workflow.remove_tab_widget_for_path(file_path)

    def _refresh_tab_presentation(self, file_path: str) -> None:
        self._editor_tab_workflow.refresh_tab_presentation(file_path)

    def _promote_preview_tab(self, file_path: str) -> bool:
        return self._editor_tab_workflow.promote_preview_tab(file_path)

    def _promote_existing_preview_tab(self) -> bool:
        return self._editor_tab_workflow.promote_existing_preview_tab()

    def _active_markdown_pane(self) -> MarkdownEditorPane | None:
        return self._editor_tab_workflow.active_markdown_pane()

    def _set_active_markdown_mode(self, mode: str) -> None:
        self._editor_tab_workflow.set_active_markdown_mode(mode)

    def _handle_markdown_show_source_action(self) -> None:
        self._editor_tab_workflow.handle_markdown_show_source_action()

    def _handle_markdown_show_preview_action(self) -> None:
        self._editor_tab_workflow.handle_markdown_show_preview_action()

    def _handle_markdown_show_split_action(self) -> None:
        self._editor_tab_workflow.handle_markdown_show_split_action()

    def _handle_markdown_toggle_preview_action(self) -> None:
        self._editor_tab_workflow.handle_markdown_toggle_preview_action()

    def _refresh_markdown_action_states(self) -> None:
        self._editor_tab_workflow.refresh_markdown_action_states()

    def _handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        self._editor_tab_workflow.handle_editor_text_changed(file_path, editor_widget)

    def _handle_editor_cursor_position_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        self._editor_tab_workflow.handle_editor_cursor_position_changed(file_path, editor_widget)

    def _update_editor_status_for_path(self, file_path: str) -> None:
        self._editor_tab_workflow.update_editor_status_for_path(file_path)

    def _active_editor_widget(self) -> CodeEditorWidget | None:
        return self._editor_tab_workflow.active_editor_widget()

    def _advance_editor_buffer_revision(self, file_path: str) -> int:
        return self._editor_tab_workflow.advance_buffer_revision(file_path)

    def _editor_buffer_revision(self, file_path: str) -> int | None:
        return self._editor_tab_workflow.buffer_revision(file_path)

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
        self._editor_tab_workflow.handle_editor_tab_changed(tab_index)

    def _handle_editor_tab_header_double_click(self, tab_index: int) -> None:
        self._editor_tab_workflow.handle_editor_tab_header_double_click(tab_index)

    def _handle_keep_preview_open_shortcut(self) -> None:
        self._editor_tab_workflow.handle_keep_preview_open_shortcut()

    def _show_editor_tab_context_menu(self, position: QPoint) -> None:
        self._editor_tab_workflow.show_editor_tab_context_menu(position)

    def _handle_tab_close_requested(self, tab_index: int) -> None:
        self._editor_tab_workflow.handle_tab_close_requested(tab_index)

    def _close_active_tab(self) -> None:
        self._editor_tab_workflow.close_active_tab()

    def _reset_editor_tabs(self) -> None:
        self._editor_tab_workflow.reset_editor_tabs()

    def _effective_font_size(self) -> int:
        return self._editor_tab_workflow.effective_font_size()

    def _apply_editor_preferences_to_open_editors(self) -> None:
        self._editor_tab_workflow.apply_editor_preferences_to_open_editors()

    def _apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        self._editor_tab_workflow.apply_runtime_intelligence_preferences_to_open_editors()

    def _apply_runtime_intelligence_preferences_to_editor(self, editor_widget: CodeEditorWidget) -> None:
        self._editor_tab_workflow.apply_runtime_intelligence_preferences_to_editor(editor_widget)

    def _apply_detected_indentation_for_widget(
        self,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
    ) -> None:
        self._editor_tab_workflow.apply_detected_indentation_for_widget(
            file_path,
            editor_widget,
            source_text,
        )

    def _record_indent_source(
        self,
        file_path: str,
        style: str,
        size: int,
        source: str,
    ) -> None:
        self._editor_tab_workflow.record_indent_source(file_path, style, size, source)

    def _update_indent_status_for_path(self, file_path: str | None) -> None:
        self._editor_tab_workflow.update_indent_status_for_path(file_path)

    def _refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        self._editor_tab_workflow.refresh_open_tabs_from_disk(file_paths)

    def _check_for_external_file_change(self, file_path: str) -> None:
        self._editor_tab_workflow.check_for_external_file_change(file_path)

    def _poll_external_file_changes(self) -> None:
        self._editor_tab_workflow.poll_external_file_changes()

    def _scan_project_tree_signature(self, loaded_project: LoadedProject) -> tuple[str, ...]:
        return self._editor_tab_workflow.scan_project_tree_signature(loaded_project)


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
