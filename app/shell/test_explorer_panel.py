"""Test explorer panel for browsing and running discovered tests."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide2.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QSizePolicy,
    QStackedLayout,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.run.pytest_discovery_service import DiscoveredTestNode, DiscoveryResult

if TYPE_CHECKING:
    from app.shell.theme_tokens import ShellThemeTokens


_ROLE_NODE_ID = Qt.UserRole + 1
_ROLE_FILE_PATH = Qt.UserRole + 2
_ROLE_LINE_NUMBER = Qt.UserRole + 3
_ROLE_KIND = Qt.UserRole + 4
_ROLE_OUTCOME = Qt.UserRole + 5

# ---------------------------------------------------------------------------
# Painted outcome icons
# ---------------------------------------------------------------------------

_OUTCOME_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def _make_passed_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.setPen(QPen(QColor("#FFFFFF"), 1.6))
    p.drawLine(4, 7, 6, 10)
    p.drawLine(6, 10, 10, 4)
    p.end()
    return QIcon(px)


def _make_failed_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.setPen(QPen(QColor("#FFFFFF"), 1.6))
    p.drawLine(4, 4, 10, 10)
    p.drawLine(10, 4, 4, 10)
    p.end()
    return QIcon(px)


def _make_skipped_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    c.setAlpha(180)
    p.setPen(QPen(c, 1.4))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(2, 2, 10, 10)
    p.drawLine(5, 7, 9, 7)
    p.end()
    return QIcon(px)


def _make_error_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    from PySide2.QtCore import QPoint
    from PySide2.QtGui import QPolygon
    tri = QPolygon()
    tri.append(QPoint(7, 1))
    tri.append(QPoint(13, 13))
    tri.append(QPoint(1, 13))
    p.drawPolygon(tri)
    p.setPen(QPen(QColor("#FFFFFF"), 1.4))
    p.drawLine(7, 5, 7, 9)
    p.drawPoint(7, 11)
    p.end()
    return QIcon(px)


def _make_not_run_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    c.setAlpha(120)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 6, 6)
    p.end()
    return QIcon(px)


_OUTCOME_BUILDERS = {
    "passed": _make_passed_icon,
    "failed": _make_failed_icon,
    "skipped": _make_skipped_icon,
    "error": _make_error_icon,
    "not_run": _make_not_run_icon,
}


def outcome_icon(outcome: str, color_hex: str) -> QIcon:
    key = (outcome, color_hex)
    cached = _OUTCOME_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    builder = _OUTCOME_BUILDERS.get(outcome, _make_not_run_icon)
    icon = builder(color_hex)
    _OUTCOME_ICON_CACHE[key] = icon
    return icon


# ---------------------------------------------------------------------------
# Painted node-kind icons
# ---------------------------------------------------------------------------

_KIND_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def _make_file_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    c.setAlpha(180)
    p.setPen(QPen(c, 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(2, 1, 10, 12, 2, 2)
    p.drawLine(2, 5, 12, 5)
    p.end()
    return QIcon(px)


def _make_class_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(1, 2, 12, 10, 2, 2)
    f = QFont()
    f.setPixelSize(9)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(px.rect(), Qt.AlignCenter, "C")
    p.end()
    return QIcon(px)


def _make_function_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(1, 2, 12, 10, 2, 2)
    f = QFont()
    f.setPixelSize(9)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(px.rect(), Qt.AlignCenter, "f")
    p.end()
    return QIcon(px)


_KIND_BUILDERS = {
    "file": _make_file_icon,
    "class": _make_class_icon,
    "function": _make_function_icon,
}


def kind_icon(kind: str, color_hex: str) -> QIcon:
    key = (kind, color_hex)
    cached = _KIND_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    builder = _KIND_BUILDERS.get(kind, _make_file_icon)
    icon = builder(color_hex)
    _KIND_ICON_CACHE[key] = icon
    return icon


# ---------------------------------------------------------------------------
# Painted toolbar action icons
# ---------------------------------------------------------------------------

_ACTION_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def clear_icon_caches() -> None:
    """Release all cached QIcon objects so Shiboken can tear down cleanly."""
    _OUTCOME_ICON_CACHE.clear()
    _KIND_ICON_CACHE.clear()
    _ACTION_ICON_CACHE.clear()


def _make_play_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    from PySide2.QtCore import QPoint
    from PySide2.QtGui import QPolygon
    tri = QPolygon()
    tri.append(QPoint(3, 2))
    tri.append(QPoint(12, 7))
    tri.append(QPoint(3, 12))
    p.drawPolygon(tri)
    p.end()
    return QIcon(px)


def _make_rerun_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color_hex), 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(2, 2, 10, 10, 30 * 16, 300 * 16)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    from PySide2.QtCore import QPoint
    from PySide2.QtGui import QPolygon
    arrow = QPolygon()
    arrow.append(QPoint(9, 1))
    arrow.append(QPoint(12, 4))
    arrow.append(QPoint(8, 5))
    p.drawPolygon(arrow)
    p.end()
    return QIcon(px)


def _make_refresh_icon(color_hex: str) -> QIcon:
    px = QPixmap(14, 14)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color_hex), 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(2, 2, 10, 10, 60 * 16, 240 * 16)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    from PySide2.QtCore import QPoint
    from PySide2.QtGui import QPolygon
    arrow = QPolygon()
    arrow.append(QPoint(10, 2))
    arrow.append(QPoint(13, 5))
    arrow.append(QPoint(9, 5))
    p.drawPolygon(arrow)
    p.end()
    return QIcon(px)


def _action_icon(name: str, color_hex: str) -> QIcon:
    key = (name, color_hex)
    cached = _ACTION_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    builders = {"play": _make_play_icon, "rerun": _make_rerun_icon, "refresh": _make_refresh_icon}
    icon = builders.get(name, _make_play_icon)(color_hex)
    _ACTION_ICON_CACHE[key] = icon
    return icon


# ---------------------------------------------------------------------------
# Outcome filter toggle
# ---------------------------------------------------------------------------

_OUTCOME_ICONS_TEXT = {
    "passed": "\u2713",
    "failed": "\u2717",
    "skipped": "\u25CB",
    "error": "\u26A0",
    "not_run": "\u00B7",
}


class _OutcomeFilterToggle(QToolButton):
    """Small toggle showing outcome label + count badge."""

    def __init__(self, label: str, object_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._base_label = label
        self._count = 0
        self.setObjectName(object_name)
        self.setCheckable(True)
        self.setChecked(True)
        self.setAutoRaise(True)
        self._refresh_text()

    def set_count(self, count: int) -> None:
        self._count = count
        self._refresh_text()

    def count(self) -> int:
        return self._count

    def _refresh_text(self) -> None:
        self.setText(f"{self._base_label}: {self._count}")


# ---------------------------------------------------------------------------
# TestExplorerPanel
# ---------------------------------------------------------------------------


class TestExplorerPanel(QWidget):
    """Tree-based test explorer showing discovered tests with run/debug actions."""

    run_test_requested: Any = Signal(str)
    debug_test_requested: Any = Signal(str)
    run_all_requested: Any = Signal()
    run_failed_requested: Any = Signal()
    debug_failed_requested: Any = Signal()
    refresh_requested: Any = Signal()
    navigate_to_test: Any = Signal(str, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.testExplorer")
        self._outcomes: dict[str, str] = {}
        self._discovery_count = 0
        self._is_running = False

        self._outcome_colors: dict[str, str] = {
            "passed": "#3FB950",
            "failed": "#FF6B6B",
            "skipped": "#ADB5BD",
            "error": "#E5A100",
            "not_run": "#6C757D",
        }
        self._kind_color = "#5B8CFF"
        self._action_color = "#CED4DA"

        self._build_ui()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- action toolbar --
        self._toolbar = QWidget(self)
        self._toolbar.setObjectName("shell.testExplorer.toolbar")
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(6, 4, 6, 4)
        tb_layout.setSpacing(4)

        title = QLabel("Tests")
        title.setObjectName("shell.testExplorer.title")
        tb_layout.addWidget(title)
        tb_layout.addStretch()

        self._refresh_btn = QToolButton()
        self._refresh_btn.setObjectName("shell.testExplorer.refreshBtn")
        self._refresh_btn.setIcon(_action_icon("refresh", self._action_color))
        self._refresh_btn.setToolTip("Refresh test discovery")
        self._refresh_btn.setAutoRaise(True)
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        tb_layout.addWidget(self._refresh_btn)

        self._run_all_btn = QToolButton()
        self._run_all_btn.setObjectName("shell.testExplorer.runAllBtn")
        self._run_all_btn.setIcon(_action_icon("play", self._action_color))
        self._run_all_btn.setText("Run All")
        self._run_all_btn.setToolTip("Run all discovered tests")
        self._run_all_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._run_all_btn.setAutoRaise(True)
        self._run_all_btn.clicked.connect(self.run_all_requested.emit)
        tb_layout.addWidget(self._run_all_btn)

        self._run_failed_btn = QToolButton()
        self._run_failed_btn.setObjectName("shell.testExplorer.runFailedBtn")
        self._run_failed_btn.setIcon(_action_icon("rerun", self._action_color))
        self._run_failed_btn.setText("Rerun Failed")
        self._run_failed_btn.setToolTip("Rerun only failed tests")
        self._run_failed_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._run_failed_btn.setAutoRaise(True)
        self._run_failed_btn.setEnabled(False)
        self._run_failed_btn.clicked.connect(self.run_failed_requested.emit)
        tb_layout.addWidget(self._run_failed_btn)

        self._debug_failed_btn = QToolButton()
        self._debug_failed_btn.setObjectName("shell.testExplorer.debugFailedBtn")
        self._debug_failed_btn.setIcon(_action_icon("rerun", self._action_color))
        self._debug_failed_btn.setText("Debug Failed")
        self._debug_failed_btn.setToolTip("Debug the first failed test")
        self._debug_failed_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._debug_failed_btn.setAutoRaise(True)
        self._debug_failed_btn.setEnabled(False)
        self._debug_failed_btn.clicked.connect(self.debug_failed_requested.emit)
        tb_layout.addWidget(self._debug_failed_btn)

        root.addWidget(self._toolbar)

        # -- filter toolbar --
        self._filter_bar = QWidget(self)
        self._filter_bar.setObjectName("shell.testExplorer.filterBar")
        fb_layout = QHBoxLayout(self._filter_bar)
        fb_layout.setContentsMargins(6, 2, 6, 2)
        fb_layout.setSpacing(6)
        fb_layout.addStretch()

        self._passed_toggle = _OutcomeFilterToggle("Passed", "shell.testExplorer.filterPassed", self._filter_bar)
        self._passed_toggle.toggled.connect(self._on_filter_changed)
        fb_layout.addWidget(self._passed_toggle)

        self._failed_toggle = _OutcomeFilterToggle("Failed", "shell.testExplorer.filterFailed", self._filter_bar)
        self._failed_toggle.toggled.connect(self._on_filter_changed)
        fb_layout.addWidget(self._failed_toggle)

        self._skipped_toggle = _OutcomeFilterToggle("Skipped", "shell.testExplorer.filterSkipped", self._filter_bar)
        self._skipped_toggle.toggled.connect(self._on_filter_changed)
        fb_layout.addWidget(self._skipped_toggle)

        self._error_toggle = _OutcomeFilterToggle("Errors", "shell.testExplorer.filterErrors", self._filter_bar)
        self._error_toggle.toggled.connect(self._on_filter_changed)
        fb_layout.addWidget(self._error_toggle)

        self._filter_bar.setVisible(False)
        root.addWidget(self._filter_bar)

        # -- stacked content area (tree vs empty label) --
        self._stack_container = QWidget(self)
        self._stack_layout = QStackedLayout(self._stack_container)
        self._stack_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget(self._stack_container)
        self._tree.setObjectName("shell.testExplorer.tree")
        self._tree.setHeaderLabels(["Test", "Status"])
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemDoubleClicked.connect(self._handle_double_click)
        self._tree.itemClicked.connect(self._handle_single_click)
        self._tree.setAlternatingRowColors(False)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.setExpandsOnDoubleClick(False)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 32)

        self._stack_layout.addWidget(self._tree)

        self._empty_label = QLabel("No tests discovered")
        self._empty_label.setObjectName("shell.testExplorer.emptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._stack_layout.addWidget(self._empty_label)

        self._stack_layout.setCurrentWidget(self._empty_label)
        root.addWidget(self._stack_container, 1)

        # -- summary status bar --
        self._status_bar = QWidget(self)
        self._status_bar.setObjectName("shell.testExplorer.statusBar")
        sb_layout = QHBoxLayout(self._status_bar)
        sb_layout.setContentsMargins(6, 3, 6, 3)
        sb_layout.setSpacing(6)

        self._status_dot = QLabel()
        self._status_dot.setObjectName("shell.testExplorer.statusDot")
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.setProperty("testState", "idle")
        sb_layout.addWidget(self._status_dot)

        self._status_text = QLabel("No tests discovered")
        self._status_text.setObjectName("shell.testExplorer.statusText")
        sb_layout.addWidget(self._status_text)

        sb_layout.addStretch()

        self._count_passed = QLabel()
        self._count_passed.setObjectName("shell.testExplorer.countPassed")
        self._count_passed.setVisible(False)
        sb_layout.addWidget(self._count_passed)

        self._count_failed = QLabel()
        self._count_failed.setObjectName("shell.testExplorer.countFailed")
        self._count_failed.setVisible(False)
        sb_layout.addWidget(self._count_failed)

        self._count_skipped = QLabel()
        self._count_skipped.setObjectName("shell.testExplorer.countSkipped")
        self._count_skipped.setVisible(False)
        sb_layout.addWidget(self._count_skipped)

        root.addWidget(self._status_bar)

    # -- theme integration --------------------------------------------------

    def apply_theme(self, tokens: "ShellThemeTokens") -> None:
        _OUTCOME_ICON_CACHE.clear()
        _KIND_ICON_CACHE.clear()
        _ACTION_ICON_CACHE.clear()

        self._outcome_colors = {
            "passed": tokens.test_passed_color or tokens.debug_running_color,
            "failed": tokens.diag_error_color,
            "skipped": tokens.text_muted,
            "error": tokens.diag_warning_color,
            "not_run": tokens.text_muted,
        }
        self._kind_color = tokens.accent
        self._action_color = tokens.icon_primary

        self._refresh_btn.setIcon(_action_icon("refresh", self._action_color))
        self._run_all_btn.setIcon(_action_icon("play", self._action_color))
        self._run_failed_btn.setIcon(_action_icon("rerun", self._action_color))
        self._debug_failed_btn.setIcon(_action_icon("rerun", self._action_color))

        self._refresh_outcome_icons()
        self._refresh_summary_colors()

    # -- public API ---------------------------------------------------------

    def update_discovery(self, result: DiscoveryResult) -> None:
        """Populate the tree from a discovery result."""
        self._tree.clear()
        if not result.succeeded:
            self._empty_label.setText(f"Discovery failed: {result.error_message}")
            self._stack_layout.setCurrentWidget(self._empty_label)
            self._status_text.setText("Discovery error")
            self._set_status_dot_state("error")
            self._discovery_count = 0
            self._run_failed_btn.setEnabled(False)
            self._debug_failed_btn.setEnabled(False)
            self._filter_bar.setVisible(False)
            return

        item_map: dict[str, QTreeWidgetItem] = {}

        for node in result.nodes:
            item = QTreeWidgetItem()
            item.setText(0, node.name)
            item.setData(0, _ROLE_NODE_ID, node.node_id)
            item.setData(0, _ROLE_FILE_PATH, node.file_path)
            item.setData(0, _ROLE_LINE_NUMBER, node.line_number)
            item.setData(0, _ROLE_KIND, node.kind)

            item.setIcon(0, kind_icon(node.kind, self._kind_color))

            cur_outcome = self._outcomes.get(node.node_id, "not_run")
            item.setData(1, _ROLE_OUTCOME, cur_outcome)
            color = self._outcome_colors.get(cur_outcome, self._outcome_colors["not_run"])
            item.setIcon(1, outcome_icon(cur_outcome, color))
            item.setText(1, "")

            if node.parent_id and node.parent_id in item_map:
                item_map[node.parent_id].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            item_map[node.node_id] = item

        for i in range(self._tree.topLevelItemCount()):
            self._tree.topLevelItem(i).setExpanded(True)

        self._discovery_count = len(result.function_nodes())

        if self._discovery_count > 0:
            self._stack_layout.setCurrentWidget(self._tree)
        else:
            self._empty_label.setText("No tests found in this project")
            self._stack_layout.setCurrentWidget(self._empty_label)

        self._refresh_failed_action_states()
        self._refresh_filter_counts()
        self._apply_filters()
        self._refresh_summary()

    def update_outcomes(self, outcomes: dict[str, str]) -> None:
        """Update per-test outcome indicators."""
        self._outcomes.update(outcomes)
        self._refresh_outcome_icons()
        self._refresh_failed_action_states()
        self._refresh_filter_counts()
        self._apply_filters()
        self._refresh_summary()

    def set_outcomes(self, outcomes: dict[str, str]) -> None:
        """Replace all tracked outcomes and refresh indicator state."""
        self._outcomes = dict(outcomes)
        self._refresh_outcome_icons()
        self._refresh_failed_action_states()
        self._refresh_filter_counts()
        self._apply_filters()
        self._refresh_summary()

    def set_running(self, running: bool) -> None:
        """Toggle running-state visual feedback."""
        self._is_running = running
        self._run_all_btn.setEnabled(not running)
        self._refresh_failed_action_states()
        self._refresh_btn.setEnabled(not running)
        if running:
            self._set_status_dot_state("running")
            self._status_text.setText("Running\u2026")
        else:
            self._refresh_summary()

    def set_discovering(self, active: bool) -> None:
        """Show a discovering-in-progress state."""
        if active:
            self._empty_label.setText("Discovering tests\u2026")
            self._stack_layout.setCurrentWidget(self._empty_label)
            self._set_status_dot_state("running")
            self._status_text.setText("Discovering\u2026")
            self._refresh_btn.setEnabled(False)

    def failed_node_ids(self) -> list[str]:
        """Return node IDs of tests that last failed."""
        return [nid for nid, outcome in self._outcomes.items() if outcome == "failed"]

    # -- internal: icon / outcome refresh -----------------------------------

    def _refresh_failed_action_states(self) -> None:
        has_failed = any(v == "failed" for v in self._outcomes.values())
        enabled = not self._is_running and has_failed
        self._run_failed_btn.setEnabled(enabled)
        self._debug_failed_btn.setEnabled(enabled)

    def _refresh_outcome_icons(self) -> None:
        for i in range(self._tree.topLevelItemCount()):
            self._refresh_item_outcome(self._tree.topLevelItem(i))

    def _refresh_item_outcome(self, item: QTreeWidgetItem) -> None:
        node_id = item.data(0, _ROLE_NODE_ID)
        if node_id and node_id in self._outcomes:
            oc = self._outcomes[node_id]
            item.setData(1, _ROLE_OUTCOME, oc)
            color = self._outcome_colors.get(oc, self._outcome_colors["not_run"])
            item.setIcon(1, outcome_icon(oc, color))
        for i in range(item.childCount()):
            self._refresh_item_outcome(item.child(i))

    # -- internal: filter toggles -------------------------------------------

    def _refresh_filter_counts(self) -> None:
        counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
        for v in self._outcomes.values():
            if v in counts:
                counts[v] += 1
        self._passed_toggle.set_count(counts["passed"])
        self._failed_toggle.set_count(counts["failed"])
        self._skipped_toggle.set_count(counts["skipped"])
        self._error_toggle.set_count(counts["error"])

        has_any = any(c > 0 for c in counts.values())
        self._filter_bar.setVisible(has_any)

    def _on_filter_changed(self) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        show = set()
        if self._passed_toggle.isChecked():
            show.add("passed")
        if self._failed_toggle.isChecked():
            show.add("failed")
        if self._skipped_toggle.isChecked():
            show.add("skipped")
        if self._error_toggle.isChecked():
            show.add("error")
        show.add("not_run")

        for i in range(self._tree.topLevelItemCount()):
            self._apply_filter_item(self._tree.topLevelItem(i), show)

    def _apply_filter_item(self, item: QTreeWidgetItem, show: set[str]) -> bool:
        kind = item.data(0, _ROLE_KIND)
        if kind == "function":
            oc = item.data(1, _ROLE_OUTCOME) or "not_run"
            visible = oc in show
            item.setHidden(not visible)
            return visible

        any_visible = False
        for i in range(item.childCount()):
            if self._apply_filter_item(item.child(i), show):
                any_visible = True
        item.setHidden(not any_visible)
        return any_visible

    # -- internal: summary bar ----------------------------------------------

    def _refresh_summary(self) -> None:
        if self._discovery_count == 0:
            self._status_text.setText("No tests discovered")
            self._set_status_dot_state("idle")
            self._count_passed.setVisible(False)
            self._count_failed.setVisible(False)
            self._count_skipped.setVisible(False)
            return

        counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
        for v in self._outcomes.values():
            if v in counts:
                counts[v] += 1
        total_run = sum(counts.values())

        self._status_text.setText(f"{self._discovery_count} tests")

        if total_run == 0:
            self._set_status_dot_state("idle")
            self._count_passed.setVisible(False)
            self._count_failed.setVisible(False)
            self._count_skipped.setVisible(False)
            return

        if counts["failed"] > 0 or counts["error"] > 0:
            self._set_status_dot_state("fail")
        elif counts["passed"] > 0:
            self._set_status_dot_state("pass")
        else:
            self._set_status_dot_state("idle")

        if counts["passed"] > 0:
            self._count_passed.setText(f"\u2713 {counts['passed']}")
            self._count_passed.setVisible(True)
        else:
            self._count_passed.setVisible(False)

        failed_total = counts["failed"] + counts["error"]
        if failed_total > 0:
            self._count_failed.setText(f"\u2717 {failed_total}")
            self._count_failed.setVisible(True)
        else:
            self._count_failed.setVisible(False)

        if counts["skipped"] > 0:
            self._count_skipped.setText(f"\u25CB {counts['skipped']}")
            self._count_skipped.setVisible(True)
        else:
            self._count_skipped.setVisible(False)

    def _refresh_summary_colors(self) -> None:
        pc = self._outcome_colors["passed"]
        fc = self._outcome_colors["failed"]
        sc = self._outcome_colors["skipped"]
        self._count_passed.setStyleSheet(f"color: {pc};")
        self._count_failed.setStyleSheet(f"color: {fc};")
        self._count_skipped.setStyleSheet(f"color: {sc};")

    def _set_status_dot_state(self, state: str) -> None:
        self._status_dot.setProperty("testState", state)
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)

    # -- interactions -------------------------------------------------------

    def _show_context_menu(self, position: Any) -> None:
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

    def _handle_single_click(self, item: QTreeWidgetItem, column: int) -> None:
        kind = item.data(0, _ROLE_KIND)
        if kind != "function":
            return
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER) or 0
        if file_path:
            self.navigate_to_test.emit(file_path, int(line_number))
