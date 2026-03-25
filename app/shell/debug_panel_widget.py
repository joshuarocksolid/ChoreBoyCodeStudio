"""Modern debug panel widget with splitter layout and tree views."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

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

from app.debug.debug_models import (
    DebugBreakpoint,
    DebugExecutionState,
    DebugFrame,
    DebugScope,
    DebugSessionState,
    DebugThread,
    DebugWatchResult,
    DebugVariable,
)


_ROLE_FILE_PATH = Qt.UserRole + 1
_ROLE_LINE_NUMBER = Qt.UserRole + 2
_ROLE_IS_CURRENT_FRAME = Qt.UserRole + 3
_ROLE_FRAME_ID = Qt.UserRole + 4
_ROLE_VARIABLE_REFERENCE = Qt.UserRole + 5
_ROLE_BREAKPOINT_ENABLED = Qt.UserRole + 6


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

    navigate_requested: Any = Signal(str, int)
    navigate_permanent_requested: Any = Signal(str, int)
    frame_selected_requested: Any = Signal(int)
    variable_expand_requested: Any = Signal(int)
    watch_evaluate_requested: Any = Signal(str)
    breakpoint_remove_requested: Any = Signal(str, int)
    breakpoint_toggle_requested: Any = Signal(str, int, bool)
    breakpoint_edit_requested: Any = Signal(str, int)
    refresh_stack_requested: Any = Signal()
    refresh_locals_requested: Any = Signal()
    command_submitted: Any = Signal(str)

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

        self._threads_header = _SectionHeader("THREADS")
        self._threads_tree = self._build_threads_tree()
        left_splitter.addWidget(_make_section(self._threads_header, self._threads_tree))

        self._stack_header = _SectionHeader("CALL STACK")
        self._stack_tree = self._build_stack_tree()
        left_splitter.addWidget(_make_section(self._stack_header, self._stack_tree))

        self._bp_header = _SectionHeader("BREAKPOINTS")
        self._bp_clear_btn = self._bp_header.add_action_button("Clear All", "Remove all breakpoints")
        self._bp_clear_btn.clicked.connect(self._handle_clear_all_breakpoints)
        self._bp_tree = self._build_breakpoints_tree()
        left_splitter.addWidget(_make_section(self._bp_header, self._bp_tree))

        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 3)
        left_splitter.setStretchFactor(2, 2)
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

        self._breakpoints: list[DebugBreakpoint] = []
        self._loaded_variable_references: set[int] = set()
        self._expanded_variable_references: set[int] = set()
        self._syncing_breakpoint_tree = False
        self._last_auto_eval_key: tuple[str, int, str] | None = None
        self.set_command_input_enabled(False)

    # -- Tree builders --------------------------------------------------------

    def _build_threads_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("shell.debug.threadsTree")
        tree.setHeaderLabels(["Thread"])
        tree.setRootIsDecorated(False)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.setFont(_mono_font())
        tree.header().hide()
        tree.setIndentation(0)
        return tree

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
        tree.itemExpanded.connect(self._on_variable_item_expanded)
        tree.itemCollapsed.connect(self._on_variable_item_collapsed)
        return tree

    def _build_breakpoints_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("shell.debug.breakpointsTree")
        tree.setHeaderLabels(["Breakpoint", "Status"])
        tree.setRootIsDecorated(False)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.setFont(_mono_font())
        tree.header().setStretchLastSection(True)
        tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        tree.header().resizeSection(0, 180)
        tree.setIndentation(0)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_bp_context_menu)
        tree.itemClicked.connect(self._on_bp_item_clicked)
        tree.itemDoubleClicked.connect(self._on_bp_item_double_clicked)
        tree.itemChanged.connect(self._on_bp_item_changed)
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
        command_input.setPlaceholderText("Evaluate in selected frame...")
        command_input.returnPressed.connect(self._handle_submit_command)
        input_layout.addWidget(command_input, 1)

        send_btn = QToolButton(input_row)
        send_btn.setObjectName("shell.debug.sectionBtn")
        send_btn.setText("Eval")
        send_btn.setToolTip("Evaluate in selected debug frame")
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
        selected_frame = state.selected_frame
        if selected_frame is not None:
            location = f"{Path(selected_frame.file_path).name}:{selected_frame.line_number} in {selected_frame.function_name}"

        self._status_header.update_state(state.execution_state, location)
        self._refresh_threads(state.threads)
        self._refresh_stack(state.frames, selected_frame_id=state.selected_frame_id)
        self._refresh_variables(state.scopes, state.variables_by_reference)
        self._refresh_watch_values(state.watch_results)

        auto_eval_key = (state.execution_state.value, state.selected_frame_id, state.last_message)
        if state.execution_state == DebugExecutionState.PAUSED and auto_eval_key != self._last_auto_eval_key:
            self._auto_evaluate_watches()
            self._last_auto_eval_key = auto_eval_key
        elif state.execution_state != DebugExecutionState.PAUSED:
            self._last_auto_eval_key = None

    def append_output(self, text: str) -> None:
        self._output_widget.appendPlainText(text)

    def set_breakpoints(self, breakpoints: List[DebugBreakpoint]) -> None:
        self._breakpoints = list(breakpoints)
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
        self._threads_tree.clear()
        self._stack_tree.clear()
        self._vars_tree.clear()
        self._watch_tree.clear()
        self._loaded_variable_references.clear()
        self._expanded_variable_references.clear()
        self._last_auto_eval_key = None
        self._threads_header.set_count(0)
        self._stack_header.set_count(0)
        self._vars_header.set_count(0)
        self._watch_header.set_count(0)
        self._status_header.update_state(DebugExecutionState.IDLE)

    def set_command_input_enabled(self, enabled: bool) -> None:
        self._command_input.setEnabled(enabled)
        self._command_send_btn.setEnabled(enabled)

    # -- Internal refresh helpers ---------------------------------------------

    def _refresh_threads(self, threads: List[DebugThread]) -> None:
        self._threads_tree.clear()
        self._threads_header.set_count(len(threads))
        for thread in threads:
            item = QTreeWidgetItem()
            label = thread.name if thread.name else "Thread"
            if thread.is_current:
                label = "%s (current)" % (label,)
            item.setText(0, label)
            item.setToolTip(0, "thread_id=%s" % (thread.thread_id,))
            self._threads_tree.addTopLevelItem(item)

    def _refresh_stack(self, frames: List[DebugFrame], *, selected_frame_id: int) -> None:
        self._stack_tree.clear()
        self._stack_header.set_count(len(frames))
        for index, frame in enumerate(frames):
            item = QTreeWidgetItem()
            item.setText(0, frame.function_name)
            item.setText(1, f"{Path(frame.file_path).name}:{frame.line_number}")
            item.setData(0, _ROLE_FILE_PATH, frame.file_path)
            item.setData(0, _ROLE_LINE_NUMBER, frame.line_number)
            item.setData(0, _ROLE_FRAME_ID, frame.frame_id)
            is_selected = frame.frame_id == selected_frame_id or (selected_frame_id <= 0 and index == 0)
            item.setData(0, _ROLE_IS_CURRENT_FRAME, is_selected)
            if is_selected:
                bold_font = self._stack_tree.font()
                bold_font.setBold(True)
                item.setFont(0, bold_font)
                item.setFont(1, bold_font)
            item.setToolTip(0, f"{frame.file_path}:{frame.line_number}")
            item.setToolTip(1, frame.file_path)
            self._stack_tree.addTopLevelItem(item)

    def _refresh_variables(
        self,
        scopes: List[DebugScope],
        variables_by_reference: Dict[int, List[DebugVariable]],
    ) -> None:
        self._loaded_variable_references = set(int(reference) for reference in variables_by_reference.keys())
        self._vars_tree.clear()
        total = 0
        for scope in scopes:
            scope_item = QTreeWidgetItem()
            scope_item.setText(0, scope.name)
            scope_item.setText(1, "")
            scope_item.setData(0, _ROLE_VARIABLE_REFERENCE, scope.variables_reference)
            scope_item.setFirstColumnSpanned(False)
            scope_item.setExpanded(True)
            self._vars_tree.addTopLevelItem(scope_item)
            variables = variables_by_reference.get(scope.variables_reference, [])
            total += len(variables)
            for variable in variables:
                scope_item.addChild(self._build_variable_item(variable, variables_by_reference))
        self._vars_header.set_count(total)

    def _build_variable_item(
        self,
        variable: DebugVariable,
        variables_by_reference: Dict[int, List[DebugVariable]],
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, variable.name)
        item.setText(1, variable.value_repr)
        item.setToolTip(1, variable.value_repr)
        item.setData(0, _ROLE_VARIABLE_REFERENCE, variable.variables_reference)
        if variable.type_name:
            item.setToolTip(0, variable.type_name)
        if variable.variables_reference > 0:
            loaded_children = variables_by_reference.get(variable.variables_reference, [])
            if loaded_children:
                for child in loaded_children:
                    item.addChild(self._build_variable_item(child, variables_by_reference))
                if variable.variables_reference in self._expanded_variable_references:
                    item.setExpanded(True)
            else:
                placeholder = QTreeWidgetItem()
                placeholder.setText(0, "Expand to load")
                placeholder.setText(1, "")
                item.addChild(placeholder)
        return item

    def _refresh_watch_values(self, watch_results: Dict[str, DebugWatchResult]) -> None:
        for index in range(self._watch_tree.topLevelItemCount()):
            item = self._watch_tree.topLevelItem(index)
            expression = item.text(0).strip()
            result = watch_results.get(expression)
            if result is None:
                continue
            if result.error_message:
                item.setText(1, result.error_message)
            else:
                item.setText(1, result.value_repr)
            item.setToolTip(1, item.text(1))

    def _refresh_breakpoints(self) -> None:
        self._syncing_breakpoint_tree = True
        try:
            self._bp_tree.clear()
            self._bp_header.set_count(len(self._breakpoints))
            for breakpoint in self._breakpoints:
                item = QTreeWidgetItem()
                label = f"{Path(breakpoint.file_path).name}:{breakpoint.line_number}"
                detail_parts: List[str] = []
                if breakpoint.condition:
                    detail_parts.append("cond")
                if breakpoint.hit_condition is not None:
                    detail_parts.append("hit %s" % (breakpoint.hit_condition,))
                if detail_parts:
                    label = "%s [%s]" % (label, ", ".join(detail_parts))
                item.setText(0, label)
                item.setText(1, "Verified" if breakpoint.verified else breakpoint.verification_message or "Pending")
                item.setCheckState(0, Qt.Checked if breakpoint.enabled else Qt.Unchecked)
                item.setData(0, _ROLE_FILE_PATH, breakpoint.file_path)
                item.setData(0, _ROLE_LINE_NUMBER, breakpoint.line_number)
                item.setData(0, _ROLE_BREAKPOINT_ENABLED, breakpoint.enabled)
                item.setToolTip(0, f"{breakpoint.file_path}:{breakpoint.line_number}")
                if breakpoint.verification_message:
                    item.setToolTip(1, breakpoint.verification_message)
                self._bp_tree.addTopLevelItem(item)
        finally:
            self._syncing_breakpoint_tree = False

    # -- Slots ----------------------------------------------------------------

    def _on_stack_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        frame_id = item.data(0, _ROLE_FRAME_ID)
        if frame_id is not None:
            self.frame_selected_requested.emit(int(frame_id))
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
        edit_action = QAction("Edit Breakpoint...", menu)
        remove_action = QAction("Remove Breakpoint", menu)
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        edit_action.triggered.connect(
            lambda: self._edit_breakpoint(file_path, line_number)
        )
        remove_action.triggered.connect(
            lambda: self._remove_breakpoint(file_path, line_number)
        )
        menu.addAction(edit_action)
        menu.addAction(remove_action)
        menu.exec_(self._bp_tree.viewport().mapToGlobal(pos))

    def _remove_breakpoint(self, file_path: str | None, line_number: int | None) -> None:
        if file_path and line_number is not None:
            self.breakpoint_remove_requested.emit(file_path, int(line_number))

    def _edit_breakpoint(self, file_path: str | None, line_number: int | None) -> None:
        if file_path and line_number is not None:
            self.breakpoint_edit_requested.emit(file_path, int(line_number))

    def _on_bp_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing_breakpoint_tree or column != 0:
            return
        file_path = item.data(0, _ROLE_FILE_PATH)
        line_number = item.data(0, _ROLE_LINE_NUMBER)
        enabled = item.checkState(0) == Qt.Checked
        if file_path and line_number is not None:
            self.breakpoint_toggle_requested.emit(file_path, int(line_number), enabled)

    def _handle_clear_all_breakpoints(self) -> None:
        for breakpoint in list(self._breakpoints):
            self.breakpoint_remove_requested.emit(breakpoint.file_path, breakpoint.line_number)

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

    def _on_variable_item_expanded(self, item: QTreeWidgetItem) -> None:
        variables_reference = item.data(0, _ROLE_VARIABLE_REFERENCE)
        if variables_reference is None:
            return
        reference = int(variables_reference)
        if reference <= 0:
            return
        self._expanded_variable_references.add(reference)
        if reference not in self._loaded_variable_references:
            self.variable_expand_requested.emit(reference)

    def _on_variable_item_collapsed(self, item: QTreeWidgetItem) -> None:
        variables_reference = item.data(0, _ROLE_VARIABLE_REFERENCE)
        if variables_reference is None:
            return
        reference = int(variables_reference)
        if reference <= 0:
            return
        self._expanded_variable_references.discard(reference)

    def _handle_clear(self) -> None:
        self.clear_output()

    def _handle_submit_command(self) -> None:
        command = self._command_input.text().strip()
        if not command:
            return
        self.command_submitted.emit(command)
        self._command_input.clear()
