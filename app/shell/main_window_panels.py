"""Panel construction helpers for the main shell window."""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import QSize, Qt
from PySide2.QtGui import QColor, QIcon
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.editors.find_replace_bar import FindReplaceBar
from app.project.project_tree_widget import ProjectTreeWidget
from app.shell.activity_bar import ActivityBar
from app.shell.debug_panel_widget import DebugPanelWidget
from app.shell.editor_tab_bar import MiddleClickTabBar
from app.shell.icon_provider import new_file_icon, new_folder_icon, refresh_icon
from app.shell.icons import explorer_icon, search_icon, test_icon
from app.shell.layout_persistence import DEFAULT_EXPLORER_SPLITTER_SIZES
from app.shell.outline_panel import OutlinePanel
from app.shell.problems_panel import ProblemsPanel
from app.shell.python_console_widget import PythonConsoleWidget
from app.shell.run_log_panel import RunLogPanel
from app.shell.search_sidebar_widget import SearchSidebarWidget
from app.shell.test_explorer_panel import TestExplorerPanel
from app.shell.welcome_widget import WelcomeWidget


def _make_explorer_button(parent: QWidget, tooltip: str, icon: QIcon) -> QToolButton:
    btn = QToolButton(parent)
    btn.setObjectName("shell.explorerAction")
    btn.setToolTip(tooltip)
    btn.setIcon(icon)
    btn.setFixedSize(QSize(24, 24))
    btn.setAutoRaise(True)
    return btn


def build_left_panel(window: Any) -> QWidget:
    panel = QWidget(window)
    panel.setObjectName("shell.leftRegion")
    outer_layout = QHBoxLayout(panel)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    window._activity_bar = ActivityBar(panel)
    tokens = window._resolve_theme_tokens()
    normal = QColor(tokens.text_muted)
    active = QColor(tokens.text_primary)
    window._activity_bar.add_view(
        "explorer",
        "\U0001F4C1",
        "Explorer",
        icon=explorer_icon(color_normal=normal, color_active=active),
    )
    window._activity_bar.add_view(
        "search",
        "\U0001F50D",
        "Search",
        icon=search_icon(color_normal=normal, color_active=active),
    )
    window._activity_bar.add_view(
        "test_explorer",
        "\U0001F9EA",
        "Test Explorer",
        icon=test_icon(color_normal=normal, color_active=active),
    )
    window._activity_bar.view_changed.connect(window._handle_sidebar_view_changed)
    outer_layout.addWidget(window._activity_bar)

    window._sidebar_stack = QStackedWidget(panel)
    window._sidebar_stack.setObjectName("shell.sidebarStack")
    outer_layout.addWidget(window._sidebar_stack, 1)

    explorer_page = build_explorer_page(window)
    window._sidebar_stack.addWidget(explorer_page)

    window._search_sidebar = SearchSidebarWidget(panel)
    window._search_sidebar.preview_file_at_line.connect(window._handle_search_preview_file_at_line)
    window._search_sidebar.open_file_at_line.connect(window._handle_search_open_file_at_line)
    window._sidebar_stack.addWidget(window._search_sidebar)

    window._test_explorer_panel = TestExplorerPanel(panel)
    window._sidebar_stack.addWidget(window._test_explorer_panel)

    window._sidebar_stack.setCurrentIndex(0)
    panel.setMinimumWidth(220)
    return panel


