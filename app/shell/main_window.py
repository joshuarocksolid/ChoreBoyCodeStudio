"""Main Qt shell composition and top-level workflow wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QFileDialog,
    QLabel,
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
from app.project.project_tree import ProjectTreeNode, build_project_tree
from app.project.project_service import open_project_and_track_recent
from app.project.recent_projects import load_recent_projects
from app.shell.menus import MenuCallbacks, MenuStubRegistry, build_menu_stubs, build_recent_project_menu_items
from app.shell.status_bar import ShellStatusBarController, create_shell_status_bar


class MainWindow(QMainWindow):
    """Top-level editor window shell with extension seams for later tasks."""

    def __init__(self, startup_report: Optional[CapabilityProbeReport] = None, state_root: str | None = None) -> None:
        super().__init__()
        self._project_placeholder_label: QLabel | None = None
        self._project_tree_widget: QTreeWidget | None = None
        self._editor_tabs_widget: QTabWidget | None = None
        self._menu_registry: MenuStubRegistry | None = None
        self._status_controller: ShellStatusBarController | None = None
        self._state_root = state_root
        self._loaded_project: LoadedProject | None = None
        self._editor_manager = EditorManager()
        self._editor_widgets_by_path: dict[str, QPlainTextEdit] = {}
        self._logger = get_subsystem_logger("shell")

        self._configure_window_frame()
        self._build_layout_shell()
        self._menu_registry = build_menu_stubs(
            self,
            callbacks=MenuCallbacks(
                on_open_project=self._handle_open_project_action,
                on_file_menu_about_to_show=self._refresh_open_recent_menu,
            ),
        )
        self._status_controller = create_shell_status_bar(self, startup_report=startup_report)
        self._refresh_open_recent_menu()

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

    def _open_project_by_path(self, project_root: str) -> bool:
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
        tabs.addTab(
            self._create_placeholder_panel(
                title="Console",
                body="Console stream placeholder (runner output wiring arrives in T19).",
                object_name="shell.bottom.console",
            ),
            "Console",
        )
        tabs.addTab(
            self._create_placeholder_panel(
                title="Problems",
                body="Problems pane placeholder (error summary wiring arrives in T21).",
                object_name="shell.bottom.problems",
            ),
            "Problems",
        )
        tabs.addTab(
            self._create_placeholder_panel(
                title="Run Log",
                body="Run log placeholder (per-run persistence wiring arrives in T20).",
                object_name="shell.bottom.runLog",
            ),
            "Run Log",
        )
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
        item.setData(0, Qt.UserRole, node.absolute_path)
        item.setData(0, Qt.UserRole + 1, node.is_directory)
        item.setData(0, Qt.UserRole + 2, node.relative_path)

        for child_node in node.children:
            item.addChild(self._build_tree_item(child_node))
        return item

    def _handle_project_tree_item_activation(self, item: QTreeWidgetItem, _column: int) -> None:
        is_directory = bool(item.data(0, Qt.UserRole + 1))
        absolute_path = item.data(0, Qt.UserRole)
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
        self._editor_widgets_by_path[opened_result.tab.file_path] = editor_widget

        tab_index = self._editor_tabs_widget.addTab(editor_widget, opened_result.tab.display_name)
        self._editor_tabs_widget.setTabToolTip(tab_index, opened_result.tab.file_path)
        self._editor_tabs_widget.setCurrentIndex(tab_index)
        self._handle_editor_tab_changed(tab_index)
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

    def _handle_editor_tab_changed(self, tab_index: int) -> None:
        if tab_index < 0 or self._editor_tabs_widget is None:
            return

        tab_path = self._editor_tabs_widget.tabToolTip(tab_index)
        if not tab_path:
            return
        self._editor_manager.set_active_file(tab_path)
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return
        if self._status_controller is not None:
            self._status_controller.set_project_state_text(
                f"Project: {self._loaded_project.metadata.name if self._loaded_project else 'none'} | "
                f"File: {active_tab.display_name}"
            )

    def _reset_editor_tabs(self) -> None:
        if self._editor_tabs_widget is not None:
            self._editor_tabs_widget.clear()
        self._editor_widgets_by_path.clear()
        self._editor_manager = EditorManager()
