"""Main Qt shell composition and top-level workflow wiring."""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Optional

from PySide2.QtCore import QTimer, Qt
from PySide2.QtGui import QCloseEvent
from PySide2.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core.errors import AppValidationError
from app.core.models import CapabilityProbeReport
from app.core.models import LoadedProject
from app.editors.editor_manager import EditorManager
from app.editors.editor_tab import EditorTabState
from app.persistence.autosave_store import AutosaveStore
from app.run.console_model import ConsoleModel
from app.run.problem_parser import ProblemEntry, parse_traceback_problems
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService
from app.support.diagnostics import ProjectHealthReport, run_project_health_check
from app.support.support_bundle import build_support_bundle
from app.templates.template_service import TemplateMetadata, TemplateService
from app.project.project_tree import ProjectTreeNode, build_project_tree
from app.project.project_service import open_project_and_track_recent
from app.project.recent_projects import load_recent_projects
from app.shell.actions import map_run_action_state
from app.shell.menus import MenuCallbacks, MenuStubRegistry, build_menu_stubs, build_recent_project_menu_items
from app.shell.status_bar import ShellStatusBarController, create_shell_status_bar

# Qt.UserRole is 0x0100 (256). Literal role IDs avoid enum typing mismatches across PySide shims.
TREE_ROLE_ABSOLUTE_PATH = 256
TREE_ROLE_IS_DIRECTORY = 257
TREE_ROLE_RELATIVE_PATH = 258


