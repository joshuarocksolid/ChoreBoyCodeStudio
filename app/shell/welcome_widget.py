"""Welcome screen shown in the center panel when no project is loaded."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

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

    new_project_requested: Any = Signal()
    open_project_requested: Any = Signal()
    project_selected: Any = Signal(str)
    runtime_center_requested: Any = Signal()
    getting_started_requested: Any = Signal()
    project_health_requested: Any = Signal()
    example_project_requested: Any = Signal()
    headless_notes_requested: Any = Signal()
    dismiss_onboarding_requested: Any = Signal()
    complete_onboarding_requested: Any = Signal()

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

        self._onboarding_card = QWidget(container)
        self._onboarding_card.setObjectName("shell.welcome.onboardingCard")
        onboarding_layout = QVBoxLayout(self._onboarding_card)
        onboarding_layout.setContentsMargins(16, 16, 16, 16)
        onboarding_layout.setSpacing(8)

        onboarding_title = QLabel("First Run Checklist", self._onboarding_card)
        onboarding_title.setObjectName("shell.welcome.onboardingTitle")
        onboarding_layout.addWidget(onboarding_title)

        self._runtime_summary_label = QLabel(
            "Runtime summary: startup capability data is unavailable.",
            self._onboarding_card,
        )
        self._runtime_summary_label.setObjectName("shell.welcome.onboardingRuntimeSummary")
        self._runtime_summary_label.setWordWrap(True)
        onboarding_layout.addWidget(self._runtime_summary_label)

        checklist_label = QLabel(
            (
                "<b>Suggested order:</b><br>"
                "1. Review Runtime Center readiness.<br>"
                "2. Read Getting Started for the basic run/edit flow.<br>"
                "3. Try an example project before changing your own code.<br>"
                "4. Keep Headless Notes handy if your code touches FreeCAD GUI APIs."
            ),
            self._onboarding_card,
        )
        checklist_label.setObjectName("shell.welcome.onboardingChecklist")
        checklist_label.setWordWrap(True)
        onboarding_layout.addWidget(checklist_label)

        action_row_one = QWidget(self._onboarding_card)
        action_row_one.setObjectName("shell.welcome.onboardingActionRow")
        action_row_one_layout = QHBoxLayout(action_row_one)
        action_row_one_layout.setContentsMargins(0, 0, 0, 0)
        action_row_one_layout.setSpacing(8)

        self._runtime_center_btn = QPushButton("Runtime Center", action_row_one)
        self._runtime_center_btn.setObjectName("shell.welcome.onboardingActionBtn")
        self._runtime_center_btn.clicked.connect(self.runtime_center_requested.emit)
        action_row_one_layout.addWidget(self._runtime_center_btn)

        self._getting_started_btn = QPushButton("Getting Started", action_row_one)
        self._getting_started_btn.setObjectName("shell.welcome.onboardingActionBtn")
        self._getting_started_btn.clicked.connect(self.getting_started_requested.emit)
        action_row_one_layout.addWidget(self._getting_started_btn)

        self._project_health_btn = QPushButton("Project Health", action_row_one)
        self._project_health_btn.setObjectName("shell.welcome.onboardingActionBtn")
        self._project_health_btn.clicked.connect(self.project_health_requested.emit)
        self._project_health_btn.setEnabled(False)
        self._project_health_btn.setToolTip("Open a project to enable Project Health Check.")
        action_row_one_layout.addWidget(self._project_health_btn)

        onboarding_layout.addWidget(action_row_one)

        action_row_two = QWidget(self._onboarding_card)
        action_row_two.setObjectName("shell.welcome.onboardingActionRow")
        action_row_two_layout = QHBoxLayout(action_row_two)
        action_row_two_layout.setContentsMargins(0, 0, 0, 0)
        action_row_two_layout.setSpacing(8)

        self._example_project_btn = QPushButton("Example Project", action_row_two)
        self._example_project_btn.setObjectName("shell.welcome.onboardingActionBtn")
        self._example_project_btn.clicked.connect(self.example_project_requested.emit)
        action_row_two_layout.addWidget(self._example_project_btn)

        self._headless_notes_btn = QPushButton("Headless Notes", action_row_two)
        self._headless_notes_btn.setObjectName("shell.welcome.onboardingActionBtn")
        self._headless_notes_btn.clicked.connect(self.headless_notes_requested.emit)
        action_row_two_layout.addWidget(self._headless_notes_btn)

        action_row_two_layout.addStretch(1)
        onboarding_layout.addWidget(action_row_two)

        reminder_label = QLabel(
            "You can reopen this checklist later from Help > Runtime Onboarding.",
            self._onboarding_card,
        )
        reminder_label.setObjectName("shell.welcome.onboardingReminder")
        reminder_label.setWordWrap(True)
        onboarding_layout.addWidget(reminder_label)

        state_row = QWidget(self._onboarding_card)
        state_row.setObjectName("shell.welcome.onboardingStateRow")
        state_row_layout = QHBoxLayout(state_row)
        state_row_layout.setContentsMargins(0, 0, 0, 0)
        state_row_layout.setSpacing(8)

        self._dismiss_onboarding_btn = QPushButton("Hide Checklist", state_row)
        self._dismiss_onboarding_btn.setObjectName("shell.welcome.onboardingSecondaryBtn")
        self._dismiss_onboarding_btn.clicked.connect(self.dismiss_onboarding_requested.emit)
        state_row_layout.addWidget(self._dismiss_onboarding_btn)

        self._complete_onboarding_btn = QPushButton("Mark Checklist Done", state_row)
        self._complete_onboarding_btn.setObjectName("shell.welcome.onboardingPrimaryBtn")
        self._complete_onboarding_btn.clicked.connect(self.complete_onboarding_requested.emit)
        state_row_layout.addWidget(self._complete_onboarding_btn)

        state_row_layout.addStretch(1)
        onboarding_layout.addWidget(state_row)

        layout.addWidget(self._onboarding_card)
        layout.addSpacing(20)

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
        self.set_onboarding_visible(False)

    # -- Public API -----------------------------------------------------------

    def set_recent_projects(self, project_paths: list[str]) -> None:
        """Populate the project list from an ordered list of paths."""
        self._all_projects = list(project_paths)
        self._apply_filter(self._search_input.text())

    def set_runtime_summary(self, summary: str, details: str = "") -> None:
        self._runtime_summary_label.setText(summary)
        self._runtime_summary_label.setToolTip(details or summary)

    def set_onboarding_visible(self, is_visible: bool) -> None:
        self._onboarding_card.setVisible(is_visible)

    def set_project_health_available(self, is_available: bool) -> None:
        self._project_health_btn.setEnabled(is_available)
        if is_available:
            self._project_health_btn.setToolTip("Run project diagnostics and open Runtime Center.")
            return
        self._project_health_btn.setToolTip("Open a project to enable Project Health Check.")

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
