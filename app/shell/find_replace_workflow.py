"""Find and replace bar workflow for the shell editor."""

from __future__ import annotations

from typing import Any, Protocol

from PySide2.QtWidgets import QMessageBox

from app.editors.find_replace_bar import FindOptions, FindReplaceBar
from app.editors.code_editor_widget import CodeEditorWidget


class FindReplaceBarHost(Protocol):
    """Host ports for :class:`FindReplaceWorkflow`."""

    def active_editor_widget(self) -> CodeEditorWidget | None:
        ...

    def find_replace_bar(self) -> FindReplaceBar | None:
        ...

    def loaded_project(self) -> object | None:
        ...

    def set_activity_view(self, view_id: str) -> None:
        ...

    def focus_search_sidebar(self, initial: str) -> None:
        ...

    def show_warning(self, title: str, message: str) -> None:
        ...


class FindReplaceWorkflow:
    """Owns find/replace bar interactions and find-in-files sidebar routing."""

    def __init__(self, host: FindReplaceBarHost) -> None:
        self._host = host

    def open_find(self) -> None:
        editor_widget = self._host.active_editor_widget()
        if editor_widget is None:
            return
        find_bar = self._host.find_replace_bar()
        if find_bar is None:
            return
        initial = editor_widget.selected_text() or editor_widget.word_under_cursor()
        find_bar.open_find(initial)

    def open_replace(self) -> None:
        editor_widget = self._host.active_editor_widget()
        if editor_widget is None:
            return
        find_bar = self._host.find_replace_bar()
        if find_bar is None:
            return
        initial = editor_widget.selected_text() or editor_widget.word_under_cursor()
        find_bar.open_find_replace(initial)

    def open_find_in_files(self) -> None:
        if self._host.loaded_project() is None:
            self._host.show_warning("Find in Files", "Open a project first.")
            return
        self._host.set_activity_view("search")
        editor_widget = self._host.active_editor_widget()
        initial = ""
        if editor_widget is not None:
            initial = editor_widget.selected_text() or editor_widget.word_under_cursor()
        if initial:
            self._host.focus_search_sidebar(initial)

    def handle_find(self, text: str, options: FindOptions) -> None:
        editor_widget = self._host.active_editor_widget()
        find_bar = self._host.find_replace_bar()
        if editor_widget is None or find_bar is None:
            return
        total = editor_widget.highlight_all_matches(text, options)
        if total > 0:
            current, total_matches = editor_widget.find_next()
            find_bar.update_match_count(current, total_matches)
        else:
            find_bar.update_match_count(0, 0)

    def handle_find_next(self) -> None:
        editor_widget = self._host.active_editor_widget()
        find_bar = self._host.find_replace_bar()
        if editor_widget is None or find_bar is None:
            return
        current, total = editor_widget.find_next()
        find_bar.update_match_count(current, total)

    def handle_find_previous(self) -> None:
        editor_widget = self._host.active_editor_widget()
        find_bar = self._host.find_replace_bar()
        if editor_widget is None or find_bar is None:
            return
        current, total = editor_widget.find_previous()
        find_bar.update_match_count(current, total)

    def handle_replace(self, replacement: str) -> None:
        editor_widget = self._host.active_editor_widget()
        find_bar = self._host.find_replace_bar()
        if editor_widget is None or find_bar is None:
            return
        query = find_bar.find_text()
        options = find_bar.find_options()
        current, total = editor_widget.replace_current_match(replacement, query, options)
        find_bar.update_match_count(current, total)

    def handle_replace_all(self, replacement: str) -> None:
        editor_widget = self._host.active_editor_widget()
        find_bar = self._host.find_replace_bar()
        if editor_widget is None or find_bar is None:
            return
        query = find_bar.find_text()
        options = find_bar.find_options()
        editor_widget.replace_all_matches(query, replacement, options)
        find_bar.update_match_count(0, 0)

    def handle_close(self) -> None:
        editor_widget = self._host.active_editor_widget()
        if editor_widget is not None:
            editor_widget.clear_search_highlights()
            editor_widget.setFocus()


class MainWindowFindReplaceHost:
    """Host ports for ``FindReplaceWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def active_editor_widget(self) -> CodeEditorWidget | None:
        return self._window._active_editor_widget()

    def find_replace_bar(self) -> FindReplaceBar | None:
        return self._window._find_replace_bar

    def loaded_project(self) -> object | None:
        return self._window._loaded_project

    def set_activity_view(self, view_id: str) -> None:
        if self._window._activity_bar is not None:
            self._window._activity_bar.set_active_view(view_id)
        self._window._handle_sidebar_view_changed(view_id)

    def focus_search_sidebar(self, initial: str) -> None:
        if self._window._search_sidebar is not None:
            self._window._search_sidebar.focus_search(initial)

    def show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self._window, title, message)