def build_explorer_page(window: Any) -> QWidget:
    page = QWidget(window)
    page.setObjectName("shell.explorerPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    header = QWidget(page)
    header.setObjectName("shell.explorerHeader")
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(10, 6, 6, 6)
    header_layout.setSpacing(2)

    title_label = QLabel("EXPLORER", header)
    title_label.setObjectName("shell.leftRegion.title")
    title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    header_layout.addWidget(title_label)

    window._explorer_new_file_btn = _make_explorer_button(
        header, "New File", new_file_icon("#495057", "#3366FF"),
    )
    window._explorer_new_file_btn.clicked.connect(window._handle_explorer_new_file)
    header_layout.addWidget(window._explorer_new_file_btn)

    window._explorer_new_folder_btn = _make_explorer_button(
        header, "New Folder", new_folder_icon("#495057", "#3366FF"),
    )
    window._explorer_new_folder_btn.clicked.connect(window._handle_explorer_new_folder)
    header_layout.addWidget(window._explorer_new_folder_btn)

    window._explorer_refresh_btn = _make_explorer_button(
        header, "Refresh Explorer", refresh_icon("#495057"),
    )
    window._explorer_refresh_btn.clicked.connect(window._reload_current_project)
    header_layout.addWidget(window._explorer_refresh_btn)

    layout.addWidget(header)

    window._project_placeholder_label = QLabel("No project loaded.", page)
    window._project_placeholder_label.setObjectName("shell.leftRegion.body")
    window._project_placeholder_label.setWordWrap(True)
    window._project_placeholder_label.setContentsMargins(10, 8, 10, 8)
    layout.addWidget(window._project_placeholder_label)

    window._project_tree_widget = ProjectTreeWidget(page)
    window._project_tree_widget.setObjectName("shell.projectTree")
    window._project_tree_widget.setHeaderHidden(True)
    window._project_tree_widget.setIndentation(16)
    window._project_tree_widget.setIconSize(QSize(16, 16))
    window._project_tree_widget.itemActivated.connect(window._handle_project_tree_item_activation)
    window._project_tree_widget.itemClicked.connect(window._handle_project_tree_item_click)
    window._project_tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
    window._project_tree_widget.customContextMenuRequested.connect(window._show_project_tree_context_menu)
    window._project_tree_widget.set_drop_callback(window._handle_project_tree_drop)
    window._project_tree_widget.itemExpanded.connect(window._handle_tree_item_expanded)
    window._project_tree_widget.itemCollapsed.connect(window._handle_tree_item_collapsed)
    window._project_tree_widget.deleteRequested.connect(window._handle_project_tree_delete_key)

    window._explorer_splitter = QSplitter(Qt.Vertical, page)
    window._explorer_splitter.setObjectName("shell.explorerSplitter")
    window._explorer_splitter.setChildrenCollapsible(True)
    window._explorer_splitter.setHandleWidth(1)
    window._explorer_splitter.addWidget(window._project_tree_widget)

    window._outline_panel = OutlinePanel(page)
    window._outline_panel.symbol_activated.connect(window._handle_outline_symbol_activated)
    window._outline_panel.collapsed_changed.connect(window._handle_outline_collapsed_changed)
    window._outline_panel.follow_cursor_changed.connect(window._handle_outline_follow_cursor_changed)
    window._outline_panel.sort_mode_changed.connect(window._handle_outline_sort_mode_changed)
    window._outline_panel.hide_requested.connect(window._handle_outline_hide_requested)
    window._explorer_splitter.addWidget(window._outline_panel)
    window._explorer_splitter.setStretchFactor(0, 7)
    window._explorer_splitter.setStretchFactor(1, 3)
    window._explorer_splitter.setSizes(list(DEFAULT_EXPLORER_SPLITTER_SIZES))
    window._apply_outline_layout_state()

    layout.addWidget(window._explorer_splitter, 1)
    window._update_explorer_buttons_enabled()
    return page


def build_center_panel(window: Any) -> QWidget:
    panel = QWidget(window)
    panel.setObjectName("shell.centerPanel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(4, 0, 4, 4)
    panel_layout.setSpacing(0)

    window._center_stack = QStackedWidget(panel)
    window._center_stack.setObjectName("shell.centerStack")

    window._welcome_widget = WelcomeWidget(window._center_stack)
    window._connect_welcome_widget_actions(window._welcome_widget)
    window._center_stack.addWidget(window._welcome_widget)

    editor_page = QWidget(window._center_stack)
    editor_page.setObjectName("shell.editorPage")
    editor_layout = QVBoxLayout(editor_page)
    editor_layout.setContentsMargins(0, 0, 0, 0)
    editor_layout.setSpacing(0)

    window._find_replace_bar = FindReplaceBar(editor_page)
    window._find_replace_bar.find_requested.connect(window._handle_find_bar_find)
    window._find_replace_bar.find_next_requested.connect(window._handle_find_bar_next)
    window._find_replace_bar.find_previous_requested.connect(window._handle_find_bar_prev)
    window._find_replace_bar.replace_requested.connect(window._handle_find_bar_replace)
    window._find_replace_bar.replace_all_requested.connect(window._handle_find_bar_replace_all)
    window._find_replace_bar.close_requested.connect(window._handle_find_bar_close)
    editor_layout.addWidget(window._find_replace_bar, 0)

    window._editor_tabs_widget = QTabWidget(editor_page)
    tab_bar = MiddleClickTabBar(window._editor_tabs_widget)
    tab_bar.set_tab_double_click_callback(window._handle_editor_tab_header_double_click)
    tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
    tab_bar.customContextMenuRequested.connect(window._show_editor_tab_context_menu)
    window._editor_tabs_widget.setTabBar(tab_bar)
    window._editor_tabs_widget.setObjectName("shell.editorTabs")
    window._editor_tabs_widget.currentChanged.connect(window._handle_editor_tab_changed)
    window._editor_tabs_widget.setTabsClosable(True)
    window._editor_tabs_widget.tabCloseRequested.connect(window._handle_tab_close_requested)
    window._editor_tabs_widget.setMinimumWidth(480)
    editor_layout.addWidget(window._editor_tabs_widget, 1)

    window._center_stack.addWidget(editor_page)
    window._center_stack.setCurrentIndex(0)
    window._refresh_welcome_project_list()

    panel_layout.addWidget(window._center_stack, 1)
    return panel


def build_bottom_panel(window: Any) -> QWidget:
    tabs = QTabWidget(window)
    tabs.setObjectName("shell.bottomRegion.tabs")
    window._bottom_tabs_widget = tabs
    tabs.setMinimumHeight(60)

    window._python_console_container = QWidget(tabs)
    window._python_console_container.setObjectName("shell.bottom.pythonConsoleContainer")
    container_layout = QVBoxLayout(window._python_console_container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(0)

    console_toolbar = QHBoxLayout()
    console_toolbar.setContentsMargins(2, 1, 2, 1)
    console_toolbar.addStretch()
    clear_btn = QToolButton(window._python_console_container)
    clear_btn.setText("Clear")
    clear_btn.setObjectName("shell.bottom.pythonConsole.clearBtn")
    clear_btn.setToolTip("Clear the Python Console display")
    clear_btn.setAutoRaise(True)
    console_toolbar.addWidget(clear_btn)
    container_layout.addLayout(console_toolbar)

    window._python_console_widget = PythonConsoleWidget(window._python_console_container)
    window._python_console_widget.setObjectName("shell.bottom.pythonConsole")
    window._python_console_widget.input_submitted.connect(window._handle_python_console_submit)
    window._python_console_widget.interrupt_requested.connect(window._handle_python_console_interrupt)
    window._python_console_widget.restart_requested.connect(window._handle_start_python_console_action)
    window._restore_python_console_history()
    clear_btn.clicked.connect(window._python_console_widget.clear_console)
    container_layout.addWidget(window._python_console_widget)

    repl_index = tabs.addTab(window._python_console_container, "Python Console")
    tabs.setTabToolTip(repl_index, "Interactive REPL session output appears here.")

    window._debug_panel = DebugPanelWidget(tabs)
    window._debug_panel.navigate_requested.connect(window._debug_control_workflow.handle_debug_navigate_preview)
    window._debug_panel.navigate_permanent_requested.connect(window._debug_control_workflow.handle_debug_navigate_permanent)
    window._debug_panel.frame_selected_requested.connect(window._debug_control_workflow.handle_debug_frame_selected)
    window._debug_panel.variable_expand_requested.connect(window._debug_control_workflow.handle_debug_variable_expand)
    window._debug_panel.watch_evaluate_requested.connect(window._debug_control_workflow.handle_debug_watch_evaluate)
    window._debug_panel.breakpoint_remove_requested.connect(window._debug_control_workflow.handle_debug_breakpoint_remove)
    window._debug_panel.breakpoint_toggle_requested.connect(window._debug_control_workflow.handle_debug_breakpoint_toggle)
    window._debug_panel.breakpoint_edit_requested.connect(window._debug_control_workflow.handle_debug_breakpoint_edit)
    window._debug_panel.refresh_stack_requested.connect(window._debug_control_workflow.handle_debug_refresh_stack)
    window._debug_panel.refresh_locals_requested.connect(window._debug_control_workflow.handle_debug_refresh_locals)
    window._debug_panel.command_submitted.connect(window._debug_control_workflow.handle_debug_command_submit)
    tabs.addTab(window._debug_panel, "Debug")

    window._problems_panel = ProblemsPanel(tabs)
    window._problems_panel.item_preview_requested.connect(window._handle_problem_item_preview)
    window._problems_panel.item_activated.connect(window._handle_problem_item_activation)
    window._problems_panel.context_menu_requested.connect(
        lambda fp, _code: window._python_style_workflow.apply_safe_fixes_for_file(fp)
    )
    window._problems_tab_widget = tabs
    problems_index = tabs.addTab(window._problems_panel, "Problems")
    tabs.setTabToolTip(problems_index, "Tracebacks and diagnostics for quick navigation.")

    window._run_log_panel = RunLogPanel(tabs)
    window._run_log_panel.open_log_requested.connect(
        lambda file_path: window._editor_tab_factory.open_file_in_editor(
            file_path,
            preview=window._editor_enable_preview,
        )
    )
    run_log_index = tabs.addTab(window._run_log_panel, "Run Log")
    tabs.setTabToolTip(run_log_index, "Run/Debug output (stdout/stderr) and per-run log.")
    return tabs
