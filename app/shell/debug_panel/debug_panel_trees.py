"""Tree widget builders and section headers for the debug panel."""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QFont, QFontDatabase
from PySide2.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.debug.debug_models import DebugExecutionState

ROLE_FILE_PATH = Qt.UserRole + 1
ROLE_LINE_NUMBER = Qt.UserRole + 2
ROLE_IS_CURRENT_FRAME = Qt.UserRole + 3
ROLE_FRAME_ID = Qt.UserRole + 4
ROLE_VARIABLE_REFERENCE = Qt.UserRole + 5
ROLE_BREAKPOINT_ENABLED = Qt.UserRole + 6


class _SectionHeader(QWidget):
    """Compact header bar for a debug panel section."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.debug.sectionHeader")
        self.setFixedHeight(22)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(4)

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("shell.debug.sectionTitle")
        layout.addWidget(self._title_label)

        self._count_label = QLabel("", self)
        self._count_label.setObjectName("shell.debug.sectionCount")
        layout.addWidget(self._count_label)

        layout.addStretch(1)

    def set_count(self, count: int) -> None:
        self._count_label.setText(str(count) if count > 0 else "")

    def add_action_button(self, text: str, tooltip: str = "") -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("shell.debug.sectionBtn")
        btn.setText(text)
        btn.setCursor(Qt.PointingHandCursor)
        if tooltip:
            btn.setToolTip(tooltip)
        self.layout().addWidget(btn)
        return btn


class _StatusHeader(QWidget):
    """Status bar across the top of the debug panel showing execution state."""

    refresh_stack_clicked: Any = Signal()
    refresh_locals_clicked: Any = Signal()
    clear_clicked: Any = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.debug.statusHeader")
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self._dot = QLabel(self)
        self._dot.setObjectName("shell.debug.statusDot")
        self._dot.setFixedSize(10, 10)
        layout.addWidget(self._dot)

        self._label = QLabel("Idle", self)
        self._label.setObjectName("shell.debug.statusLabel")
        layout.addWidget(self._label)

        layout.addStretch(1)

        refresh_stack_btn = QToolButton(self)
        refresh_stack_btn.setObjectName("shell.debug.sectionBtn")
        refresh_stack_btn.setText("Stack")
        refresh_stack_btn.setToolTip("Refresh call stack")
        refresh_stack_btn.setCursor(Qt.PointingHandCursor)
        refresh_stack_btn.clicked.connect(self.refresh_stack_clicked)
        layout.addWidget(refresh_stack_btn)

        refresh_locals_btn = QToolButton(self)
        refresh_locals_btn.setObjectName("shell.debug.sectionBtn")
        refresh_locals_btn.setText("Locals")
        refresh_locals_btn.setToolTip("Refresh local variables")
        refresh_locals_btn.setCursor(Qt.PointingHandCursor)
        refresh_locals_btn.clicked.connect(self.refresh_locals_clicked)
        layout.addWidget(refresh_locals_btn)

        clear_btn = QToolButton(self)
        clear_btn.setObjectName("shell.debug.sectionBtn")
        clear_btn.setText("Clear")
        clear_btn.setToolTip("Clear debug output")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_clicked)
        layout.addWidget(clear_btn)

    def update_state(self, state: DebugExecutionState, location: str = "") -> None:
        labels = {
            DebugExecutionState.IDLE: "Idle",
            DebugExecutionState.RUNNING: "Running",
            DebugExecutionState.PAUSED: "Paused",
            DebugExecutionState.EXITED: "Session ended",
        }
        dot_classes = {
            DebugExecutionState.IDLE: "idle",
            DebugExecutionState.RUNNING: "running",
            DebugExecutionState.PAUSED: "paused",
            DebugExecutionState.EXITED: "idle",
        }
        text = labels.get(state, "Idle")
        if location and state == DebugExecutionState.PAUSED:
            text = f"Paused at {location}"
        self._label.setText(text)
        self._dot.setProperty("debugState", dot_classes.get(state, "idle"))
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)


def make_section(header: _SectionHeader, content: QWidget, parent: QWidget | None = None) -> QWidget:
    """Combine a section header with its content widget in a vertical stack."""
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(header)
    layout.addWidget(content, 1)
    return container


def mono_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(9)
    return font


def build_threads_tree() -> QTreeWidget:
    tree = QTreeWidget()
    tree.setObjectName("shell.debug.threadsTree")
    tree.setHeaderLabels(["Thread"])
    tree.setRootIsDecorated(False)
    tree.setSelectionMode(QAbstractItemView.SingleSelection)
    tree.setAlternatingRowColors(True)
    tree.setFont(mono_font())
    tree.header().hide()
    tree.setIndentation(0)
    return tree


def build_stack_tree(
    *,
    on_item_clicked: Callable[[QTreeWidgetItem, int], None],
    on_item_double_clicked: Callable[[QTreeWidgetItem, int], None],
) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setObjectName("shell.debug.stackTree")
    tree.setHeaderLabels(["Function", "Location"])
    tree.setRootIsDecorated(False)
    tree.setSelectionMode(QAbstractItemView.SingleSelection)
    tree.setAlternatingRowColors(True)
    tree.setFont(mono_font())
    tree.header().setStretchLastSection(True)
    tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
    tree.header().resizeSection(0, 140)
    tree.setIndentation(0)
    tree.itemClicked.connect(on_item_clicked)
    tree.itemDoubleClicked.connect(on_item_double_clicked)
    return tree


def build_variables_tree(
    *,
    on_item_expanded: Callable[[QTreeWidgetItem], None],
    on_item_collapsed: Callable[[QTreeWidgetItem], None],
) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setObjectName("shell.debug.variablesTree")
    tree.setHeaderLabels(["Name", "Value"])
    tree.setRootIsDecorated(True)
    tree.setSelectionMode(QAbstractItemView.SingleSelection)
    tree.setAlternatingRowColors(True)
    tree.setFont(mono_font())
    tree.header().setStretchLastSection(True)
    tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
    tree.header().resizeSection(0, 120)
    tree.setIndentation(12)
    tree.itemExpanded.connect(on_item_expanded)
    tree.itemCollapsed.connect(on_item_collapsed)
    return tree


def build_breakpoints_tree(
    *,
    on_context_menu: Callable[..., None],
    on_item_clicked: Callable[[QTreeWidgetItem, int], None],
    on_item_double_clicked: Callable[[QTreeWidgetItem, int], None],
    on_item_changed: Callable[[QTreeWidgetItem, int], None],
) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setObjectName("shell.debug.breakpointsTree")
    tree.setHeaderLabels(["Breakpoint", "Status"])
    tree.setRootIsDecorated(False)
    tree.setSelectionMode(QAbstractItemView.SingleSelection)
    tree.setAlternatingRowColors(True)
    tree.setFont(mono_font())
    tree.header().setStretchLastSection(True)
    tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
    tree.header().resizeSection(0, 180)
    tree.setIndentation(0)
    tree.setContextMenuPolicy(Qt.CustomContextMenu)
    tree.customContextMenuRequested.connect(on_context_menu)
    tree.itemClicked.connect(on_item_clicked)
    tree.itemDoubleClicked.connect(on_item_double_clicked)
    tree.itemChanged.connect(on_item_changed)
    return tree


def build_watch_section(
    *,
    on_add_watch: Callable[[], None],
    on_context_menu: Callable[..., None],
) -> tuple[QTreeWidget, QLineEdit, QWidget]:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    input_row = QWidget(container)
    input_row.setObjectName("shell.debug.watchInputRow")
    input_layout = QHBoxLayout(input_row)
    input_layout.setContentsMargins(4, 3, 4, 3)
    input_layout.setSpacing(4)

    watch_input = QLineEdit(input_row)
    watch_input.setObjectName("shell.debug.watchInput")
    watch_input.setPlaceholderText("Add safe expression...")
    watch_input.setToolTip(
        "Watch expressions are evaluated in a safe read-only subset; function calls are blocked."
    )
    watch_input.returnPressed.connect(on_add_watch)
    input_layout.addWidget(watch_input, 1)

    add_btn = QToolButton(input_row)
    add_btn.setObjectName("shell.debug.sectionBtn")
    add_btn.setText("+")
    add_btn.setToolTip("Add watch expression")
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.clicked.connect(on_add_watch)
    input_layout.addWidget(add_btn)

    layout.addWidget(input_row)

    tree = QTreeWidget(container)
    tree.setObjectName("shell.debug.watchTree")
    tree.setHeaderLabels(["Expression", "Value"])
    tree.setRootIsDecorated(False)
    tree.setSelectionMode(QAbstractItemView.SingleSelection)
    tree.setAlternatingRowColors(True)
    tree.setFont(mono_font())
    tree.header().setStretchLastSection(True)
    tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
    tree.header().resizeSection(0, 120)
    tree.setIndentation(0)
    tree.setContextMenuPolicy(Qt.CustomContextMenu)
    tree.customContextMenuRequested.connect(on_context_menu)
    layout.addWidget(tree, 1)

    return tree, watch_input, container


def build_output_widget() -> QPlainTextEdit:
    widget = QPlainTextEdit()
    widget.setObjectName("shell.debug.output")
    widget.setReadOnly(True)
    widget.setFont(mono_font())
    widget.setLineWrapMode(QPlainTextEdit.NoWrap)
    return widget


def build_output_section(
    *,
    on_submit_command: Callable[[], None],
) -> tuple[QPlainTextEdit, QLineEdit, QToolButton, QWidget]:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    input_row = QWidget(container)
    input_row.setObjectName("shell.debug.commandInputRow")
    input_layout = QHBoxLayout(input_row)
    input_layout.setContentsMargins(4, 3, 4, 3)
    input_layout.setSpacing(4)

    command_input = QLineEdit(input_row)
    command_input.setObjectName("shell.debug.commandInput")
    command_input.setPlaceholderText("Evaluate in selected frame...")
    command_input.returnPressed.connect(on_submit_command)
    input_layout.addWidget(command_input, 1)

    send_btn = QToolButton(input_row)
    send_btn.setObjectName("shell.debug.sectionBtn")
    send_btn.setText("Eval")
    send_btn.setToolTip("Evaluate in selected debug frame")
    send_btn.setCursor(Qt.PointingHandCursor)
    send_btn.clicked.connect(on_submit_command)
    input_layout.addWidget(send_btn)

    output_widget = build_output_widget()
    layout.addWidget(input_row)
    layout.addWidget(output_widget, 1)
    return output_widget, command_input, send_btn, container
