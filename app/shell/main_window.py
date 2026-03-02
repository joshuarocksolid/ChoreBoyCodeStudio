"""Main Qt shell composition and top-level workflow wiring."""

from __future__ import annotations

import queue
from pathlib import Path
import subprocess
import time
from typing import Callable, Optional

from PySide2.QtCore import QEvent, QTimer, Qt
from PySide2.QtGui import QCloseEvent
from PySide2.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.paths import global_cache_dir
from app.core import constants
from app.core.errors import AppValidationError
from app.core.models import CapabilityProbeReport
from app.core.models import LoadedProject
from app.debug.debug_command_service import (
    continue_command,
    evaluate_command,
    locals_command,
    stack_command,
    step_into_command,
    step_out_command,
    step_over_command,
)
from app.debug.debug_session import DebugSession
from app.intelligence.code_actions import apply_quick_fixes, plan_safe_fixes_for_file
from app.intelligence.cache_controls import (
    IntelligenceRuntimeSettings,
    parse_intelligence_runtime_settings,
    rebuild_symbol_cache,
    should_refresh_index_after_save,
)
from app.intelligence.diagnostics_service import DiagnosticSeverity, analyze_python_file, find_unresolved_imports
from app.intelligence.hover_service import resolve_hover_info
from app.intelligence.navigation_service import lookup_definition_with_cache
from app.intelligence.outline_service import build_file_outline
from app.intelligence.reference_service import find_references
from app.intelligence.refactor_service import apply_rename_plan, plan_rename_symbol
from app.intelligence.signature_service import resolve_signature_help
from app.intelligence.symbol_index import SymbolIndexWorker
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_service import CompletionRequest, CompletionService
from app.editors.editor_manager import EditorManager
from app.editors.editor_tab import EditorTabState
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.indentation import detect_indentation_style_and_size
from app.editors.quick_open import QuickOpenCandidate, rank_candidates
from app.editors.search_panel import SearchMatch, SearchWorker
from app.persistence.autosave_store import AutosaveStore
from app.persistence.settings_store import load_settings, save_settings
from app.run.console_model import ConsoleModel
from app.run.output_tail_buffer import OutputTailBuffer
from app.run.problem_parser import ProblemEntry, parse_traceback_problems
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService
from app.support.diagnostics import ProjectHealthReport, run_project_health_check
from app.support.support_bundle import build_support_bundle
from app.templates.template_service import TemplateMetadata, TemplateService
from app.shell.layout_persistence import (
    DEFAULT_TOP_SPLITTER_SIZES,
    DEFAULT_VERTICAL_SPLITTER_SIZES,
    ShellLayoutState,
    merge_layout_into_settings,
    parse_shell_layout_state,
)
from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import merge_editor_settings_snapshot, parse_editor_settings_snapshot
from app.shell.style_sheet import build_shell_style_sheet
from app.shell.theme_tokens import tokens_from_palette
from app.project.project_tree import build_project_tree
from app.project.project_tree_widget import ProjectTreeWidget
from app.project.project_tree_presenter import ProjectTreeDisplayNode, build_project_tree_display
from app.project.file_operation_models import ImportUpdatePolicy
from app.project.file_operations import copy_path, create_directory, create_file, delete_path, duplicate_path, move_path, rename_path
from app.project.project_service import open_project
from app.shell.background_tasks import BackgroundTaskRunner
from app.shell.menus import MenuCallbacks, MenuStubRegistry, build_menu_stubs
from app.shell.project_controller import ProjectController
from app.shell.project_tree_controller import ProjectTreeController
from app.shell.run_session_controller import RunSessionController
from app.shell.status_bar import ShellStatusBarController, create_shell_status_bar
from app.shell.toolbar import build_shell_toolbar

# Qt.UserRole is 0x0100 (256). Literal role IDs avoid enum typing mismatches across PySide shims.
TREE_ROLE_ABSOLUTE_PATH = 256
TREE_ROLE_IS_DIRECTORY = 257
TREE_ROLE_RELATIVE_PATH = 258
PROBLEM_ROLE_FILE_PATH = 320
PROBLEM_ROLE_LINE_NUMBER = 321
PROBLEM_ROLE_DIAGNOSTIC_CODE = 322


