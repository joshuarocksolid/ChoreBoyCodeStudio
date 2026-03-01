"""Main Qt shell for T05.

T05 scope guardrails:
- This is a composition shell only.
- It provides placeholder regions and startup visibility.
- It does not implement project-open, tab editing, run control, or persistence flows.
"""

from __future__ import annotations

from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QMainWindow, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app.core.models import CapabilityProbeReport
from app.shell.menus import MenuStubRegistry, build_menu_stubs
from app.shell.status_bar import ShellStatusBarController, create_shell_status_bar


class MainWindow(QMainWindow):
    """Top-level editor window shell with extension seams for later tasks."""

    def __init__(self, startup_report: Optional[CapabilityProbeReport] = None) -> None:
        super().__init__()
        self._project_placeholder_label: QLabel | None = None
        self._menu_registry: MenuStubRegistry | None = None
        self._status_controller: ShellStatusBarController | None = None

        self._configure_window_frame()
        self._build_layout_shell()
        self._menu_registry = build_menu_stubs(self)
        self._status_controller = create_shell_status_bar(self, startup_report=startup_report)

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
        panel = self._create_placeholder_panel(
            title="Project",
            body=(
                "Project panel placeholder.\n"
                "Open/load flows and tree wiring are introduced in T09/T10."
            ),
            object_name="shell.leftRegion",
        )
        self._project_placeholder_label = panel.findChild(QLabel, "shell.leftRegion.body")
        return panel

    def _build_center_panel(self) -> QWidget:
        return self._create_placeholder_panel(
            title="Editor",
            body=(
                "Editor area placeholder.\n"
                "Tabbed editing and file open behavior arrive in later tasks."
            ),
            object_name="shell.centerRegion",
        )

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