class MainWindow(QMainWindow):
    """Top-level editor window shell with extension seams for later tasks."""

    def __init__(self, startup_report: Optional[CapabilityProbeReport] = None, state_root: str | None = None) -> None:
        super().__init__()
        self._project_placeholder_label: QLabel | None = None
        self._project_tree_widget: QTreeWidget | None = None
        self._editor_tabs_widget: QTabWidget | None = None
        self._console_output_widget: QPlainTextEdit | None = None
        self._run_log_output_widget: QPlainTextEdit | None = None
        self._problems_list_widget: QListWidget | None = None
        self._menu_registry: MenuStubRegistry | None = None
        self._status_controller: ShellStatusBarController | None = None
        self._state_root = state_root
        self._loaded_project: LoadedProject | None = None
        self._editor_manager = EditorManager()
        self._editor_widgets_by_path: dict[str, QPlainTextEdit] = {}
        self._autosave_store = AutosaveStore(state_root=self._state_root)
        self._console_model = ConsoleModel()
        self._run_event_queue: queue.Queue[ProcessEvent] = queue.Queue()
        self._active_run_output_chunks: list[str] = []
        self._active_run_session_log_path: str | None = None
        self._latest_health_report: ProjectHealthReport | None = None
        self._run_service = RunService(on_event=self._enqueue_run_event)
        self._template_service = TemplateService()
        self._logger = get_subsystem_logger("shell")

        self._configure_window_frame()
        self._build_layout_shell()
        self._menu_registry = build_menu_stubs(
            self,
            callbacks=MenuCallbacks(
                on_open_project=self._handle_open_project_action,
                on_file_menu_about_to_show=self._refresh_open_recent_menu,
                on_save=self._handle_save_action,
                on_save_all=self._handle_save_all_action,
                on_run=self._handle_run_action,
                on_stop=self._handle_stop_action,
                on_clear_console=self._handle_clear_console_action,
                on_project_health_check=self._handle_project_health_check_action,
                on_generate_support_bundle=self._handle_generate_support_bundle_action,
                on_new_project=self._handle_new_project_action,
            ),
        )
        self._status_controller = create_shell_status_bar(self, startup_report=startup_report)
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

    def _prompt_for_template(self, templates: list[TemplateMetadata]) -> TemplateMetadata | None:
        labels = [f"{template.display_name} ({template.template_id})" for template in templates]
        selected_label, ok = QInputDialog.getItem(self, "New Project", "Template:", labels, 0, editable=False)
        if not ok:
            return None
        for template in templates:
            if selected_label == f"{template.display_name} ({template.template_id})":
                return template
        return None

    def _open_project_by_path(self, project_root: str) -> bool:
        if not self._confirm_proceed_with_unsaved_changes("opening another project"):
            return False

        try:
            loaded_project = open_project_and_track_recent(
                project_root,
                state_root=self._state_root,
            )
        except (AppValidationError, ValueError) as exc:
            self._show_open_project_error(project_root, str(exc))
            return False
        except Exception as exc:  # pragma: no cover - defensive shell guard
            self._logger.exception("Unexpected error while opening project: %s", project_root)
            self._show_open_project_error(project_root, f"Unexpected error: {exc}")
            return False

        self._loaded_project = loaded_project
        self.set_project_placeholder(loaded_project.metadata.name)
        self.setWindowTitle(f"ChoreBoy Code Studio — {loaded_project.metadata.name}")
        self._logger.info("Project loaded: %s", loaded_project.project_root)
        self._populate_project_tree(loaded_project)
        self._reset_editor_tabs()
        self._refresh_open_recent_menu()
        self._refresh_save_action_states()
        self._refresh_run_action_states()
        return True

    def _refresh_open_recent_menu(self) -> None:
        if self._menu_registry is None:
            return

        open_recent_menu = self._menu_registry.menu("shell.menu.file.openRecent")
        if open_recent_menu is None:
            return

        open_recent_menu.clear()
        recent_paths = load_recent_projects(state_root=self._state_root)
        recent_items = build_recent_project_menu_items(recent_paths)

        if not recent_items:
            placeholder_action = open_recent_menu.addAction("(No recent projects)")
            placeholder_action.setEnabled(False)
            return

        for recent_item in recent_items:
            action = open_recent_menu.addAction(recent_item.display_text)
            action.setToolTip(recent_item.project_path)
            action.triggered.connect(
                lambda _checked=False, project_path=recent_item.project_path: self._open_project_by_path(project_path)
            )

    def _show_open_project_error(self, project_root: str, details: str) -> None:
        self._logger.warning("Project open failed for %s: %s", project_root, details)
        QMessageBox.critical(
            self,
            "Unable to open project",
            f"Could not open project:\n{project_root}\n\n{details}",
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

        self._autosave_store.delete_draft(saved_tab.file_path)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(saved_tab.file_path)
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
        if self._loaded_project is None:
            QMessageBox.warning(self, "Run unavailable", "Open a project before running code.")
            return False
        if self._run_service.supervisor.is_running():
            return False

        if not self._handle_save_all_action():
            QMessageBox.warning(self, "Run cancelled", "Fix save errors before running.")
            return False

        self._active_run_output_chunks.clear()
        self._clear_problems()
        self._append_console_line("[system] Starting run...\n")

        try:
            session = self._run_service.start_run(self._loaded_project)
        except Exception as exc:
            QMessageBox.warning(self, "Run failed to start", str(exc))
            self._append_console_line(f"[system] Run failed to start: {exc}\n", stream="stderr")
            self._refresh_run_action_states()
            return False

        self._active_run_session_log_path = session.log_file_path
        self._append_console_line(f"[system] Run started ({session.run_id})\n")
        self._refresh_run_action_states()
        return True

    def _handle_stop_action(self) -> None:
        self._run_service.stop_run()
        self._append_console_line("[system] Stop requested.\n")
        self._refresh_run_action_states()

    def _handle_clear_console_action(self) -> None:
        self._console_model.clear()
        if self._console_output_widget is not None:
            self._console_output_widget.clear()

    def _handle_project_health_check_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Health check unavailable", "Open a project before running diagnostics.")
            return

        report = run_project_health_check(self._loaded_project.project_root, state_root=self._state_root)
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

    def _handle_generate_support_bundle_action(self) -> None:
        if self._loaded_project is None:
            QMessageBox.warning(self, "Support bundle unavailable", "Open a project before generating support bundle.")
            return
        if self._latest_health_report is None:
            self._latest_health_report = run_project_health_check(
                self._loaded_project.project_root,
                state_root=self._state_root,
            )

        bundle_path = build_support_bundle(
            self._loaded_project.project_root,
            diagnostics_report=self._latest_health_report,
            last_run_log_path=self._resolve_latest_run_log_path(),
            state_root=self._state_root,
            destination_dir=self._loaded_project.project_root,
        )
        QMessageBox.information(self, "Support bundle created", f"Bundle written to:\n{bundle_path}")

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
        if self._menu_registry is None:
            return

        run_action = self._menu_registry.action("shell.action.run.run")
        stop_action = self._menu_registry.action("shell.action.run.stop")
        state = map_run_action_state(
            has_project=self._loaded_project is not None,
            is_running=self._run_service.supervisor.is_running(),
        )

        if run_action is not None:
            run_action.setEnabled(state.run_enabled)
        if stop_action is not None:
            stop_action.setEnabled(state.stop_enabled)

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
            self._active_run_output_chunks.append(text)
            self._append_console_line(text, stream=stream)
            return

        if event.event_type == "exit":
            return_code = event.return_code
            if event.terminated_by_user:
                self._append_console_line(f"[system] Run terminated by user (code={return_code}).\n")
            else:
                self._append_console_line(f"[system] Run finished (code={return_code}).\n")

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
        self._console_output_widget.appendPlainText(f"{prefix}{line.text.rstrip()}")

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
        output_text = "".join(self._active_run_output_chunks)
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

    def _clear_problems(self) -> None:
        if self._problems_list_widget is not None:
            self._problems_list_widget.clear()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt signature
        if self._confirm_proceed_with_unsaved_changes("exiting"):
            if self._status_controller is not None:
                self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            event.accept()
            return
        event.ignore()

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

        top_splitter = QSplitter(Qt.Horizontal, vertical_splitter)
        top_splitter.setObjectName("shell.topSplitter")
        top_splitter.addWidget(self._build_left_panel())
        top_splitter.addWidget(self._build_center_panel())
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 3)

        vertical_splitter.addWidget(top_splitter)
        vertical_splitter.addWidget(self._build_bottom_panel())
        vertical_splitter.setStretchFactor(0, 4)
        vertical_splitter.setStretchFactor(1, 2)

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

        self._project_tree_widget = QTreeWidget(panel)
        self._project_tree_widget.setObjectName("shell.projectTree")
        self._project_tree_widget.setHeaderHidden(True)
        self._project_tree_widget.itemActivated.connect(self._handle_project_tree_item_activation)
        self._project_tree_widget.itemClicked.connect(self._handle_project_tree_item_activation)
        layout.addWidget(self._project_tree_widget, 1)
        return panel

    def _build_center_panel(self) -> QWidget:
        self._editor_tabs_widget = QTabWidget(self)
        self._editor_tabs_widget.setObjectName("shell.editorTabs")
        self._editor_tabs_widget.currentChanged.connect(self._handle_editor_tab_changed)
        return self._editor_tabs_widget

    def _build_bottom_panel(self) -> QWidget:
        tabs = QTabWidget(self)
        tabs.setObjectName("shell.bottomRegion.tabs")

        self._console_output_widget = QPlainTextEdit(tabs)
        self._console_output_widget.setObjectName("shell.bottom.console")
        self._console_output_widget.setReadOnly(True)
        tabs.addTab(self._console_output_widget, "Console")

        self._problems_list_widget = QListWidget(tabs)
        self._problems_list_widget.setObjectName("shell.bottom.problems")
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
        for root_node in root_nodes:
            root_item = self._build_tree_item(root_node)
            self._project_tree_widget.addTopLevelItem(root_item)
            if root_node.is_directory:
                root_item.setExpanded(True)

    def _build_tree_item(self, node: ProjectTreeNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name])
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

    def _open_file_in_editor(self, file_path: str) -> bool:
        if self._editor_tabs_widget is None:
            return False

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

        editor_widget = QPlainTextEdit(self._editor_tabs_widget)
        editor_widget.setObjectName("shell.editorTabs.textEditor")
        editor_widget.setPlainText(opened_result.tab.current_content)
        editor_widget.textChanged.connect(
            lambda file_path=opened_result.tab.file_path, widget=editor_widget: self._handle_editor_text_changed(
                file_path,
                widget,
            )
        )
        editor_widget.cursorPositionChanged.connect(
            lambda file_path=opened_result.tab.file_path, widget=editor_widget: self._handle_editor_cursor_position_changed(
                file_path,
                widget,
            )
        )
        self._editor_widgets_by_path[opened_result.tab.file_path] = editor_widget

        tab_index = self._editor_tabs_widget.addTab(editor_widget, opened_result.tab.display_name)
        self._editor_tabs_widget.setTabToolTip(tab_index, opened_result.tab.file_path)
        self._editor_tabs_widget.setCurrentIndex(tab_index)
        self._maybe_restore_draft(opened_result.tab, editor_widget)
        self._handle_editor_tab_changed(tab_index)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(opened_result.tab.file_path)
        return True

    def _tab_index_for_path(self, file_path: str) -> int:
        if self._editor_tabs_widget is None:
            return -1

        normalized_path = str(Path(file_path).expanduser().resolve())
        for index in range(self._editor_tabs_widget.count()):
            if self._editor_tabs_widget.tabToolTip(index) == normalized_path:
                return index
        return -1

    def _handle_editor_text_changed(self, file_path: str, editor_widget: QPlainTextEdit) -> None:
        tab_state = self._editor_manager.update_tab_content(file_path, editor_widget.toPlainText())
        if self._editor_tabs_widget is None:
            return

        tab_index = self._tab_index_for_path(tab_state.file_path)
        if tab_index < 0:
            return
        suffix = " *" if tab_state.is_dirty else ""
        self._editor_tabs_widget.setTabText(tab_index, f"{tab_state.display_name}{suffix}")
        if tab_state.is_dirty:
            self._autosave_store.save_draft(tab_state.file_path, tab_state.current_content)
        else:
            self._autosave_store.delete_draft(tab_state.file_path)
        self._refresh_save_action_states()
        self._update_editor_status_for_path(tab_state.file_path)

    def _handle_editor_cursor_position_changed(self, file_path: str, editor_widget: QPlainTextEdit) -> None:
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
        self._editor_widgets_by_path.clear()
        self._editor_manager = EditorManager()
        self._refresh_save_action_states()
        if self._status_controller is not None:
            self._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)

    def _maybe_restore_draft(self, tab_state: EditorTabState, editor_widget: QPlainTextEdit) -> None:
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
        self._autosave_store.save_draft(updated_tab.file_path, updated_tab.current_content)