class MainWindow(QMainWindow):
    """Top-level editor window shell with extension seams for later tasks."""

    def __init__(self, startup_report: Optional[CapabilityProbeReport] = None, state_root: str | None = None) -> None:
        super().__init__()
        self._project_placeholder_label: QLabel | None = None
        self._breadcrumbs_label: QLabel | None = None
        self._project_tree_widget: ProjectTreeWidget | None = None
        self._editor_tabs_widget: QTabWidget | None = None
        self._bottom_tabs_widget: QTabWidget | None = None
        self._console_output_widget: QPlainTextEdit | None = None
        self._python_console_output_widget: QPlainTextEdit | None = None
        self._python_console_input_widget: QLineEdit | None = None
        self._python_console_send_button: QPushButton | None = None
        self._debug_inspector_output_widget: QPlainTextEdit | None = None
        self._watch_input_widget: QLineEdit | None = None
        self._watch_list_widget: QListWidget | None = None
        self._debug_stack_list_widget: QListWidget | None = None
        self._debug_variables_list_widget: QListWidget | None = None
        self._breakpoints_list_widget: QListWidget | None = None
        self._run_log_output_widget: QPlainTextEdit | None = None
        self._problems_list_widget: QListWidget | None = None
        self._menu_registry: MenuStubRegistry | None = None
        self._status_controller: ShellStatusBarController | None = None
        self._toolbar = None
        self._top_splitter: QSplitter | None = None
        self._vertical_splitter: QSplitter | None = None
        self._is_applying_theme_styles = False
        self._state_root = state_root
        self._loaded_project: LoadedProject | None = None
        self._editor_manager = EditorManager()
        self._editor_widgets_by_path: dict[str, CodeEditorWidget] = {}
        self._breakpoints_by_file: dict[str, set[int]] = {}
        self._tree_clipboard_path: str | None = None
        self._tree_clipboard_cut: bool = False
        self._import_update_policy = self._load_import_update_policy()
        (
            self._editor_tab_width,
            self._editor_font_size,
            self._editor_indent_style,
            self._editor_indent_size,
            self._editor_detect_indentation_from_file,
        ) = self._load_editor_preferences()
        (
            self._completion_enabled,
            self._completion_auto_trigger,
            self._completion_min_chars,
        ) = self._load_completion_preferences()
        self._intelligence_runtime_settings = self._load_intelligence_runtime_settings()
        self._symbol_cache_db_path = str(global_cache_dir(self._state_root) / "symbols.sqlite3")
        self._completion_service = CompletionService(cache_db_path=self._symbol_cache_db_path)
        self._autosave_store = AutosaveStore(state_root=self._state_root)
        self._pending_autosave_payloads: dict[str, str] = {}
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self._flush_pending_autosaves)
        self._console_model = ConsoleModel()
        self._run_event_queue: queue.Queue[ProcessEvent] = queue.Queue()
        self._active_run_output_tail = OutputTailBuffer(max_chars=300_000, max_chunks=6_000)
        self._active_run_session_log_path: str | None = None
        self._active_session_mode: str | None = None
        self._debug_session = DebugSession()
        self._active_search_worker: SearchWorker | None = None
        self._active_symbol_index_worker: SymbolIndexWorker | None = None
        self._latest_health_report: ProjectHealthReport | None = None
        self._run_service = RunService(on_event=self._enqueue_run_event)
        self._run_session_controller = RunSessionController(self._run_service)
        self._template_service = TemplateService()
        self._background_tasks = BackgroundTaskRunner(
            dispatch_to_main_thread=self._dispatch_to_main_thread
        )
        self._logger = get_subsystem_logger("shell")
        self._project_controller = ProjectController(state_root=self._state_root, logger=self._logger)
        self._project_tree_controller = ProjectTreeController()

        self._configure_window_frame()
        self._build_layout_shell()
        self._menu_registry = build_menu_stubs(
            self,
            callbacks=MenuCallbacks(
                on_open_project=self._handle_open_project_action,
                on_file_menu_about_to_show=self._refresh_open_recent_menu,
                on_save=self._handle_save_action,
                on_save_all=self._handle_save_all_action,
                on_open_settings=self._handle_open_settings_action,
                on_run=self._handle_run_action,
                on_debug=self._handle_debug_action,
                on_stop=self._handle_stop_action,
                on_restart=self._handle_restart_action,
                on_continue_debug=self._handle_continue_debug_action,
                on_pause_debug=self._handle_pause_debug_action,
                on_step_over=self._handle_step_over_action,
                on_step_into=self._handle_step_into_action,
                on_step_out=self._handle_step_out_action,
                on_toggle_breakpoint=self._handle_toggle_breakpoint_action,
                on_start_python_console=self._handle_start_python_console_action,
                on_clear_console=self._handle_clear_console_action,
                on_reset_layout=self._handle_reset_layout_action,
                on_lint_current_file=self._handle_lint_current_file_action,
                on_apply_safe_fixes=self._handle_apply_safe_fixes_action,
                on_rebuild_intelligence_cache=self._handle_rebuild_intelligence_cache_action,
                on_project_health_check=self._handle_project_health_check_action,
                on_generate_support_bundle=self._handle_generate_support_bundle_action,
                on_new_project=self._handle_new_project_action,
                on_quick_open=self._handle_quick_open_action,
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
                on_headless_notes=self._handle_headless_notes_action,
                on_help_getting_started=self._handle_getting_started_action,
                on_help_shortcuts=self._handle_shortcuts_action,
                on_help_about=self._handle_about_action,
            ),
        )
        self._status_controller = create_shell_status_bar(self, startup_report=startup_report)
        self._toolbar = build_shell_toolbar(self, self._menu_registry)
        self._apply_theme_styles()
        self._restore_layout_from_settings()
        self._refresh_open_recent_menu()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        self._run_event_timer = QTimer(self)
        self._run_event_timer.setInterval(50)
        self._run_event_timer.timeout.connect(self._process_queued_run_events)
        self._run_event_timer.start()

    def set_startup_report(self, report: Optional[CapabilityProbeReport]) -> None:
        """Extension seam for startup status refresh from bootstrap updates."""
        if self._status_controller is None:
            return
        self._status_controller.set_startup_report(report)

    def set_project_placeholder(self, project_text: str) -> None:
        """Extension seam for T09/T10 project-shell wiring."""
        if self._project_placeholder_label is not None:
            self._project_placeholder_label.setText(project_text)
        if self._status_controller is not None:
            self._status_controller.set_project_state_text(f"Project: {project_text}")

    def _restore_layout_from_settings(self) -> None:
        settings_payload = load_settings(state_root=self._state_root)
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
        settings_payload = load_settings(state_root=self._state_root)
        merged = merge_layout_into_settings(settings_payload, layout_state)
        save_settings(merged, state_root=self._state_root)

    def _handle_reset_layout_action(self) -> None:
        self.resize(ShellLayoutState().width, ShellLayoutState().height)
        if self._top_splitter is not None:
            self._top_splitter.setSizes(list(DEFAULT_TOP_SPLITTER_SIZES))
        if self._vertical_splitter is not None:
            self._vertical_splitter.setSizes(list(DEFAULT_VERTICAL_SPLITTER_SIZES))
        self._persist_layout_to_settings()

    def _load_import_update_policy(self) -> ImportUpdatePolicy:
        settings_payload = load_settings(state_root=self._state_root)
        raw_value = settings_payload.get(constants.UI_IMPORT_UPDATE_POLICY_KEY, constants.UI_IMPORT_UPDATE_POLICY_DEFAULT)
        try:
            return ImportUpdatePolicy(str(raw_value))
        except ValueError:
            return ImportUpdatePolicy.ASK

    def _apply_theme_styles(self) -> None:
        if self._is_applying_theme_styles:
            return
        self._is_applying_theme_styles = True
        palette = self.palette()
        try:
            tokens = tokens_from_palette(palette, prefer_dark=self._system_prefers_dark_theme())
            self.setStyleSheet(build_shell_style_sheet(tokens))
        finally:
            self._is_applying_theme_styles = False

    def _system_prefers_dark_theme(self) -> bool:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return False
        if result.returncode != 0:
            return False
        return "prefer-dark" in result.stdout

    def _save_import_update_policy(self, policy: ImportUpdatePolicy) -> None:
        settings_payload = load_settings(state_root=self._state_root)
        settings_payload[constants.UI_IMPORT_UPDATE_POLICY_KEY] = policy.value
        save_settings(settings_payload, state_root=self._state_root)
        self._import_update_policy = policy

    def _load_editor_preferences(self) -> tuple[int, int, str, int, bool]:
        settings_payload = load_settings(state_root=self._state_root)
        editor_settings = settings_payload.get(constants.UI_EDITOR_SETTINGS_KEY, {})
        if not isinstance(editor_settings, dict):
            return (
                constants.UI_EDITOR_TAB_WIDTH_DEFAULT,
                constants.UI_EDITOR_FONT_SIZE_DEFAULT,
                constants.UI_EDITOR_INDENT_STYLE_DEFAULT,
                constants.UI_EDITOR_INDENT_SIZE_DEFAULT,
                constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_DEFAULT,
            )

        tab_width = editor_settings.get(constants.UI_EDITOR_TAB_WIDTH_KEY, constants.UI_EDITOR_TAB_WIDTH_DEFAULT)
        font_size = editor_settings.get(constants.UI_EDITOR_FONT_SIZE_KEY, constants.UI_EDITOR_FONT_SIZE_DEFAULT)
        indent_style = editor_settings.get(constants.UI_EDITOR_INDENT_STYLE_KEY, constants.UI_EDITOR_INDENT_STYLE_DEFAULT)
        indent_size = editor_settings.get(constants.UI_EDITOR_INDENT_SIZE_KEY, constants.UI_EDITOR_INDENT_SIZE_DEFAULT)
        detect_indentation_from_file = editor_settings.get(
            constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_KEY,
            constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_DEFAULT,
        )
        if not isinstance(tab_width, int):
            tab_width = constants.UI_EDITOR_TAB_WIDTH_DEFAULT
        if not isinstance(font_size, int):
            font_size = constants.UI_EDITOR_FONT_SIZE_DEFAULT
        if indent_style not in {"spaces", "tabs"}:
            indent_style = constants.UI_EDITOR_INDENT_STYLE_DEFAULT
        if not isinstance(indent_size, int):
            indent_size = constants.UI_EDITOR_INDENT_SIZE_DEFAULT
        if not isinstance(detect_indentation_from_file, bool):
            detect_indentation_from_file = constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_DEFAULT
        return (max(2, tab_width), max(8, font_size), str(indent_style), max(1, indent_size), detect_indentation_from_file)

    def _load_completion_preferences(self) -> tuple[bool, bool, int]:
        settings_payload = load_settings(state_root=self._state_root)
        intelligence_settings = settings_payload.get(constants.UI_INTELLIGENCE_SETTINGS_KEY, {})
        if not isinstance(intelligence_settings, dict):
            return (
                constants.UI_INTELLIGENCE_ENABLE_COMPLETION_DEFAULT,
                constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_DEFAULT,
                constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_DEFAULT,
            )

        enabled = intelligence_settings.get(
            constants.UI_INTELLIGENCE_ENABLE_COMPLETION_KEY,
            constants.UI_INTELLIGENCE_ENABLE_COMPLETION_DEFAULT,
        )
        auto_trigger = intelligence_settings.get(
            constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_KEY,
            constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_DEFAULT,
        )
        min_chars = intelligence_settings.get(
            constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_KEY,
            constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_DEFAULT,
        )
        if not isinstance(enabled, bool):
            enabled = constants.UI_INTELLIGENCE_ENABLE_COMPLETION_DEFAULT
        if not isinstance(auto_trigger, bool):
            auto_trigger = constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_DEFAULT
        if not isinstance(min_chars, int):
            min_chars = constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_DEFAULT
        return (enabled, auto_trigger, max(1, min_chars))

    def _load_intelligence_runtime_settings(self) -> IntelligenceRuntimeSettings:
        settings_payload = load_settings(state_root=self._state_root)
        return parse_intelligence_runtime_settings(settings_payload)

    def _dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        QTimer.singleShot(0, callback)

    @property
    def menu_registry(self) -> MenuStubRegistry | None:
        return self._menu_registry

    @property
    def loaded_project(self) -> LoadedProject | None:
        """Return the currently loaded project, if any."""
        return self._loaded_project

    def _handle_open_project_action(self) -> None:
        selected_path = QFileDialog.getExistingDirectory(self, "Open Project", str(Path.home()))
        if not selected_path:
            return
        self._open_project_by_path(selected_path)

    def _handle_new_project_action(self) -> None:
        templates = self._template_service.list_templates()
        if not templates:
            QMessageBox.warning(self, "No templates available", "No project templates were found.")
            return

        selected_template = self._prompt_for_template(templates)
        if selected_template is None:
            return

        project_name, ok = QInputDialog.getText(self, "New Project", "Project name:", QLineEdit.Normal, "")
        if not ok or not project_name.strip():
            return

        destination_parent = QFileDialog.getExistingDirectory(self, "Choose Project Folder", str(Path.home()))
        if not destination_parent:
            return

        destination_path = Path(destination_parent) / project_name.strip()
        try:
            created_path = self._template_service.materialize_template(
                template_id=selected_template.template_id,
                destination_path=destination_path,
                project_name=project_name.strip(),
            )
        except AppValidationError as exc:
            QMessageBox.warning(self, "Failed to create project", str(exc))
            return

        self._open_project_by_path(str(created_path))

    def _handle_open_settings_action(self) -> None:
        settings_payload = load_settings(state_root=self._state_root)
        snapshot = parse_editor_settings_snapshot(settings_payload)
        dialog = SettingsDialog(snapshot, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        updated_snapshot = dialog.snapshot()
        merged_settings = merge_editor_settings_snapshot(settings_payload, updated_snapshot)
        save_settings(merged_settings, state_root=self._state_root)

        (
            self._editor_tab_width,
            self._editor_font_size,
            self._editor_indent_style,
            self._editor_indent_size,
            self._editor_detect_indentation_from_file,
        ) = self._load_editor_preferences()
        (
            self._completion_enabled,
            self._completion_auto_trigger,
            self._completion_min_chars,
        ) = self._load_completion_preferences()
        self._intelligence_runtime_settings = self._load_intelligence_runtime_settings()
        if not self._intelligence_runtime_settings.cache_enabled:
            if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
                self._active_symbol_index_worker.cancel()
        elif self._loaded_project is not None:
            self._start_symbol_indexing(self._loaded_project.project_root)
        self._apply_editor_preferences_to_open_editors()
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

        query, ok = QInputDialog.getText(self, "Quick Open", "Filename query:", QLineEdit.Normal, "")
        if not ok:
            return

        candidates = [
            QuickOpenCandidate(relative_path=entry.relative_path, absolute_path=entry.absolute_path)
            for entry in self._loaded_project.entries
            if not entry.is_directory
        ]
        ranked = rank_candidates(candidates, query, limit=50)
        if not ranked:
            QMessageBox.information(self, "Quick Open", "No matching files.")
            return

        labels = [candidate.relative_path for candidate in ranked]
        selected_label, ok = QInputDialog.getItem(self, "Quick Open", "Open file:", labels, 0, editable=False)
        if not ok:
            return

        selected_candidate = next(candidate for candidate in ranked if candidate.relative_path == selected_label)
        self._open_file_in_editor(selected_candidate.absolute_path)

    def _handle_find_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(self, "Find", "Open a file tab first.")
            return

        query, ok = QInputDialog.getText(self, "Find", "Find text:", QLineEdit.Normal, "")
        if not ok or not query:
            return
        if not editor_widget.find(query):
            QMessageBox.information(self, "Find", f"No matches for: {query}")

    def _handle_replace_action(self) -> None:
        editor_widget = self._active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(self, "Replace", "Open a file tab first.")
            return

        find_text, ok = QInputDialog.getText(self, "Replace", "Find text:", QLineEdit.Normal, "")
        if not ok or not find_text:
            return
        replace_text, ok = QInputDialog.getText(self, "Replace", "Replace with:", QLineEdit.Normal, "")
        if not ok:
            return

        content = editor_widget.toPlainText()
        replaced_content = content.replace(find_text, replace_text)
        if replaced_content == content:
            QMessageBox.information(self, "Replace", "No matching text found.")
            return
        editor_widget.setPlainText(replaced_content)

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
        query, ok = QInputDialog.getText(self, "Find in Files", "Find text:", QLineEdit.Normal, "")
        if not ok or not query:
            return

        self._set_search_results([], f"{query} (searching...)")
        if self._active_search_worker is not None and self._active_search_worker.is_running():
            self._active_search_worker.cancel()
        started_at = time.perf_counter()
        self._active_search_worker = SearchWorker(
            project_root=self._loaded_project.project_root,
            query=query,
            max_results=500,
            on_results=lambda matches, search_query: self._schedule_search_results_update(matches, search_query),
            on_done=lambda: self._handle_search_worker_done(started_at, query),
        )
        self._active_search_worker.start()

    def _handle_find_references_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Find References", "Open a project first.")
            return
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Find References", "Open a file tab first.")
            return

        result = find_references(
            project_root=self._loaded_project.project_root,
            current_file_path=active_tab.file_path,
            source_text=editor_widget.toPlainText(),
            cursor_position=editor_widget.textCursor().position(),
        )
        if not result.symbol_name:
            QMessageBox.information(self, "Find References", "Place cursor on a symbol first.")
            return
        if not result.hits:
            QMessageBox.information(self, "Find References", f"No references found for '{result.symbol_name}'.")
            return

        if self._problems_list_widget is None:
            return
        self._problems_list_widget.clear()
        for hit in result.hits:
            marker = "def" if hit.is_definition else "ref"
            item = QListWidgetItem(
                f"[{marker}] {Path(hit.file_path).name}:{hit.line_number}:{hit.column_number + 1} | {hit.line_text}",
                self._problems_list_widget,
            )
            item.setToolTip(hit.file_path)
            item.setData(PROBLEM_ROLE_FILE_PATH, hit.file_path)
            item.setData(PROBLEM_ROLE_LINE_NUMBER, hit.line_number)

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

        plan = plan_rename_symbol(
            project_root=self._loaded_project.project_root,
            current_file_path=active_tab.file_path,
            source_text=editor_widget.toPlainText(),
            cursor_position=editor_widget.textCursor().position(),
            new_symbol=new_symbol,
        )
        if plan is None or not plan.hits:
            QMessageBox.information(self, "Rename Symbol", f"No references found for '{old_symbol}'.")
            return

        preview_lines = [f"{Path(hit.file_path).name}:{hit.line_number}:{hit.column_number + 1}" for hit in plan.hits[:20]]
        preview_body = "\n".join(preview_lines)
        if len(plan.hits) > 20:
            preview_body += f"\n... and {len(plan.hits) - 20} more occurrence(s)"
        confirm = QMessageBox.question(
            self,
            "Rename Preview",
            (
                f"Rename '{plan.old_symbol}' to '{plan.new_symbol}'?\n"
                f"Occurrences: {len(plan.hits)} across {len(plan.touched_files)} file(s)\n\n"
                f"{preview_body}"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            result = apply_rename_plan(plan)
        except OSError as exc:
            QMessageBox.warning(self, "Rename Symbol", f"Failed to apply rename: {exc}")
            return

        self._refresh_open_tabs_from_disk(result.changed_files)
        self._reload_current_project()
        QMessageBox.information(
            self,
            "Rename Symbol",
            f"Renamed {result.changed_occurrences} occurrence(s) across {len(result.changed_files)} file(s).",
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

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return lookup_definition_with_cache(
                project_root=project_root,
                current_file_path=current_file_path,
                symbol_name=symbol_name,
                cache_db_path=self._symbol_cache_db_path,
            )

        def on_success(lookup) -> None:  # type: ignore[no-untyped-def]
            if not lookup.found:
                QMessageBox.information(self, "Go To Definition", f"No definition found for '{symbol_name}'.")
                return
            location = lookup.locations[0]
            self._open_file_at_line(location.file_path, location.line_number)

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Go To Definition", f"Lookup failed: {exc}")

        self._background_tasks.run(key="go_to_definition", task=task, on_success=on_success, on_error=on_error)

    def _handle_signature_help_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Signature Help", "Open a file tab first.")
            return

        signature = resolve_signature_help(editor_widget.toPlainText(), editor_widget.textCursor().position())
        if signature is None:
            QMessageBox.information(self, "Signature Help", "No callable signature information available.")
            return

        details = [
            signature.signature_text,
            f"Active parameter index: {signature.argument_index}",
        ]
        if signature.doc_summary:
            details.append(f"Doc: {signature.doc_summary}")
        details.append(f"Source: {signature.source}")
        QMessageBox.information(self, "Signature Help", "\n".join(details))

    def _handle_hover_info_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            QMessageBox.warning(self, "Hover Info", "Open a file tab first.")
            return

        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        hover_info = resolve_hover_info(
            source_text=editor_widget.toPlainText(),
            cursor_position=editor_widget.textCursor().position(),
            current_file_path=active_tab.file_path,
            project_root=project_root,
            cache_db_path=self._symbol_cache_db_path,
        )
        if hover_info is None:
            QMessageBox.information(self, "Hover Info", "No symbol info available.")
            return

        details = [f"Symbol: {hover_info.symbol_name}", f"Kind: {hover_info.symbol_kind}"]
        if hover_info.file_path:
            details.append(f"File: {hover_info.file_path}")
        if hover_info.line_number is not None:
            details.append(f"Line: {hover_info.line_number}")
        if hover_info.doc_summary:
            details.append(f"Doc: {hover_info.doc_summary}")
        details.append(f"Source: {hover_info.source}")
        QMessageBox.information(self, "Hover Info", "\n".join(details))

    def _handle_analyze_imports_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Analyze Imports", "Open a project first.")
            return
        project_root = self._loaded_project.project_root

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return find_unresolved_imports(project_root)

        def on_success(diagnostics) -> None:  # type: ignore[no-untyped-def]
            if self._problems_list_widget is None:
                return
            self._problems_list_widget.clear()
            if not diagnostics:
                self._problems_list_widget.addItem(QListWidgetItem("No unresolved project-local imports found."))
                return
            for diagnostic in diagnostics:
                item = QListWidgetItem(
                    f"{Path(diagnostic.file_path).name}:{diagnostic.line_number} | {diagnostic.message}",
                    self._problems_list_widget,
                )
                item.setToolTip(diagnostic.file_path)
                item.setData(PROBLEM_ROLE_FILE_PATH, diagnostic.file_path)
                item.setData(PROBLEM_ROLE_LINE_NUMBER, diagnostic.line_number)

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Analyze Imports", f"Import analysis failed: {exc}")

        self._background_tasks.run(key="analyze_imports", task=task, on_success=on_success, on_error=on_error)

    def _handle_show_outline_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Outline", "Open a Python file first.")
            return
        symbols = build_file_outline(active_tab.file_path)
        if self._problems_list_widget is None:
            return
        self._problems_list_widget.clear()
        if not symbols:
            self._problems_list_widget.addItem(QListWidgetItem("No symbols found in current file."))
            return
        for symbol in symbols:
            item = QListWidgetItem(
                f"{symbol.kind} {symbol.name} (line {symbol.line_number})",
                self._problems_list_widget,
            )
            item.setData(PROBLEM_ROLE_FILE_PATH, active_tab.file_path)
            item.setData(PROBLEM_ROLE_LINE_NUMBER, symbol.line_number)

    def _handle_getting_started_action(self) -> None:
        self._show_help_file("Getting Started", "getting_started.md")

    def _handle_shortcuts_action(self) -> None:
        self._show_help_file("Keyboard Shortcuts", "shortcuts.md")

    def _handle_headless_notes_action(self) -> None:
        self._show_help_file("FreeCAD Headless Notes", "headless_notes.md")

    def _handle_about_action(self) -> None:
        QMessageBox.information(
            self,
            "About",
            "ChoreBoy Code Studio\nProject-first editor + runner for constrained systems.",
        )

    def _show_help_file(self, title: str, file_name: str) -> None:
        help_path = Path(__file__).resolve().parents[1] / "ui" / "help" / file_name
        if not help_path.exists():
            QMessageBox.warning(self, title, f"Help file not found: {help_path}")
            return
        QMessageBox.information(self, title, help_path.read_text(encoding="utf-8"))

    def _open_project_by_path(self, project_root: str) -> bool:
        started_at = time.perf_counter()
        return self._project_controller.open_project_by_path(
            project_root,
            confirm_proceed=self._confirm_proceed_with_unsaved_changes,
            on_loaded=lambda loaded_project: self._apply_loaded_project(loaded_project, started_at=started_at),
            on_error=self._show_open_project_error,
        )

    def _refresh_open_recent_menu(self) -> None:
        self._project_controller.refresh_open_recent_menu(
            self._menu_registry,
            open_project_by_path=self._open_project_by_path,
        )

    def _show_open_project_error(self, project_root: str, details: str) -> None:
        self._logger.warning("Project open failed for %s: %s", project_root, details)
        QMessageBox.critical(
            self,
            "Unable to open project",
            f"Could not open project:\n{project_root}\n\n{details}",
        )

    def _apply_loaded_project(self, loaded_project: LoadedProject, *, started_at: float) -> None:
        self._loaded_project = loaded_project
        self.set_project_placeholder(loaded_project.metadata.name)
        self.setWindowTitle(f"ChoreBoy Code Studio — {loaded_project.metadata.name}")
        self._logger.info("Project loaded: %s", loaded_project.project_root)
        self._populate_project_tree(loaded_project)
        self._reset_editor_tabs()
        self._breakpoints_by_file.clear()
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

    def _save_tab(self, file_path: str) -> bool:
        try:
            saved_tab = self._editor_manager.save_tab(file_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            self._logger.warning("Save failed for %s: %s", file_path, exc)
            return False

        if self._editor_tabs_widget is not None:
            tab_index = self._tab_index_for_path(saved_tab.file_path)
            if tab_index >= 0:
                self._editor_tabs_widget.setTabText(tab_index, saved_tab.display_name)

        self._pending_autosave_payloads.pop(saved_tab.file_path, None)
        self._autosave_store.delete_draft(saved_tab.file_path)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(saved_tab.file_path)
        if should_refresh_index_after_save(
            self._intelligence_runtime_settings,
            has_loaded_project=self._loaded_project is not None,
        ) and self._loaded_project is not None:
            self._start_symbol_indexing(self._loaded_project.project_root)
        self._logger.info("Saved file: %s", saved_tab.file_path)
        return True

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

    def _handle_run_action(self) -> bool:
        return self._start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)

    def _handle_debug_action(self) -> bool:
        breakpoint_entries: list[dict[str, int | str]] = []
        for file_path, line_numbers in self._breakpoints_by_file.items():
            for line_number in sorted(line_numbers):
                breakpoint_entries.append({"file_path": file_path, "line_number": line_number})
        return self._start_session(mode=constants.RUN_MODE_PYTHON_DEBUG, breakpoints=breakpoint_entries)

    def _handle_start_python_console_action(self) -> bool:
        return self._start_session(mode=constants.RUN_MODE_PYTHON_REPL, skip_save=True)

    def _prepare_for_session_start(self) -> None:
        self._active_run_output_tail.clear()
        self._clear_problems()
        self._debug_session = DebugSession()

    def _start_session(
        self,
        *,
        mode: str,
        breakpoints: list[dict[str, int | str]] | None = None,
        skip_save: bool = False,
    ) -> bool:
        result = self._run_session_controller.start_session(
            loaded_project=self._loaded_project,
            mode=mode,
            breakpoints=breakpoints,
            skip_save=skip_save,
            save_all=self._handle_save_all_action,
            before_start=self._prepare_for_session_start,
            append_console_line=lambda text, stream: self._append_console_line(text, stream=stream),
            append_python_console_line=self._append_python_console_line,
        )
        if not result.started:
            if result.error_message and result.error_message == "Open a project before running code.":
                QMessageBox.warning(self, "Run unavailable", result.error_message)
            elif result.error_message and result.error_message == "Fix save errors before running.":
                QMessageBox.warning(self, "Run cancelled", result.error_message)
            elif result.error_message:
                QMessageBox.warning(self, "Run failed to start", result.error_message)
            self._refresh_run_action_states()
            return False

        if result.session is not None:
            self._active_run_session_log_path = result.session.log_file_path
        self._active_session_mode = self._run_session_controller.active_session_mode
        self._refresh_run_action_states()
        return True

    def _handle_stop_action(self) -> None:
        self._run_session_controller.stop_session(lambda text, stream: self._append_console_line(text, stream=stream))
        self._refresh_run_action_states()

    def _handle_restart_action(self) -> None:
        if self._run_service.supervisor.is_running():
            self._run_service.stop_run()
        if self._active_session_mode == constants.RUN_MODE_PYTHON_DEBUG:
            self._handle_debug_action()
        elif self._active_session_mode == constants.RUN_MODE_PYTHON_REPL:
            self._handle_start_python_console_action()
        else:
            self._handle_run_action()

    def _handle_continue_debug_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        self._send_runner_input(continue_command())

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
        self._send_runner_input(step_over_command())

    def _handle_step_into_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        self._send_runner_input(step_into_command())

    def _handle_step_out_action(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        self._send_runner_input(step_out_command())

    def _handle_toggle_breakpoint_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        editor_widget = self._active_editor_widget()
        if active_tab is None or editor_widget is None:
            return
        line_number = editor_widget.textCursor().blockNumber() + 1
        editor_widget.toggle_breakpoint(line_number)

    def _handle_editor_breakpoint_toggled(self, file_path: str, line_number: int, enabled: bool) -> None:
        breakpoints = self._breakpoints_by_file.setdefault(file_path, set())
        if enabled:
            breakpoints.add(line_number)
        else:
            breakpoints.discard(line_number)
        if not breakpoints:
            self._breakpoints_by_file.pop(file_path, None)
        self._refresh_breakpoints_list()

    def _refresh_breakpoints_list(self) -> None:
        if self._breakpoints_list_widget is None:
            return
        self._breakpoints_list_widget.clear()
        for file_path in sorted(self._breakpoints_by_file.keys()):
            for line_number in sorted(self._breakpoints_by_file[file_path]):
                self._breakpoints_list_widget.addItem(f"{Path(file_path).name}:{line_number}")

    def _handle_clear_console_action(self) -> None:
        self._console_model.clear()
        if self._console_output_widget is not None:
            self._console_output_widget.clear()
        if self._python_console_output_widget is not None:
            self._python_console_output_widget.clear()
        if self._debug_inspector_output_widget is not None:
            self._debug_inspector_output_widget.clear()

    def _handle_lint_current_file_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Lint Current File", "Open a file tab first.")
            return
        if not active_tab.file_path.lower().endswith(".py"):
            QMessageBox.information(self, "Lint Current File", "Linting is currently available for Python files only.")
            return
        self._render_lint_diagnostics_for_file(active_tab.file_path)

    def _handle_apply_safe_fixes_action(self) -> None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            QMessageBox.warning(self, "Apply Safe Fixes", "Open a file tab first.")
            return
        self._apply_safe_fixes_for_file(active_tab.file_path)

    def _render_lint_diagnostics_for_file(self, file_path: str) -> None:
        if not file_path.lower().endswith(".py"):
            QMessageBox.information(self, "Lint Current File", "Linting is currently available for Python files only.")
            return
        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        diagnostics = analyze_python_file(file_path, project_root=project_root)
        if self._problems_list_widget is None:
            return
        self._problems_list_widget.clear()
        if not diagnostics:
            self._problems_list_widget.addItem(QListWidgetItem("No diagnostics found in current file."))
            return
        severity_prefix = {
            DiagnosticSeverity.ERROR: "error",
            DiagnosticSeverity.WARNING: "warn",
            DiagnosticSeverity.INFO: "info",
        }
        for diagnostic in diagnostics:
            prefix = severity_prefix.get(diagnostic.severity, "info")
            item = QListWidgetItem(
                f"[{prefix}] {Path(diagnostic.file_path).name}:{diagnostic.line_number} {diagnostic.code} | {diagnostic.message}",
                self._problems_list_widget,
            )
            item.setToolTip(diagnostic.file_path)
            item.setData(PROBLEM_ROLE_FILE_PATH, diagnostic.file_path)
            item.setData(PROBLEM_ROLE_LINE_NUMBER, diagnostic.line_number)
            item.setData(PROBLEM_ROLE_DIAGNOSTIC_CODE, diagnostic.code)

    def _apply_safe_fixes_for_file(self, file_path: str) -> None:
        if not file_path.lower().endswith(".py"):
            QMessageBox.information(self, "Apply Safe Fixes", "Safe fixes currently support Python files only.")
            return
        project_root = None if self._loaded_project is None else self._loaded_project.project_root
        diagnostics = analyze_python_file(file_path, project_root=project_root)
        fixes = plan_safe_fixes_for_file(file_path, diagnostics, project_root=project_root)
        if not fixes:
            QMessageBox.information(self, "Apply Safe Fixes", "No safe fixes available for current file.")
            return

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

        self._refresh_open_tabs_from_disk([file_path])
        self._render_lint_diagnostics_for_file(file_path)
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

    def _send_runner_input(self, command_text: str) -> None:
        text = command_text if command_text.endswith("\n") else f"{command_text}\n"
        try:
            self._run_service.send_input(text)
        except Exception as exc:
            QMessageBox.warning(self, "Runner input failed", str(exc))
            return
        self._append_python_console_line(f">>> {command_text.rstrip()}")
        self._append_debug_output_line(f">>> {command_text.rstrip()}")

    def _handle_python_console_submit(self) -> None:
        if self._python_console_input_widget is None:
            return
        command_text = self._python_console_input_widget.text().strip()
        if not command_text:
            return
        if not self._run_service.supervisor.is_running():
            QMessageBox.warning(self, "Python Console", "Start a Python console or debug session first.")
            return
        self._send_runner_input(command_text)
        self._python_console_input_widget.clear()

    def _append_python_console_line(self, text: str) -> None:
        if self._python_console_output_widget is None:
            return
        self._python_console_output_widget.appendPlainText(text)

    def _append_debug_output_line(self, text: str) -> None:
        if self._debug_inspector_output_widget is None:
            return
        self._debug_inspector_output_widget.appendPlainText(text)

    def _apply_debug_inspector_event(self) -> None:
        state = self._debug_session.state
        if self._debug_stack_list_widget is not None:
            self._debug_stack_list_widget.clear()
            for frame in state.frames:
                self._debug_stack_list_widget.addItem(
                    f"{Path(frame.file_path).name}:{frame.line_number} ({frame.function_name})"
                )
        if self._debug_variables_list_widget is not None:
            self._debug_variables_list_widget.clear()
            for variable in state.variables:
                self._debug_variables_list_widget.addItem(f"{variable.name} = {variable.value_repr}")

    def _handle_debug_refresh_stack(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        self._send_runner_input(stack_command())

    def _handle_debug_refresh_locals(self) -> None:
        if not self._run_service.supervisor.is_running():
            return
        self._send_runner_input(locals_command())

    def _handle_add_watch_expression(self) -> None:
        if self._watch_input_widget is None or self._watch_list_widget is None:
            return
        expression = self._watch_input_widget.text().strip()
        if not expression:
            return
        existing = [self._watch_list_widget.item(index).text() for index in range(self._watch_list_widget.count())]
        if expression not in existing:
            self._watch_list_widget.addItem(expression)
        self._watch_input_widget.clear()

    def _handle_evaluate_watch_expressions(self) -> None:
        if self._watch_list_widget is None:
            return
        for index in range(self._watch_list_widget.count()):
            expression = self._watch_list_widget.item(index).text().strip()
            if not expression:
                continue
            self._send_runner_input(evaluate_command(expression))

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
            failed_checks = [check for check in report.checks if not check.is_ok]
            summary_lines = [
                f"{'OK' if check.is_ok else 'FAIL'} - {check.check_id}: {check.message}"
                for check in report.checks
            ]
            summary_text = "\n".join(summary_lines)
            if failed_checks:
                QMessageBox.warning(self, "Project health check", summary_text)
            else:
                QMessageBox.information(self, "Project health check", summary_text)

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Project health check", f"Health check failed: {exc}")

        self._background_tasks.run(key="project_health_check", task=task, on_success=on_success, on_error=on_error)

    def _handle_generate_support_bundle_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Support bundle unavailable", "Open a project before generating support bundle.")
            return
        project_root = self._loaded_project.project_root
        state_root = self._state_root
        latest_report = self._latest_health_report
        latest_run_log_path = self._resolve_latest_run_log_path()

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            report = latest_report
            if report is None:
                report = run_project_health_check(project_root, state_root=state_root)
            bundle_path = build_support_bundle(
                project_root,
                diagnostics_report=report,
                last_run_log_path=latest_run_log_path,
                state_root=state_root,
                destination_dir=project_root,
            )
            return (report, bundle_path)

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            report, bundle_path = payload
            self._latest_health_report = report
            QMessageBox.information(self, "Support bundle created", f"Bundle written to:\n{bundle_path}")

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self, "Support bundle", f"Support bundle generation failed: {exc}")

        self._background_tasks.run(key="support_bundle", task=task, on_success=on_success, on_error=on_error)

    def _resolve_latest_run_log_path(self) -> str | None:
        if self._active_run_session_log_path and Path(self._active_run_session_log_path).exists():
            return self._active_run_session_log_path
        if self._loaded_project is None:
            return None
        log_dir = Path(self._loaded_project.project_root) / "logs"
        if not log_dir.exists():
            return None
        candidate_logs = sorted(log_dir.glob("run_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidate_logs:
            return None
        return str(candidate_logs[0].resolve())

    def _refresh_run_action_states(self) -> None:
        self._run_session_controller.refresh_action_states(
            self._menu_registry,
            has_project=self._loaded_project is not None,
        )

    def _enqueue_run_event(self, event: ProcessEvent) -> None:
        self._run_event_queue.put(event)

    def _process_queued_run_events(self) -> None:
        while True:
            try:
                event = self._run_event_queue.get_nowait()
            except queue.Empty:
                break
            self._apply_run_event(event)

    def _apply_run_event(self, event: ProcessEvent) -> None:
        if event.event_type == "output":
            stream = event.stream or "stdout"
            text = event.text or ""
            parsed_debug_event = self._debug_session.ingest_output_line(text)
            if parsed_debug_event is not None and parsed_debug_event.event_type in {"paused", "running", "stack"}:
                if parsed_debug_event.message:
                    self._append_python_console_line(f"[debug] {parsed_debug_event.message}")
                    self._append_debug_output_line(f"[debug] {parsed_debug_event.message}")
                self._apply_debug_inspector_event()
                self._refresh_run_action_states()
                return
            self._active_run_output_tail.append(text)
            self._append_console_line(text, stream=stream)
            if self._active_session_mode in {constants.RUN_MODE_PYTHON_REPL, constants.RUN_MODE_PYTHON_DEBUG}:
                for line in text.rstrip().splitlines():
                    self._append_python_console_line(line)
                    if self._active_session_mode == constants.RUN_MODE_PYTHON_DEBUG:
                        self._append_debug_output_line(line)
            return

        if event.event_type == "exit":
            return_code = event.return_code
            if self._active_session_mode == constants.RUN_MODE_PYTHON_DEBUG:
                self._debug_session.mark_exited()
            if event.terminated_by_user:
                self._append_console_line(f"Run terminated by user (code={return_code}).\n", stream="system")
                self._append_python_console_line(f"[system] Session terminated (code={return_code}).")
            else:
                self._append_console_line(f"Run finished (code={return_code}).\n", stream="system")
                self._append_python_console_line(f"[system] Session finished (code={return_code}).")

            self._active_session_mode = None
            self._run_session_controller.clear_active_session_mode()
            self._refresh_run_action_states()
            self._load_latest_run_log()
            self._update_problems_from_output()
            return

        if event.event_type == "state":
            self._refresh_run_action_states()

    def _append_console_line(self, text: str, *, stream: str = "stdout") -> None:
        line = self._console_model.append(stream, text)
        if self._console_output_widget is None:
            return
        prefix = ""
        if stream == "stderr":
            prefix = "[stderr] "
        elif stream == "system":
            prefix = "[system] "
        timestamp = line.timestamp.split("T")[-1]
        self._console_output_widget.appendPlainText(f"[{timestamp}] {prefix}{line.text.rstrip()}")

    def _load_latest_run_log(self) -> None:
        if self._run_log_output_widget is None:
            return
        if not self._active_run_session_log_path:
            return

        log_path = Path(self._active_run_session_log_path)
        if not log_path.exists():
            self._run_log_output_widget.setPlainText("(No run log available)")
            return
        self._run_log_output_widget.setPlainText(log_path.read_text(encoding="utf-8"))

    def _update_problems_from_output(self) -> None:
        output_text = self._active_run_output_tail.text()
        problems = parse_traceback_problems(output_text)
        self._set_problems(problems)

    def _set_problems(self, problems: list[ProblemEntry]) -> None:
        if self._problems_list_widget is None:
            return
        self._problems_list_widget.clear()
        for problem in problems:
            item = QListWidgetItem(
                f"{problem.file_path}:{problem.line_number} | {problem.context} | {problem.message}",
                self._problems_list_widget,
            )
            item.setToolTip(problem.message)
            item.setData(PROBLEM_ROLE_FILE_PATH, problem.file_path)
            item.setData(PROBLEM_ROLE_LINE_NUMBER, problem.line_number)

    def _set_search_results(self, matches: list[SearchMatch], query: str) -> None:
        if self._problems_list_widget is None:
            return
        self._problems_list_widget.clear()
        if not matches:
            self._problems_list_widget.addItem(QListWidgetItem(f"No results for '{query}'."))
            return

        for match in matches:
            item = QListWidgetItem(
                f"{match.relative_path}:{match.line_number} | {match.line_text}",
                self._problems_list_widget,
            )
            item.setToolTip(match.absolute_path)
            item.setData(PROBLEM_ROLE_FILE_PATH, match.absolute_path)
            item.setData(PROBLEM_ROLE_LINE_NUMBER, match.line_number)

    def _schedule_search_results_update(self, matches: list[SearchMatch], query: str) -> None:
        QTimer.singleShot(0, lambda: self._set_search_results(matches, query))

    def _handle_search_worker_done(self, started_at: float, query: str) -> None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self._logger.info("Find in files telemetry: query=%r elapsed_ms=%.2f", query, elapsed_ms)
        QTimer.singleShot(0, lambda: setattr(self, "_active_search_worker", None))

    def _start_symbol_indexing(self, project_root: str) -> None:
        if not self._intelligence_runtime_settings.cache_enabled:
            return
        if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
            self._active_symbol_index_worker.cancel()
        started_at = time.perf_counter()
        self._active_symbol_index_worker = SymbolIndexWorker(
            project_root=project_root,
            cache_db_path=self._symbol_cache_db_path,
            on_done=lambda count: self._handle_symbol_index_done(project_root, count, started_at),
            on_error=lambda message: self._handle_symbol_index_error(project_root, message),
        )
        self._active_symbol_index_worker.start()

    def _rebuild_intelligence_cache(self) -> bool | None:
        if self._active_symbol_index_worker is not None and self._active_symbol_index_worker.is_running():
            self._active_symbol_index_worker.cancel()
        try:
            deleted = rebuild_symbol_cache(self._symbol_cache_db_path)
        except OSError as exc:
            QMessageBox.warning(self, "Rebuild Intelligence Cache", f"Unable to rebuild cache: {exc}")
            return None
        return deleted

    def _handle_symbol_index_done(self, project_root: str, symbol_count: int, started_at: float) -> None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self._logger.info(
            "Symbol index telemetry: root=%s symbols=%s elapsed_ms=%.2f",
            project_root,
            symbol_count,
            elapsed_ms,
        )
        QTimer.singleShot(0, lambda: setattr(self, "_active_symbol_index_worker", None))

    def _handle_symbol_index_error(self, project_root: str, message: str) -> None:
        self._logger.warning("Symbol index failed for %s: %s", project_root, message)
        QTimer.singleShot(0, lambda: setattr(self, "_active_symbol_index_worker", None))

    def _clear_problems(self) -> None:
        if self._problems_list_widget is not None:
            self._problems_list_widget.clear()

    def _handle_problem_item_activation(self, item: QListWidgetItem) -> None:
        file_path = item.data(PROBLEM_ROLE_FILE_PATH)
        line_number = item.data(PROBLEM_ROLE_LINE_NUMBER)
        if not file_path:
            return
        try:
            resolved_line = int(line_number) if line_number is not None else None
        except (TypeError, ValueError):
            resolved_line = None
        self._open_file_at_line(str(file_path), resolved_line)

    def _show_problems_context_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        if self._problems_list_widget is None:
            return
        item = self._problems_list_widget.itemAt(position)
        if item is None:
            return

        diagnostic_code = item.data(PROBLEM_ROLE_DIAGNOSTIC_CODE)
        file_path = item.data(PROBLEM_ROLE_FILE_PATH)
        if not file_path:
            return

        menu = QMenu(self)
        apply_fixes_action = None
        if diagnostic_code in {"PY220", "PY200"}:
            apply_fixes_action = menu.addAction("Apply Safe Fixes for File")
        if apply_fixes_action is None:
            return
        chosen = menu.exec_(self._problems_list_widget.viewport().mapToGlobal(position))
        if chosen == apply_fixes_action:
            self._apply_safe_fixes_for_file(str(file_path))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt signature
        if self._confirm_proceed_with_unsaved_changes("exiting"):
            self._background_tasks.cancel_all()
            self._flush_pending_autosaves()
            if self._status_controller is not None:
                self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            self._persist_layout_to_settings()
            event.accept()
            return
        event.ignore()

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.type() == QEvent.PaletteChange and not self._is_applying_theme_styles:
            self._apply_theme_styles()
        super().changeEvent(event)

    def _configure_window_frame(self) -> None:
        self.setObjectName("shell.mainWindow")
        self.setWindowTitle("ChoreBoy Code Studio")
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
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title_label = QLabel("Project", panel)
        title_label.setObjectName("shell.leftRegion.title")
        layout.addWidget(title_label)

        self._project_placeholder_label = QLabel("No project loaded.", panel)
        self._project_placeholder_label.setObjectName("shell.leftRegion.body")
        self._project_placeholder_label.setWordWrap(True)
        layout.addWidget(self._project_placeholder_label)

        self._project_tree_widget = ProjectTreeWidget(panel)
        self._project_tree_widget.setObjectName("shell.projectTree")
        self._project_tree_widget.setHeaderHidden(True)
        self._project_tree_widget.itemActivated.connect(self._handle_project_tree_item_activation)
        self._project_tree_widget.itemClicked.connect(self._handle_project_tree_item_activation)
        self._project_tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._project_tree_widget.customContextMenuRequested.connect(self._show_project_tree_context_menu)
        self._project_tree_widget.set_drop_callback(self._handle_project_tree_drop)
        layout.addWidget(self._project_tree_widget, 1)
        panel.setMinimumWidth(220)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget(self)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.setSpacing(4)

        self._breadcrumbs_label = QLabel("Path: /", panel)
        self._breadcrumbs_label.setObjectName("shell.editor.breadcrumbs")
        panel_layout.addWidget(self._breadcrumbs_label, 0)

        self._editor_tabs_widget = QTabWidget(panel)
        self._editor_tabs_widget.setObjectName("shell.editorTabs")
        self._editor_tabs_widget.currentChanged.connect(self._handle_editor_tab_changed)
        self._editor_tabs_widget.setMinimumWidth(480)
        panel_layout.addWidget(self._editor_tabs_widget, 1)
        return panel

    def _build_bottom_panel(self) -> QWidget:
        tabs = QTabWidget(self)
        tabs.setObjectName("shell.bottomRegion.tabs")
        self._bottom_tabs_widget = tabs

        self._console_output_widget = QPlainTextEdit(tabs)
        self._console_output_widget.setObjectName("shell.bottom.console")
        self._console_output_widget.setReadOnly(True)
        tabs.addTab(self._console_output_widget, "Console")

        console_panel = QWidget(tabs)
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(8, 8, 8, 8)
        console_layout.setSpacing(6)

        self._python_console_output_widget = QPlainTextEdit(console_panel)
        self._python_console_output_widget.setObjectName("shell.bottom.pythonConsole.output")
        self._python_console_output_widget.setReadOnly(True)
        console_layout.addWidget(self._python_console_output_widget, 1)

        input_row = QWidget(console_panel)
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)
        self._python_console_input_widget = QLineEdit(input_row)
        self._python_console_input_widget.setObjectName("shell.bottom.pythonConsole.input")
        self._python_console_input_widget.returnPressed.connect(self._handle_python_console_submit)
        input_layout.addWidget(self._python_console_input_widget, 1)
        self._python_console_send_button = QPushButton("Send", input_row)
        self._python_console_send_button.clicked.connect(self._handle_python_console_submit)
        input_layout.addWidget(self._python_console_send_button, 0)
        console_layout.addWidget(input_row, 0)
        tabs.addTab(console_panel, "Python Console")

        debug_panel = QWidget(tabs)
        debug_layout = QVBoxLayout(debug_panel)
        debug_layout.setContentsMargins(8, 8, 8, 8)
        debug_layout.setSpacing(6)

        debug_controls = QWidget(debug_panel)
        debug_controls_layout = QHBoxLayout(debug_controls)
        debug_controls_layout.setContentsMargins(0, 0, 0, 0)
        debug_controls_layout.setSpacing(6)
        stack_button = QPushButton("Refresh Stack", debug_controls)
        stack_button.clicked.connect(self._handle_debug_refresh_stack)
        debug_controls_layout.addWidget(stack_button)
        locals_button = QPushButton("Refresh Locals", debug_controls)
        locals_button.clicked.connect(self._handle_debug_refresh_locals)
        debug_controls_layout.addWidget(locals_button)
        debug_layout.addWidget(debug_controls)

        watch_row = QWidget(debug_panel)
        watch_row_layout = QHBoxLayout(watch_row)
        watch_row_layout.setContentsMargins(0, 0, 0, 0)
        watch_row_layout.setSpacing(6)
        self._watch_input_widget = QLineEdit(watch_row)
        self._watch_input_widget.setPlaceholderText("watch expression, e.g. my_var")
        watch_row_layout.addWidget(self._watch_input_widget, 1)
        add_watch_button = QPushButton("Add Watch", watch_row)
        add_watch_button.clicked.connect(self._handle_add_watch_expression)
        watch_row_layout.addWidget(add_watch_button)
        eval_watch_button = QPushButton("Evaluate Watches", watch_row)
        eval_watch_button.clicked.connect(self._handle_evaluate_watch_expressions)
        watch_row_layout.addWidget(eval_watch_button)
        debug_layout.addWidget(watch_row)

        stack_and_vars = QWidget(debug_panel)
        stack_and_vars_layout = QHBoxLayout(stack_and_vars)
        stack_and_vars_layout.setContentsMargins(0, 0, 0, 0)
        stack_and_vars_layout.setSpacing(6)

        self._debug_stack_list_widget = QListWidget(stack_and_vars)
        self._debug_stack_list_widget.setObjectName("shell.bottom.debug.stackList")
        stack_and_vars_layout.addWidget(self._debug_stack_list_widget, 1)

        self._debug_variables_list_widget = QListWidget(stack_and_vars)
        self._debug_variables_list_widget.setObjectName("shell.bottom.debug.variablesList")
        stack_and_vars_layout.addWidget(self._debug_variables_list_widget, 1)
        debug_layout.addWidget(stack_and_vars, 1)

        self._watch_list_widget = QListWidget(debug_panel)
        self._watch_list_widget.setObjectName("shell.bottom.debug.watchList")
        debug_layout.addWidget(self._watch_list_widget, 1)

        self._breakpoints_list_widget = QListWidget(debug_panel)
        self._breakpoints_list_widget.setObjectName("shell.bottom.debug.breakpointsList")
        debug_layout.addWidget(self._breakpoints_list_widget, 1)

        self._debug_inspector_output_widget = QPlainTextEdit(debug_panel)
        self._debug_inspector_output_widget.setObjectName("shell.bottom.debug.output")
        self._debug_inspector_output_widget.setReadOnly(True)
        debug_layout.addWidget(self._debug_inspector_output_widget, 2)
        tabs.addTab(debug_panel, "Debug")

        self._problems_list_widget = QListWidget(tabs)
        self._problems_list_widget.setObjectName("shell.bottom.problems")
        self._problems_list_widget.itemActivated.connect(self._handle_problem_item_activation)
        self._problems_list_widget.itemDoubleClicked.connect(self._handle_problem_item_activation)
        self._problems_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._problems_list_widget.customContextMenuRequested.connect(self._show_problems_context_menu)
        tabs.addTab(self._problems_list_widget, "Problems")

        self._run_log_output_widget = QPlainTextEdit(tabs)
        self._run_log_output_widget.setObjectName("shell.bottom.runLog")
        self._run_log_output_widget.setReadOnly(True)
        tabs.addTab(self._run_log_output_widget, "Run Log")
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

    def _populate_project_tree(self, loaded_project: LoadedProject) -> None:
        if self._project_tree_widget is None:
            return

        self._project_tree_widget.clear()
        root_nodes = build_project_tree(loaded_project.entries)
        display_nodes = build_project_tree_display(root_nodes)
        for display_node in display_nodes:
            root_item = self._build_tree_item(display_node)
            self._project_tree_widget.addTopLevelItem(root_item)
            if display_node.is_directory:
                root_item.setExpanded(True)

    def _build_tree_item(self, node: ProjectTreeDisplayNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.display_label])
        item.setData(0, TREE_ROLE_ABSOLUTE_PATH, node.absolute_path)
        item.setData(0, TREE_ROLE_IS_DIRECTORY, node.is_directory)
        item.setData(0, TREE_ROLE_RELATIVE_PATH, node.relative_path)

        for child_node in node.children:
            item.addChild(self._build_tree_item(child_node))
        return item

    def _handle_project_tree_item_activation(self, item: QTreeWidgetItem, _column: int) -> None:
        is_directory = bool(item.data(0, TREE_ROLE_IS_DIRECTORY))
        absolute_path = item.data(0, TREE_ROLE_ABSOLUTE_PATH)
        if is_directory or not absolute_path:
            return
        self._open_file_in_editor(str(absolute_path))

    def _show_project_tree_context_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        if self._project_tree_widget is None:
            return
        item = self._project_tree_widget.itemAt(position)
        if item is None:
            return
        absolute_path = str(item.data(0, TREE_ROLE_ABSOLUTE_PATH) or "")
        relative_path = str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "")
        is_directory = bool(item.data(0, TREE_ROLE_IS_DIRECTORY))
        if not absolute_path:
            return

        menu = QMenu(self)
        new_file_action = menu.addAction("New File…")
        new_folder_action = menu.addAction("New Folder…")
        menu.addSeparator()
        rename_action = menu.addAction("Rename…")
        delete_action = menu.addAction("Delete")
        duplicate_action = menu.addAction("Duplicate")
        menu.addSeparator()
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        copy_path_action = menu.addAction("Copy Path")
        copy_relative_path_action = menu.addAction("Copy Relative Path")
        reveal_action = menu.addAction("Reveal in File Manager")

        paste_action.setEnabled(self._tree_clipboard_path is not None)
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
            self._tree_clipboard_path = absolute_path
            self._tree_clipboard_cut = False
        elif chosen == cut_action:
            self._tree_clipboard_path = absolute_path
            self._tree_clipboard_cut = True
        elif chosen == paste_action:
            self._handle_tree_paste(absolute_path if is_directory else str(Path(absolute_path).parent))
        elif chosen == copy_path_action:
            QApplication.clipboard().setText(absolute_path)
        elif chosen == copy_relative_path_action:
            QApplication.clipboard().setText(relative_path)
        elif chosen == reveal_action:
            self._reveal_path_in_file_manager(absolute_path)

    def _handle_tree_new_file(self, destination_directory: str) -> None:
        file_name, ok = QInputDialog.getText(self, "New File", "File name:", QLineEdit.Normal, "")
        if not ok or not file_name.strip():
            return
        result = create_file(str(Path(destination_directory) / file_name.strip()))
        if not result.success:
            QMessageBox.warning(self, "New File", result.message)
            return
        self._reload_current_project()

    def _handle_tree_new_folder(self, destination_directory: str) -> None:
        folder_name, ok = QInputDialog.getText(self, "New Folder", "Folder name:", QLineEdit.Normal, "")
        if not ok or not folder_name.strip():
            return
        result = create_directory(str(Path(destination_directory) / folder_name.strip()))
        if not result.success:
            QMessageBox.warning(self, "New Folder", result.message)
            return
        self._reload_current_project()

    def _handle_tree_rename(self, source_path: str) -> None:
        source = Path(source_path)
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", QLineEdit.Normal, source.name)
        if not ok or not new_name.strip() or new_name.strip() == source.name:
            return
        destination = source.with_name(new_name.strip())
        result = rename_path(str(source), str(destination))
        if not result.success:
            QMessageBox.warning(self, "Rename", result.message)
            return
        self._apply_path_move_updates(str(source), str(destination))
        self._reload_current_project()

    def _handle_tree_delete(self, target_path: str) -> None:
        confirmation = QMessageBox.question(
            self,
            "Delete",
            f"Delete '{Path(target_path).name}'?\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        result = delete_path(target_path)
        if not result.success:
            QMessageBox.warning(self, "Delete", result.message)
            return
        self._close_deleted_editor_paths(target_path)
        self._reload_current_project()

    def _handle_tree_duplicate(self, source_path: str) -> None:
        result = duplicate_path(source_path)
        if not result.success:
            QMessageBox.warning(self, "Duplicate", result.message)
            return
        self._reload_current_project()

    def _handle_tree_paste(self, destination_directory: str) -> None:
        if self._tree_clipboard_path is None:
            return
        source = Path(self._tree_clipboard_path).resolve()
        destination = Path(destination_directory).resolve() / source.name
        if self._tree_clipboard_cut:
            result = move_path(str(source), str(destination))
            if result.success:
                self._apply_path_move_updates(str(source), str(destination))
                self._tree_clipboard_path = None
                self._tree_clipboard_cut = False
        else:
            result = copy_path(str(source), str(destination))
        if not result.success:
            QMessageBox.warning(self, "Paste", result.message)
            return
        self._reload_current_project()

    def _handle_project_tree_drop(self, source_path: str, target_path: str) -> bool:
        source = Path(source_path).resolve()
        target = Path(target_path).resolve()
        destination_directory = target if target.is_dir() else target.parent
        destination = destination_directory / source.name
        result = move_path(str(source), str(destination))
        if not result.success:
            QMessageBox.warning(self, "Move", result.message)
            return False
        self._apply_path_move_updates(str(source), str(destination))
        self._reload_current_project()
        return True

    def _reveal_path_in_file_manager(self, path: str) -> None:
        from PySide2.QtCore import QUrl
        from PySide2.QtGui import QDesktopServices

        target = Path(path).expanduser().resolve()
        reveal_target = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(reveal_target)))

    def _close_deleted_editor_paths(self, deleted_path: str) -> None:
        self._project_tree_controller.close_deleted_editor_paths(
            deleted_path,
            editor_widgets_by_path=self._editor_widgets_by_path,
            tab_index_for_path=self._tab_index_for_path,
            remove_tab_at_index=lambda tab_index: self._editor_tabs_widget.removeTab(tab_index)
            if self._editor_tabs_widget is not None
            else None,
            release_editor_widget=lambda widget: widget.deleteLater(),
            close_editor_file=self._editor_manager.close_file,
            breakpoints_by_file=self._breakpoints_by_file,
            refresh_breakpoints_list=self._refresh_breakpoints_list,
        )

    def _apply_path_move_updates(self, source_path: str, destination_path: str) -> None:
        self._project_tree_controller.apply_path_move_updates(
            source_path,
            destination_path,
            remap_editor_paths=self._editor_manager.remap_paths_for_move,
            editor_widgets_by_path=self._editor_widgets_by_path,
            tab_index_for_path=self._tab_index_for_path,
            update_tab_path_and_name=lambda tab_index, new_path: self._update_tab_path_and_name(tab_index, new_path),
            breakpoints_by_file=self._breakpoints_by_file,
            apply_breakpoints_to_widget=lambda widget, breakpoints: widget.set_breakpoints(breakpoints),
            update_widget_language=lambda widget, new_path: widget.set_language_for_path(new_path),
            refresh_breakpoints_list=self._refresh_breakpoints_list,
            maybe_rewrite_imports=self._maybe_rewrite_imports_for_move,
        )

    def _update_tab_path_and_name(self, tab_index: int, new_path: str) -> None:
        if self._editor_tabs_widget is None:
            return
        self._editor_tabs_widget.setTabToolTip(tab_index, new_path)
        self._editor_tabs_widget.setTabText(tab_index, Path(new_path).name)

    def _maybe_rewrite_imports_for_move(self, source_path: str, destination_path: str) -> None:
        self._project_tree_controller.maybe_rewrite_imports_for_move(
            project_root=None if self._loaded_project is None else self._loaded_project.project_root,
            source_path=source_path,
            destination_path=destination_path,
            resolve_policy_for_operation=self._resolve_import_update_policy_for_operation,
            request_confirmation=self._request_import_rewrite_confirmation,
            show_warning=lambda details: self._show_import_update_warning(details),
        )

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
        self._loaded_project = open_project(self._loaded_project.project_root)
        self._populate_project_tree(self._loaded_project)
        self._start_symbol_indexing(self._loaded_project.project_root)

    def _open_file_in_editor(self, file_path: str) -> bool:
        if self._editor_tabs_widget is None:
            return False

        started_at = time.perf_counter()
        try:
            opened_result = self._editor_manager.open_file(file_path)
        except ValueError as exc:
            QMessageBox.warning(self, "Unable to open file", str(exc))
            return False

        if opened_result.was_already_open:
            existing_index = self._tab_index_for_path(opened_result.tab.file_path)
            if existing_index >= 0:
                self._editor_tabs_widget.setCurrentIndex(existing_index)
            self._refresh_save_action_states()
            self._update_editor_status_for_path(opened_result.tab.file_path)
            return True

        editor_widget = CodeEditorWidget(self._editor_tabs_widget)
        editor_widget.setObjectName("shell.editorTabs.textEditor")
        editor_widget.set_editor_preferences(
            tab_width=self._editor_tab_width,
            font_point_size=self._editor_font_size,
            indent_style=self._editor_indent_style,
            indent_size=self._editor_indent_size,
        )
        editor_widget.set_completion_preferences(
            enabled=self._completion_enabled,
            auto_trigger=self._completion_auto_trigger,
            min_chars=self._completion_min_chars,
        )
        editor_widget.set_language_for_path(opened_result.tab.file_path)
        editor_widget.setPlainText(opened_result.tab.current_content)
        tab_file_path = opened_result.tab.file_path

        def completion_provider(
            _prefix: str,
            source_text: str,
            cursor_position: int,
            manual_trigger: bool,
        ) -> list[CompletionItem]:
            return self._request_editor_completions(
                file_path=tab_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
                manual_trigger=manual_trigger,
            )

        def on_breakpoint_toggled(line_number: int, enabled: bool) -> None:
            self._handle_editor_breakpoint_toggled(tab_file_path, line_number, enabled)

        def on_text_changed() -> None:
            self._handle_editor_text_changed(tab_file_path, editor_widget)

        def on_cursor_position_changed() -> None:
            self._handle_editor_cursor_position_changed(tab_file_path, editor_widget)

        editor_widget.set_breakpoint_toggled_callback(on_breakpoint_toggled)
        editor_widget.set_completion_provider(completion_provider)
        editor_widget.set_breakpoints(self._breakpoints_by_file.get(opened_result.tab.file_path, set()))
        editor_widget.textChanged.connect(on_text_changed)
        editor_widget.cursorPositionChanged.connect(on_cursor_position_changed)
        self._editor_widgets_by_path[opened_result.tab.file_path] = editor_widget

        tab_index = self._editor_tabs_widget.addTab(editor_widget, opened_result.tab.display_name)
        self._editor_tabs_widget.setTabToolTip(tab_index, opened_result.tab.file_path)
        self._editor_tabs_widget.setCurrentIndex(tab_index)
        self._maybe_restore_draft(opened_result.tab, editor_widget)
        self._apply_detected_indentation_for_widget(
            opened_result.tab.file_path,
            editor_widget,
            editor_widget.toPlainText(),
        )
        self._handle_editor_tab_changed(tab_index)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(opened_result.tab.file_path)
        self._logger.info(
            "File open telemetry: file=%s elapsed_ms=%.2f",
            opened_result.tab.file_path,
            (time.perf_counter() - started_at) * 1000.0,
        )
        return True

    def _open_file_at_line(self, file_path: str, line_number: int | None) -> None:
        if not self._open_file_in_editor(file_path):
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

    def _handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        tab_state = self._editor_manager.update_tab_content(file_path, editor_widget.toPlainText())
        if self._editor_tabs_widget is None:
            return

        tab_index = self._tab_index_for_path(tab_state.file_path)
        if tab_index < 0:
            return
        suffix = " *" if tab_state.is_dirty else ""
        self._editor_tabs_widget.setTabText(tab_index, f"{tab_state.display_name}{suffix}")
        if tab_state.is_dirty:
            self._schedule_autosave(tab_state.file_path, tab_state.current_content)
        else:
            self._pending_autosave_payloads.pop(tab_state.file_path, None)
            self._autosave_store.delete_draft(tab_state.file_path)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(tab_state.file_path)

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
            self._update_breadcrumb_for_path(None)
            return
        self._status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=editor_widget.textCursor().blockNumber() + 1,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )
        self._update_breadcrumb_for_path(tab_state.file_path)

    def _update_breadcrumb_for_path(self, file_path: str | None) -> None:
        if self._breadcrumbs_label is None:
            return
        if file_path is None:
            self._breadcrumbs_label.setText("Path: /")
            return
        relative = None
        if self._loaded_project is not None:
            try:
                relative = Path(file_path).resolve().relative_to(Path(self._loaded_project.project_root).resolve()).as_posix()
            except ValueError:
                relative = Path(file_path).name
        else:
            relative = Path(file_path).name
        self._breadcrumbs_label.setText(f"Path: {relative}")

    def _active_editor_widget(self) -> CodeEditorWidget | None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return None
        return self._editor_widgets_by_path.get(active_tab.file_path)

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
        completions = list(self._completion_service.complete(request))
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

    def _handle_editor_tab_changed(self, tab_index: int) -> None:
        if tab_index < 0 or self._editor_tabs_widget is None:
            return

        tab_path = self._editor_tabs_widget.tabToolTip(tab_index)
        if not tab_path:
            return
        self._editor_manager.set_active_file(tab_path)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(tab_path)

    def _reset_editor_tabs(self) -> None:
        if self._editor_tabs_widget is not None:
            self._editor_tabs_widget.clear()
        self._autosave_timer.stop()
        self._pending_autosave_payloads.clear()
        self._editor_widgets_by_path.clear()
        self._editor_manager = EditorManager()
        self._refresh_save_action_states()
        if self._status_controller is not None:
            self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
        self._update_breadcrumb_for_path(None)

    def _apply_editor_preferences_to_open_editors(self) -> None:
        for file_path, editor_widget in self._editor_widgets_by_path.items():
            editor_widget.set_editor_preferences(
                tab_width=self._editor_tab_width,
                font_point_size=self._editor_font_size,
                indent_style=self._editor_indent_style,
                indent_size=self._editor_indent_size,
            )
            self._apply_detected_indentation_for_widget(file_path, editor_widget, editor_widget.toPlainText())
            editor_widget.set_completion_preferences(
                enabled=self._completion_enabled,
                auto_trigger=self._completion_auto_trigger,
                min_chars=self._completion_min_chars,
            )

    def _apply_detected_indentation_for_widget(
        self,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
    ) -> None:
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
            font_point_size=self._editor_font_size,
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
            self._apply_detected_indentation_for_widget(file_path, editor_widget, refreshed)
            updated_tab = self._editor_manager.update_tab_content(file_path, refreshed)
            updated_tab.mark_saved()
            tab_index = self._tab_index_for_path(file_path)
            if self._editor_tabs_widget is not None and tab_index >= 0:
                self._editor_tabs_widget.setTabText(tab_index, updated_tab.display_name)
        self._refresh_save_action_states()

    def _maybe_restore_draft(self, tab_state: EditorTabState, editor_widget: CodeEditorWidget) -> None:
        draft_entry = self._autosave_store.load_draft(tab_state.file_path)
        if draft_entry is None or draft_entry.content == tab_state.current_content:
            return

        response = QMessageBox.question(
            self,
            "Restore draft",
            f"A recovery draft is available for {tab_state.display_name}.\nRestore unsaved changes?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if response != QMessageBox.Yes:
            return

        editor_widget.blockSignals(True)
        editor_widget.setPlainText(draft_entry.content)
        editor_widget.blockSignals(False)
        updated_tab = self._editor_manager.update_tab_content(tab_state.file_path, draft_entry.content)
        tab_index = self._tab_index_for_path(tab_state.file_path)
        if self._editor_tabs_widget is not None and tab_index >= 0:
            self._editor_tabs_widget.setTabText(tab_index, f"{updated_tab.display_name} *")
        self._schedule_autosave(updated_tab.file_path, updated_tab.current_content)

    def _schedule_autosave(self, file_path: str, content: str) -> None:
        self._pending_autosave_payloads[file_path] = content
        self._autosave_timer.start()

    def _flush_pending_autosaves(self) -> None:
        if not self._pending_autosave_payloads:
            return
        pending_items = list(self._pending_autosave_payloads.items())
        self._pending_autosave_payloads.clear()
        for file_path, content in pending_items:
            try:
                self._autosave_store.save_draft(file_path, content)
            except OSError as exc:
                self._logger.warning("Autosave draft write failed for %s: %s", file_path, exc)
