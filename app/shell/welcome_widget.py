"""Welcome screen shown in the center panel when no project is loaded."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class WelcomeWidget(QWidget):
    """Landing page with New/Open buttons and a searchable project history."""

    new_project_requested = Signal()
    open_project_requested = Signal()
    project_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.welcome")
        self._all_projects: list[str] = []
        self._build_ui()
        self._apply_filter("")

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Centering container so content doesn't stretch to full width
        container = QWidget(self)
        container.setObjectName("shell.welcome.container")
        container.setMaximumWidth(560)
        container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 48, 32, 32)
        layout.setSpacing(0)

        # -- Header -----------------------------------------------------------
        title = QLabel("ChoreBoy Code Studio", container)
        title.setObjectName("shell.welcome.title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Open a project to get started", container)
        subtitle.setObjectName("shell.welcome.subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(28)

        # -- Action buttons ---------------------------------------------------
        btn_row = QWidget(container)
        btn_row.setObjectName("shell.welcome.btnRow")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(12)

        self._new_project_btn = QPushButton("New Project", btn_row)
        self._new_project_btn.setObjectName("shell.welcome.newProjectBtn")
        self._new_project_btn.setCursor(Qt.PointingHandCursor)
        self._new_project_btn.clicked.connect(self.new_project_requested.emit)
        btn_layout.addWidget(self._new_project_btn)

        self._open_project_btn = QPushButton("Open Project", btn_row)
        self._open_project_btn.setObjectName("shell.welcome.openProjectBtn")
        self._open_project_btn.setCursor(Qt.PointingHandCursor)
        self._open_project_btn.clicked.connect(self.open_project_requested.emit)
        btn_layout.addWidget(self._open_project_btn)

        layout.addWidget(btn_row, 0, Qt.AlignCenter)
        layout.addSpacing(24)

        # -- Search bar -------------------------------------------------------
        self._search_input = QLineEdit(container)
        self._search_input.setObjectName("shell.welcome.searchInput")
        self._search_input.setPlaceholderText("Search projects\u2026")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_input)
        layout.addSpacing(8)

        # -- Recent projects header -------------------------------------------
        recent_label = QLabel("Recent Projects", container)
        recent_label.setObjectName("shell.welcome.recentLabel")
        layout.addWidget(recent_label)
        layout.addSpacing(4)

        # -- Project list -----------------------------------------------------
        self._project_list = QListWidget(container)
        self._project_list.setObjectName("shell.welcome.projectList")
        self._project_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._project_list.itemDoubleClicked.connect(self._handle_item_double_clicked)
        self._project_list.itemActivated.connect(self._handle_item_activated)
        layout.addWidget(self._project_list, 1)

        # -- Empty state (hidden when list is populated) ----------------------
        self._empty_label = QLabel(
            "No projects yet. Create or open one above.", container,
        )
        self._empty_label.setObjectName("shell.welcome.emptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label, 1)

        outer.addWidget(container, 1, Qt.AlignHCenter)

    # -- Public API -----------------------------------------------------------

    def set_recent_projects(self, project_paths: list[str]) -> None:
        """Populate the project list from an ordered list of paths."""
        self._all_projects = list(project_paths)
        self._apply_filter(self._search_input.text())

    # -- Internal -------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        filtered = [
            p for p in self._all_projects if query in p.lower()
        ] if query else list(self._all_projects)

        self._project_list.clear()
        for project_path in filtered:
            leaf = Path(project_path).name or project_path
            item = QListWidgetItem(f"{leaf}\n{project_path}")
            item.setData(Qt.UserRole, project_path)
            item.setToolTip(project_path)
            self._project_list.addItem(item)

        has_items = self._project_list.count() > 0
        self._project_list.setVisible(has_items)
        self._empty_label.setVisible(not has_items)

    def _handle_item_double_clicked(self, item: QListWidgetItem) -> None:
        project_path = item.data(Qt.UserRole)
        if project_path:
            self.project_selected.emit(project_path)

    def _handle_item_activated(self, item: QListWidgetItem) -> None:
        project_path = item.data(Qt.UserRole)
        if project_path:
            self.project_selected.emit(project_path)
