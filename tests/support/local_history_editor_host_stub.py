"""Test double for :class:`LocalHistoryEditorHost`."""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.shell.breakpoint_store import BreakpointStore
from app.shell.session_persistence import SessionTreeState
from app.shell.theme_tokens import ShellThemeTokens


class LocalHistoryEditorHostStub:
    """Minimal ``LocalHistoryEditorHost`` for unit tests."""

    def __init__(
        self,
        *,
        parent: object | None = None,
        loaded_project: Callable[[], LoadedProject | None] | None = None,
        editor_widget_for_path: Callable[[str], CodeEditorWidget | None] | None = None,
        open_file_in_editor: Callable[[str], bool] | None = None,
        open_file_for_session_restore: Callable[[str], bool] | None = None,
        open_restored_history_buffer: Callable[[str, str], bool] | None = None,
        apply_text_to_open_tab: Callable[[str, str], None] | None = None,
        tab_index_for_path: Callable[[str], int] | None = None,
        refresh_tab_presentation: Callable[[str], None] | None = None,
        set_current_tab_index: Callable[[int], None] | None = None,
        show_status_message: Callable[[str, int], None] | None = None,
        current_theme_tokens: Callable[[], ShellThemeTokens | None] | None = None,
        breakpoint_store: BreakpointStore | None = None,
        refresh_breakpoints_list: Callable[[], None] | None = None,
        capture_tree_state: Callable[[], SessionTreeState | None] | None = None,
        restore_tree_state: Callable[[SessionTreeState], None] | None = None,
        reveal_tree_path: Callable[[str], None] | None = None,
        set_tree_reveal_suppressed: Callable[[bool], None] | None = None,
    ) -> None:
        self._parent = parent
        self._loaded_project = loaded_project or (lambda: None)
        self._editor_widget_for_path = editor_widget_for_path or (lambda _path: None)
        self._open_file_in_editor = open_file_in_editor or (lambda _path: False)
        self._open_file_for_session_restore = open_file_for_session_restore or self._open_file_in_editor
        self._open_restored_history_buffer = open_restored_history_buffer or (lambda _path, _content: False)
        self._apply_text_to_open_tab = apply_text_to_open_tab or (lambda _path, _content: None)
        self._tab_index_for_path = tab_index_for_path or (lambda _path: -1)
        self._refresh_tab_presentation = refresh_tab_presentation or (lambda _path: None)
        self._set_current_tab_index = set_current_tab_index or (lambda _index: None)
        self._show_status_message = show_status_message or (lambda _message, _timeout: None)
        self._current_theme_tokens = current_theme_tokens or (lambda: None)
        self._breakpoint_store = breakpoint_store
        self._refresh_breakpoints_list = refresh_breakpoints_list or (lambda: None)
        self._capture_tree_state = capture_tree_state or (lambda: None)
        self._restore_tree_state = restore_tree_state or (lambda _state: None)
        self._reveal_tree_path = reveal_tree_path or (lambda _path: None)
        self._set_tree_reveal_suppressed = set_tree_reveal_suppressed or (lambda _suppressed: None)

    def parent_widget(self) -> Any:
        return self._parent

    def loaded_project(self) -> LoadedProject | None:
        return self._loaded_project()

    def editor_widget_for_path(self, file_path: str) -> CodeEditorWidget | None:
        return self._editor_widget_for_path(file_path)

    def open_file_in_editor(self, file_path: str) -> bool:
        return self._open_file_in_editor(file_path)

    def open_file_for_session_restore(self, file_path: str) -> bool:
        return self._open_file_for_session_restore(file_path)

    def open_restored_history_buffer(self, file_path: str, content: str) -> bool:
        return self._open_restored_history_buffer(file_path, content)

    def apply_text_to_open_tab(self, file_path: str, content: str) -> None:
        self._apply_text_to_open_tab(file_path, content)

    def tab_index_for_path(self, file_path: str) -> int:
        return self._tab_index_for_path(file_path)

    def refresh_tab_presentation(self, file_path: str) -> None:
        self._refresh_tab_presentation(file_path)

    def set_current_tab_index(self, tab_index: int) -> None:
        self._set_current_tab_index(tab_index)

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self._show_status_message(message, timeout_ms)

    def current_theme_tokens(self) -> ShellThemeTokens | None:
        return self._current_theme_tokens()

    def breakpoint_store(self) -> BreakpointStore | None:
        return self._breakpoint_store

    def refresh_breakpoints_list(self) -> None:
        self._refresh_breakpoints_list()

    def capture_tree_state(self) -> SessionTreeState | None:
        return self._capture_tree_state()

    def restore_tree_state(self, tree_state: SessionTreeState) -> None:
        self._restore_tree_state(tree_state)

    def reveal_tree_path(self, file_path: str) -> None:
        self._reveal_tree_path(file_path)

    def set_tree_reveal_suppressed(self, suppressed: bool) -> None:
        self._set_tree_reveal_suppressed(suppressed)
