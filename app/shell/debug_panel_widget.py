"""Modern debug panel widget with splitter layout and tree views."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QFont, QFontDatabase
from PySide2.QtWidgets import (
    QAbstractItemView,
    QAction,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.debug.debug_models import DebugExecutionState, DebugFrame, DebugSessionState, DebugVariable


_ROLE_FILE_PATH = Qt.UserRole + 1
_ROLE_LINE_NUMBER = Qt.UserRole + 2
_ROLE_IS_CURRENT_FRAME = Qt.UserRole + 3


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

    refresh_stack_clicked = Signal()
    refresh_locals_clicked = Signal()
    clear_clicked = Signal()

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


def _make_section(header: _SectionHeader, content: QWidget, parent: QWidget | None = None) -> QWidget:
    """Combine a section header with its content widget in a vertical stack."""
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(header)
    layout.addWidget(content, 1)
    return container


def _mono_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(9)
    return font


class DebugPanelWidget(QWidget):
    """Self-contained debug panel with splitter layout and tree views."""

    navigate_requested = Signal(str, int)
    navigate_permanent_requested = Signal(str, int)
    watch_evaluate_requested = Signal(str)
    breakpoint_remove_requested = Signal(str, int)
    refresh_stack_requested = Signal()
    refresh_locals_requested = Signal()
    command_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.debug.panel")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._status_header = _StatusHeader(self)
        self._status_header.refresh_stack_clicked.connect(self.refresh_stack_requested)
        self._status_header.refresh_locals_clicked.connect(self.refresh_locals_requested)
        self._status_header.clear_clicked.connect(self._handle_clear)
        root_layout.addWidget(self._status_header)

        main_splitter = QSplitter(Qt.Horizontal, self)
        main_splitter.setObjectName("shell.debug.mainSplitter")
        main_splitter.setChildrenCollapsible(True)
        main_splitter.setHandleWidth(1)

        left_splitter = QSplitter(Qt.Vertical, main_splitter)
        left_splitter.setObjectName("shell.debug.leftSplitter")
        left_splitter.setChildrenCollapsible(True)
        left_splitter.setHandleWidth(1)

        self._stack_header = _SectionHeader("CALL STACK")
        self._stack_tree = self._build_stack_tree()
        left_splitter.addWidget(_make_section(self._stack_header, self._stack_tree))

        self._bp_header = _SectionHeader("BREAKPOINTS")
        self._bp_clear_btn = self._bp_header.add_action_button("Clear All", "Remove all breakpoints")
        self._bp_clear_btn.clicked.connect(self._handle_clear_all_breakpoints)
        self._bp_tree = self._build_breakpoints_tree()
        left_splitter.addWidget(_make_section(self._bp_header, self._bp_tree))

        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 2)
        main_splitter.addWidget(left_splitter)

        self._vars_header = _SectionHeader("VARIABLES")
        self._vars_tree = self._build_variables_tree()
        main_splitter.addWidget(_make_section(self._vars_header, self._vars_tree))

        right_splitter = QSplitter(Qt.Vertical, main_splitter)
        right_splitter.setObjectName("shell.debug.rightSplitter")
        right_splitter.setChildrenCollapsible(True)
        right_splitter.setHandleWidth(1)

        self._watch_header = _SectionHeader("WATCH")
        self._watch_tree, self._watch_input, watch_container = self._build_watch_section()
        right_splitter.addWidget(_make_section(self._watch_header, watch_container))

        self._output_header = _SectionHeader("DEBUG OUTPUT")
        self._output_widget, self._command_input, self._command_send_btn, output_container = self._build_output_section()
        right_splitter.addWidget(_make_section(self._output_header, output_container))

        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 3)
        main_splitter.addWidget(right_splitter)

        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setStretchFactor(2, 3)
        root_layout.addWidget(main_splitter, 1)

        self._breakpoints_by_file: Dict[str, Set[int]] = {}
        self.set_command_input_enabled(False)

    # -- Tree builders --------------------------------------------------------

    def _build_stack_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("shell.debug.stackTree")
        tree.setHeaderLabels(["Function", "Location"])
        tree.setRootIsDecorated(False)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.setFont(_mono_font())
        tree.header().setStretchLastSection(True)
        tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        tree.header().resizeSection(0, 140)
        tree.setIndentation(0)
        tree.itemClicked.connect(self._on_stack_item_clicked)
        tree.itemDoubleClicked.connect(self._on_stack_item_double_clicked)
        return tree

    def _build_variables_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("shell.debug.variablesTree")
        tree.setHeaderLabels(["Name", "Value"])
        tree.setRootIsDecorated(True)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.setFont(_mono_font())
        tree.header().setStretchLastSection(True)
        tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        tree.header().resizeSection(0, 120)
        tree.setIndentation(12)
        return tree

    def _build_breakpoints_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("shell.debug.breakpointsTree")
        tree.setHeaderLabels(["Breakpoint"])
        tree.setRootIsDecorated(False)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.setFont(_mono_font())
        tree.header().hide()
        tree.setIndentation(0)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_bp_context_menu)
        tree.itemClicked.connect(self._on_bp_item_clicked)
        tree.itemDoubleClicked.connect(self._on_bp_item_double_clicked)
        return tree

    def _build_watch_section(self) -> tuple[QTreeWidget, QLineEdit, QWidget]:
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
        watch_input.setPlaceholderText("Add expression...")
        watch_input.returnPressed.connect(self._handle_add_watch)
        input_layout.addWidget(watch_input, 1)

        add_btn = QToolButton(input_row)
        add_btn.setObjectName("shell.debug.sectionBtn")
        add_btn.setText("+")
        add_btn.setToolTip("Add watch expression")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._handle_add_watch)
        input_layout.addWidget(add_btn)

        layout.addWidget(input_row)

        tree = QTreeWidget(container)
        tree.setObjectName("shell.debug.watchTree")
        tree.setHeaderLabels(["Expression", "Value"])
        tree.setRootIsDecorated(False)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.setFont(_mono_font())
        tree.header().setStretchLastSection(True)
        tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        tree.header().resizeSection(0, 120)
        tree.setIndentation(0)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_watch_context_menu)
        layout.addWidget(tree, 1)

        return tree, watch_input, container

    def _build_output_widget(self) -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setObjectName("shell.debug.output")
        widget.setReadOnly(True)
        widget.setFont(_mono_font())
        widget.setLineWrapMode(QPlainTextEdit.NoWrap)
        return widget

    def _build_output_section(self) -> tuple[QPlainTextEdit, QLineEdit, QToolButton, QWidget]:
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
        command_input.setPlaceholderText("Enter pdb command...")
        command_input.returnPressed.connect(self._handle_submit_command)
        input_layout.addWidget(command_input, 1)

        send_btn = QToolButton(input_row)
        send_btn.setObjectName("shell.debug.sectionBtn")
        send_btn.setText("Send")
        send_btn.setToolTip("Send command to debugger")
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.clicked.connect(self._handle_submit_command)
        input_layout.addWidget(send_btn)

        output_widget = self._build_output_widget()
        layout.addWidget(input_row)
        layout.addWidget(output_widget, 1)
        return output_widget, command_input, send_btn, container

    # -- Public API -----------------------------------------------------------

    def update_from_state(self, state: DebugSessionState) -> None:
        """Refresh stack, variables, and status from debug session state."""
        location = ""
        if state.frames:
            top = state.frames[0]
            location = f"{Path(top.file_path).name}:{top.line_number} in {top.function_name}"

        self._status_header.update_state(state.execution_state, location)
        self._refresh_stack(state.frames)
        self._refresh_variables(state.variables)

        if state.execution_state == DebugExecutionState.PAUSED:
            self._auto_evaluate_watches()

    def append_output(self, text: str) -> None:
        self._output_widget.appendPlainText(text)

    def set_breakpoints(self, breakpoints_by_file: Dict[str, Set[int]]) -> None:
        self._breakpoints_by_file = {fp: set(lines) for fp, lines in breakpoints_by_file.items()}
        self._refresh_breakpoints()

    def watch_expressions(self) -> List[str]:
        exprs: List[str] = []
        for i in range(self._watch_tree.topLevelItemCount()):
            item = self._watch_tree.topLevelItem(i)
            expr = item.text(0).strip()
            if expr:
                exprs.append(expr)
        return exprs

    def set_watch_value(self, expression: str, value: str) -> None:
        """Update the value column for a watch expression."""
        for i in range(self._watch_tree.topLevelItemCount()):
            item = self._watch_tree.topLevelItem(i)
            if item.text(0).strip() == expression.strip():
                item.setText(1, value)
                return

    def clear_output(self) -> None:
        self._output_widget.clear()

    def clear_all(self) -> None:
        self._output_widget.clear()
        self._stack_tree.clear()
        self._vars_tree.clear()
        self._stack_header.set_count(0)
        self._vars_header.set_count(0)
        self._status_header.update_state(DebugExecutionState.IDLE)

    def set_command_input_enabled(self, enabled: bool) -> None:
        self._command_input.setEnabled(enabled)
        self._command_send_btn.setEnabled(enabled)

    # -- Internal refresh helpers ---------------------------------------------

    def _refresh_stack(self, frames: List[DebugFrame]) -> None:
        self._stack_tree.clear()
        self._stack_header.set_count(len(frames))
        for idx, frame in enumerate(frames):
            item = QTreeWidgetItem()
            item.setText(0, frame.function_name)
            item.setText(1, f"{Path(frame.file_path).name}:{frame.line_number}")
            item.setData(0, _ROLE_FILE_PATH, frame.file_path)
            item.setData(0, _ROLE_LINE_NUMBER, frame.line_number)
            item.setData(0, _ROLE_IS_CURRENT_FRAME, idx == 0)
            if idx == 0:
                bold_font = self._stack_tree.font()
                bold_font.setBold(True)
                item.setFont(0, bold_font)
                item.setFont(1, bold_font)
            item.setToolTip(0, f"{frame.file_path}:{frame.line_number}")
            item.setToolTip(1, frame.file_path)
            self._stack_tree.addTopLevelItem(item)

    def _refresh_variables(self, variables: List[DebugVariable]) -> None:
        self._vars_tree.clear()
        self._vars_header.set_count(len(variables))
        for var in variables:
            item = QTreeWidgetItem()
            item.setText(0, var.name)
            value = var.value_repr
            item.setText(1, value)
            item.setToolTip(1, value)
            self._try_expand_variable(item, value)
            self._vars_tree.addTopLevelItem(item)

    def _try_expand_variable(self, parent_item: QTreeWidgetItem, value_repr: str) -> None:
        """Add child nodes for dict/list-like values when parseable."""
        stripped = value_repr.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            self._expand_dict_repr(parent_item, stripped)
        elif stripped.startswith("[") and stripped.endswith("]"):
            self._expand_list_repr(parent_item, stripped)

    def _expand_dict_repr(self, parent_item: QTreeWidgetItem, repr_str: str) -> None:
        inner = repr_str[1:-1].strip()
        if not inner or len(inner) > 2000:
            return
        pairs = self._split_top_level(inner)
        if len(pairs) <= 1:
            return
        for pair in pairs:
            colon_idx = pair.find(":")
            if colon_idx == -1:
                colon_idx = pair.find("=")
            if colon_idx != -1:
                key = pair[:colon_idx].strip()
                val = pair[colon_idx + 1:].strip()
                child = QTreeWidgetItem()
                child.setText(0, key)
                child.setText(1, val)
                child.setToolTip(1, val)
                parent_item.addChild(child)

    def _expand_list_repr(self, parent_item: QTreeWidgetItem, repr_str: str) -> None:
        inner = repr_str[1:-1].strip()
        if not inner or len(inner) > 2000:
            return
        items = self._split_top_level(inner)
        if len(items) <= 1:
            return
        for idx, val in enumerate(items):
            child = QTreeWidgetItem()
            child.setText(0, f"[{idx}]")
            child.setText(1, val.strip())
            child.setToolTip(1, val.strip())
            parent_item.addChild(child)

    @staticmethod
    def _split_top_level(text: str) -> List[str]:
        """Split on commas that are not inside brackets/braces/parens."""
        parts: List[str] = []
        depth = 0
        current: List[str] = []
        for ch in text:
            if ch in "({[":
                depth += 1
            elif ch in ")}]":
                depth = max(0, depth - 1)
            if ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts

    def _refresh_breakpoints(self) -> None:
        self._bp_tree.clear()
        total = 0
        for file_path in sorted(self._breakpoints_by_file.keys()):
            for line_number in sorted(self._breakpoints_by_file[file_path]):
                item = QTreeWidgetItem()
                item.setText(0, f"{Path(file_path).name}:{line_number}")
                item.setCheckState(0, Qt.Checked)
                item.setData(0, _ROLE_FILE_PATH, file_path)
                item.setData(0, _ROLE_LINE_NUMBER, line_number)
                item.setToolTip(0, f"{file_path}:{line_number}")
                self._bp_tree.addTopLevelItem(item)
                total += 1
        self._bp_header.set_count(total)

    # -- Slots ----------------------------------------------------------------

    def _on_stack_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        if file_path and line_number is not None:
            self.navigate_requested.emit(file_path, int(line_number))

    def _on_stack_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        if file_path and line_number is not None:
            self.navigate_permanent_requested.emit(file_path, int(line_number))

    def _on_bp_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        if file_path and line_number is not None:
            self.navigate_requested.emit(file_path, int(line_number))

    def _on_bp_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        if file_path and line_number is not None:
            self.navigate_permanent_requested.emit(file_path, int(line_number))

    def _on_bp_context_menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        item = self._bp_tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self._bp_tree)
        remove_action = QAction("Remove Breakpoint", menu)
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        remove_action.triggered.connect(
            lambda: self._remove_breakpoint(file_path, line_number)
        )
        menu.addAction(remove_action)
        menu.exec_(self._bp_tree.viewport().mapToGlobal(pos))

    def _remove_breakpoint(self, file_path: str | None, line_number: int | None) -> None:
        if file_path and line_number is not None:
            self.breakpoint_remove_requested.emit(file_path, int(line_number))

    def _handle_clear_all_breakpoints(self) -> None:
        for file_path in list(self._breakpoints_by_file.keys()):
            for line_number in list(self._breakpoints_by_file.get(file_path, set())):
                self.breakpoint_remove_requested.emit(file_path, line_number)

    def _handle_add_watch(self) -> None:
        expression = self._watch_input.text().strip()
        if not expression:
            return
        existing = self.watch_expressions()
        if expression not in existing:
            item = QTreeWidgetItem()
            item.setText(0, expression)
            item.setText(1, "")
            self._watch_tree.addTopLevelItem(item)
            self._watch_header.set_count(self._watch_tree.topLevelItemCount())
        self._watch_input.clear()

    def _on_watch_context_menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        item = self._watch_tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self._watch_tree)

        eval_action = QAction("Evaluate", menu)
        expression = item.text(0).strip()
        eval_action.triggered.connect(lambda: self.watch_evaluate_requested.emit(expression))
        menu.addAction(eval_action)

        remove_action = QAction("Remove Watch", menu)
        remove_action.triggered.connect(lambda: self._remove_watch_item(item))
        menu.addAction(remove_action)

        menu.addSeparator()
        remove_all_action = QAction("Remove All Watches", menu)
        remove_all_action.triggered.connect(self._clear_all_watches)
        menu.addAction(remove_all_action)

        menu.exec_(self._watch_tree.viewport().mapToGlobal(pos))

    def _remove_watch_item(self, item: QTreeWidgetItem) -> None:
        idx = self._watch_tree.indexOfTopLevelItem(item)
        if idx >= 0:
            self._watch_tree.takeTopLevelItem(idx)
            self._watch_header.set_count(self._watch_tree.topLevelItemCount())

    def _clear_all_watches(self) -> None:
        self._watch_tree.clear()
        self._watch_header.set_count(0)

    def _auto_evaluate_watches(self) -> None:
        for expr in self.watch_expressions():
            self.watch_evaluate_requested.emit(expr)

    def _handle_clear(self) -> None:
        self.clear_output()

    def _handle_submit_command(self) -> None:
        command = self._command_input.text().strip()
        if not command:
            return
        self.command_submitted.emit(command)
        self._command_input.clear()
