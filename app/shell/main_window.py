"""Main Qt shell composition and top-level workflow wiring."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

from PySide2.QtCore import QEvent
from PySide2.QtGui import QCloseEvent, QIcon
from PySide2.QtWidgets import QInputDialog, QMainWindow, QMessageBox

from app.core import constants
from app.core.models import CapabilityProbeReport, LoadedProject, RuntimeIssueReport
from app.packaging.layout import resolve_entry_path
from app.persistence.settings_store import project_settings_has_overrides
from app.project.file_inventory import iter_python_files
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator
from app.shell.icon_provider import (
    file_icon,
    file_type_icon_map,
    filename_icon_map,
    folder_icon,
    folder_open_icon,
)
from app.shell.main_window_composition import install_main_window_composition
from app.shell.main_window_lifecycle import MainWindowLifecycle
from app.shell.menus import MenuStubRegistry
from app.shell.problems_controller import ProblemsController
from app.shell.project_tree_presenter import ProjectTreePresenter as ShellProjectTreePresenter
from app.shell.python_tooling_status_copy import PythonToolingRuntimeContext, PythonToolingSettingsCopy
from app.shell.theme_tokens import ShellThemeTokens
from app.shell.toolbar_icons import icon_run

if TYPE_CHECKING:
    from PySide2.QtWidgets import QLabel, QStackedWidget, QTabWidget, QToolButton, QWidget

    from app.editors.quick_open_dialog import QuickOpenDialog
    from app.project.project_tree_widget import ProjectTreeWidget
    from app.shell.activity_bar import ActivityBar
    from app.shell.debug_control_workflow import DebugControlWorkflow
    from app.shell.debug_inspector_workflow import DebugInspectorWorkflow
    from app.shell.debug_panel import DebugPanelWidget
    from app.shell.dependency_panel import DependencyInspectorDialog
    from app.shell.editor_tab_factory import EditorTabFactory
    from app.shell.editor_tab_workflow import EditorTabWorkflow
    from app.shell.local_history_workflow import LocalHistoryWorkflow
    from app.shell.plugin_activation_workflow import PluginActivationWorkflow
    from app.shell.plugins_panel import PluginManagerDialog
    from app.shell.problems_panel import ProblemsPanel
    from app.shell.python_console_widget import PythonConsoleWidget
    from app.shell.python_style_workflow import PythonStyleWorkflow
    from app.shell.repl_event_workflow import ReplEventWorkflow
    from app.shell.run_event_workflow import RunEventWorkflow
    from app.shell.run_log_panel import RunLogPanel
    from app.shell.runtime_onboarding_workflow import RuntimeOnboardingWorkflow
    from app.shell.runtime_support_workflow import RuntimeSupportWorkflow
    from app.shell.save_workflow import SaveWorkflow
    from app.shell.search_sidebar_widget import SearchSidebarWidget
    from app.shell.test_explorer_panel import TestExplorerPanel
    from app.shell.test_runner_workflow import TestRunnerWorkflow
    from app.shell.welcome_widget import WelcomeWidget

ShellEventT = TypeVar("ShellEventT")


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

    def set_startup_report(self, report: Optional[CapabilityProbeReport]) -> None:
        """Extension seam for startup status refresh from bootstrap updates."""
        self._runtime_onboarding_workflow.set_startup_report(report)

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

    def current_theme_tokens(self) -> ShellThemeTokens:
        """Public accessor used by child dialogs to inherit shell theming."""
        return self._shell_theme_workflow.resolve_theme_tokens()

    def _current_project_root(self) -> str | None:
        if self._loaded_project is None:
            return None
        return self._loaded_project.project_root

    def _current_python_tooling_status_context(self) -> PythonToolingRuntimeContext:
        return self._python_tooling_status_controller.current_status_context()

    def _settings_dialog_python_tooling_copy(self) -> PythonToolingSettingsCopy:
        return self._python_tooling_status_controller.settings_dialog_copy()

    def _refresh_python_tooling_status(self) -> None:
        if self._status_controller is None:
            return
        context = self._current_python_tooling_status_context()
        self._status_controller.set_python_tooling_status(
            runtime_available=context.runtime_available,
            config_state=context.config_state,
            config_path=context.config_path,
            config_error=context.config_error,
        )

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
        if tab_state.current_content == replacement_text:
            return
        self._editor_manager.replace_tab_content(file_path, replacement_text)
        editor_widget = self._editor_widgets_by_path.get(file_path)
        if editor_widget is not None and editor_widget.toPlainText() != replacement_text:
            editor_widget.replace_document_text(replacement_text)

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
        if self._project_tree_ui_workflow.set_project_entry_point(replacement):
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

    def _clear_problems(self) -> None:
        self._stored_lint_diagnostics.clear()
        self._stored_runtime_problems = []
        self._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=[])
        self._latest_run_issue_ids = ()
        self._latest_runtime_issue_report = self._runtime_onboarding_workflow.build_runtime_issue_report()
        if self._problems_panel is not None:
            self._problems_panel.clear()
            self._problems_controller.update_problems_tab_title(0)
        self._problems_controller.clear_all_tab_diagnostic_indicators()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt signature
        MainWindowLifecycle.handle_close_event(self, event)

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.type() == QEvent.PaletteChange and not self._shell_theme_workflow.host.is_applying_theme_styles:
            self._shell_theme_workflow.apply_theme_styles()
        super().changeEvent(event)
