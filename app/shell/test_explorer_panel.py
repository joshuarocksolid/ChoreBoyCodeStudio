"""Test explorer panel for browsing and running discovered tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QAction,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.run.test_discovery_service import DiscoveredTestNode, DiscoveryResult


_ROLE_NODE_ID = Qt.UserRole + 1
_ROLE_FILE_PATH = Qt.UserRole + 2
_ROLE_LINE_NUMBER = Qt.UserRole + 3
_ROLE_KIND = Qt.UserRole + 4

_OUTCOME_ICONS = {
    "passed": "✓",
    "failed": "✗",
    "skipped": "○",
    "error": "⚠",
    "not_run": "·",
}


class TestExplorerPanel(QWidget):
    """Tree-based test explorer showing discovered tests with run/debug actions."""

    run_test_requested: Any = Signal(str)  # node_id
    debug_test_requested: Any = Signal(str)  # node_id
    run_all_requested: Any = Signal()
    run_failed_requested: Any = Signal()
    navigate_to_test: Any = Signal(str, int)  # file_path, line_number

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.testExplorer")
        self._outcomes: dict[str, str] = {}  # node_id -> outcome
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)
        toolbar.setSpacing(4)

        title = QLabel("Tests")
        title.setObjectName("shell.testExplorer.title")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self._run_all_btn = QPushButton("Run All")
        self._run_all_btn.setObjectName("shell.testExplorer.runAll")
        self._run_all_btn.clicked.connect(self.run_all_requested.emit)
        toolbar.addWidget(self._run_all_btn)

        self._run_failed_btn = QPushButton("Rerun Failed")
        self._run_failed_btn.setObjectName("shell.testExplorer.runFailed")
        self._run_failed_btn.clicked.connect(self.run_failed_requested.emit)
        self._run_failed_btn.setEnabled(False)
        toolbar.addWidget(self._run_failed_btn)

        layout.addLayout(toolbar)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Test", "Status"])
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemDoubleClicked.connect(self._handle_double_click)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        layout.addWidget(self._tree, stretch=1)

        # Status
        self._status_label = QLabel("No tests discovered")
        self._status_label.setObjectName("shell.testExplorer.status")
        self._status_label.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._status_label)

    def update_discovery(self, result: DiscoveryResult) -> None:
        """Populate the tree from a discovery result."""
        self._tree.clear()
        if not result.succeeded:
            self._status_label.setText(f"Discovery error: {result.error_message}")
            self._run_failed_btn.setEnabled(False)
            return

        item_map: dict[str, QTreeWidgetItem] = {}

        for node in result.nodes:
            item = QTreeWidgetItem()
            item.setText(0, node.name)
            item.setData(0, _ROLE_NODE_ID, node.node_id)
            item.setData(0, _ROLE_FILE_PATH, node.file_path)
            item.setData(0, _ROLE_LINE_NUMBER, node.line_number)
            item.setData(0, _ROLE_KIND, node.kind)

            outcome = self._outcomes.get(node.node_id, "not_run")
            item.setText(1, _OUTCOME_ICONS.get(outcome, "·"))

            if node.parent_id and node.parent_id in item_map:
                item_map[node.parent_id].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            item_map[node.node_id] = item

        # Expand file nodes
        for i in range(self._tree.topLevelItemCount()):
            self._tree.topLevelItem(i).setExpanded(True)

        total = len(result.function_nodes())
        self._status_label.setText(f"{total} test(s) discovered")
        self._run_failed_btn.setEnabled(any(v == "failed" for v in self._outcomes.values()))

    def update_outcomes(self, outcomes: dict[str, str]) -> None:
        """Update per-test outcome indicators."""
        self._outcomes.update(outcomes)
        self._update_outcome_display()
        has_failures = any(v == "failed" for v in self._outcomes.values())
        self._run_failed_btn.setEnabled(has_failures)

    def set_outcomes(self, outcomes: dict[str, str]) -> None:
        """Replace all tracked outcomes and refresh indicator state."""
        self._outcomes = dict(outcomes)
        self._update_outcome_display()
        self._run_failed_btn.setEnabled(any(v == "failed" for v in self._outcomes.values()))

    def failed_node_ids(self) -> list[str]:
        """Return node IDs of tests that last failed."""
        return [nid for nid, outcome in self._outcomes.items() if outcome == "failed"]

    def _update_outcome_display(self) -> None:
        """Refresh status column for all visible items."""
        for i in range(self._tree.topLevelItemCount()):
            self._refresh_item_outcome(self._tree.topLevelItem(i))

    def _refresh_item_outcome(self, item: QTreeWidgetItem) -> None:
        node_id = item.data(0, _ROLE_NODE_ID)
        if node_id and node_id in self._outcomes:
            item.setText(1, _OUTCOME_ICONS.get(self._outcomes[node_id], "·"))
        for i in range(item.childCount()):
            self._refresh_item_outcome(item.child(i))

    def _show_context_menu(self, position) -> None:
        item = self._tree.itemAt(position)
        if item is None:
            return
        node_id = item.data(0, _ROLE_NODE_ID)
        kind = item.data(0, _ROLE_KIND)
        if not node_id:
            return

        menu = QMenu(self)
        run_action = menu.addAction(f"Run {kind.title()}")
        debug_action = menu.addAction(f"Debug {kind.title()}")
        chosen = menu.exec_(self._tree.viewport().mapToGlobal(position))
        if chosen == run_action:
            self.run_test_requested.emit(node_id)
        elif chosen == debug_action:
            self.debug_test_requested.emit(node_id)

    def _handle_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER) or 0
        if file_path:
            self.navigate_to_test.emit(file_path, int(line_number))
