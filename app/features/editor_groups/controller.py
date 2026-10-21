"""Split editor groups: up to two tab widgets side by side, VS Code style.

Each group is a ``QTabWidget`` with the shell's editor tab bar. The focused
group's tab widget is ``window._editor_tabs_widget``, so every "active editor"
action (Save, Run, Debug, Find, ...) acts on the focused group's current tab.
A buffer can be shown in both groups: the second view shares the buffer's
``QTextDocument`` and buffer state (see :mod:`app.editors.editor_buffer`).
``window._workspace_controller`` maps each buffer to the view in the most
recently focused group that shows it.

Dragging a tab out of its bar vertically moves it to the other group. That
drag uses plain mouse tracking, never ``QDrag``: QDrag runs a nested event
loop that wedges the VM test bridge. The drop target is shown with a separate
overlay frame; restyling a group mid-drag would re-polish its tab bar, which
cancels Qt's own tab slide.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.qt.QtCore import QPoint, QRect, Qt, QTimer
from app.qt.QtGui import QColor
from app.qt.QtWidgets import QApplication, QFrame, QLabel, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app.editors.code_editor_widget import CodeEditorWidget
from app.features.markdown.markdown_editor_pane import MarkdownEditorPane
from app.shell.document_safety import DocumentCloseIntent, DocumentScope
from app.shell.editor_tab_bar import MiddleClickTabBar
from app.shell.editor_tab_page import EditorTabPage, page_editor

MAX_EDITOR_GROUPS = 2
_NEW_GROUP_DROP_FRACTION = 0.6
LAYOUT_KEY_GROUPS = "groups"
LAYOUT_KEY_ACTIVE = "active"
LAYOUT_KEY_FOCUSED = "focused"
LAYOUT_KEY_SIZES = "sizes"


class EditorGroupTabWidget(QTabWidget):
    """A group's tab widget; tells the controller when a tab leaves it."""

    def __init__(self, controller: "EditorGroupsController", parent: QWidget) -> None:
        super().__init__(parent)
        self._controller = controller

    def tabRemoved(self, index: int) -> None:  # noqa: N802 - Qt signature
        super().tabRemoved(index)
        self._controller.schedule_collapse()


class EditorGroup(QFrame):
    """One editor group: a frame (for the focus accent) around a tab widget."""

    def __init__(self, controller: "EditorGroupsController", number: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("shell.editorGroup")
        self.setProperty("groupNumber", number)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.tabs = EditorGroupTabWidget(controller, self)
        self.tab_bar = MiddleClickTabBar(self.tabs)
        self.tabs.setTabBar(self.tab_bar)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setMinimumWidth(240)
        layout.addWidget(self.tabs)
        self._accent: Optional[str] = None

    def set_accent(self, color: Optional[str]) -> None:
        # Only on a change: a stylesheet change re-polishes the tab bar.
        if color == self._accent:
            return
        self._accent = color
        border = color if color else "transparent"
        self.setStyleSheet(f"QFrame#shell\\.editorGroup {{ border: 1px solid {border}; }}")

    def pages(self) -> list[EditorTabPage]:
        return [page for page in (self.tabs.widget(i) for i in range(self.tabs.count())) if isinstance(page, EditorTabPage)]

    def index_of_buffer(self, buffer_id: str) -> int:
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if isinstance(page, EditorTabPage) and page.buffer_id == buffer_id:
                return index
        return -1


class EditorGroupsController:
    """Owns the editor groups, which one is focused, and moves between them."""

    def __init__(self, window: Any) -> None:
        self._window = window
        self._groups: list[EditorGroup] = []
        self._focused: Optional[EditorGroup] = None
        self._splitter: Optional[QSplitter] = None
        self._host: Optional[QWidget] = None
        self._collapse_pending = False
        self._drag_source: Optional[EditorGroup] = None
        self._drag_buffer_id: Optional[str] = None
        self._drag_target: Optional[EditorGroup] = None
        self._drag_new_group = False
        self._ghost: Optional[QLabel] = None
        self._drop_overlay: Optional[QFrame] = None
        self._accent_color = "#3366FF"
        self._last_path_query: Optional[str] = None

    # -- Construction ------------------------------------------------------

    def build(self, parent: QWidget) -> QWidget:
        """Create the groups area with the first group and make it focused."""
        # The drag ghost and drop overlay float over the groups. They are
        # children of this host, not of the splitter: QSplitter adopts every
        # child widget as a pane.
        host = QWidget(parent)
        host.setObjectName("shell.editorGroupsHost")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal, host)
        splitter.setObjectName("shell.editorGroups")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(3)
        host_layout.addWidget(splitter)
        self._host = host
        self._splitter = splitter
        self._ghost = QLabel(host)
        self._ghost.setObjectName("shell.editorGroups.dragGhost")
        self._ghost.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._ghost.hide()
        self._drop_overlay = QFrame(host)
        self._drop_overlay.setObjectName("shell.editorGroups.dropOverlay")
        self._drop_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._drop_overlay.hide()
        self.apply_theme_colors(accent="#3366FF")
        self._add_group()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.focusChanged.connect(self._handle_focus_changed)
        return host

    def apply_theme_colors(self, *, accent: str) -> None:
        self._accent_color = accent or "#3366FF"
        if self._ghost is not None:
            self._ghost.setStyleSheet(
                f"background: {self._accent_color}; color: white; padding: 3px 8px; border-radius: 3px;"
            )
        if self._drop_overlay is not None:
            # The fill is the theme accent, faint, so it tints light and dark editors alike.
            fill = QColor(self._accent_color)
            self._drop_overlay.setStyleSheet(
                f"QFrame#shell\\.editorGroups\\.dropOverlay {{ background: rgba({fill.red()}, {fill.green()}, {fill.blue()}, 40);"
                f" border: 2px dashed {self._accent_color}; }}"
            )
        self._refresh_accents(force=True)

    def _add_group(self) -> EditorGroup:
        assert self._splitter is not None
        group = EditorGroup(self, len(self._groups) + 1, self._splitter)
        if not self._groups:
            group.tabs.setObjectName("shell.editorTabs")
        else:
            group.tabs.setObjectName("shell.editorTabs.group2")
        self._wire_group(group)
        self._groups.append(group)
        self._splitter.addWidget(group)
        if len(self._groups) > 1:
            half = max(1, self._splitter.width() // 2)
            self._splitter.setSizes([half, half])
        if self._focused is None:
            self._set_focused(group)
        self._refresh_accents()
        return group

    def _wire_group(self, group: EditorGroup) -> None:
        workflow = self._window._editor_tab_workflow
        tabs = group.tabs
        bar = group.tab_bar
        bar.set_tab_double_click_callback(lambda index, g=group: self._in_group(g, workflow.handle_editor_tab_header_double_click, index))
        bar.setContextMenuPolicy(Qt.CustomContextMenu)
        bar.customContextMenuRequested.connect(lambda pos, g=group: self._in_group(g, workflow.show_editor_tab_context_menu, pos))
        bar.tabBarClicked.connect(lambda _index, g=group: self._set_focused(g))
        bar.tabMoved.connect(lambda _from, _to: self._window._editor_tabs_coordinator.sync_open_order_from_tabs())
        bar.set_group_drag_callbacks(
            started=lambda index, g=group: self._begin_drag(g, index),
            moved=self._update_drag,
            finished=self._end_drag,
        )
        tabs.currentChanged.connect(lambda index, g=group: self._handle_current_changed(g, index))
        tabs.tabCloseRequested.connect(lambda index, g=group: self._in_group(g, workflow.handle_tab_close_requested, index))

    # -- Queries -----------------------------------------------------------

    def tab_widgets(self) -> list[QTabWidget]:
        return [group.tabs for group in self._groups]

    def groups(self) -> list[EditorGroup]:
        return list(self._groups)

    def group_count(self) -> int:
        return len(self._groups)

    def focused_index(self) -> int:
        return -1 if self._focused is None else self._groups.index(self._focused)

    def focused_group(self) -> Optional[EditorGroup]:
        return self._focused

    def groups_showing(self, buffer_id: str) -> list[EditorGroup]:
        return [group for group in self._groups if group.index_of_buffer(buffer_id) >= 0]

    def all_pages(self) -> list[EditorTabPage]:
        return [page for group in self._groups for page in group.pages()]

    # -- Focus -------------------------------------------------------------

    def focus_group(self, index: int) -> bool:
        """Ctrl+1 / Ctrl+2: focus a group and its current editor."""
        if index < 0 or index >= len(self._groups):
            return False
        group = self._groups[index]
        self._set_focused(group)
        page = group.tabs.currentWidget()
        if page is not None:
            page.setFocus(Qt.ShortcutFocusReason)
        return True

    def _in_group(self, group: EditorGroup, handler: Any, argument: Any) -> None:
        self._set_focused(group)
        handler(argument)

    def _handle_focus_changed(self, _old: Optional[QWidget], new: Optional[QWidget]) -> None:
        if new is None:
            return
        for group in self._groups:
            if group is new or group.isAncestorOf(new):
                self._set_focused(group)
                return

    def _set_focused(self, group: EditorGroup) -> None:
        if group not in self._groups:
            return
        changed = group is not self._focused
        self._focused = group
        self._window._editor_tabs_widget = group.tabs
        self._repoint_buffers_to(group)
        if not changed:
            return
        self._refresh_accents()
        index = group.tabs.currentIndex()
        if index >= 0:
            self._window._editor_tab_workflow.handle_editor_tab_changed(index)

    def _repoint_buffers_to(self, group: EditorGroup) -> None:
        workspace = self._window._workspace_controller
        for page in group.pages():
            editor = page_editor(page)
            if editor is not None and workspace.widget_for_buffer_id(page.buffer_id) is not None:
                workspace.repoint_editor(page.buffer_id, editor)

    def _handle_current_changed(self, group: EditorGroup, index: int) -> None:
        if group is self._focused:
            self._window._editor_tab_workflow.handle_editor_tab_changed(index)

    def _refresh_accents(self, *, force: bool = False) -> None:
        split = len(self._groups) > 1
        for group in self._groups:
            if force:
                group._accent = "?"
            group.set_accent(self._accent_color if split and group is self._focused else None)

    # -- Revealing and closing views -----------------------------------------

    def reveal_buffer(self, buffer_id: str) -> bool:
        """Select the buffer's tab, preferring the focused group, and focus that group."""
        groups = self.groups_showing(buffer_id)
        if not groups:
            return False
        group = self._focused if self._focused is not None and self._focused in groups else groups[0]
        self._set_focused(group)
        group.tabs.setCurrentIndex(group.index_of_buffer(buffer_id))
        return True

    def close_view_if_shared(self, tab_index: int) -> bool:
        """Close only the focused group's view when another group shows the buffer too."""
        group = self._focused
        if group is None:
            return False
        page = group.tabs.widget(tab_index)
        if not isinstance(page, EditorTabPage):
            return False
        others = [other for other in self.groups_showing(page.buffer_id) if other is not group]
        if not others:
            return False
        self._remove_view(group, tab_index, keep_page=False)
        self._repoint_buffers_to(others[0])
        return True

    def remove_buffer_everywhere(self, buffer_id: str) -> None:
        """Drop the buffer's extra views in every group but the primary view's."""
        primary = self._window._workspace_controller.widget_for_buffer_id(buffer_id)
        for group in self._groups:
            index = group.index_of_buffer(buffer_id)
            if index >= 0 and page_editor(group.tabs.widget(index)) is not primary:
                self._remove_view(group, index, keep_page=False)

    def _remove_view(self, group: EditorGroup, tab_index: int, *, keep_page: bool) -> Optional[EditorTabPage]:
        page = group.tabs.widget(tab_index)
        group.tabs.removeTab(tab_index)
        if not isinstance(page, EditorTabPage):
            return None
        if keep_page:
            return page
        editor = page_editor(page)
        workspace = self._window._workspace_controller
        if editor is not None and workspace.widget_for_buffer_id(page.buffer_id) is editor:
            # The primary view is going away; another group's view takes over.
            for other in self._groups:
                index = other.index_of_buffer(page.buffer_id)
                other_editor = page_editor(other.tabs.widget(index)) if index >= 0 else None
                if other_editor is not None and other_editor is not editor:
                    workspace.repoint_editor(page.buffer_id, other_editor)
                    break
        if editor is not None:
            self._window._editor_tab_workflow.release_editor_widget(editor)
        page.hide()
        page.deleteLater()
        self._register_remaining_markdown_pane(page.buffer_id)
        return None

    def _register_remaining_markdown_pane(self, buffer_id: str) -> None:
        """When the registered markdown view closes, the buffer's view in the other group takes over."""
        window = self._window
        tab = window._editor_manager.get_tab_by_id(buffer_id)
        if tab is None:
            return
        registry = window._tab_content_registry.markdown_registry()
        if registry.pane_for_path(tab.file_path) is not None:
            return
        for group in self._groups:
            index = group.index_of_buffer(buffer_id)
            view_page = group.tabs.widget(index) if index >= 0 else None
            content = view_page.content() if isinstance(view_page, EditorTabPage) else None
            if isinstance(content, MarkdownEditorPane):
                registry.register(tab.file_path, content)
                return

    # -- Project-tree deletes and renames ------------------------------------

    def tab_index_for_path_in_any_group(self, file_path: str) -> int:
        """Focused-group index, else the index in the other group, else -1.

        The project tree's delete flow calls this and then
        :meth:`remove_tabs_for_last_path`, which removes the buffer's tab from
        every group.
        """
        self._last_path_query = file_path
        tab = self._window._editor_manager.get_tab(file_path)
        if tab is None:
            return -1
        groups = self.groups_showing(tab.buffer_id)
        if not groups:
            return -1
        group = self._focused if self._focused is not None and self._focused in groups else groups[0]
        return group.index_of_buffer(tab.buffer_id)

    def remove_tabs_for_last_path(self, _tab_index: int) -> None:
        file_path = self._last_path_query
        tab = None if file_path is None else self._window._editor_manager.get_tab(file_path)
        if tab is None:
            return
        for group in self._groups:
            index = group.index_of_buffer(tab.buffer_id)
            if index >= 0:
                page = group.tabs.widget(index)
                group.tabs.removeTab(index)
                if page is not None:
                    page.hide()
                    page.deleteLater()

    # -- Split, close and collapse -------------------------------------------

    def split_right(self) -> bool:
        """Show the focused group's current buffer in the other group too."""
        source = self._focused
        if source is None:
            return False
        page = source.tabs.currentWidget()
        source_editor = page_editor(page)
        if not isinstance(page, EditorTabPage) or source_editor is None:
            return False
        target = self._other_group(source)
        if target is None:
            if len(self._groups) >= MAX_EDITOR_GROUPS:
                return False
            target = self._add_group()
        if target.index_of_buffer(page.buffer_id) < 0:
            self._add_view(target, page.buffer_id, source_editor)
        self._set_focused(target)
        target.tabs.setCurrentIndex(target.index_of_buffer(page.buffer_id))
        current = target.tabs.currentWidget()
        if current is not None:
            current.setFocus(Qt.OtherFocusReason)
        return True

    def _other_group(self, group: EditorGroup) -> Optional[EditorGroup]:
        for other in self._groups:
            if other is not group:
                return other
        return None

    def _add_view(self, target: EditorGroup, buffer_id: str, source_editor: CodeEditorWidget) -> int:
        window = self._window
        tab_state = window._editor_manager.get_tab_by_id(buffer_id)
        if tab_state is None:
            return -1
        view = window._editor_tab_factory.create_buffer_view(tab_state, source_editor, parent=target.tabs)
        # A Markdown file gets the same source / preview pane in every group.
        content = window._editor_tab_workflow.wrap_tab_content_if_markdown(
            editor_widget=view,
            file_path=tab_state.file_path,
            parent=target.tabs,
            theme_tokens=window._shell_theme_workflow.resolve_theme_tokens(),
            open_linked_file=lambda linked_path: window._editor_tab_factory.open_file_in_editor(linked_path, preview=False),
            register=False,
        )
        page = window._editor_tab_factory.build_tab_page(content, buffer_id)
        index = target.tabs.addTab(page, tab_state.display_name)
        window._editor_tabs_coordinator.present_tab_at(index, tab_state, tabs=target.tabs)
        return index

    def close_group(self, index: Optional[int] = None) -> bool:
        """Close a group (the focused one by default), asking about buffers shown only there."""
        if len(self._groups) < 2:
            return False
        group = self._focused if index is None else self._groups[index]
        if group is None:
            return False
        window = self._window
        other = self._other_group(group)
        only_here = [page.buffer_id for page in group.pages() if other is None or other.index_of_buffer(page.buffer_id) < 0]
        dirty = [
            tab
            for tab in (window._editor_manager.get_tab_by_id(buffer_id) for buffer_id in only_here)
            if tab is not None and tab.is_dirty
        ]
        if dirty:
            save_workflow = window._save_workflow
            decision = save_workflow.request_unsaved_changes_decision(
                "closing this editor group",
                scope=DocumentScope.TAB,
                allow_keep_for_next_launch=False,
                dirty_buffers=tuple(dirty),
            )
            if decision.intent is DocumentCloseIntent.CANCEL:
                return False
            if not save_workflow.apply_unsaved_changes_decision(decision):
                return False
        self._set_focused(group)
        while group.tabs.count():
            page = group.tabs.widget(0)
            buffer_id = page.buffer_id if isinstance(page, EditorTabPage) else None
            tab = None if buffer_id is None else window._editor_manager.get_tab_by_id(buffer_id)
            if tab is not None and buffer_id in only_here:
                window._editor_tab_workflow.close_tab_discarding_edits(tab.file_path)
            else:
                self._remove_view(group, 0, keep_page=False)
        self._collapse_now()
        return True

    def schedule_collapse(self) -> None:
        if self._collapse_pending:
            return
        self._collapse_pending = True
        QTimer.singleShot(0, self._collapse_now)

    def _collapse_now(self) -> None:
        """Remove an empty group; if the first group emptied, the second takes its place."""
        self._collapse_pending = False
        if len(self._groups) < 2 or self._drag_source is not None:
            return
        first, second = self._groups[0], self._groups[1]
        if second.tabs.count() and first.tabs.count():
            return
        if not second.tabs.count() and not first.tabs.count():
            self._drop_group(second)
            return
        if not first.tabs.count():
            current = second.tabs.currentIndex()
            while second.tabs.count():
                self._move_page(second, 0, first)
            if current >= 0:
                first.tabs.setCurrentIndex(current)
        self._drop_group(second)

    def _drop_group(self, group: EditorGroup) -> None:
        self._groups.remove(group)
        if self._focused is group or self._focused not in self._groups:
            self._focused = None
            self._set_focused(self._groups[0])
        group.hide()
        group.setParent(None)  # type: ignore[call-overload]
        group.deleteLater()
        self._refresh_accents()

    def reset(self) -> None:
        """Back to one empty group (after every tab was closed)."""
        while len(self._groups) > 1:
            self._drop_group(self._groups[-1])

    def _move_page(self, source: EditorGroup, index: int, target: EditorGroup) -> int:
        label = source.tabs.tabText(index)
        tooltip = source.tabs.tabToolTip(index)
        data = source.tab_bar.tabData(index)
        icon = source.tabs.tabIcon(index)
        page = self._remove_view(source, index, keep_page=True)
        if page is None:
            return -1
        new_index = target.tabs.addTab(page, icon, label)
        target.tabs.setTabToolTip(new_index, tooltip)
        target.tab_bar.setTabData(new_index, data)
        return new_index

    # -- Drag a tab to the other group ---------------------------------------

    def _begin_drag(self, source: EditorGroup, index: int) -> None:
        page = source.tabs.widget(index)
        if not isinstance(page, EditorTabPage) or self._ghost is None:
            return
        self._drag_source = source
        self._drag_buffer_id = page.buffer_id
        self._ghost.setText("⇢ " + source.tabs.tabText(index))
        self._ghost.adjustSize()
        self._ghost.show()
        self._ghost.raise_()

    def _update_drag(self, global_pos: QPoint) -> None:
        if self._drag_source is None or self._host is None or self._ghost is None or self._drop_overlay is None:
            return
        local = self._host.mapFromGlobal(global_pos)
        self._ghost.move(local + QPoint(12, 8))
        target = self._group_at(global_pos)
        self._drag_new_group = False
        if target is not None and target is self._drag_source and len(self._groups) < MAX_EDITOR_GROUPS:
            group_local = target.mapFromGlobal(global_pos)
            self._drag_new_group = group_local.x() > target.width() * _NEW_GROUP_DROP_FRACTION
        self._drag_target = target if target is not self._drag_source or self._drag_new_group else None
        if self._drag_target is None:
            self._drop_overlay.hide()
            return
        top_left = self._drag_target.mapTo(self._host, QPoint(0, 0))
        rect = QRect(top_left, self._drag_target.size())
        if self._drag_new_group:
            rect.setLeft(rect.left() + rect.width() // 2)
        self._drop_overlay.setGeometry(rect)
        self._drop_overlay.show()
        self._drop_overlay.raise_()
        self._ghost.raise_()

    def _end_drag(self, global_pos: QPoint) -> None:
        self._update_drag(global_pos)
        source, buffer_id, target = self._drag_source, self._drag_buffer_id, self._drag_target
        new_group = self._drag_new_group
        self._drag_source = self._drag_buffer_id = self._drag_target = None
        self._drag_new_group = False
        if self._ghost is not None:
            self._ghost.hide()
        if self._drop_overlay is not None:
            self._drop_overlay.hide()
        if source is None or buffer_id is None or target is None or source not in self._groups:
            return
        if new_group:
            target = self._add_group()
        self.move_buffer(source, buffer_id, target)

    def move_buffer(self, source: EditorGroup, buffer_id: str, target: EditorGroup) -> bool:
        """Move a buffer's tab from ``source`` to ``target`` (both groups keep their other tabs)."""
        index = source.index_of_buffer(buffer_id)
        if index < 0 or source is target:
            return False
        existing = target.index_of_buffer(buffer_id)
        if existing >= 0:
            self._set_focused(source)
            self._remove_view(source, index, keep_page=False)
            target.tabs.setCurrentIndex(existing)
        else:
            new_index = self._move_page(source, index, target)
            target.tabs.setCurrentIndex(new_index)
        self._set_focused(target)
        self._repoint_buffers_to(target)
        self._window._editor_tabs_coordinator.sync_open_order_from_tabs()
        current = target.tabs.currentWidget()
        if current is not None:
            current.setFocus(Qt.OtherFocusReason)
        self._collapse_now()
        return True

    def _group_at(self, global_pos: QPoint) -> Optional[EditorGroup]:
        for group in self._groups:
            if group.rect().contains(group.mapFromGlobal(global_pos)):
                return group
        return None

    # -- Session layout ------------------------------------------------------

    def capture_layout(self) -> Optional[dict[str, Any]]:
        """Group membership by file path, for the session file. None with one group."""
        if len(self._groups) < 2:
            return None
        manager = self._window._editor_manager
        groups: list[list[str]] = []
        active: list[Optional[str]] = []
        for group in self._groups:
            paths: list[str] = []
            for page in group.pages():
                tab = manager.get_tab_by_id(page.buffer_id)
                if tab is not None:
                    paths.append(tab.file_path)
            groups.append(paths)
            current = group.tabs.currentWidget()
            current_tab = manager.get_tab_by_id(current.buffer_id) if isinstance(current, EditorTabPage) else None
            active.append(None if current_tab is None else current_tab.file_path)
        assert self._splitter is not None
        return {
            LAYOUT_KEY_GROUPS: groups,
            LAYOUT_KEY_ACTIVE: active,
            LAYOUT_KEY_FOCUSED: self.focused_index(),
            LAYOUT_KEY_SIZES: list(self._splitter.sizes()),
        }

    def restore_layout(self, layout: Any) -> None:
        """Re-create the second group after the session's files were opened in the first."""
        if not isinstance(layout, dict) or len(self._groups) != 1:
            return
        groups = layout.get(LAYOUT_KEY_GROUPS)
        if not isinstance(groups, list) or len(groups) < 2:
            return
        first_paths = {_normalize(path) for path in groups[0] if isinstance(path, str)}
        second_paths = [_normalize(path) for path in groups[1] if isinstance(path, str)]
        manager = self._window._editor_manager
        first = self._groups[0]
        second: Optional[EditorGroup] = None
        for path in second_paths:
            tab = manager.get_tab(path)
            if tab is None or first.index_of_buffer(tab.buffer_id) < 0:
                continue
            if second is None:
                second = self._add_group()
            if path in first_paths:
                source_editor = page_editor(first.tabs.widget(first.index_of_buffer(tab.buffer_id)))
                if source_editor is not None:
                    self._add_view(second, tab.buffer_id, source_editor)
            else:
                self._move_page(first, first.index_of_buffer(tab.buffer_id), second)
        if second is None:
            return
        active = layout.get(LAYOUT_KEY_ACTIVE)
        if isinstance(active, list):
            for group, path in zip(self._groups, active):
                tab = manager.get_tab(path) if isinstance(path, str) else None
                if tab is not None and group.index_of_buffer(tab.buffer_id) >= 0:
                    group.tabs.setCurrentIndex(group.index_of_buffer(tab.buffer_id))
        sizes = layout.get(LAYOUT_KEY_SIZES)
        if isinstance(sizes, list) and len(sizes) == 2 and all(isinstance(size, int) and size > 0 for size in sizes):
            assert self._splitter is not None
            self._splitter.setSizes(sizes)
        focused = layout.get(LAYOUT_KEY_FOCUSED)
        self._collapse_now()
        if isinstance(focused, int) and 0 <= focused < len(self._groups):
            self._set_focused(self._groups[focused])
        self._window._editor_tabs_coordinator.sync_open_order_from_tabs()


def _normalize(file_path: str) -> str:
    return str(Path(file_path).expanduser().resolve())


__all__ = [
    "EditorGroup",
    "EditorGroupTabWidget",
    "EditorGroupsController",
    "MAX_EDITOR_GROUPS",
    "page_editor",
]
